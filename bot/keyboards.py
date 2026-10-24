from __future__ import annotations

import os

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .i18n import LANGUAGE_NAMES, t

# Telegram (Bot API 9.4+) can colour buttons: "primary" = blue, "success" = green,
# "danger" = red. Set BUTTON_STYLES=0 in the environment to switch colours off.
BUTTON_STYLES = os.getenv("BUTTON_STYLES", "1").strip().lower() not in ("0", "false", "no", "off")

CLOSE_CALLBACK = "ui:close"


def _extra(style: str | None) -> dict | None:
    return {"style": style} if (style and BUTTON_STYLES) else None


def kb(text: str, style: str | None = None) -> KeyboardButton:
    """Reply-keyboard button, optionally coloured."""
    return KeyboardButton(text, api_kwargs=_extra(style))


def ib(text: str, style: str | None = None, **kwargs) -> InlineKeyboardButton:
    """Inline button, optionally coloured."""
    return InlineKeyboardButton(text, api_kwargs=_extra(style), **kwargs)


def close_button(lang: str | None = None, label: str | None = None) -> InlineKeyboardButton:
    return ib(f"❌ {label or t(lang, 'close')}", "danger", callback_data=CLOSE_CALLBACK)


def menu_keyboard(lang: str | None, admin: bool) -> ReplyKeyboardMarkup:
    # Main dashboard: blue / green / red buttons in two columns.
    rows = [
        [kb(t(lang, "menu_numbers"), "primary"), kb(t(lang, "menu_search"), "primary")],
        [kb(t(lang, "menu_traffic"), "success"), kb(t(lang, "menu_2fa"), "primary")],
        [kb(t(lang, "menu_refer"), "success"), kb(t(lang, "menu_withdraw"), "danger")],
        [kb(t(lang, "menu_support"), "primary")],
    ]
    if admin:
        rows.append([kb(t(lang, "menu_admin"), "danger")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def wallet_keyboard(lang: str | None) -> ReplyKeyboardMarkup:
    """Keep all Buy Coin actions together, with a clear way back."""
    return ReplyKeyboardMarkup(
        [
            [kb(t(lang, "menu_send_points"), "primary")],
            [kb(t(lang, "menu_invite"), "success")],
            [kb(t(lang, "menu_daily_points"), "success")],
            [kb(t(lang, "menu_wallet_back"), "danger")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def refer_keyboard(lang: str | None, link: str) -> InlineKeyboardMarkup:
    """Refer & Earn card: copy-link (green) and close (red)."""
    return InlineKeyboardMarkup(
        [
            [ib(f"📋 {t(lang, 'copy_link')}", "success", copy_text=CopyTextButton(text=link))],
            [close_button(lang, t(lang, "close"))],
        ]
    )


def language_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """prefix is 'setlang' (first run) or 'lang' (change later)."""
    return InlineKeyboardMarkup(
        [[ib(name, "primary", callback_data=f"{prefix}:{code}") for code, name in LANGUAGE_NAMES.items()]]
    )


def join_keyboard(lang: str | None, channels: list[dict], bilingual: bool = False) -> InlineKeyboardMarkup:
    rows = [[ib(f"📢 {c['title']}", "primary", url=c["link"])] for c in channels if c.get("link")]
    label = f"{t('en', 'verify')} / {t('dr', 'verify')}" if bilingual else t(lang, "verify")
    rows.append([ib(label, "success", callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)


def url_keyboard(lang: str | None, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[ib(t(lang, "open_link"), "primary", url=url)]])


# ---------------- bilingual admin panel ----------------
# Button colours by callback: green = positive, red = destructive / closing, blue = everything else.
_ADMIN_STYLES = {
    "adm:stats": "success",
    "adm:unban": "success",
    "adm:bc_yes": "success",
    "adm:ban": "danger",
    "adm:bc_no": "danger",
    "adm:maint": "danger",
    "adm:close": "danger",
}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return ib(text, _ADMIN_STYLES.get(data, "primary"), callback_data=data)


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
