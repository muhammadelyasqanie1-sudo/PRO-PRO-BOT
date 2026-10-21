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
    if await db.get_setting("maintenance") == "1" and auth["user_id"] != settings.owner_id and not await db.is_admin(auth["user_id"]):
        return None, _json({"ok": False, "error": "The service is temporarily under maintenance."}, 503)
    # Enforce the same required-channel gate for API calls, not just bot messages.
    try:
        for channel in await db.list_channels():
            member = await app.bot.get_chat_member(chat_id=channel["chat_id"], user_id=auth["user_id"])
            if member.status in ("left", "kicked") or (member.status == "restricted" and not getattr(member, "is_member", True)):
                return None, _json({
                    "ok": False,
                    "error": "Join the required channel(s) in the bot before using the Mini App.",
                    "join_required": True,
                    "channels": [{"title": c["title"], "link": c["link"]} for c in await db.list_channels()],
                }, 403)
    except TelegramError:
        # If Telegram cannot verify a configured channel, fail closed instead of bypassing the gate.
        if await db.list_channels():
            return None, _json({"ok": False, "error": "Membership verification is temporarily unavailable. Try again shortly."}, 503)
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
    rows = await db._all(
        f"SELECT service, country, COUNT(*) AS count FROM phone_numbers "
        f"WHERE status='available' AND service IN ({placeholders}) "
        "GROUP BY service, country ORDER BY service COLLATE NOCASE, country COLLATE NOCASE",
        tuple(active_services),
    )
    grouped: dict[str, list[dict]] = {}
    total = 0
    for item in rows:
        count = int(item["count"])
        total += count
        grouped.setdefault(item["service"], []).append({"country": item["country"], "count": count})
    services = [
        {"name": name, "countries": countries, "count": sum(c["count"] for c in countries)}
        for name, countries in grouped.items()
    ]
    return _json({"ok": True, "services": services, "total_available": total})


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
        otp = next((row for row in otp_rows if digits(row["number"]) == normalized), None)
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
        for candidate in candidates:
            if await db.assign_phone_number(candidate["id"], uid):
                return _json({
                    "ok": True,
                    "number": {
                        "id": candidate["id"],
                        "service": candidate["service"],
                        "country": candidate["country"],
                        "number": candidate["number"],
                        "created_at": candidate["created_at"],
                    },
                    "message": "Number assigned. OTP messages will appear here when the provider delivers them.",
                }, 201)
        return _json({"ok": False, "error": "No numbers are available for this selection right now."}, 409)


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
    server.router.add_get("/api/me", me)
    server.router.add_get("/api/catalog", catalog)
    server.router.add_get("/api/sessions", sessions)
    server.router.add_post("/api/number", request_number)
    runner = web.AppRunner(server, access_log=None)
    await runner.setup()
    host = os.getenv("WEB_HOST", "0.0.0.0")
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("Mini App web server listening on %s:%s", host, port)

    public_url = os.getenv("MINI_APP_URL", "").strip() or os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if public_url and not public_url.startswith(("https://", "http://")):
        public_url = "https://" + public_url
    if public_url.startswith("https://"):
        try:
            await telegram_app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Open NUM BOT", web_app=WebAppInfo(url=public_url.rstrip("/") + "/"))
            )
        except TelegramError as exc:
            log.warning("Could not set Telegram Mini App menu button (%s).", type(exc).__name__)
    elif public_url:
        log.warning("MINI_APP_URL must be an HTTPS URL; Telegram Web Apps require HTTPS.")
    return runner
