"""Handlers for regular users."""
from __future__ import annotations

import html
import time

from telegram import LinkPreviewOptions, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .. import membership
from ..i18n import LANGUAGE_NAMES, MENU_LOOKUP, t, t_all
from ..keyboards import (
    close_button,
    ib,
    join_keyboard,
    language_keyboard,
    menu_keyboard,
    refer_keyboard,
    url_keyboard,
    wallet_keyboard,
)
from ..utils import get_db, is_admin
from . import admin as admin_handlers

REFER_REWARD = 10  # Buy Coin per valid invite (matches db referral bonus)


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
    elif key in ("menu_refer", "menu_invite"):
        link = f"https://t.me/{context.bot.username}?start={user.id}"
        await msg.reply_text(
            t(lang, "refer_card", link=link, referrals=row["referrals"], per=REFER_REWARD),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=refer_keyboard(lang, link),
        )
    elif key == "menu_traffic":
        active_services = await db.list_active_services()
        numbers = await db.list_available_numbers(services=active_services)
        if not numbers:
            await msg.reply_text(t(lang, "no_numbers"))
            return
        counts: dict[str, int] = {}
        for n in numbers:
            counts[n["service"]] = counts.get(n["service"], 0) + 1
        if any(name.casefold() == "any service" for name in counts):
            # Provider stock is shared by every active service.
            lines = [f"📱 <b>{html.escape(str(s)).upper()}</b>" for s in active_services]
        else:
            lines = [f"📱 <b>{html.escape(str(s)).upper()}</b> — {c}" for s, c in counts.items()]
        await msg.reply_text(
            t(lang, "traffic_title") + "\n" + "\n".join(lines) + "\n" + t(lang, "traffic_footer", total=len(numbers))
        )
    elif key == "menu_2fa":
        await msg.reply_text(t(lang, "twofa_soon"))
    elif key == "menu_withdraw":
        await msg.reply_text(
            t(lang, "withdraw_note") + "\n\n" + t(lang, "points", points=row.get("points", 0)),
            reply_markup=wallet_keyboard(lang),
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
            "\n\n📜 Recent history / تاریخچهٔ اخیر:\n" + history_text +
            "\n\n👇 <b>Choose an action / یک گزینه را انتخاب کنید</b>",
            reply_markup=wallet_keyboard(lang),
        )
    elif key == "menu_wallet_back":
        await msg.reply_text(
            t(lang, "wallet_back_message"),
            reply_markup=menu_keyboard(lang, await is_admin(context, user.id)),
        )
    elif key == "menu_daily_points":
        claimed, balance = await db.claim_daily_points(user.id, 15)
        if claimed:
            await msg.reply_text(
                t(lang, "daily_claim_success", balance=balance),
                reply_markup=wallet_keyboard(lang),
            )
        else:
            await msg.reply_text(
                t(lang, "daily_claim_used", balance=balance),
                reply_markup=wallet_keyboard(lang),
            )
    elif key == "menu_send_points":
        context.user_data["state"] = "points_transfer_target"
        await msg.reply_text(t(lang, "send_points_prompt"), reply_markup=wallet_keyboard(lang))
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
    elif key in ("menu_sessions", "menu_search"):
        assigned = await db._all(
            "SELECT id, service, country, number, created_at FROM phone_numbers "
            "WHERE assigned_user_id=? AND status='assigned' ORDER BY id DESC LIMIT 6",
            (user.id,),
        )
        if not assigned:
            await msg.reply_text(t(lang, "sessions_empty"))
            return
        # Only show OTP records for numbers assigned to this Telegram user.
        recent_otps = await db._all(
            "SELECT number, message, received_at FROM otp_messages ORDER BY received_at DESC LIMIT 100"
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
                otp_line = "🔐 Latest OTP: " + html.escape(str(otp["message"])[:250]) + "\n🕒 " + html.escape(str(otp["received_at"]))
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
    """Two-column green choice grid with country flags, matching the supplied bot reference."""
    from telegram import InlineKeyboardMarkup

    start = max(0, page) * page_size
    shown = items[start:start + page_size]
    service_icons = {
        "whatsapp": "🟢", "telegram": "✈️", "facebook": "🔵",
        "instagram": "📸", "tiktok": "🎵", "gmail": "✉️",
        "google": "🔎", "gaming": "🎮", "other services": "🧩",
    }
    country_flags = {
        "afghanistan": "🇦🇫", "united states": "🇺🇸", "usa": "🇺🇸", "us": "🇺🇸",
        "united kingdom": "🇬🇧", "uk": "🇬🇧", "great britain": "🇬🇧",
        "russia": "🇷🇺", "russian federation": "🇷🇺", "india": "🇮🇳",
        "pakistan": "🇵🇰", "bangladesh": "🇧🇩", "indonesia": "🇮🇩",
        "brazil": "🇧🇷", "canada": "🇨🇦", "germany": "🇩🇪",
        "france": "🇫🇷", "turkey": "🇹🇷", "türkiye": "🇹🇷",
        "iran": "🇮🇷", "iran, islamic republic of": "🇮🇷",
        "united arab emirates": "🇦🇪", "uae": "🇦🇪", "saudi arabia": "🇸🇦",
        "nigeria": "🇳🇬", "egypt": "🇪🇬", "vietnam": "🇻🇳",
        "thailand": "🇹🇭", "philippines": "🇵🇭", "malaysia": "🇲🇾",
        "nepal": "🇳🇵", "uzbekistan": "🇺🇿", "kazakhstan": "🇰🇿",
        "ukraine": "🇺🇦", "spain": "🇪🇸", "italy": "🇮🇹",
        "mexico": "🇲🇽", "south africa": "🇿🇦", "china": "🇨🇳",
        "japan": "🇯🇵", "south korea": "🇰🇷", "korea": "🇰🇷",
        "australia": "🇦🇺", "poland": "🇵🇱", "netherlands": "🇳🇱",
        "sweden": "🇸🇪", "switzerland": "🇨🇭", "argentina": "🇦🇷",
    }

    rows = []
    for offset in range(0, len(shown), 2):
        row = []
        for index in range(offset, min(offset + 2, len(shown))):
            item = str(shown[index])
            if prefix == "service":
                icon = next((emoji for name, emoji in service_icons.items() if name in item.casefold()), "📱")
                label = f"{icon} {item[:24].upper()}"
            else:
                normalized = item.casefold().strip()
                base_country = normalized.split(" · ", 1)[0].split(" - ", 1)[0].strip()
                flag = country_flags.get(base_country, "🌍")
                label = f"{flag} {item[:25]}"
            row.append(ib(label[:60], "success", callback_data=f"number:{prefix}:{start + index}"))
        rows.append(row)

    navigation = []
    if start > 0:
        navigation.append(ib("⬅️ Previous", "primary", callback_data=f"number:{prefix}_page:{page - 1}"))
    if start + page_size < len(items):
        navigation.append(ib("Next ➡️", "primary", callback_data=f"number:{prefix}_page:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([close_button(label="Close")])
    return InlineKeyboardMarkup(rows)


async def on_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Red Close / CLOSE button: remove the message the button is attached to."""
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except TelegramError:
        pass


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

    if len(data) >= 3 and data[1] == "back" and data[2] == "countries":
        service = context.user_data.get("number_selected_service", "")
        numbers = await db.list_available_numbers(service=service)
        countries = list(dict.fromkeys(n["country"] for n in numbers))
        context.user_data["number_countries"] = countries
        if not countries:
            await q.message.reply_text(t(lang, "no_numbers"))
        else:
            await q.message.reply_text(
                t(lang, "choose_number_country", service=html.escape(service)),
                reply_markup=_number_choice_keyboard(countries, "country", 0),
            )
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
        # Keep operator-tagged inventory in the same country list, e.g. "Afghanistan · Etisalat".
        # This removes the extra operator-selection screen and keeps the flow short.
        countries = list(dict.fromkeys(n["country"] for n in numbers))
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
        numbers = await db.list_available_numbers(service=service, country=country)
        if not numbers:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        # Selecting a country immediately assigns up to THREE available numbers.
        context.user_data["number_selected_country"] = country
        now = time.monotonic()
        last_request = float(context.user_data.get("last_number_request_at", 0))
        wait = 10 - (now - last_request)
        if wait > 0:
            await q.message.reply_text(t(lang, "number_cooldown", seconds=max(1, int(wait + 0.99))))
            return
        active_services = {s.casefold() for s in await db.list_active_services()}
        if service.casefold() not in active_services:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        assigned = []
        for item in numbers:
            if len(assigned) >= 3:
                break
            if await db.assign_phone_number(int(item["id"]), q.from_user.id):
                assigned.append(item)
        if not assigned:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        context.user_data["last_number_request_at"] = time.monotonic()
        context.user_data["number_last_assigned_ids"] = [int(item["id"]) for item in assigned]
        blocks = []
        buttons = []
        for index, item in enumerate(assigned, 1):
            blocks.append(
                f"{index}. 📱 <b>{html.escape(str(service))}</b> — 🌍 {html.escape(str(item['country']))}\n"
                f"📞 <code>{html.escape(str(item['number']))}</code>\n"
                f"📩 " + ("Waiting for OTP" if lang == "en" else "منتظر کد تأیید")
            )
            buttons.append([ib(f"📋 {item['number']}", "success", copy_text=CopyTextButton(text=str(item["number"])))])
        message_text = "🎉 Assigned numbers / شماره‌های اختصاص‌یافته: " + str(len(assigned)) + "\n\n" + "\n\n".join(blocks)
        buttons.append([ib("🔄 " + ("Change numbers (10s)" if lang == "en" else "تغییر شماره‌ها (۱۰ ثانیه)"), "primary", callback_data="number:get:0")])
        buttons.extend([
            [ib("⬅️ " + ("Back to countries" if lang == "en" else "برگشت به کشورها"), "primary", callback_data="number:back:countries")],
            [ib("⬅️ " + ("Back to services" if lang == "en" else "برگشت به سرویس‌ها"), "danger", callback_data="number:back:services")],
        ])
        otp_link = (await db.get_setting("otp_channel_link")).strip()
        if otp_link.startswith("https://t.me/"):
            buttons.insert(len(assigned), [ib("📢 " + ("OTP Channel" if lang == "en" else "کانال کدها"), "primary", url=otp_link)])
        await q.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(buttons))
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
        # No separate Get Number confirmation: assign up to three immediately.
        context.user_data["number_selected_country"] = country
        numbers = await db.list_available_numbers(service=service, country=country)
        assigned = []
        for item in numbers:
            if len(assigned) >= 3:
                break
            if await db.assign_phone_number(int(item["id"]), q.from_user.id):
                assigned.append(item)
        if not assigned:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        context.user_data["last_number_request_at"] = time.monotonic()
        context.user_data["number_last_assigned_ids"] = [int(item["id"]) for item in assigned]
        blocks = [f"{i}. 📱 <b>{html.escape(str(service))}</b> — <code>{html.escape(str(item['number']))}</code>" for i, item in enumerate(assigned, 1)]
        buttons = [[ib(f"📋 {item['number']}", "success", copy_text=CopyTextButton(text=str(item["number"]))) ] for item in assigned]
        buttons.extend([
            [ib("🔄 Change numbers (10s)", "primary", callback_data="number:get:0")],
            [ib("⬅️ Back to countries", "primary", callback_data="number:back:countries")],
            [ib("⬅️ Back to services", "danger", callback_data="number:back:services")],
        ])
        otp_link = (await db.get_setting("otp_channel_link")).strip()
        if otp_link.startswith("https://t.me/"):
            buttons.insert(len(assigned), [ib("📢 OTP Channel", "primary", url=otp_link)])
        await q.message.reply_text("🎉 Assigned numbers: " + str(len(assigned)) + "\n\n" + "\n".join(blocks), reply_markup=InlineKeyboardMarkup(buttons))
        return

    if len(data) >= 2 and data[1] == "get":
        now = time.monotonic()
        last_request = float(context.user_data.get("last_number_request_at", 0))
        wait = 10 - (now - last_request)
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
        assigned = []
        for item in numbers:
            if len(assigned) >= 3:
                break
            if await db.assign_phone_number(int(item["id"]), q.from_user.id):
                assigned.append(item)
        if not assigned:
            await q.message.reply_text(t(lang, "no_numbers"))
            return
        context.user_data["last_number_request_at"] = time.monotonic()
        context.user_data["number_last_assigned_ids"] = [int(item["id"]) for item in assigned]
        blocks = []
        buttons = []
        for index, item in enumerate(assigned, 1):
            blocks.append(
                f"{index}. 📱 <b>{html.escape(str(service))}</b> — 🌍 {html.escape(str(item['country']))}\n"
                f"📞 <code>{html.escape(str(item['number']))}</code>\n"
                f"📩 " + ("Waiting for OTP" if lang == "en" else "منتظر کد تأیید")
            )
            buttons.append([ib(f"📋 {item['number']}", "success", copy_text=CopyTextButton(text=str(item["number"])))])
        message_text = "🎉 Assigned numbers / شماره‌های اختصاص‌یافته: " + str(len(assigned)) + "\n\n" + "\n\n".join(blocks)
        buttons.append([ib("🔄 " + ("Change numbers (10s)" if lang == "en" else "تغییر شماره‌ها (۱۰ ثانیه)"), "primary", callback_data="number:get:0")])
        buttons.extend([
            [ib("⬅️ " + ("Back to countries" if lang == "en" else "برگشت به کشورها"), "primary", callback_data="number:back:countries")],
            [ib("⬅️ " + ("Back to services" if lang == "en" else "برگشت به سرویس‌ها"), "danger", callback_data="number:back:services")],
        ])
        otp_link = (await db.get_setting("otp_channel_link")).strip()
        if otp_link.startswith("https://t.me/"):
            buttons.insert(len(assigned), [ib("📢 " + ("OTP Channel" if lang == "en" else "کانال کدها"), "primary", url=otp_link)])
        await q.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(buttons))
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
        wait = 10 - (now - last_request)
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
