"""Optional Augestel IPRN SMS poller. Polls conservatively (max 4 requests/minute)."""
from __future__ import annotations
import asyncio, hashlib, html, logging, os, re
from datetime import datetime, timedelta, timezone
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton

log = logging.getLogger(__name__)

def _records(payload):
    """Normalize common Augestel API response envelopes into record dictionaries."""
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
            elif isinstance(item, (list, tuple)) and len(item) >= 5:
                yield {"received_at": item[0], "country": item[1], "number": item[2], "source": item[3], "message": item[4]}
        return
    if not isinstance(payload, dict):
        return

    # Some API versions wrap the actual response in data/result/payload objects.
    for key in ("messages", "numbers", "results", "items", "records", "data", "result", "payload"):
        val = payload.get(key)
        if isinstance(val, list):
            yield from _records(val)
            return
        if isinstance(val, dict):
            # Prefer known collection keys inside the envelope, otherwise treat it
            # as a single record if it already contains a recognizable field.
            nested_collection = any(k in val for k in (
                "messages", "numbers", "results", "items", "records", "data", "aaData"
            ))
            if nested_collection:
                yield from _records(val)
                return
            if any(k in val for k in ("number", "phone_number", "phone", "msisdn", "message", "sms", "text", "body")):
                yield val
                return

    # Some Augestel dashboard endpoints return DataTables aaData rows.
    rows = payload.get("aaData")
    if isinstance(rows, list):
        yield from _records(rows)
        return
    if any(k in payload for k in ("number", "phone_number", "phone", "msisdn", "message", "sms", "text", "body")):
        yield payload

def _field(record, *keys):
    for key in keys:
        val = record.get(key)
        if val is not None and str(val).strip(): return str(val).strip()
    return ""

def _digits(number): return re.sub(r"\D", "", number or "")

def _otp(text):
    match = re.search(r"(?<!\d)(\d{3}-\d{3}|\d{4,8})(?!\d)", text or "")
    return match.group(1) if match else "not detected"

def _fetch(base, key):
    endpoint = os.getenv("AUGESTEL_MESSAGES_PATH", "/messages").strip()
    url = base.rstrip("/") + "/" + endpoint.lstrip("/")
    start = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    response = requests.get(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, params={"start_date": start, "per_page": 200}, timeout=12)
    response.raise_for_status()
    return response.json()

async def sync_augestel_numbers(db):
    """Import provider inventory, limiting Afghanistan's three named carriers to 50 each.

    Carrier metadata is preserved in the country label as 'Afghanistan · Carrier'
    so the user flow can offer a separate operator choice without risking a DB schema
    migration. Numbers without trustworthy carrier metadata remain in their original
    country bucket; we never guess an operator from a phone prefix.
    """
    base = os.getenv("AUGESTEL_API_BASE", "https://augestel.com/api/v1/iprn").strip()
    keys = await db.list_active_api_keys()
    key = keys[0]["api_key"] if keys else os.getenv("AUGESTEL_API_KEY", "").strip()
    if not key:
        raise RuntimeError("No active Augestel API key is configured.")

    now = datetime.now(timezone.utc)
    last_sync = await db.get_setting("augestel_inventory_last_sync", "")
    if last_sync:
        try:
            previous = datetime.fromisoformat(last_sync)
            if (now - previous).total_seconds() < 30:
                raise RuntimeError("Please wait at least 30 seconds between inventory sync requests.")
        except ValueError:
            pass
    await db.set_setting("augestel_inventory_last_sync", now.isoformat(timespec="seconds"))

    def fetch_page(page_number):
        url = base.rstrip("/") + "/numbers"
        response = requests.get(
            url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            params={"page": page_number, "per_page": 100}, timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def detect_operator(record):
        raw = _field(record, "operator_name", "operator", "carrier_name", "carrier",
                     "network_name", "network", "telecom", "range_name", "range")
        folded = raw.casefold().replace("-", " ").replace("_", " ")
        if "etisalat" in folded:
            return "Etisalat"
        if "areeba" in folded or "areba" in folded or "aria" in folded:
            return "Areba"
        if "awcc" in folded or "afghan wireless" in folded or "afghan-w" in folded:
            return "AWCC"
        return ""

    def is_afghanistan(record, number):
        country = _field(record, "country_name", "country", "country_code", "iso2", "country_iso")
        folded = country.casefold()
        return ("afghanistan" in folded or folded in ("af", "afg", "93", "+93")
                or (not country and _digits(number).startswith("93")))

    added = duplicates = received = pages_read = 0
    operator_counts = {"Etisalat": 0, "Areba": 0, "AWCC": 0}
    page = 1
    for _ in range(500):
        payload = await asyncio.to_thread(fetch_page, page)
        records = list(_records(payload))
        pages_read += 1
        normalized = []
        active_names = await db.list_active_services()
        defaults = ["WhatsApp", "Telegram", "TikTok", "Instagram", "Facebook",
                    "Gmail", "Gaming", "Other Services"]
        custom_names = [v.strip() for v in (await db.get_setting("custom_services")).split("\n") if v.strip()]
        known_names = list(dict.fromkeys(active_names + defaults + custom_names))

        for record in records:
            number = _field(record, "number", "phone_number", "phone", "msisdn")
            if not number:
                continue
            received += 1
            country = _field(record, "country_name", "country", "country_code", "iso2", "range_name", "range") or "Unknown"
            service = _field(record, "service_name", "service", "app", "product", "platform") or "Other Services"
            canonical_service = next((name for name in known_names if name.casefold() == service.casefold()), service)[:40]
            operator = detect_operator(record) if is_afghanistan(record, number) else ""
            if operator:
                if operator_counts[operator] >= 50:
                    continue
                operator_counts[operator] += 1
                country_label = f"Afghanistan · {operator}"
            else:
                country_label = country[:60]
            normalized.append({"number": number, "country": country_label, "service": canonical_service})

        groups = {}
        for item in normalized:
            groups.setdefault((item["service"], item["country"]), []).append(item["number"])
        for (service, country), numbers in groups.items():
            added_count, duplicate_count = await db.add_phone_numbers_bulk(service, country, numbers)
            added += added_count
            duplicates += duplicate_count

        pagination = payload.get("pagination", {}) if isinstance(payload, dict) else {}
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        try:
            last_page = int(pagination.get("last_page") or meta.get("last_page")
                            or (payload.get("last_page") if isinstance(payload, dict) else 0) or 0)
        except (TypeError, ValueError):
            last_page = 0
        if not records or (last_page and page >= last_page) or (not last_page and len(records) < 100):
            break
        page += 1
    else:
        raise RuntimeError("Inventory scan reached the 500-page safety limit; not all pages were imported.")

    if not await db.list_active_services():
        await db.set_setting("active_services", "\n".join(dict.fromkeys(defaults + custom_names)))
    return {
        "pages_read": pages_read, "received": received, "added": added,
        "duplicates": duplicates, "next_page": page + 1,
        "operators": operator_counts,
    }


async def poll_augestel(app):
    base = os.getenv("AUGESTEL_API_BASE", "https://augestel.com/api/v1/iprn").strip()
    env_key = os.getenv("AUGESTEL_API_KEY", "").strip()
    log.info("Augestel OTP polling task started; API keys can be managed in the admin panel.")
    while True:
        try:
            db = app.bot_data["db"]
            managed = await db.list_active_api_keys()
            keys = [{"name": x["name"], "api_key": x["api_key"]} for x in managed]
            if not keys and env_key:
                keys = [{"name": "Railway environment key", "api_key": env_key}]
            if not keys:
                await asyncio.sleep(30)
                continue

            payload = None
            used_key = None
            last_error = None
            # Try active keys in order, stopping at the first successful response.
            # This avoids unnecessary duplicate API requests on every polling cycle.
            for item in keys:
                try:
                    payload = await asyncio.to_thread(_fetch, base, item["api_key"])
                    used_key = item["name"]
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    last_error = exc
                    log.warning("Augestel key '%s' failed (%s); trying the next active key if available.",
                                str(item["name"])[:60], type(exc).__name__)
            if payload is None:
                if last_error:
                    log.warning("All active Augestel API keys failed this cycle (%s).", type(last_error).__name__)
                await asyncio.sleep(30)
                continue

            for rec in _records(payload):
                number = _field(rec, "number", "phone_number", "phone", "msisdn")
                message = _field(rec, "message", "sms", "text", "body")
                if not number or not message:
                    continue
                received = _field(rec, "received_at", "created_at", "time", "timestamp", "date") or datetime.now(timezone.utc).isoformat()
                source = _field(rec, "source", "service", "app", "sender") or "SMS"
                raw_id = _field(rec, "id", "message_id")
                dedupe = raw_id or hashlib.sha256(f"{number}|{received}|{source}|{message}".encode()).hexdigest()
                if not await db.save_otp_once(dedupe, number, message, received):
                    continue
                assigned = await db.assigned_users_for_number(number)
                if not assigned:
                    for candidate in await db._all("SELECT number, assigned_user_id FROM phone_numbers WHERE status='assigned' AND assigned_user_id IS NOT NULL"):
                        if _digits(candidate["number"]) == _digits(number):
                            assigned.append(int(candidate["assigned_user_id"]))
                if assigned:
                    code = _otp(message)
                    country_name = _field(rec, "country", "country_name")
                    country_code = _field(rec, "country_code", "iso", "iso2")
                    if not country_code and "afghanistan" in country_name.lower():
                        country_code = "AFG"
                    country_label = country_code or country_name or "N/A"
                    lang_label = _field(rec, "language", "lang") or "English / دری"
                    values = {
                        "{language}": html.escape(lang_label),
                        "{service}": html.escape(source),
                        "{country}": html.escape(country_label),
                        "{number}": html.escape(number),
                        "{code}": html.escape(code),
                        "{time}": html.escape(received),
                        "{message}": html.escape(message[:2500]),
                    }
                    template = await db.get_setting("otp_template", "🔐 <b>NUM BOT</b>\n📱 {service}\n🌍 {country}\n📞 <code>{number}</code>\n🔢 Code: <code>{code}</code>\n🕒 {time}\n🗣 {language}\n<pre>{message}</pre>")
                    text = template
                    for token, value in values.items():
                        text = text.replace(token, value)
                    config = (await db.get_setting("otp_button_config", "📋 Copy code | 🤖 NUM BOT | https://t.me/")).split("|")
                    copy_label = config[0].strip() if len(config) > 0 else "📋 Copy code"
                    bot_label = config[1].strip() if len(config) > 1 else "🤖 NUM BOT"
                    bot_link = config[2].strip() if len(config) > 2 else ""
                    if not bot_link.startswith("https://t.me/"):
                        bot_link = os.getenv("BOT_PUBLIC_LINK", "").strip()
                    button_row = [InlineKeyboardButton(copy_label, copy_text=CopyTextButton(text=code))]
                    if bot_link.startswith("https://t.me/"):
                        button_row.append(InlineKeyboardButton(bot_label, url=bot_link))
                    buttons = InlineKeyboardMarkup([button_row])
                    channel_id = os.getenv("OTP_CHANNEL_ID", "").strip()
                    if channel_id:
                        try:
                            await app.bot.send_message(chat_id=int(channel_id), text=text, reply_markup=buttons)
                        except Exception as exc:
                            log.warning("Could not post OTP to configured channel (%s).", type(exc).__name__)
                    for uid in set(assigned):
                        try:
                            await app.bot.send_message(chat_id=uid, text=text, reply_markup=buttons)
                        except Exception as exc:
                            log.warning("Could not deliver OTP to user %s: %s", uid, type(exc).__name__)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never log keys, query strings, or provider response bodies.
            log.warning("Augestel polling cycle failed (%s).", type(exc).__name__)
        await asyncio.sleep(30)
