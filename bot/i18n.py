"""User-facing strings. Add a new language by adding another dict to STRINGS."""
from __future__ import annotations

DEFAULT_LANG = "en"

LANGUAGE_NAMES = {"en": "🇺🇸 English", "dr": "🇦🇫 دری"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "choose_lang": "Please choose your language:",
        "lang_changed": "✅ Language updated.",
        "welcome": "Welcome, <b>{name}</b>! 👋\nChoose an option from the menu below.",
        "menu_profile": "👤 Profile",
        "menu_invite": "🎁 Invite friends",
        "menu_support": "💬 Support",
        "menu_about": "📢 Official channel",
        "menu_language": "🌐 Language",
        "menu_numbers": "📱 Get number",
        "menu_admin": "⚙️ Admin panel",
        "profile": (
            "👤 <b>Your profile</b>\n\n"
            "🆔 ID: <code>{uid}</code>\n"
            "🏷 Name: {name}\n"
            "🌐 Username: {username}\n"
            "🗣 Language: {language}\n"
            "👥 Friends invited: <b>{referrals}</b>\n"
            "📅 Joined: {joined}"
        ),
        "invite": "🎁 <b>Invite friends</b>\n\nShare your personal link:\n{link}\n\nFriends invited so far: <b>{referrals}</b>",
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
        "number_added": "Number added to your session:\nService: <b>{service}</b>\nCountry: <b>{country}</b>\nNumber: <code>{number}</code>\n\nWaiting for the OTP from the provider. It will be sent here when received.",
    },
    "dr": {
        "choose_lang": "لطفاً زبان خود را انتخاب کنید:",
        "lang_changed": "✅ زبان تغییر کرد.",
        "welcome": "خوش آمدید، <b>{name}</b>! 👋\nیکی از گزینه‌های منو را انتخاب کنید.",
        "menu_profile": "👤 پروفایل",
        "menu_invite": "🎁 دعوت دوستان",
        "menu_support": "💬 پشتیبانی",
        "menu_about": "📢 کانال رسمی",
        "menu_language": "🌐 زبان",
        "menu_numbers": "📱 دریافت شماره",
        "menu_admin": "⚙️ پنل مدیریت",
        "profile": (
            "👤 <b>پروفایل شما</b>\n\n"
            "🆔 آی‌دی: <code>{uid}</code>\n"
            "🏷 نام: {name}\n"
            "🌐 نام کاربری: {username}\n"
            "🗣 زبان: {language}\n"
            "👥 دوستان دعوت‌شده: <b>{referrals}</b>\n"
            "📅 تاریخ عضویت: {joined}"
        ),
        "invite": "🎁 <b>دعوت دوستان</b>\n\nلینک اختصاصی شما:\n{link}\n\nتعداد دوستان دعوت‌شده: <b>{referrals}</b>",
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
        "number_added": "شماره برای شما ثبت شد:\nسرویس: <b>{service}</b>\nکشور: <b>{country}</b>\nشماره: <code>{number}</code>\n\nمنتظر کد تأیید از ارائه‌دهنده باشید؛ پس از دریافت، همین‌جا فرستاده می‌شود.",
    },
}

MENU_KEYS = (
    "menu_profile",
    "menu_invite",
    "menu_support",
    "menu_about",
    "menu_language",
    "menu_numbers",
    "menu_admin",
)

# Button text (in any language) -> menu key. Used to route reply-keyboard presses.
MENU_LOOKUP: dict[str, str] = {
    STRINGS[lang][key]: key for lang in STRINGS for key in MENU_KEYS
}


def norm_lang(lang: str | None) -> str:
    return lang if lang in STRINGS else DEFAULT_LANG


def t(lang: str | None, key: str, **kwargs) -> str:
    text = STRINGS[norm_lang(lang)].get(key) or STRINGS[DEFAULT_LANG][key]
    return text.format(**kwargs) if kwargs else text


def t_all(key: str, **kwargs) -> str:
    """The same string in every language (used before a language is chosen)."""
    return "\n\n".join(t(lang, key, **kwargs) for lang in STRINGS)
