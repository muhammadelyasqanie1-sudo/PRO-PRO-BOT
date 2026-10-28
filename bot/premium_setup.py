"""Plugs the premium-emoji system into the existing bot without touching its other modules.

install() must run before build_application(): it
  * gives menu buttons a leading emoji (so they can become animated button icons) and keeps
    routing working for both the labelled and the icon-only text,
  * adds the "Premium Emoji" button to the owner's admin panel,
  * makes the bot object a PremiumBot (animated emoji in all outgoing messages),
  * fills the animated-emoji map automatically from Telegram's official animated emoji, and
  * registers the Premium Emoji admin handlers.
"""
from __future__ import annotations

from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ExtBot,
    MessageHandler,
    filters,
)

from . import emoji as pe
from . import i18n, keyboards
from .handlers import admin as admin_handlers
from .handlers import emoji_admin

# menu key -> label with a leading emoji (same wording as before, only an emoji is added)
_LABELS = {
    "menu_support": "\U0001F4AC SUPPORT",
    "menu_numbers": "\U0001F4F2 GET NUMBER",
    "menu_admin": "\U0001F6E0 Admin Panel",
    "menu_search": "\U0001F50E Search Number",
    "menu_traffic": "\U0001F4CA TRAFFIC",
    "menu_2fa": "\U0001F510 2FA ONLINE",
    "menu_withdraw": "\U0001F4B8 WITHDRAWAL",
}


def _style_menu() -> None:
    for lang, strings in i18n.STRINGS.items():
        for key, label in _LABELS.items():
            old = strings.get(key)
            if not old or pe.strip_leading_emoji(old) != old:  # missing, or already has an emoji: keep
                continue
            strings[key] = label
            i18n.MENU_LOOKUP[label] = key  # labelled text
            i18n.MENU_LOOKUP.setdefault(old, key)  # old/bare text (what an icon-only button sends back)
    # any other label: also accept it without its leading emoji
    for label, key in list(i18n.MENU_LOOKUP.items()):
        bare = pe.strip_leading_emoji(label)
        if bare:
            i18n.MENU_LOOKUP.setdefault(bare, key)


def _wrap_admin_keyboard() -> None:
    original = keyboards.admin_panel_keyboard

    def admin_panel_keyboard(maintenance: bool, is_owner: bool):
        markup = original(maintenance, is_owner)
        if not is_owner:
            return markup
        rows = [list(r) for r in markup.inline_keyboard]
        rows.insert(max(0, len(rows) - 3), [keyboards._btn("\U0001F3AD Premium Emoji", "adm:pe")])
        return type(markup)(rows)

    keyboards.admin_panel_keyboard = admin_panel_keyboard
    admin_handlers.admin_panel_keyboard = admin_panel_keyboard


async def autoseed(bot, db) -> int:
    """Fill the emoji map automatically from Telegram's official animated emoji.

    Uses getForumTopicIconStickers (official custom emoji, available to every bot, no pack names
    needed) plus any packs listed in the `premium_emoji_packs` setting (comma separated).
    Emoji the admin already saved are never overwritten. Returns how many were added.
    """
    added = 0
    stickers = []
    try:
        stickers += list(await bot.get_forum_topic_icon_stickers())
    except Exception as exc:  # noqa: BLE001 - best effort
        emoji_admin.log.warning("Could not load official animated emoji: %s", exc)
    for name in [p.strip() for p in (await db.get_setting("premium_emoji_packs", "")).split(",") if p.strip()]:
        try:
            stickers += list((await bot.get_sticker_set(name)).stickers)
        except Exception as exc:  # noqa: BLE001
            emoji_admin.log.warning("Could not load emoji pack %s: %s", name, exc)
    for st in stickers:
        if st.custom_emoji_id and st.emoji:
            key = pe.norm(st.emoji)
            if key not in pe.REGISTRY.map:
                pe.REGISTRY.map[key] = st.custom_emoji_id
                added += 1
    if added:
        await db.set_setting(pe.SETTING_MAP, pe.REGISTRY.dump())
    return added


async def _pe_callback(update, context) -> None:
    q = update.callback_query
    if (q.data or "") == "adm:pe_auto":
        from .utils import get_db, is_admin

        if not await is_admin(context, q.from_user.id):
            await q.answer("Not authorized.", show_alert=True)
        else:
            added = await autoseed(context.bot, get_db(context))
            await q.answer(f"Added {added} animated emoji. Total: {len(pe.REGISTRY.map)}", show_alert=True)
            await emoji_admin._edit(q, emoji_admin._home_text(), emoji_admin._home_markup())
    else:
        await emoji_admin.on_callback(update, context)
    raise ApplicationHandlerStop  # never let the generic admin callback handle it again


def _wrap_pe_home() -> None:
    original = emoji_admin._home_markup

    def home_markup():
        markup = original()
        rows = [list(r) for r in markup.inline_keyboard]
        rows.insert(0, [keyboards._btn("\U0001FA84 Auto-fill official animated emoji", "adm:pe_auto")])
        return type(markup)(rows)

    emoji_admin._home_markup = home_markup


async def _pe_message(update, context) -> None:
    state = context.user_data.get("state")
    if state not in emoji_admin.STATES:
        return
    from .utils import is_admin

    if await is_admin(context, update.effective_user.id):
        await emoji_admin.handle_state(update, context, state)
        raise ApplicationHandlerStop
    context.user_data.pop("state", None)


def install_on(app) -> None:
    """Call on the built Application."""
    if not isinstance(app.bot, pe.PremiumBot):
        app.bot.__class__ = pe.PremiumBot  # same constructor/layout as ExtBot, only _do_post differs
    # group -2 runs before everything else; handlers only act on their own callbacks/states.
    app.add_handler(CallbackQueryHandler(_pe_callback, pattern=r"^adm:pe(_|$)"), group=-2)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, _pe_message), group=-2)


def install() -> None:
    """Patch menu labels / admin keyboard and wrap build_application. Idempotent."""
    from . import app as app_module

    if getattr(app_module, "_premium_installed", False):
        return
    _style_menu()
    _wrap_admin_keyboard()
    _wrap_pe_home()
    original_build = app_module.build_application

    def build_application(settings):
        app = original_build(settings)
        install_on(app)
        return app

    app_module.build_application = build_application
    original_post_init = app_module._post_init

    async def post_init(app):
        await original_post_init(app)
        db = app.bot_data["db"]
        await pe.reload(db)
        if await db.get_setting("premium_emoji_auto", "1") == "1":
            try:
                n = await autoseed(app.bot, db)
                emoji_admin.log.info("Premium emoji: %s auto-added, %s total", n, len(pe.REGISTRY.map))
            except Exception:  # noqa: BLE001
                emoji_admin.log.exception("Premium emoji auto-fill failed")

    app_module._post_init = post_init
    app_module._premium_installed = True
