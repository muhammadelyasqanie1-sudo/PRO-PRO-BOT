from __future__ import annotations

import os

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .i18n import LANGUAGE_NAMES, t

# Telegram (Bot API 9.4+) can colour buttons: "primary" = blue, "success" = green,
# "danger" = red. Set BUTTON_STYLES=0 in the environment to switch colours off.
BUTTON_STYLES = os.getenv("BUTTON_STYLES", "1").strip().lower() not in ("0", "false", "no", "off")

CLOSE_CALLBACK = "ui:close"
BUTTON_CUSTOMIZATIONS: dict[str, dict] = {}

def set_button_customizations(value: dict) -> None:
    global BUTTON_CUSTOMIZATIONS
    BUTTON_CUSTOMIZATIONS = value if isinstance(value, dict) else {}

def _custom_button(key: str, lang: str | None, fallback: str, style: str | None = None) -> KeyboardButton:
    item = BUTTON_CUSTOMIZATIONS.get(key, {})
    label = item.get("dr" if lang == "dr" else "en") or fallback
    extra = _extra(style) or {}
    emoji_id = str(item.get("emoji_id", "")).strip()
    if emoji_id.isdigit():
        extra["icon_custom_emoji_id"] = emoji_id
    return KeyboardButton(label, api_kwargs=extra or None)


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
    # Compact green dashboard inspired by the supplied bot reference:
    # the main number action is prominent, with history and related tools grouped below.
    rows = [
        [_custom_button("menu_numbers", lang, t(lang, "menu_numbers"), "success")],
        [_custom_button("menu_sessions", lang, t(lang, "menu_sessions"), "success")],
        [_custom_button("menu_withdraw", lang, t(lang, "menu_withdraw"), "success"), _custom_button("menu_2fa", lang, t(lang, "menu_2fa"), "success")],
        [_custom_button("menu_points", lang, t(lang, "menu_points"), "success"), _custom_button("menu_invite", lang, t(lang, "menu_invite"), "success")],
        [_custom_button("menu_language", lang, t(lang, "menu_language"), "success"), _custom_button("menu_support", lang, t(lang, "menu_support"), "success")],
        [_custom_button("menu_about", lang, t(lang, "menu_about"), "primary")],
    ]
    if admin:
        rows.append([_custom_button("menu_admin", lang, t(lang, "menu_admin"), "danger")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


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
        [_btn("📊 Stats", "adm:stats"), _btn("📣 Broadcast", "adm:broadcast")],
        [_btn("🔎 User info", "adm:user_info"), _btn("📢 Force join", "adm:channels")],
        [_btn("🚫 Ban", "adm:ban"), _btn("✅ Unban", "adm:unban")],
        [_btn("📱 Numbers", "adm:num_stock"), _btn("🧩 Services", "adm:services")],
        [_btn("🌍 Countries", "adm:countries"), _btn("📥 Provider review", "adm:provider_pending")],
    ]
    if is_owner:
        rows.append([_btn("🔑 API keys", "adm:api_keys"), _btn("⭐ Buy Coin", "adm:points")])
        rows.append([_btn("🎨 Button text & emoji", "adm:button_custom")])
        rows.append([_btn("📝 OTP message", "adm:otp_template"), _btn("🔘 OTP buttons", "adm:otp_buttons")])
        rows.append([_btn("👮 Admins", "adm:admins"), _btn("📝 OTP settings", "adm:otp_settings")])
    rows.append([_btn(f"🛠 Maintenance: {'ON 🔴' if maintenance else 'OFF 🟢'}", "adm:maint")])
    rows.append([_btn("🔗 Support", "adm:support"), _btn("📢 Official channel", "adm:official")])
    rows.append([_btn("✖️ Close", "adm:close")])
    return InlineKeyboardMarkup(rows)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("⬅️ Admin panel / پنل مدیریت", "adm:home")]])


def confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_btn("✅ Send / ارسال", "adm:bc_yes"), _btn("❌ Cancel / لغو", "adm:bc_no")]]
    )
