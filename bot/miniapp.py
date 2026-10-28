"""Authenticated Telegram Mini App API and lightweight static web server."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from telegram import Bot, MenuButtonWebApp, WebAppInfo
from telegram.error import TelegramError

log = logging.getLogger(__name__)
WEB_ROOT = Path(__file__).resolve().parent.parent / "webapp"
MAX_INIT_AGE_SECONDS = 60 * 60 * 24
_request_times: dict[int, float] = {}
_request_locks: dict[int, asyncio.Lock] = {}
_membership_cache: dict[int, tuple[float, bool]] = {}


def validate_init_data(init_data: str, bot_token: str, now: int | None = None) -> dict:
    """Validate Telegram WebApp initData according to Telegram's HMAC procedure."""
    if not init_data or not bot_token:
        raise ValueError("Missing Telegram WebApp authentication data.")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        values = dict(pairs)
    except (ValueError, TypeError) as exc:
        raise ValueError("Malformed Telegram WebApp authentication data.") from exc
    received_hash = values.pop("hash", "")
    if not received_hash or len(received_hash) != 64:
        raise ValueError("Missing or invalid Telegram WebApp signature.")
    if len(values) != len(pairs) - 1:
        raise ValueError("Duplicate Telegram WebApp fields are not allowed.")
    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Telegram WebApp signature verification failed.")
    try:
        auth_date = int(values.get("auth_date", "0"))
        user = json.loads(values["user"])
        user_id = int(user["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Telegram WebApp user data is incomplete.") from exc
    current = int(time.time()) if now is None else int(now)
    if auth_date > current + 60 or current - auth_date > MAX_INIT_AGE_SECONDS:
        raise ValueError("Telegram WebApp session expired. Reopen the Mini App from Telegram.")
    if user_id <= 0 or not isinstance(user, dict):
        raise ValueError("Invalid Telegram user.")
    return {"user": user, "user_id": user_id, "auth_date": auth_date}


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store"})


async def _telegram_user(request: web.Request) -> tuple[dict | None, web.Response | None]:
    app = request.app["telegram_app"]
    settings = app.bot_data["settings"]
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    try:
        auth = validate_init_data(init_data, settings.bot_token)
    except ValueError as exc:
        return None, _json({"ok": False, "error": str(exc)}, 401)
    db = app.bot_data["db"]
    row = await db.get_user(auth["user_id"])
    if not row:
        return None, _json({"ok": False, "error": "Open the bot and press /start before using the Mini App."}, 403)
    if row.get("is_banned"):
        return None, _json({"ok": False, "error": "This account is restricted."}, 403)
    # This Mini App is an administration console, never a public user workspace.
    if auth["user_id"] != settings.owner_id and not await db.is_admin(auth["user_id"]):
        return None, _json({"ok": False, "error": "This Mini App is restricted to the bot owner and administrators."}, 403)
    if await db.get_setting("maintenance") == "1" and auth["user_id"] != settings.owner_id and not await db.is_admin(auth["user_id"]):
        return None, _json({"ok": False, "error": "The service is temporarily under maintenance."}, 503)
    # Match the bot guard: administrators can still access the Mini App while configuring force-join.
    if auth["user_id"] == settings.owner_id or await db.is_admin(auth["user_id"]):
        return {"auth": auth, "row": row, "db": db, "app": app}, None
    # Cache successful checks briefly: the UI refreshes several endpoints at once.
    channels = await db.list_channels()
    cached = _membership_cache.get(auth["user_id"])
    if cached and time.monotonic() - cached[0] < (120 if cached[1] else 5):
        if cached[1]:
            return {"auth": auth, "row": row, "db": db, "app": app}, None
        return None, _json({
            "ok": False,
            "error": "Join the required channel(s) in the bot before using the Mini App.",
            "join_required": True,
            "channels": [{"title": c["title"], "link": c["link"]} for c in channels],
        }, 403)
    try:
        for channel in channels:
            member = await app.bot.get_chat_member(chat_id=channel["chat_id"], user_id=auth["user_id"])
            if member.status in ("left", "kicked") or (member.status == "restricted" and not getattr(member, "is_member", True)):
                _membership_cache[auth["user_id"]] = (time.monotonic(), False)
                return None, _json({
                    "ok": False,
                    "error": "Join the required channel(s) in the bot before using the Mini App.",
                    "join_required": True,
                    "channels": [{"title": c["title"], "link": c["link"]} for c in channels],
                }, 403)
    except TelegramError:
        # If Telegram cannot verify a configured channel, fail closed instead of bypassing the gate.
        if channels:
            return None, _json({"ok": False, "error": "Membership verification is temporarily unavailable. Try again shortly."}, 503)
    _membership_cache[auth["user_id"]] = (time.monotonic(), True)
    return {"auth": auth, "row": row, "db": db, "app": app}, None


async def health(request: web.Request) -> web.Response:
    return _json({"ok": True, "service": "telegram-mini-app"})


async def index(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(WEB_ROOT / "index.html")


async def me(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    row = session["row"]
    return _json({
        "ok": True,
        "user": {
            "id": row["id"],
            "first_name": row.get("first_name") or "",
            "username": row.get("username") or "",
            "lang": row.get("lang") or "en",
            "points": int(row.get("points") or 0),
            "referrals": int(row.get("referrals") or 0),
            "is_admin": session["auth"]["user_id"] == session["app"].bot_data["settings"].owner_id or await session["db"].is_admin(session["auth"]["user_id"]),
        },
    })


async def catalog(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    db = session["db"]
    active_services = await db.list_active_services()
    if not active_services:
        return _json({"ok": True, "services": [], "total_available": 0})
    placeholders = ",".join("?" for _ in active_services)
    # Counts are service-specific. Never add a shared generic pool to every app.
    rows = await db._all(
        f"SELECT service, country, COUNT(*) AS count FROM phone_numbers "
        f"WHERE status='available' AND service IN ({placeholders}) "
        "GROUP BY service, country ORDER BY service COLLATE NOCASE, country COLLATE NOCASE",
        tuple(active_services),
    )
    counts: dict[str, dict[str, int]] = {}
    total_available = 0
    for item in rows:
        service_name = str(item["service"])
        country_name = str(item["country"])
        count = int(item["count"])
        total_available += count
        counts.setdefault(service_name.casefold(), {})[country_name] = count

    services = []
    for name in active_services:
        country_counts = counts.get(name.casefold(), {})
        countries = [
            {"country": country_name, "count": count}
            for country_name, count in sorted(country_counts.items(), key=lambda pair: pair[0].casefold())
            if count > 0
        ]
        if countries:
            services.append({
                "name": name,
                "countries": countries,
                "count": sum(item["count"] for item in countries),
            })
    return _json({"ok": True, "services": services, "total_available": total_available})


async def sessions(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    uid = session["auth"]["user_id"]
    assigned = await session["db"]._all(
        "SELECT id, service, country, number, created_at FROM phone_numbers "
        "WHERE assigned_user_id=? AND status='assigned' ORDER BY id DESC LIMIT 100",
        (uid,),
    )
    otp_rows = await session["db"]._all(
        "SELECT number, message, received_at FROM otp_messages ORDER BY received_at DESC LIMIT 500"
    )
    def digits(value: str) -> str:
        return "".join(ch for ch in (value or "") if ch.isdigit())
    sessions_out = []
    for item in assigned:
        normalized = digits(item["number"])
        otp = next((row for row in otp_rows if normalized and digits(row["number"]) == normalized), None)
        sessions_out.append({
            "id": int(item["id"]),
            "service": item["service"],
            "country": item["country"],
            "number": item["number"],
            "created_at": item["created_at"],
            "otp_message": otp["message"] if otp else None,
            "otp_received_at": otp["received_at"] if otp else None,
        })
    return _json({"ok": True, "sessions": sessions_out})


async def request_number(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    uid = session["auth"]["user_id"]
    try:
        payload = await request.json()
        service = str(payload.get("service", "")).strip()[:40]
        country = str(payload.get("country", "")).strip()[:60]
    except (json.JSONDecodeError, AttributeError, TypeError):
        return _json({"ok": False, "error": "Invalid request body."}, 400)
    if not service or not country:
        return _json({"ok": False, "error": "Choose a service and country."}, 400)
    lock = _request_locks.setdefault(uid, asyncio.Lock())
    async with lock:
        remaining = 5 - (time.monotonic() - _request_times.get(uid, 0))
        if remaining > 0:
            return _json({"ok": False, "error": f"Please wait {max(1, int(remaining + 0.99))} seconds before requesting another number."}, 429)
        db = session["db"]
        active = {name.casefold(): name for name in await db.list_active_services()}
        canonical_service = active.get(service.casefold())
        if not canonical_service:
            return _json({"ok": False, "error": "This service is not currently enabled."}, 400)
        _request_times[uid] = time.monotonic()
        candidates = await db.list_available_numbers(service=canonical_service, country=country)
        assigned = []
        for candidate in candidates:
            if await db.assign_phone_number(candidate["id"], uid):
                assigned.append({
                    "id": candidate["id"],
                    "service": candidate["service"],
                    "country": candidate["country"],
                    "number": candidate["number"],
                    "created_at": candidate["created_at"],
                })
                if len(assigned) == 2:
                    break
        if assigned:
            return _json({
                "ok": True,
                "numbers": assigned,
                # Keep the original singular field for older Mini App clients.
                "number": assigned[0],
                "message": f"{len(assigned)} number(s) assigned. OTP messages will appear here when the provider delivers them.",
            }, 201)
        return _json({"ok": False, "error": "No numbers are available for this selection right now."}, 409)


async def admin_provider_sync(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    uid = session["auth"]["user_id"]
    settings = session["app"].bot_data["settings"]
    db = session["db"]
    if uid != settings.owner_id and not await db.is_admin(uid):
        return _json({"ok": False, "error": "Administrator access required."}, 403)
    from .otp_api import sync_augestel_numbers
    try:
        result = await sync_augestel_numbers(db)
    except RuntimeError as exc:
        message = str(exc)
        status = 429 if "wait at least" in message.lower() else 502
        return _json({"ok": False, "error": message if status == 429 else "Provider API sync failed. Check the active API key and provider API status."}, status)
    except Exception as exc:
        log.warning("Mini App provider inventory sync failed (%s).", type(exc).__name__)
        return _json({"ok": False, "error": "Provider API sync failed. Check the active API key and provider API status."}, 502)
    return _json({"ok": True, "sync": result})


async def admin_overview(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    uid = session["auth"]["user_id"]
    settings = session["app"].bot_data["settings"]
    db = session["db"]
    if uid != settings.owner_id and not await db.is_admin(uid):
        return _json({"ok": False, "error": "Administrator access required."}, 403)
    stats = await db.stats()
    inventory = await db._all(
        "SELECT service, country, COUNT(*) AS count FROM phone_numbers "
        "WHERE status='available' GROUP BY service, country ORDER BY service, country"
    )
    pending = await db._one("SELECT COUNT(*) AS count FROM pending_provider_numbers WHERE status='pending'")
    return _json({
        "ok": True,
        "stats": {
            "users": int(stats.get("total") or 0),
            "active_users": int(stats.get("active") or 0),
            "banned_users": int(stats.get("banned") or 0),
            "available_numbers": sum(int(row["count"]) for row in inventory),
            "pending_provider_numbers": int((pending or {}).get("count") or 0),
        },
        "active_services": await db.list_active_services(),
        "services": list(dict.fromkeys([v.strip() for v in (await db.get_setting("custom_services")).split("\n") if v.strip()] + await db.list_phone_number_services())),
        "inventory": inventory,
    })


async def admin_settings(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    db = session["db"]
    keys = ("maintenance", "otp_template", "button_customizations", "support_url", "official_url", "custom_services")
    values = {}
    for key in keys:
        values[key] = await db.get_setting(key, "")
    return _json({"ok": True, "settings": values})


async def admin_save_settings(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    db = session["db"]
    try:
        payload = await request.json()
    except (json.JSONDecodeError, AttributeError, TypeError):
        return _json({"ok": False, "error": "Invalid request body."}, 400)
    allowed = {"maintenance", "otp_template", "button_customizations", "support_url", "official_url", "custom_services"}
    for key, value in payload.items():
        if key not in allowed or not isinstance(value, str):
            continue
        if len(value) > 10000:
            return _json({"ok": False, "error": f"Setting {key} is too long."}, 400)
        if key in ("support_url", "official_url") and value and value != "-" and not value.startswith(("https://t.me/", "https://telegram.me/", "https://")):
            return _json({"ok": False, "error": f"Invalid URL for {key}."}, 400)
        if key == "maintenance" and value not in ("0", "1"):
            return _json({"ok": False, "error": "maintenance must be 0 or 1."}, 400)
        if key == "button_customizations":
            try:
                decoded = json.loads(value or "{}")
                if not isinstance(decoded, dict):
                    raise ValueError()
            except (ValueError, json.JSONDecodeError):
                return _json({"ok": False, "error": "Button configuration must be valid JSON."}, 400)
        await db.set_setting(key, value)
    return _json({"ok": True, "message": "Settings saved."})


async def admin_add_number(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    uid = session["auth"]["user_id"]
    settings = session["app"].bot_data["settings"]
    db = session["db"]
    if uid != settings.owner_id and not await db.is_admin(uid):
        return _json({"ok": False, "error": "Administrator access required."}, 403)
    try:
        payload = await request.json()
        service = str(payload.get("service", "")).strip()[:40]
        country = str(payload.get("country", "")).strip()[:60]
        raw_number = str(payload.get("number", "")).strip()
        activate = payload.get("activate", True) is not False
    except (json.JSONDecodeError, AttributeError, TypeError):
        return _json({"ok": False, "error": "Invalid request body."}, 400)
    import re
    number = re.sub(r"[\s().-]", "", raw_number)
    known_services = list(dict.fromkeys([v.strip() for v in (await db.get_setting("custom_services")).split("\n") if v.strip()] + await db.list_phone_number_services()))
    canonical = next((name for name in known_services if name.casefold() == service.casefold()), None)
    if not canonical or not country or not re.fullmatch(r"\+?\d{7,20}", number):
        return _json({"ok": False, "error": "Enter a service, country and valid international number."}, 400)
    service = canonical
    if not await db.add_phone_number(service, country, number):
        return _json({"ok": False, "error": "This number already exists in the inventory."}, 409)
    if activate:
        active = {name.casefold() for name in await db.list_active_services()}
        if service.casefold() not in active:
            await db.toggle_service_active(service)
    return _json({"ok": True, "message": "Number added to inventory.", "number": number}, 201)


async def admin_create_service(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    uid = session["auth"]["user_id"]
    settings = session["app"].bot_data["settings"]
    db = session["db"]
    if uid != settings.owner_id and not await db.is_admin(uid):
        return _json({"ok": False, "error": "Administrator access required."}, 403)
    try:
        payload = await request.json()
        service = str(payload.get("service", "")).strip()
    except (json.JSONDecodeError, AttributeError, TypeError):
        return _json({"ok": False, "error": "Invalid request body."}, 400)
    if not service or len(service) > 40 or any(ord(ch) < 32 for ch in service):
        return _json({"ok": False, "error": "Service name must be 1–40 characters."}, 400)
    custom = [v.strip() for v in (await db.get_setting("custom_services")) .split("\n") if v.strip()]
    existing = list(dict.fromkeys(custom + await db.list_phone_number_services()))
    canonical = next((v for v in existing if v.casefold() == service.casefold()), None)
    if canonical:
        return _json({"ok": False, "error": "That service already exists."}, 409)
    custom.append(service)
    await db.set_setting("custom_services", "\n".join(custom))
    # New services stay disabled until an administrator explicitly enables them.
    return _json({"ok": True, "service": service, "active": False}, 201)


async def admin_toggle_service(request: web.Request) -> web.Response:
    session, error = await _telegram_user(request)
    if error:
        return error
    uid = session["auth"]["user_id"]
    settings = session["app"].bot_data["settings"]
    db = session["db"]
    if uid != settings.owner_id and not await db.is_admin(uid):
        return _json({"ok": False, "error": "Administrator access required."}, 403)
    try:
        payload = await request.json()
        service = str(payload.get("service", "")).strip()[:40]
    except (json.JSONDecodeError, AttributeError, TypeError):
        return _json({"ok": False, "error": "Invalid request body."}, 400)
    services = list(dict.fromkeys([v.strip() for v in (await db.get_setting("custom_services")).split("\n") if v.strip()] + await db.list_phone_number_services()))
    canonical = next((item for item in services if item.casefold() == service.casefold()), None)
    if not canonical:
        return _json({"ok": False, "error": "Service not found in inventory."}, 404)
    active = await db.toggle_service_active(canonical)
    return _json({"ok": True, "service": canonical, "active": active})


async def ksi_webhook(request: web.Request) -> web.Response:
    """Receive signed KSI IPRN events and relay delivered SMS messages."""
    secret = os.getenv("KSI_WEBHOOK_SECRET", "").strip()
    if not secret:
        return _json({"ok": False, "error": "Webhook secret is not configured."}, 503)

    raw_body = await request.read()
    signature = request.headers.get("X-KSIIPRNTECHNOLOGY-Signature", "").strip()
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        return _json({"ok": False, "error": "Invalid webhook signature."}, 401)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json({"ok": False, "error": "Invalid JSON body."}, 400)
    if not isinstance(payload, dict):
        return _json({"ok": False, "error": "Invalid event payload."}, 400)

    event = str(payload.get("event") or request.headers.get("X-KSIIPRNTECHNOLOGY-Event", "")).strip()
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return _json({"ok": False, "error": "Missing event data."}, 400)
    if event != "message.received":
        log.info("Acknowledged KSI webhook event: %s", event[:60])
        return _json({"ok": True, "event": event})

    number = str(data.get("number") or data.get("phone_number") or "").strip()
    message = str(data.get("message") or data.get("text") or "").strip()
    status = str(data.get("status") or "").strip().lower()
    if not number or not message:
        return _json({"ok": False, "error": "Message event is missing number or message."}, 400)
    if status and status not in ("delivered", "received", "success", "successful"):
        return _json({"ok": True, "ignored": "message was not delivered"})

    received = str(data.get("received_at") or payload.get("timestamp") or "")
    source = str(data.get("source") or data.get("type") or "SMS")
    raw_id = str(data.get("id") or data.get("message_id") or "")
    dedupe = raw_id or hashlib.sha256(
        f"{number}|{received}|{source}|{message}".encode("utf-8")
    ).hexdigest()

    telegram_app = request.app["telegram_app"]
    db = telegram_app.bot_data["db"]
    if not await db.save_otp_once(dedupe, number, message, received):
        return _json({"ok": True, "duplicate": True})

    assigned = await db.assigned_users_for_number(number)
    if not assigned:
        rows = await db._all(
            "SELECT number, assigned_user_id FROM phone_numbers "
            "WHERE status='assigned' AND assigned_user_id IS NOT NULL"
        )
        digits = lambda value: "".join(ch for ch in str(value or "") if ch.isdigit())
        assigned = [
            int(row["assigned_user_id"]) for row in rows
            if digits(row["number"]) == digits(number)
        ]

    if assigned:
        import re
        match = re.search(r"(?<!\\d)(\\d{3}-\\d{3}|\\d{4,8})(?!\\d)", message)
        code = match.group(1) if match else "not detected"
        country = str(data.get("country") or data.get("country_name") or data.get("range_name") or "N/A")
        values = {
            "{language}": "English / دری",
            "{service}": source,
            "{country}": country,
            "{number}": number,
            "{code}": code,
            "{time}": received or "N/A",
            "{message}": message[:2500],
        }
        template = await db.get_setting(
            "otp_template",
            "🔐 <b>PRO+PRO</b>\\n📱 {service}\\n🌍 {country}\\n📞 <code>{number}</code>\\n🔢 Code: <code>{code}</code>\\n🕒 {time}\\n🗣 {language}\\n<pre>{message}</pre>",
        )
        import html
        text_message = template
        for token, value in values.items():
            text_message = text_message.replace(token, html.escape(value))
        for uid in set(assigned):
            try:
                await telegram_app.bot.send_message(chat_id=uid, text=text_message)
            except Exception as exc:
                log.warning("Could not deliver KSI webhook OTP to user %s (%s).", uid, type(exc).__name__)

        channel_id = os.getenv("OTP_CHANNEL_ID", "").strip()
        if channel_id:
            try:
                await telegram_app.bot.send_message(chat_id=int(channel_id), text=text_message)
            except Exception as exc:
                log.warning("Could not post KSI webhook OTP to channel (%s).", type(exc).__name__)

    return _json({"ok": True, "event": event, "relayed": bool(assigned)})

async def start_web_server(telegram_app) -> web.AppRunner | None:
    """Start the Mini App server on Railway's PORT (or WEB_PORT locally)."""
    port_text = os.getenv("PORT", os.getenv("WEB_PORT", "8080")).strip()
    try:
        port = int(port_text)
    except ValueError:
        log.error("Invalid web server port; Mini App server was not started.")
        return None
    server = web.Application(client_max_size=16 * 1024)
    server["telegram_app"] = telegram_app
    server.router.add_get("/", index)
    server.router.add_get("/health", health)
    server.router.add_post("/webhooks/ksiiprn", ksi_webhook)
    server.router.add_get("/api/me", me)
    server.router.add_get("/api/catalog", catalog)
    server.router.add_get("/api/sessions", sessions)
    server.router.add_post("/api/number", request_number)
    server.router.add_get("/api/admin/overview", admin_overview)
    server.router.add_get("/api/admin/settings", admin_settings)
    server.router.add_post("/api/admin/settings", admin_save_settings)
    server.router.add_post("/api/admin/provider-sync", admin_provider_sync)
    server.router.add_post("/api/admin/number", admin_add_number)
    server.router.add_post("/api/admin/service", admin_toggle_service)
    server.router.add_post("/api/admin/services", admin_create_service)
    runner = web.AppRunner(server, access_log=None)
    await runner.setup()
    host = os.getenv("WEB_HOST", "0.0.0.0")
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("Mini App web server listening on %s:%s", host, port)

    # No global menu button: Telegram displays it to every user.
    # Administrators open the console using the owner/admin-only /app command.
    return runner
