"""Admin panel: stats, broadcast, ban/unban, force-join channels, admins, settings."""
from __future__ import annotations

import asyncio
import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from ..keyboards import admin_panel_keyboard, back_keyboard, confirm_broadcast_keyboard
from ..utils import get_db, get_settings, is_admin, is_owner, valid_url

from . import extra_admin

log = logging.getLogger(__name__)
esc = html.escape

PROMPTS = {
    "user_info": "Send a user's numeric ID or @username.",
    "ban": "Send the numeric ID or @username of the user to ban.",
    "unban": "Send the numeric ID or @username of the user to unban.",
    "ch_add": (
        "Send the channel as <code>@username</code> or numeric ID.\n"
        "For a private channel add an invite link: <code>-1001234567890 | https://t.me/+abc</code>\n\n"
        "⚠️ The bot must be an <b>administrator</b> of the channel, otherwise membership cannot be checked."
    ),
    "ad_add": "Send the numeric Telegram ID of the new admin.",
    "support": "Send the support link (https://t.me/...). Send <code>-</code> to remove it.",
    "official": "Send the official channel link (https://t.me/...). Send <code>-</code> to remove it.",
    "broadcast": "Send the message to broadcast (text, photo, video, document... anything).",
    "num_add": "Choose a service to add a number.",
}
CANCEL_HINT = "\n\nSend /cancel to abort."


NUMBER_SERVICES = ["WhatsApp", "Telegram", "TikTok", "Instagram", "Facebook", "Gmail", "Gaming", "Other Services"]
NUMBER_COUNTRIES = ["Afghanistan", "United States", "United Kingdom", "Canada", "Germany", "France", "India", "Pakistan", "Turkey", "Russia", "Indonesia", "Brazil", "Nigeria", "Philippines", "Other"]


def _number_service_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(s, callback_data=f"adm:num_service:{s}")] for s in NUMBER_SERVICES]
    rows.append([InlineKeyboardButton("✖️ Cancel", callback_data="adm:home")])
    return InlineKeyboardMarkup(rows)


def _number_country_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(NUMBER_COUNTRIES), 2):
        pair = NUMBER_COUNTRIES[i:i + 2]
        rows.append([InlineKeyboardButton(c, callback_data=f"adm:num_country:{c}") for c in pair])
    rows.append([InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------- panel
async def _render_panel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    db = get_db(context)
    maintenance = await db.get_setting("maintenance") == "1"
    stats = await db.stats()
    text = (
        "⚙️ <b>Admin panel</b>\n\n"
        f"👥 Users: <b>{stats['total']}</b>  ·  🟢 Active: <b>{stats['active']}</b>\n"
        f"🛠 Maintenance: <b>{'ON' if maintenance else 'OFF'}</b>"
    )
    return text, admin_panel_keyboard(maintenance, is_owner(context, user_id))


async def open_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not await is_admin(context, user.id):
        return
    text, markup = await _render_panel(context, user.id)
    await update.effective_message.reply_text(text, reply_markup=markup)


async def _edit(q, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await q.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def _show_home(q, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, markup = await _render_panel(context, q.from_user.id)
    await _edit(q, text, markup)


# ------------------------------------------------------------ callbacks
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    uid = q.from_user.id
    if not await is_admin(context, uid):
        await q.answer("Not authorized.", show_alert=True)
        return
    await q.answer()

    db = get_db(context)
    action, _, arg = (q.data or "").split(":", 1)[1].partition(":")
    owner = is_owner(context, uid)

    if action in ("api_keys", "api_add", "api_toggle", "api_del", "points", "points_add", "points_sub"):
        await extra_admin.on_callback(update, context, action, arg)
        return

    if action == "home":
        context.user_data.pop("state", None)
        await _show_home(q, context)

    elif action == "close":
        context.user_data.pop("state", None)
        try:
            await q.message.delete()
        except TelegramError:
            pass

    elif action == "stats":
        s = await db.stats()
        langs = ", ".join(f"{esc(str(k))}: {v}" for k, v in s["langs"].items()) or "-"
        await _edit(
            q,
            "📊 <b>Statistics</b>\n\n"
            f"👥 Total users: <b>{s['total']}</b>\n"
            f"🟢 Active (can receive messages): <b>{s['active']}</b>\n"
            f"🚫 Banned: <b>{s['banned']}</b>\n"
            f"🆕 Joined today: <b>{s['today']}</b>\n"
            f"📅 Joined last 7 days: <b>{s['week']}</b>\n"
            f"🎁 Total referrals: <b>{s['referrals']}</b>\n"
            f"🗣 Languages: {langs}",
            back_keyboard(),
        )

    elif action in ("user_info", "ban", "unban", "ch_add", "support", "official", "broadcast", "otp_template", "otp_buttons"):
        context.user_data["state"] = action
        if action == "otp_template":
            current = await db.get_setting("otp_template", "🔐 <b>NUM BOT</b>\n📱 {service}\n🌍 {country}\n📞 <code>{number}</code>\n🔢 Code: <code>{code}</code>\n🕒 {time}\n🗣 {language}\n<pre>{message}</pre>")
            await _edit(q, "📝 <b>Edit OTP message</b>\nSend the full template. Placeholders: {service}, {country}, {number}, {code}, {time}, {language}, {message}. Must include {number} and {code}.\n\nCurrent template:\n" + esc(current), back_keyboard())
        elif action == "otp_buttons":
            current = await db.get_setting("otp_button_config", "📋 Copy code | 🤖 NUM BOT | https://t.me/")
            await _edit(q, "🔘 <b>Edit OTP buttons</b>\nSend: <code>Copy label | Bot label | https://t.me/YourBot</code>\nUse - instead of link to disable it.\n\nCurrent: " + esc(current), back_keyboard())
        else:
            await _edit(q, PROMPTS[action] + CANCEL_HINT, back_keyboard())

    elif action == "otp_settings":
        rows = [
            [InlineKeyboardButton("📝 Edit OTP message", callback_data="adm:otp_template")],
            [InlineKeyboardButton("📋 Copy button label", callback_data="adm:otp_copy_label")],
            [InlineKeyboardButton("🤖 Bot button label", callback_data="adm:otp_bot_label")],
            [InlineKeyboardButton("🔗 Bot button link", callback_data="adm:otp_bot_link")],
            [InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")],
        ]
        await _edit(q, "📝 <b>OTP message settings</b>\n\nPlaceholders: {service}, {country}, {number}, {code}, {time}, {language}, {message}\nHTML formatting is supported.", InlineKeyboardMarkup(rows))

    elif action in ("otp_template", "otp_copy_label", "otp_bot_label", "otp_bot_link"):
        context.user_data["state"] = action
        prompts = {
            "otp_template": "Send the new OTP message template. Placeholders: {service}, {country}, {number}, {code}, {time}, {language}, {message}",
            "otp_copy_label": "Send the Copy Code button text.",
            "otp_bot_label": "Send the NUM BOT button text.",
            "otp_bot_link": "Send the bot link starting with https://t.me/",
        }
        await _edit(q, prompts[action] + CANCEL_HINT, back_keyboard())

    elif action == "num_add":
        context.user_data.pop("num_add", None)
        services = list(dict.fromkeys(NUMBER_SERVICES + [v for v in (await db.get_setting("custom_services")).split("\n") if v]))
        rows = [[InlineKeyboardButton(s, callback_data=f"adm:num_service:{s}")] for s in services]
        rows.append([InlineKeyboardButton("➕ Add service", callback_data="adm:service_add")])
        rows.append([InlineKeyboardButton("✖️ Cancel", callback_data="adm:home")])
        await _edit(q, "📱 <b>Add a number</b>\nChoose the service:", InlineKeyboardMarkup(rows))

    elif action == "num_service":
        service = arg
        context.user_data["num_add"] = {"service": service}
        await _edit(q, f"📱 <b>Service:</b> {esc(service)}\nChoose the country:", _number_country_keyboard())

    elif action in ("service_add", "country_add"):
        context.user_data["state"] = action
        await _edit(q, "Send the new service name:" if action == "service_add" else "Send the new country name:", back_keyboard())

    elif action == "num_country":
        selected = context.user_data.get("num_add") or {}
        if not selected.get("service"):
            await _edit(q, "Please start adding the number again.", back_keyboard())
            return
        selected["country"] = arg
        context.user_data["num_add"] = selected
        context.user_data["state"] = "num_add_number"
        service_name = esc(str(selected["service"]))
        country_name = esc(arg)
        await _edit(q, f"📱 <b>{service_name}</b> · <b>{country_name}</b>\nSend the phone number now.\nIf it does not start with 0, a leading 0 will be added. Numbers starting with + are preserved.\n\nSend /cancel to abort.", back_keyboard())

    elif action == "num_stock":
        numbers = await db.list_available_numbers()
        if not numbers:
            await _edit(q, "📱 No available numbers.", InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add number", callback_data="adm:num_add")],[InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")]]))
        else:
            rows = [[InlineKeyboardButton(f"🗑 #{n['id']} {n['service']} · {n['country']} · {n['number']}"[:60], callback_data=f"adm:num_del:{n['id']}")] for n in numbers]
            rows.append([InlineKeyboardButton("➕ Add number", callback_data="adm:num_add")])
            rows.append([InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")])
            await _edit(q, "📱 <b>Available numbers</b>\nTap a number to remove it.", InlineKeyboardMarkup(rows))

    elif action == "num_del":
        await db.delete_phone_number(int(arg))
        await _show_home(q, context)

    elif action == "maint":
        new = "0" if await db.get_setting("maintenance") == "1" else "1"
        await db.set_setting("maintenance", new)
        await _show_home(q, context)

    elif action == "channels":
        await _show_channels(q, context)

    elif action == "chdel":
        await db.remove_channel(int(arg))
        context.bot_data.get("join_cache", {}).clear()
        await _show_channels(q, context)

    elif action == "admins":
        if not owner:
            await q.answer("Only the owner can manage admins.", show_alert=True)
            return
        await _show_admins(q, context)

    elif action == "ad_add":
        if not owner:
            await q.answer("Only the owner can manage admins.", show_alert=True)
            return
        context.user_data["state"] = "ad_add"
        await _edit(q, PROMPTS["ad_add"] + CANCEL_HINT, back_keyboard())

    elif action == "ad_del":
        if not owner:
            await q.answer("Only the owner can manage admins.", show_alert=True)
            return
        await db.remove_admin(int(arg))
        await _show_admins(q, context)

    elif action == "bc_no":
        context.user_data.pop("bc", None)
        await _edit(q, "Broadcast cancelled.", back_keyboard())

    elif action == "bc_yes":
        await _start_broadcast(q, context)


async def _show_channels(q, context: ContextTypes.DEFAULT_TYPE) -> None:
    channels = await get_db(context).list_channels()
    if channels:
        lines = "\n".join(f"• {esc(c['title'])} (<code>{c['chat_id']}</code>)" for c in channels)
    else:
        lines = "No force-join channels configured."
    rows = [
        [InlineKeyboardButton(f"🗑 Remove {c['title']}"[:60], callback_data=f"adm:chdel:{c['chat_id']}")]
        for c in channels
    ]
    rows.append([InlineKeyboardButton("➕ Add channel", callback_data="adm:ch_add")])
    rows.append([InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")])
    await _edit(q, f"📢 <b>Force-join channels</b>\n\n{lines}", InlineKeyboardMarkup(rows))


async def _show_admins(q, context: ContextTypes.DEFAULT_TYPE) -> None:
    admins = await get_db(context).list_admins()
    owner_id = get_settings(context).owner_id
    lines = [f"👑 <code>{owner_id}</code> (owner)"] + [f"• <code>{a}</code>" for a in admins]
    rows = [[InlineKeyboardButton(f"🗑 Remove {a}", callback_data=f"adm:ad_del:{a}")] for a in admins]
    rows.append([InlineKeyboardButton("➕ Add admin", callback_data="adm:ad_add")])
    rows.append([InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")])
    await _edit(q, "👮 <b>Admins</b>\n\n" + "\n".join(lines), InlineKeyboardMarkup(rows))


# ------------------------------------------------- text input (states)
async def handle_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    """Called for any message an admin sends while a panel action is waiting for input."""
    msg = update.effective_message
    uid = update.effective_user.id
    db = get_db(context)
    text = (msg.text or "").strip()

    if state in ("api_add", "points_add", "points_sub"):
        await extra_admin.handle_state(update, context, state)
        return

    if state == "broadcast":
        context.user_data.pop("state", None)
        context.user_data["bc"] = (msg.chat_id, msg.message_id)
        total = len(await db.broadcast_targets())
        await msg.reply_text(
            f"📣 Send the message above to <b>{total}</b> users?",
            reply_to_message_id=msg.message_id,
            reply_markup=confirm_broadcast_keyboard(),
        )
        return

    if not text:
        await msg.reply_text("Please send text.")
        return

    done = True
    reply = ""

    if state == "otp_template":
        if len(text) > 3000 or "{number}" not in text or "{code}" not in text:
            await msg.reply_text("Template must be under 3000 characters and include {number} and {code}.")
            return
        await db.set_setting("otp_template", text)
        context.user_data.pop("state", None)
        await msg.reply_text("✅ OTP message template saved.", reply_markup=back_keyboard())
        return

    if state == "otp_buttons":
        parts = [part.strip() for part in text.split("|")]
        if len(parts) != 3 or not parts[0] or not parts[1] or (parts[2] != "-" and not valid_url(parts[2])):
            await msg.reply_text("Format: Copy label | Bot label | https://t.me/YourBot (or -)")
            return
        await db.set_setting("otp_button_config", text)
        context.user_data.pop("state", None)
        await msg.reply_text("✅ OTP button settings saved.", reply_markup=back_keyboard())
        return

    if state in ("otp_template", "otp_copy_label", "otp_bot_label", "otp_bot_link"):
        if len(text) > 3000 or len(text) < 2:
            await msg.reply_text("Please send text between 2 and 3000 characters.")
            return
        if state == "otp_bot_link" and not text.startswith("https://t.me/"):
            await msg.reply_text("The bot link must start with https://t.me/")
            return
        key = {"otp_template": "otp_message_template", "otp_copy_label": "otp_copy_label",
               "otp_bot_label": "otp_bot_label", "otp_bot_link": "otp_bot_link"}[state]
        await db.set_setting(key, text)
        context.user_data.pop("state", None)
        await msg.reply_text("✅ OTP setting saved.", reply_markup=back_keyboard())
        return

    if state in ("service_add", "country_add"):
        if len(text) < 2 or len(text) > 40:
            await msg.reply_text("Please send a name between 2 and 40 characters.")
            return
        key = "custom_services" if state == "service_add" else "custom_countries"
        values = [v for v in (await db.get_setting(key)).split("\n") if v]
        if text.casefold() not in {v.casefold() for v in values}:
            values.append(text)
            await db.set_setting(key, "\n".join(values))
        context.user_data.pop("state", None)
        await msg.reply_text(f"✅ Added: <b>{esc(text)}</b>. Reopen Add number to see it.", reply_markup=back_keyboard())
        return

    if state == "num_add_number":
        selected = context.user_data.get("num_add") or {}
        service = selected.get("service")
        country = selected.get("country")
        number = text.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not service or not country:
            context.user_data.pop("state", None)
            context.user_data.pop("num_add", None)
            await msg.reply_text("Please start adding the number again.", reply_markup=back_keyboard())
            return
        digits = "".join(ch for ch in number if ch.isdigit())
        if len(digits) < 7 or len(digits) > 20 or any(ch not in "+0123456789" for ch in number) or number.count("+") > 1 or ("+" in number and not number.startswith("+")):
            await msg.reply_text("Number looks invalid. Send digits, optionally starting with +. Try again or /cancel.")
            return
        # Store phone numbers as text to preserve leading zeros.
        # Add a leading zero to local-format numbers only; keep international + numbers unchanged.
        if not number.startswith("0") and not number.startswith("+"):
            number = "0" + number
        ok = await db.add_phone_number(str(service)[:40], str(country)[:60], number[:30])
        if not ok:
            await msg.reply_text("That number already exists. Send another or /cancel.")
            return
        context.user_data.pop("state", None)
        context.user_data.pop("num_add", None)
        await msg.reply_text(f"✅ Number added to stock.\nService: <b>{esc(str(service))}</b>\nCountry: <b>{esc(str(country))}</b>\nNumber: <code>{esc(number)}</code>", reply_markup=back_keyboard())
        return

    if state in ("user_info", "ban", "unban"):
        target = await db.find_user(text)
        if not target:
            await msg.reply_text("User not found. They must have started the bot. Try again or /cancel.")
            return
        if state == "user_info":
            reply = (
                "🔎 <b>User</b>\n\n"
                f"🆔 <code>{target['id']}</code>\n"
                f"🏷 {esc(target['first_name'] or '-')}\n"
                f"🌐 {'@' + esc(target['username']) if target['username'] else '-'}\n"
                f"🗣 Language: {esc(str(target['lang'] or '-'))}\n"
                f"👥 Referrals: {target['referrals']}  ·  Invited by: {target['referrer_id'] or '-'}\n"
                f"🚫 Banned: {'yes' if target['is_banned'] else 'no'}  ·  "
                f"🟢 Active: {'yes' if target['is_active'] else 'no (blocked the bot)'}\n"
                f"📅 Joined: {target['joined_at']}\n"
                f"👁 Last seen: {target['last_seen']}"
            )
        elif state == "ban":
            if is_owner(context, target["id"]) or await db.is_admin(target["id"]):
                reply = "You cannot ban an admin."
            else:
                await db.set_banned(target["id"], True)
                reply = f"🚫 User <code>{target['id']}</code> banned."
        else:
            await db.set_banned(target["id"], False)
            reply = f"✅ User <code>{target['id']}</code> unbanned."

    elif state == "ad_add":
        if not is_owner(context, uid):
            context.user_data.pop("state", None)
            return
        if not text.isdigit():
            await msg.reply_text("Send a numeric Telegram ID, or /cancel.")
            return
        await db.add_admin(int(text))
        reply = f"👮 <code>{int(text)}</code> is now an admin."

    elif state in ("support", "official"):
        key = "support_link" if state == "support" else "official_link"
        if text == "-":
            await db.set_setting(key, "")
            reply = "Link removed."
        elif valid_url(text):
            await db.set_setting(key, text)
            reply = "✅ Link saved."
        else:
            await msg.reply_text("Please send a valid link starting with https://, or /cancel.")
            return

    elif state == "ch_add":
        done, reply = await _add_channel(context, text)

    if done:
        context.user_data.pop("state", None)
    await msg.reply_text(reply, reply_markup=back_keyboard() if done else None)


async def _add_channel(context: ContextTypes.DEFAULT_TYPE, text: str) -> tuple[bool, str]:
    ref, _, link = (p.strip() for p in text.partition("|"))
    if ref.lstrip("-").isdigit():
        target: int | str = int(ref)
    else:
        target = ref if ref.startswith("@") else f"@{ref}"
    try:
        chat = await context.bot.get_chat(target)
    except TelegramError as exc:
        return False, f"Could not find that chat: {esc(str(exc))}\nTry again or /cancel."

    if not link:
        link = f"https://t.me/{chat.username}" if chat.username else (chat.invite_link or "")
    if not link:
        return False, (
            "This channel has no public username. Send it with an invite link:\n"
            "<code>-1001234567890 | https://t.me/+abc</code>"
        )

    try:
        me = await context.bot.get_chat_member(chat.id, context.bot.id)
        bot_is_admin = me.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except TelegramError:
        bot_is_admin = False

    await get_db(context).add_channel(chat.id, chat.title or str(chat.id), link)
    context.bot_data.get("join_cache", {}).clear()
    warning = "" if bot_is_admin else "\n\n⚠️ The bot is NOT an admin there yet — add it as admin or the check is skipped."
    return True, f"✅ Added <b>{esc(chat.title or str(chat.id))}</b>.{warning}"


# ----------------------------------------------------------- broadcast
async def _start_broadcast(q, context: ContextTypes.DEFAULT_TYPE) -> None:
    source = context.user_data.pop("bc", None)
    if not source:
        await _edit(q, "Nothing to broadcast. Start again from the panel.", back_keyboard())
        return
    if context.bot_data.get("broadcasting"):
        await _edit(q, "⏳ Another broadcast is still running.", back_keyboard())
        return

    context.bot_data["broadcasting"] = True
    await _edit(q, "📣 Broadcast started… you will get a report when it finishes.")
    context.application.create_task(
        _run_broadcast(context, q.message.chat_id, source[0], source[1]),
        name="broadcast",
    )


async def _send_one(context: ContextTypes.DEFAULT_TYPE, uid: int, src_chat: int, src_msg: int) -> str:
    for _ in range(3):
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=src_chat, message_id=src_msg)
            return "sent"
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except Forbidden:
            return "blocked"
        except TelegramError as exc:
            log.warning("Broadcast to %s failed: %s", uid, exc)
            return "failed"
    return "failed"


async def _run_broadcast(context: ContextTypes.DEFAULT_TYPE, admin_chat: int, src_chat: int, src_msg: int) -> None:
    db = get_db(context)
    delay = 1.0 / get_settings(context).broadcast_rate
    sent = blocked = failed = 0
    try:
        targets = await db.broadcast_targets()
        for uid in targets:
            result = await _send_one(context, uid, src_chat, src_msg)
            if result == "sent":
                sent += 1
            elif result == "blocked":
                blocked += 1
                await db.set_active(uid, False)
            else:
                failed += 1
            await asyncio.sleep(delay)
        report = (
            "📣 <b>Broadcast finished</b>\n\n"
            f"✅ Delivered: <b>{sent}</b>\n"
            f"🚫 Blocked the bot: <b>{blocked}</b>\n"
            f"⚠️ Failed: <b>{failed}</b>"
        )
    except Exception:  # noqa: BLE001
        log.exception("Broadcast crashed")
        report = f"❌ Broadcast stopped unexpectedly after {sent} deliveries. See the logs."
    finally:
        context.bot_data["broadcasting"] = False
    try:
        await context.bot.send_message(admin_chat, report, reply_markup=back_keyboard())
    except TelegramError:
        pass
