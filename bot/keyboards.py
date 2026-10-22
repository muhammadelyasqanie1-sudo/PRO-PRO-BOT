from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from .i18n import LANGUAGE_NAMES, t


def menu_keyboard(lang: str | None, admin: bool) -> ReplyKeyboardMarkup:
    # Compact premium dashboard: paired actions, clear visual grouping, consistent emoji.
    rows = [
        [t(lang, "menu_numbers"), t(lang, "menu_profile")],
        [t(lang, "menu_points"), t(lang, "menu_send_points")],
        [t(lang, "menu_daily_points"), t(lang, "menu_invite")],
        [t(lang, "menu_support"), t(lang, "menu_about")],
        [t(lang, "menu_language")],
    ]
    if admin:
        rows.append([t(lang, "menu_admin")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def language_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """prefix is 'setlang' (first run) or 'lang' (change later)."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(name, callback_data=f"{prefix}:{code}") for code, name in LANGUAGE_NAMES.items()]]
    )


def join_keyboard(lang: str | None, channels: list[dict], bilingual: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📢 {c['title']}", url=c["link"])] for c in channels if c.get("link")]
    label = f"{t('en', 'verify')} / {t('dr', 'verify')}" if bilingual else t(lang, "verify")
    rows.append([InlineKeyboardButton(label, callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)


def url_keyboard(lang: str | None, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "open_link"), url=url)]])


# ---------------- bilingual admin panel ----------------
def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def admin_panel_keyboard(maintenance: bool, is_owner: bool) -> InlineKeyboardMarkup:
    # English / Dari labels are shown together so admins can operate the panel
    # regardless of the language selected for their public bot account.
    rows = [
        [_btn("📊 Stats / آمار", "adm:stats"), _btn("📣 Broadcast / پیام همگانی", "adm:broadcast")],
        [_btn("🔎 User info / معلومات کاربر", "adm:user_info")],
        [_btn("🚫 Ban / مسدود", "adm:ban"), _btn("✅ Unban / رفع مسدودی", "adm:unban")],
        [_btn("📢 Force join / عضویت اجباری", "adm:channels")],
        [_btn("📱 Manage numbers / مدیریت شماره‌ها", "adm:num_stock")],
        [_btn("🧩 Services / سرویس‌ها", "adm:services"), _btn("🌍 Countries / کشورها", "adm:countries")],
        [_btn("📥 Provider review / بررسی شماره‌ها", "adm:provider_pending")],
    ]
    if is_owner:
        rows.append([_btn("🔑 API keys / کلیدهای API", "adm:api_keys"), _btn("⭐ Points / امتیازها", "adm:points")])
        rows.append([_btn("📝 OTP message / متن OTP", "adm:otp_template"), _btn("🔘 OTP buttons / دکمه‌های OTP", "adm:otp_buttons")])
        rows.append([_btn("👮 Admins / مدیران", "adm:admins")])
        rows.append([_btn("📝 OTP settings / تنظیمات OTP", "adm:otp_settings")])
    rows.append([_btn(f"🛠 Maintenance / حالت تعمیر: {'ON 🔴' if maintenance else 'OFF 🟢'}", "adm:maint")])
    rows.append([_btn("🔗 Support / پشتیبانی", "adm:support"), _btn("🔗 Official channel / کانال رسمی", "adm:official")])
    rows.append([_btn("✖️ Close / بستن", "adm:close")])
    return InlineKeyboardMarkup(rows)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("⬅️ Admin panel / پنل مدیریت", "adm:home")]])


def confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_btn("✅ Send / ارسال", "adm:bc_yes"), _btn("❌ Cancel / لغو", "adm:bc_no")]]
    )
