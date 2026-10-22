from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    TypeHandler,
    filters,
)

from .config import Settings, load_settings
from .db import Database
from .guards import guard
from .handlers import admin, router, user
from .otp_api import poll_augestel
from .miniapp import start_web_server

log = logging.getLogger("bot")


async def _post_init(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    db = Database(settings.db_path)
    await db.connect()
    app.bot_data["db"] = db
    await db.ensure_owner_points(settings.owner_id, 100000)
    await app.bot.set_my_commands(
        [BotCommand("start", "Start / menu"), BotCommand("app", "Open Mini App"), BotCommand("help", "Help"), BotCommand("cancel", "Cancel current action")]
    )
    me = await app.bot.get_me()
    log.info("Started as @%s (db: %s)", me.username, settings.db_path)
    # Poller checks managed API keys from the admin panel and optional env fallback.
    app.create_task(poll_augestel(app), name="augestel-otp-poller")
    # The Mini App and Telegram bot share the same database and process.
    app.bot_data["miniapp_runner"] = await start_web_server(app)


async def _post_shutdown(app: Application) -> None:
    runner = app.bot_data.get("miniapp_runner")
    if runner:
        await runner.cleanup()
    db: Database | None = app.bot_data.get("db")
    if db:
        await db.close()


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error while processing an update", exc_info=context.error)


async def open_mini_app(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Offer the Mini App button when a public HTTPS URL has been configured."""
    import os
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    url = os.getenv("MINI_APP_URL", "").strip()
    if not url:
        domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if domain:
            url = domain if domain.startswith("https://") else f"https://{domain}"
    if not url.startswith("https://"):
        await update.effective_message.reply_text(
            "Mini App is not configured yet. Set MINI_APP_URL to this Railway service's public HTTPS URL."
        )
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Open NUM BOT Mini App / باز کردن مینی‌اپ", web_app=WebAppInfo(url=url.rstrip("/") + "/"))
    ]])
    await update.effective_message.reply_text(
        "Open your premium number workspace / فضای مدیریت شماره‌های خود را باز کنید:",
        reply_markup=keyboard,
    )


def build_application(settings: Settings) -> Application:
    app = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings

    private = filters.ChatType.PRIVATE
    app.add_handler(TypeHandler(Update, guard), group=-1)  # runs first for every update

    app.add_handler(CommandHandler("start", user.start, filters=private))
    app.add_handler(CommandHandler("help", user.help_cmd, filters=private))
    app.add_handler(CommandHandler("cancel", user.cancel, filters=private))
    app.add_handler(CommandHandler("admin", admin.open_panel, filters=private))
    app.add_handler(CommandHandler("app", open_mini_app, filters=private))

    app.add_handler(CallbackQueryHandler(user.on_verify, pattern=r"^verify_join$"))
    app.add_handler(CallbackQueryHandler(user.on_set_language, pattern=r"^(setlang|lang):"))
    app.add_handler(CallbackQueryHandler(admin.on_callback, pattern=r"^adm:"))
    app.add_handler(CallbackQueryHandler(user.on_number_request, pattern=r"^number:"))

    app.add_handler(
        MessageHandler(private & filters.UpdateType.MESSAGE & ~filters.COMMAND, router.on_message)
    )
    app.add_error_handler(_on_error)
    return app


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=getattr(logging, settings.log_level, logging.INFO),
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # keeps the bot token out of the logs
    # Python 3.14 no longer guarantees a current event loop in the main thread.
    # python-telegram-bot's run_polling() expects one to exist before it starts.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    build_application(settings).run_polling()
