"""Handlers for regular users."""
from __future__ import annotations

import html

from telegram import LinkPreviewOptions, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .. import membership
from ..i18n import LANGUAGE_NAMES, MENU_LOOKUP, t, t_all
from ..keyboards import join_keyboard, language_keyboard, menu_keyboard, url_keyboard
from ..utils import get_db, is_admin
from . import admin as admin_handlers


async def _show_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    user = update.effective_user
    await update.effective_message.reply_text(
        t(lang, "welcome", name=html.escape(user.first_name or "")),
        reply_markup=menu_keyboard(lang, await is_admin(context, user.id)),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    row = await get_db(context).get_user(user.id)
    lang = row.get("lang") if row else None
    if not lang:
        await update.effective_message.reply_text(t_all("choose_lang"), reply_markup=language_keyboard("setlang"))
        return
    await _show_welcome(update, context, lang)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    row = await get_db(context).get_user(update.effective_user.id)
    await update.effective_message.reply_text(t(row.get("lang") if row else None, "help"))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    row = await get_db(context).get_user(update.effective_user.id)
    lang = row.get("lang") if row else None
    await update.effective_message.reply_text(
        t(lang, "cancelled"),
        reply_markup=menu_keyboard(lang, await is_admin(context, update.effective_user.id)),
    )


async def on_verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = q.from_user
    membership.forget(context, user.id)
    row = await get_db(context).get_user(user.id)
    lang = row.get("lang") if row else None

    missing = await membership.missing_channels(context, user.id)
    if missing:
        await q.answer(t(lang, "verify_failed"), show_alert=True)
        return

    await q.answer(t(lang, "verify_ok"))
    try:
        await q.message.delete()
    except TelegramError:
        pass

    if not lang:
        await q.message.chat.send_message(t_all("choose_lang"), reply_markup=language_keyboard("setlang"))
    else:
        await q.message.chat.send_message(
            t(lang, "welcome", name=html.escape(user.first_name or "")),
            reply_markup=menu_keyboard(lang, await is_admin(context, user.id)),
        )


async def on_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    code = (q.data or "").split(":", 1)[1]
    if code not in LANGUAGE_NAMES:
        await q.answer()
        return
    await get_db(context).set_lang(q.from_user.id, code)
    await q.answer(t(code, "lang_changed"))
    try:
        await q.message.delete()
    except TelegramError:
        pass
    await q.message.chat.send_message(
        t(code, "welcome", name=html.escape(q.from_user.first_name or "")),
        reply_markup=menu_keyboard(code, await is_admin(context, q.from_user.id)),
    )


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch a reply-keyboard button press (in any language)."""
    user = update.effective_user
    msg = update.effective_message
    db = get_db(context)
    row = await db.get_user(user.id)
    lang = row.get("lang") if row else None
    if not lang:
        await msg.reply_text(t_all("choose_lang"), reply_markup=language_keyboard("setlang"))
        return

    key = MENU_LOOKUP.get((msg.text or "").strip())
    if (msg.text or "").strip() in ("🎁 Daily points", "🎁 امتیاز روزانه"):
        key = "menu_daily_points"

    if key == "menu_profile":
        username = f"@{user.username}" if user.username else "-"
        await msg.reply_text(
            t(
                lang,
                "profile",
                uid=user.id,
                name=html.escape(user.first_name or "-"),
                username=html.escape(username),
                language=LANGUAGE_NAMES.get(lang, lang),
                referrals=row["referrals"],
                points=row.get("points", 0),
                joined=row["joined_at"][:10],
            )
        )
    elif key == "menu_invite":
        link = f"https://t.me/{context.bot.username}?start={user.id}"
        await msg.reply_text(
            t(lang, "invite", link=link, referrals=row["referrals"], points=row.get("points", 0)),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    elif key in ("menu_support", "menu_about"):
        setting = "support_link" if key == "menu_support" else "official_link"
        url = await db.get_setting(setting)
        if not url:
            await msg.reply_text(t(lang, "not_configured"))
        else:
            await msg.reply_text(
                t(lang, "support" if key == "menu_support" else "about"),
                reply_markup=url_keyboard(lang, url),
            )
    elif key == "menu_points":
        history = await db.points_history(user.id, 5)
        lines = []
        for item in history:
            delta = int(item["delta"])
            reason = item["reason"]
            if reason == "referral":
                label = "Referral bonus / پاداش دعوت"
            elif reason.startswith("transfer_to:"):
                label = f"Sent to {reason.split(':', 1)[1]} / ارسال به کاربر"
            elif reason.startswith("transfer_from:"):
                label = f"Received from {reason.split(':', 1)[1]} / دریافت از کاربر"
            elif reason == "initial_owner_bonus":
                label = "Initial bonus / امتیاز اولیه"
            elif reason == "admin_adjustment":
                label = "Admin adjustment / تغییر مدیر"
            else:
                label = reason
            lines.append(f"• {'+' if delta > 0 else ''}{delta} — {html.escape(label)}")
        history_text = "\n".join(lines) if lines else "No transactions yet / هنوز تراکنشی نیست."
        await msg.reply_text(
            t(lang, "points", points=row.get("points", 0)) +
            "\n\n📜 Recent history / تاریخچهٔ اخیر:\n" + history_text
        )
    elif key == "menu_daily_points":
        claimed, balance = await db.claim_daily_points(user.id, 15)
        if claimed:
            await msg.reply_text(f"🎉 +15 daily points! Balance: {balance} / پاداش روزانه: ۱۵ امتیاز دریافت شد")
        else:
            await msg.reply_text(f"⏳ Daily reward already claimed. Balance: {balance} / پاداش امروز را قبلاً گرفته‌اید")
    elif key == "menu_send_points":
        context.user_data["state"] = "points_transfer_target"
        await msg.reply_text(t(lang, "send_points_prompt"))
    elif key == "menu_numbers":
        active_services = await db.list_active_services()
        numbers = await db.list_available_numbers(services=active_services)
        if not numbers:
            await msg.reply_text(t(lang, "no_numbers"))
        else:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            rows = [[InlineKeyboardButton(f"{n['service']} · {n['country']} · {n['number']}", callback_data=f"number:claim:{n['id']}")] for n in numbers]
            await msg.reply_text("📱 Available numbers / شماره‌های موجود:", reply_markup=InlineKeyboardMarkup(rows))
    elif key == "menu_language":
        await msg.reply_text(t(lang, "choose_lang"), reply_markup=language_keyboard("lang"))
    elif key == "menu_admin":
        if await is_admin(context, user.id):
            await admin_handlers.open_panel(update, context)
    else:
        await msg.reply_text(t(lang, "unknown"), reply_markup=menu_keyboard(lang, await is_admin(context, user.id)))


async def on_number_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    try:
        number_id = int((q.data or "").rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return
    db = get_db(context)
    item = await db.get_phone_number(number_id)
    active_services = {s.casefold() for s in await db.list_active_services()}
    if not item or item["status"] != "available" or item["service"].casefold() not in active_services:
        await q.message.reply_text("This number or its service is no longer available. / این شماره یا سرویس دیگر موجود نیست.")
        return
    if not await db.assign_phone_number(number_id, q.from_user.id):
        await q.message.reply_text("This number was just taken. Please choose another.")
        return
    row = await db.get_user(q.from_user.id)
    lang = row.get("lang") if row else None
    await q.message.reply_text(t(lang, "number_added", service=html.escape(item["service"]), country=html.escape(item["country"]), number=html.escape(item["number"])))

 
async def handle_points_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    """Two-step user-to-user points transfer."""
    msg = update.effective_message
    user = update.effective_user
    db = get_db(context)
    row = await db.get_user(user.id)
    lang = row.get("lang") if row else None
    value = (msg.text or "").strip()

    if state == "points_transfer_target":
        if not value.isdigit():
            await msg.reply_text("Please send the recipient's numeric Telegram ID, or /cancel.")
            return
        recipient_id = int(value)
        if recipient_id == user.id:
            await msg.reply_text("You cannot send points to yourself. Send another ID or /cancel.")
            return
        recipient = await db.get_user(recipient_id)
        if not recipient or recipient.get("is_banned"):
            await msg.reply_text(t(lang, "send_points_failed"))
            return
        context.user_data["points_recipient_id"] = recipient_id
        context.user_data["state"] = "points_transfer_amount"
        await msg.reply_text(t(lang, "send_points_amount", uid=recipient_id, points=row.get("points", 0)))
        return

    if state == "points_transfer_amount":
        if not value.isdigit() or int(value) <= 0 or int(value) > 1_000_000_000:
            await msg.reply_text("Please send a whole number between 1 and 1,000,000,000 points, or /cancel.")
            return
        recipient_id = context.user_data.get("points_recipient_id")
        context.user_data.pop("state", None)
        context.user_data.pop("points_recipient_id", None)
        amount = int(value)
        ok = bool(recipient_id) and await db.transfer_points(user.id, int(recipient_id), amount)
        if ok:
            await msg.reply_text(t(lang, "send_points_success", amount=amount, uid=recipient_id))
            try:
                await context.bot.send_message(
                    chat_id=int(recipient_id),
                    text=f"🎁 You received {amount} points from user <code>{user.id}</code>.",
                )
            except TelegramError:
                pass
        else:
            await msg.reply_text(t(lang, "send_points_failed"))
