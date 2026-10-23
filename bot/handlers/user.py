"""Handlers for regular users."""
from __future__ import annotations

import html
import time

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
                label = "Buy Coin referral / پاداش دعوت بای‌کوین"
            elif reason.startswith("transfer_to:"):
                label = f"Sent to {reason.split(':', 1)[1]} / ارسال به کاربر"
            elif reason.startswith("transfer_from:"):
                label = f"Received from {reason.split(':', 1)[1]} / دریافت از کاربر"
            elif reason == "initial_owner_bonus":
                label = "Initial Buy Coin / بای‌کوین اولیه"
            elif reason == "admin_adjustment":
                label = "Buy Coin adjustment / تغییر بای‌کوین"
            else:
                label = reason
            lines.append(f"• {'+' if delta > 0 else ''}{delta} — {html.escape(label)}")
        history_text = "\n".join(lines) if lines else "No Buy Coin transactions yet / هنوز تراکنش بای‌کوین ندارید."
        await msg.reply_text(
            t(lang, "points", points=row.get("points", 0)) +
            "\n\n📜 Recent history / تاریخچهٔ اخیر:\n" + history_text
        )
    elif key == "menu_daily_points":
        claimed, balance = await db.claim_daily_points(user.id, 15)
        if claimed:
            await msg.reply_text(f"🎉 +15 Buy Coin! Balance: {balance} / ۱۵ بای‌کوین روزانه دریافت شد")
        else:
            await msg.reply_text(f"⏳ Daily Buy Coin already claimed. Balance: {balance} / بای‌کوین امروز را قبلاً گرفته‌اید")
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
            # Provider-imported numbers use Any Service, so expose every active
            # service in the bot rather than displaying the internal stock label.
            if any(n["service"].casefold() == "any service" for n in numbers):
                services = active_services
            else:
                services = list(dict.fromkeys(n["service"] for n in numbers))
            context.user_data["number_services"] = services
            await msg.reply_text(
                t(lang, "choose_number_service"),
                reply_markup=_number_choice_keyboard(services, "service", 0),
            )
    elif key == "menu_sessions":
        assigned = await db._all(
            "SELECT id, service, country, number, created_at FROM phone_numbers "
            "WHERE assigned_user_id=? AND status='assigned' ORDER BY id DESC LIMIT 10",
            (user.id,),
        )
        if not assigned:
            await msg.reply_text(t(lang, "sessions_empty"))
            return
        # Only show OTP records for numbers assigned to this Telegram user.
        recent_otps = await db._all(
            "SELECT number, message, received_at FROM otp_messages ORDER BY received_at DESC LIMIT 300"
        )
        def _digits(value: str) -> str:
            return "".join(ch for ch in str(value or "") if ch.isdigit())
        otp_by_number = {}
        assigned_digits = {_digits(item["number"]) for item in assigned}
        for otp in recent_otps:
            digits = _digits(otp.get("number", ""))
            if digits in assigned_digits and digits not in otp_by_number:
                otp_by_number[digits] = otp
        blocks = [t(lang, "sessions_title")]
        for item in assigned:
            otp = otp_by_number.get(_digits(item["number"]))
            if otp:
                otp_line = "🔐 Latest OTP: " + html.escape(str(otp["message"])[:500]) + "\n🕒 " + html.escape(str(otp["received_at"]))
            else:
                otp_line = "⏳ Waiting for OTP / منتظر کد تأیید"
            blocks.append(t(
                lang, "session_item",
                service=html.escape(str(item["service"])),
                country=html.escape(str(item["country"])),
                number=html.escape(str(item["number"])),
                created=html.escape(str(item["created_at"])[:16].replace("T", " ")),
                otp_line=otp_line,
            ))
        await msg.reply_text("\n\n".join(blocks))
    elif key == "menu_language":
        await msg.reply_text(t(lang, "choose_lang"), reply_markup=language_keyboard("lang"))
    elif key == "menu_admin":
        if await is_admin(context, user.id):
            await admin_handlers.open_panel(update, context)
    else:
        await msg.reply_text(t(lang, "unknown"), reply_markup=menu_keyboard(lang, await is_admin(context, user.id)))


def _number_choice_keyboard(items: list[str], prefix: str, page: int = 0, page_size: int = 20) -> "InlineKeyboardMarkup":
    """Keep Telegram inline markup small even when provider inventory has many countries."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    start = max(0, page) * page_size
    shown = items[start:start + page_size]
    rows = [
        [InlineKeyboardButton(str(item)[:60], callback_data=f"number:{prefix}:{start + i}")]
        for i, item in enumerate(shown)
    ]
    navigation = []
    if start > 0:
        navigation.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"number:{prefix}_page:{page - 1}"))
    if start + page_size < len(items):
        navigation.append(InlineKeyboardButton("Next ➡️", callback_data=f"number:{prefix}_page:{page + 1}"))
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(rows)


async def on_number_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Choose service/country and assign up to two distinct available numbers."""
    q = update.callback_query
    await q.answer()
    data = (q.data or "").split(":")
    db = get_db(context)
    row = await db.get_user(q.from_user.id)
    lang = row.get("lang") if row else None
    from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

    if len(data) >= 3 and data[1] == "back" and data[2] == "services":
        services = await db.list_active_services()
        available = await db.list_available_numbers(services=services)
        services_with_stock = list(dict.fromkeys(item["service"] for item in available))
        context.user_data["number_services"] = services_with_stock
        if not services_with_stock:
            await q.message.reply_text(t(lang, "no_numbers"))
        else:
            await q.message.reply_text(t(lang, "choose_number_service"), reply_markup=_number_choice_keyboard(services_with_stock, "service", 0))
        return

    if len(data) >= 3 and data[1] == "service_page":
        services = context.user_data.get("number_services", [])
        page = int(data[2]) if data[2].isdigit() else 0
        await q.message.reply_text(t(lang, "choose_number_service"), reply_markup=_number_choice_keyboard(services, "service", page))
        return

    if len(data) >= 3 and data[1] == "country_page":
        countries = context.user_data.get("number_countries", [])
        page = int(data[2]) if data[2].isdigit() else 0
        service = context.user_data.get("number_selected_service", "")
        await q.message.reply_text(
            t(lang, "choose_number_country", service=html.escape(service)),
            reply_markup=_number_choice_keyboard(countries, "country", page),
        )
        return

    if len(data) >= 3 and data[1] == "operator_page":
        operators = context.user_data.get("number_operators", [])
        page = int(data[2]) if data[2].isdigit() else 0
        country = context.user_data.get("number_base_country", "")
        await q.message.reply_text(
            f"🌐 Country: <b>{html.escape(country)}</b>\nChoose an operator / اپراتور را انتخاب کنید:",
            reply_markup=_number_choice_keyboard(operators, "operator", page),
        )
        return

    if len(data) >= 3 and data[1] == "service":
        try:
            index = int(data[2])
            service = context.user_data["number_services"][index]
        except (ValueError, IndexError, KeyError):
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        active_services = {s.casefold() for s in await db.list_active_services()}
        if service.casefold() not in active_services:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        numbers = await db.list_available_numbers(service=service)
        # Operator-tagged Afghan stock is grouped under a display country label.
        countries = list(dict.fromkeys((n["country"].split(" · ", 1)[0]) for n in numbers))
        if not countries:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        context.user_data["number_selected_service"] = service
        context.user_data["number_countries"] = countries
        await q.message.reply_text(
            t(lang, "choose_number_country", service=html.escape(service)),
            reply_markup=_number_choice_keyboard(countries, "country", 0),
        )
        return

    if len(data) >= 3 and data[1] == "country":
        try:
            index = int(data[2])
            country = context.user_data["number_countries"][index]
            service = context.user_data["number_selected_service"]
        except (ValueError, IndexError, KeyError):
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        numbers = await db.list_available_numbers(service=service)
        matching = [n for n in numbers if n["country"] == country or n["country"].startswith(country + " · ")]
        if not matching:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        operators = list(dict.fromkeys(n["country"].split(" · ", 1)[1] for n in matching if " · " in n["country"]))
        context.user_data["number_base_country"] = country
        if operators:
            context.user_data["number_operators"] = operators
            context.user_data["number_operator_country_map"] = {
                n["country"].split(" · ", 1)[1]: n["country"] for n in matching if " · " in n["country"]
            }
            await q.message.reply_text(
                f"🌐 Country: <b>{html.escape(country)}</b>\nChoose an operator / اپراتور را انتخاب کنید:",
                reply_markup=_number_choice_keyboard(operators, "operator", 0),
            )
            return
        context.user_data["number_selected_country"] = country
        await q.message.reply_text(
            t(lang, "confirm_get_number", country=html.escape(country)),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "get_number_button"), callback_data="number:get:0")
            ]]),
        )
        return

    if len(data) >= 3 and data[1] == "operator":
        try:
            index = int(data[2])
            operator = context.user_data["number_operators"][index]
            country = context.user_data["number_operator_country_map"][operator]
            service = context.user_data["number_selected_service"]
        except (ValueError, IndexError, KeyError):
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        if not await db.list_available_numbers(service=service, country=country):
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        context.user_data["number_selected_country"] = country
        await q.message.reply_text(
            f"🌐 Country: <b>{html.escape(context.user_data.get('number_base_country', 'Afghanistan'))}</b>\n📶 Operator: <b>{html.escape(operator)}</b>\nPress the button below to get one number.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "get_number_button"), callback_data="number:get:0")
            ]]),
        )
        return

    if len(data) >= 2 and data[1] == "get":
        now = time.monotonic()
        last_request = float(context.user_data.get("last_number_request_at", 0))
        wait = 5 - (now - last_request)
        if wait > 0:
            await q.message.reply_text(t(lang, "number_cooldown", seconds=max(1, int(wait + 0.99))))
            return
        service = context.user_data.get("number_selected_service")
        country = context.user_data.get("number_selected_country")
        if not service or not country:
            await q.message.reply_text(t(lang, "choose_number_service"))
            return
        active_services = {s.casefold() for s in await db.list_active_services()}
        if service.casefold() not in active_services:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        numbers = await db.list_available_numbers(service=service, country=country)
        if not numbers:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        # Allocate up to two distinct numbers from this service/country only.
        # Each number is claimed independently so concurrent users cannot get duplicates.
        assigned = []
        for item in numbers:
            if await db.assign_phone_number(int(item["id"]), q.from_user.id):
                assigned.append(item)
                if len(assigned) == 2:
                    break
        if assigned:
            context.user_data["last_number_request_at"] = time.monotonic()
            blocks = []
            for index, item in enumerate(assigned, 1):
                blocks.append(
                    f"📱 <b>Number {index}</b>\n"
                    + t(lang, "number_added",
                        service=html.escape(service),
                        country=html.escape(item["country"]),
                        number=html.escape(item["number"]))
                )
            buttons = [
                [InlineKeyboardButton(f"📋 Copy number {index} / کاپی شماره {index}", copy_text=CopyTextButton(text=item["number"]))]
                for index, item in enumerate(assigned, 1)
            ]
            buttons.extend([
                [InlineKeyboardButton("🔄 Get another pair / شماره‌های جدید", callback_data="number:get:0")],
                [InlineKeyboardButton("⬅️ Back to services / برگشت به سرویس‌ها", callback_data="number:back:services")],
            ])
            otp_link = (await db.get_setting("otp_channel_link")).strip()
            if otp_link.startswith("https://t.me/"):
                buttons.insert(1, [InlineKeyboardButton("📢 OTP Channel / کانال کدها", url=otp_link)])
            markup = InlineKeyboardMarkup(buttons)
            if len(assigned) == 1:
                await q.message.reply_text("\n\n".join(blocks) + "\n\n⚠️ Only one number is available in this selection right now.", reply_markup=markup)
            else:
                await q.message.reply_text("\n\n".join(blocks), reply_markup=markup)
            return
        await q.message.reply_text(t(lang, "no_numbers"))
        return

    # Compatibility for older inline buttons sent before this update.
    if len(data) >= 3 and data[1] == "claim":
        try:
            number_id = int(data[2])
        except ValueError:
            return
        item = await db.get_phone_number(number_id)
        active_services = {s.casefold() for s in await db.list_active_services()}
        if not item or item["status"] != "available" or item["service"].casefold() not in active_services:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        now = time.monotonic()
        last_request = float(context.user_data.get("last_number_request_at", 0))
        wait = 5 - (now - last_request)
        if wait > 0:
            await q.message.reply_text(t(lang, "number_cooldown", seconds=max(1, int(wait + 0.99))))
            return
        if not await db.assign_phone_number(number_id, q.from_user.id):
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        context.user_data["last_number_request_at"] = time.monotonic()
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
            await msg.reply_text("Send the Telegram ID of a user registered in this bot, or /cancel. / آی‌دی کاربری را بفرستید که همین ربات را شروع کرده باشد.")
            return
        recipient_id = int(value)
        if recipient_id == user.id:
            await msg.reply_text("You cannot transfer Buy Coin to yourself. / نمی‌توانید بای‌کوین را به خودتان انتقال دهید؛ آی‌دی دیگری بفرستید یا /cancel.")
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
            await msg.reply_text("Send a whole Buy Coin amount between 1 and 1,000,000,000, or /cancel. / مقدار صحیح بای‌کوین را بفرستید.")
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
