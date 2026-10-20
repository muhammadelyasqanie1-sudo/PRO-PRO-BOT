from __future__ import annotations

import logging

from telegram import BotCommand, Update
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

log = logging.getLogger("bot")


async def _post_init(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    db = Database(settings.db_path)
    await db.connect()
    app.bot_data["db"] = db
    await app.bot.set_my_commands(
        [BotCommand("start", "Start / menu"), BotCommand("help", "Help"), BotCommand("cancel", "Cancel current action")]
    )
    me = await app.bot.get_me()
    log.info("Started as @%s (db: %s)", me.username, settings.db_path)
    if __import__("os").getenv("AUGESTEL_API_KEY", "").strip():
        app.create_task(poll_augestel(app), name="augestel-otp-poller")
    else:
        log.warning("AUGESTEL_API_KEY is not set; OTP polling is disabled.")


async def _post_shutdown(app: Application) -> None:
    db: Database | None = app.bot_data.get("db")
    if db:
        await db.close()


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error while processing an update", exc_info=context.error)


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

    app.add_handler(CallbackQueryHandler(user.on_verify, pattern=r"^verify_join$"))
    app.add_handler(CallbackQueryHandler(user.on_set_language, pattern=r"^(setlang|lang):"))
    app.add_handler(CallbackQueryHandler(admin.on_callback, pattern=r"^adm:"))
    app.add_handler(CallbackQueryHandler(user.on_number_request, pattern=r"^number:claim:"))

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
    build_application(settings).run_polling()
