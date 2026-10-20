from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)

from .i18n import LANGUAGE_NAMES, t


def menu_keyboard(lang: str | None, admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [t(lang, "menu_profile"), t(lang, "menu_invite")],
        [t(lang, "menu_support"), t(lang, "menu_about")],
        [t(lang, "menu_language"), t(lang, "menu_numbers")],
        [t(lang, "menu_points"), t(lang, "menu_send_points")],
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
    label = t("en", "verify") if not bilingual else f"{t('en', 'verify')} / {t('dr', 'verify')}"
    rows.append([InlineKeyboardButton(t(lang, "verify") if not bilingual else label, callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)


def url_keyboard(lang: str | None, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "open_link"), url=url)]])


# ---------------- admin ----------------
def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def admin_panel_keyboard(maintenance: bool, is_owner: bool) -> InlineKeyboardMarkup:
    rows = [
        [_btn("📊 Stats", "adm:stats"), _btn("📣 Broadcast", "adm:broadcast")],
        [_btn("🔎 User info", "adm:user_info")],
        [_btn("🚫 Ban user", "adm:ban"), _btn("✅ Unban user", "adm:unban")],
        [_btn("📢 Force-join channels", "adm:channels")],
        [_btn("📱 Manage numbers", "adm:num_stock")],
    ]
    if is_owner:
        rows.append([_btn("🔑 API keys", "adm:api_keys"), _btn("⭐ Points", "adm:points")])
        rows.append([_btn("👮 Admins", "adm:admins")])
    rows.append([_btn(f"🛠 Maintenance: {'ON 🔴' if maintenance else 'OFF 🟢'}", "adm:maint")])
    rows.append([_btn("🔗 Support link", "adm:support"), _btn("🔗 Official link", "adm:official")])
    rows.append([_btn("✖️ Close", "adm:close")])
    return InlineKeyboardMarkup(rows)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("⬅️ Admin panel", "adm:home")]])


def confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_btn("✅ Send to everyone", "adm:bc_yes"), _btn("❌ Cancel", "adm:bc_no")]]
    )
