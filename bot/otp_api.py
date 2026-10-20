"""Optional Augestel IPRN SMS poller. Polls conservatively (max 4 requests/minute)."""
from __future__ import annotations
import asyncio, hashlib, html, logging, os, re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
import requests

log = logging.getLogger(__name__)

def _records(payload):
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict): yield item
        return
    if not isinstance(payload, dict): return
    for key in ("messages", "data", "results", "items"):
        val = payload.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict): yield item
            return
    # Some Augestel dashboard endpoints return DataTables aaData rows.
    rows = payload.get("aaData")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, (list, tuple)) and len(row) >= 5:
                yield {"received_at": row[0], "country": row[1], "number": row[2], "source": row[3], "message": row[4]}
            elif isinstance(row, dict): yield row
        return
    if any(k in payload for k in ("message", "sms", "text")):
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
    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    response = requests.get(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, params={"start_date": start}, timeout=12)
    response.raise_for_status()
    return response.json()

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
                await asyncio.sleep(15)
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
                await asyncio.sleep(15)
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
                    text = ("🔐 <b>New OTP received</b>\n\n"
                            f"📱 Service: <b>{html.escape(source)}</b>\n"
                            f"📞 Number: <code>{html.escape(number)}</code>\n"
                            f"🔢 Code: <code>{html.escape(code)}</code>\n"
                            f"🕒 Time: {html.escape(received)}\n\n"
                            f"<pre>{html.escape(message[:2500])}</pre>")
                    for uid in set(assigned):
                        try:
                            await app.bot.send_message(chat_id=uid, text=text)
                        except Exception as exc:
                            log.warning("Could not deliver OTP to user %s: %s", uid, type(exc).__name__)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never log keys, query strings, or provider response bodies.
            log.warning("Augestel polling cycle failed (%s).", type(exc).__name__)
        await asyncio.sleep(15)
