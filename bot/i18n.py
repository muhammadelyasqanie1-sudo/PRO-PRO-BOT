"""User-facing strings. Add a new language by adding another dict to STRINGS."""
from __future__ import annotations

DEFAULT_LANG = "en"

LANGUAGE_NAMES = {"en": "🇺🇸 English", "dr": "🇦🇫 دری"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "choose_lang": "Please choose your language:",
        "lang_changed": "✅ Language updated.",
        "welcome": "┏━━━━━━━━━━━━━━┓\n      📊 <b>NUMBER BOT</b>\n┗━━━━━━━━━━━━━━┛\n🚀 Welcome to Number &amp; OTP Service\n──────────────\n✅ Choose an option below\nto continue using the bot.\n──────────────\n💎 Premium OTP Service",
        "menu_profile": "👤 Profile",
        "menu_invite": "🎁 Invite friends",
        "menu_support": "❓ Help",
        "menu_about": "📢 Official channel",
        "menu_language": "🌐 Language",
        "menu_numbers": "📲 Get Number",
        "menu_sessions": "📋 My History",
        "menu_points": "🪙 Buy Coin",
        "menu_wallet_back": "⬅️ Main menu",
        "wallet_back_message": "🏠 You are back at the main menu.",
        "daily_claim_success": "🎉 Daily reward claimed! +15 Buy Coin. Your balance: <b>{balance}</b>",
        "daily_claim_used": "⏳ You have already claimed today's reward. Balance: <b>{balance}</b>",
        "menu_send_points": "🔁 Transfer Buy Coin",
        "menu_daily_points": "🎁 Daily Buy Coin",
        "menu_admin": "Admin Panel",
        "menu_search": "Search Number",
        "menu_traffic": "TRAFFIC",
        "menu_2fa": "🧪 Wu Checker",
        "menu_refer": "Refer",
        "menu_withdraw": "💸 Withdraw",
        "refer_card": "━━━━━━━━━━━━━━━━━━\n« 🎁 <b>REFER &amp; EARN</b> »\n━━━━━━━━━━━━━━━━━━\n🔗 <b>YOUR LINK:</b>\n<code>{link}</code>\n━━━━━━━━━━━━━━━━━━\n👤 <b>TOTAL REFERS:</b> {referrals}\n━━━━━━━━━━━━━━━━━━\n💎 <b>PER REFER:</b> {per} Buy Coin\n━━━━━━━━━━━━━━━━━━",
        "copy_link": "COPY LINK",
        "close": "CLOSE",
        "traffic_title": "📊 <b>TRAFFIC</b>\n━━━━━━━━━━━━━━━━━━",
        "traffic_footer": "━━━━━━━━━━━━━━━━━━\n📦 Total available: <b>{total}</b>",
        "twofa_soon": "🔐 <b>2FA ONLINE</b>\n━━━━━━━━━━━━━━━━━━\n⏳ This feature is coming soon.",
        "withdraw_note": "💸 <b>WITHDRAWAL</b>\nWithdrawals are not enabled yet. Buy Coin are in-bot points for now.",
        "profile": (
            "👤 <b>Your profile</b>\n\n"
            "🆔 ID: <code>{uid}</code>\n"
            "🏷 Name: {name}\n"
            "🌐 Username: {username}\n"
            "🗣 Language: {language}\n"
            "👥 Friends invited: <b>{referrals}</b>\n"
            "⭐ Points: <b>{points}</b>\n"
            "📅 Joined: {joined}"
        ),
        "invite": "🎁 <b>Invite friends</b>\n\nShare your personal link:\n{link}\n\nFriends invited: <b>{referrals}</b>\n⭐ Points earned: <b>{points}</b> (10 points per valid invite)",
        "points": "🪙 <b>Buy Coin wallet</b>\n\nBalance: <b>{points}</b> points.\nYou earn 10 points for each valid new user invited.",
        "send_points_prompt": "🔁 <b>Transfer Buy Coin</b>\n\nSend the recipient Telegram ID:",
        "send_points_amount": "Recipient: <code>{uid}</code>\nYour Buy Coin balance: <b>{points}</b>\n\nNow send the whole number of points to transfer, or /cancel.",
        "send_points_success": "✅ Transferred <b>{amount}</b> Buy Coin to <code>{uid}</code>.",
        "send_points_failed": "❌ Transfer failed. Check the recipient ID and your balance, then try again.",
        "new_referral": "🎉 <b>{name}</b> joined using your invite link!",
        "support": "💬 Need help? Tap the button below to contact support.",
        "about": "📢 Follow our official channel for news and updates.",
        "open_link": "Open",
        "not_configured": "This section is not configured yet.",
        "join_required": "To use this bot, please join the channel(s) below, then press <b>Verify</b>.",
        "verify": "✅ Verify",
        "verify_failed": "❌ You have not joined all required channels yet.",
        "verify_ok": "✅ Verified. Thank you!",
        "banned": "🚫 You are not allowed to use this bot.",
        "maintenance": "🛠 The bot is under maintenance. Please try again later.",
        "help": "Use the menu buttons below. Send /start to show the menu again.",
        "unknown": "Please use the menu buttons below.",
        "cancelled": "Cancelled.",
        "no_numbers": "No numbers are available right now. Please try again later.",
        "choose_number_service": "📍 Select a service:",
        "choose_number_country": "🌍 Service: <b>{service}</b>\nChoose a country:",
        "confirm_get_number": "🌍 Country: <b>{country}</b>\nPress the button below to get up to two numbers.",
        "get_number_button": "📲 Get number",
        "number_cooldown": "⏳ Please wait {seconds} second(s) before requesting another number.",
        "number_added": "Number added to your session:\nService: <b>{service}</b>\nCountry: <b>{country}</b>\nNumber: <code>{number}</code>\n\nWaiting for the OTP from the provider. It will be sent here when received.",
        "sessions_title": "📋 <b>Your numbers & recent OTPs</b>",
        "sessions_empty": "You have no assigned numbers yet. Choose GET NUMBER to start.",
        "session_item": "📱 <b>{service}</b> · {country}\nNumber: <code>{number}</code>\nAssigned: {created}\n{otp_line}",
    },
    "dr": {
        "choose_lang": "لطفاً زبان خود را انتخاب کنید:",
        "lang_changed": "✅ زبان تغییر کرد.",
        "welcome": "┏━━━━━━━━━━━━━━┓\n      📊 <b>NUMBER BOT</b>\n┗━━━━━━━━━━━━━━┛\n🚀 به سرویس شماره و OTP خوش آمدید\n──────────────\n✅ برای ادامه، یکی از گزینه‌های\nزیر را انتخاب کنید.\n──────────────\n💎 سرویس پریمیوم OTP",
        "menu_profile": "👤 پروفایل",
        "menu_invite": "🎁 دعوت دوستان",
        "menu_support": "❓ راهنما",
        "menu_about": "📢 کانال رسمی",
        "menu_language": "🌐 زبان",
        "menu_numbers": "📲 دریافت شماره",
        "menu_sessions": "📋 تاریخچهٔ من",
        "menu_points": "🪙 بای‌کوین",
        "menu_wallet_back": "⬅️ منوی اصلی",
        "wallet_back_message": "🏠 به منوی اصلی برگشتید.",
        "daily_claim_success": "🎉 پاداش روزانه دریافت شد! ۱۵ بای‌کوین اضافه شد. موجودی شما: <b>{balance}</b>",
        "daily_claim_used": "⏳ پاداش امروز را قبلاً دریافت کرده‌اید. موجودی: <b>{balance}</b>",
        "menu_send_points": "🔁 انتقال بای‌کوین",
        "menu_daily_points": "🎁 بای‌کوین روزانه",
        "menu_admin": "Admin Panel",
        "menu_search": "Search Number",
        "menu_traffic": "TRAFFIC",
        "menu_2fa": "🧪 بررسی Wu",
        "menu_refer": "Refer",
        "menu_withdraw": "💸 برداشت",
        "refer_card": "━━━━━━━━━━━━━━━━━━\n« 🎁 <b>دعوت و درآمد</b> »\n━━━━━━━━━━━━━━━━━━\n🔗 <b>لینک شما:</b>\n<code>{link}</code>\n━━━━━━━━━━━━━━━━━━\n👤 <b>مجموع دعوت‌ها:</b> {referrals}\n━━━━━━━━━━━━━━━━━━\n💎 <b>هر دعوت:</b> {per} بای‌کوین\n━━━━━━━━━━━━━━━━━━",
        "copy_link": "کاپی لینک",
        "close": "بستن",
        "traffic_title": "📊 <b>ترافیک</b>\n━━━━━━━━━━━━━━━━━━",
        "traffic_footer": "━━━━━━━━━━━━━━━━━━\n📦 مجموع موجود: <b>{total}</b>",
        "twofa_soon": "🔐 <b>2FA ONLINE</b>\n━━━━━━━━━━━━━━━━━━\n⏳ این بخش به‌زودی فعال می‌شود.",
        "withdraw_note": "💸 <b>برداشت</b>\nبرداشت هنوز فعال نیست. فعلاً بای‌کوین امتیاز داخل ربات است.",
        "profile": (
            "👤 <b>پروفایل شما</b>\n\n"
            "🆔 آی‌دی: <code>{uid}</code>\n"
            "🏷 نام: {name}\n"
            "🌐 نام کاربری: {username}\n"
            "🗣 زبان: {language}\n"
            "👥 دوستان دعوت‌شده: <b>{referrals}</b>\n"
            "⭐ امتیازها: <b>{points}</b>\n"
            "📅 تاریخ عضویت: {joined}"
        ),
        "invite": "🎁 <b>دعوت دوستان</b>\n\nلینک اختصاصی شما:\n{link}\n\nدوستان دعوت‌شده: <b>{referrals}</b>\n⭐ امتیاز کسب‌شده: <b>{points}</b> (برای هر دعوت معتبر ۱۰ امتیاز)",
        "points": "🪙 <b>کیف پول بای‌کوین (Buy Coin)</b>\n\nموجودی: <b>{points}</b> امتیاز.\nبرای هر کاربر جدیدی که با لینک شما عضو شود، ۱۰ امتیاز می‌گیرید.",
        "send_points_prompt": "🔁 <b>انتقال بای‌کوین</b>\n\nآی‌دی عددی تلگرام گیرنده را بفرستید:",
        "send_points_amount": "گیرنده: <code>{uid}</code>\nموجودی بای‌کوین شما: <b>{points}</b>\n\nحالا تعداد امتیاز صحیح را بفرستید، یا /cancel.",
        "send_points_success": "✅ تعداد <b>{amount}</b> بای‌کوین به <code>{uid}</code> انتقال یافت.",
        "send_points_failed": "❌ انتقال انجام نشد. آی‌دی گیرنده و موجودی خود را بررسی کنید.",
        "new_referral": "🎉 <b>{name}</b> با لینک دعوت شما عضو شد!",
        "support": "💬 به کمک نیاز دارید؟ روی دکمهٔ زیر بزنید تا با پشتیبانی در ارتباط باشید.",
        "about": "📢 برای دریافت اخبار و اطلاعیه‌ها کانال رسمی ما را دنبال کنید.",
        "open_link": "باز کردن",
        "not_configured": "این بخش هنوز تنظیم نشده است.",
        "join_required": "برای استفاده از ربات، لطفاً در کانال(های) زیر عضو شوید و سپس <b>تأیید</b> را بزنید.",
        "verify": "✅ تأیید عضویت",
        "verify_failed": "❌ هنوز در همهٔ کانال‌های لازم عضو نشده‌اید.",
        "verify_ok": "✅ تأیید شد. متشکریم!",
        "banned": "🚫 شما اجازهٔ استفاده از این ربات را ندارید.",
        "maintenance": "🛠 ربات در حال بروزرسانی است. لطفاً بعداً دوباره تلاش کنید.",
        "help": "از دکمه‌های منوی پایین استفاده کنید. برای نمایش دوبارهٔ منو /start را بفرستید.",
        "unknown": "لطفاً از دکمه‌های منوی پایین استفاده کنید.",
        "cancelled": "لغو شد.",
        "no_numbers": "فعلاً شماره‌ای موجود نیست. لطفاً بعداً دوباره تلاش کنید.",
        "choose_number_service": "📍 یک سرویس را انتخاب کنید:",
        "choose_number_country": "🌍 سرویس: <b>{service}</b>\nکشور را انتخاب کنید:",
        "confirm_get_number": "🌍 کشور: <b>{country}</b>\nبرای دریافت تا دو شماره، دکمهٔ زیر را بزنید.",
        "get_number_button": "📲 دریافت شماره",
        "number_cooldown": "⏳ لطفاً برای درخواست شمارهٔ بعدی {seconds} ثانیه صبر کنید.",
        "number_added": "شماره برای شما ثبت شد:\nسرویس: <b>{service}</b>\nکشور: <b>{country}</b>\nشماره: <code>{number}</code>\n\nمنتظر کد تأیید از ارائه‌دهنده باشید؛ پس از دریافت، همین‌جا فرستاده می‌شود.",
        "sessions_title": "📋 <b>شماره‌های شما و کدهای تأیید اخیر</b>",
        "sessions_empty": "هنوز شماره‌ای به شما اختصاص نیافته است. برای شروع روی GET NUMBER بزنید.",
        "session_item": "📱 <b>{service}</b> · {country}\nشماره: <code>{number}</code>\nتاریخ دریافت: {created}\n{otp_line}",
    },
}

MENU_KEYS = (
    "menu_profile",
    "menu_invite",
    "menu_support",
    "menu_about",
    "menu_language",
    "menu_numbers",
    "menu_sessions",
    "menu_points",
    "menu_wallet_back",
    "menu_send_points",
    "menu_daily_points",
    "menu_admin",
    "menu_search",
    "menu_traffic",
    "menu_2fa",
    "menu_refer",
    "menu_withdraw",
)

# Button text (in any language) -> menu key. Used to route reply-keyboard presses.
MENU_LOOKUP: dict[str, str] = {
    STRINGS[lang][key]: key for lang in STRINGS for key in MENU_KEYS
}

def apply_button_customizations(value: dict) -> None:
    """Apply persisted button labels and keep reply-keyboard routing synchronized."""
    for key, item in (value or {}).items():
        if key not in MENU_KEYS or not isinstance(item, dict):
            continue
        if item.get("en"):
            STRINGS["en"][key] = str(item["en"])[:50]
        if item.get("dr"):
            STRINGS["dr"][key] = str(item["dr"])[:50]
    MENU_LOOKUP.clear()
    MENU_LOOKUP.update({STRINGS[lang][key]: key for lang in STRINGS for key in MENU_KEYS})


def norm_lang(lang: str | None) -> str:
    return lang if lang in STRINGS else DEFAULT_LANG


def t(lang: str | None, key: str, **kwargs) -> str:
    text = STRINGS[norm_lang(lang)].get(key) or STRINGS[DEFAULT_LANG][key]
    return text.format(**kwargs) if kwargs else text


def t_all(key: str, **kwargs) -> str:
    """The same string in every language (used before a language is chosen)."""
    return "\n\n".join(t(lang, key, **kwargs) for lang in STRINGS)
