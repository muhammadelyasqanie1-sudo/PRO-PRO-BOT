"""Runs before every handler: registers users, applies bans, maintenance mode and force-join."""
from __future__ import annotations

import html
import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from . import membership
from .i18n import norm_lang, t, t_all
from .keyboards import join_keyboard
from .utils import get_db, is_admin

log = logging.getLogger(__name__)


def _referrer_from(update: Update) -> int | None:
    msg = update.message
    if msg and msg.text and msg.text.startswith("/start"):
        parts = msg.text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip().isdigit():
            return int(parts[1].strip())
    return None


async def _say(update: Update, text: str, markup=None) -> None:
    msg = update.effective_message
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except TelegramError:
            pass
    if msg:
        await msg.reply_text(text, reply_markup=markup)


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or user.is_bot or chat is None:
        return
    if chat.type != "private":  # the bot only works in private chats
        raise ApplicationHandlerStop

    db = get_db(context)
    row, is_new, counted = await db.touch_user(user, _referrer_from(update))
    lang = row.get("lang")

    if counted and row.get("referrer_id"):
        referrer = await db.get_user(row["referrer_id"])
        if referrer:
            try:
                await context.bot.send_message(
                    referrer["id"],
                    t(referrer.get("lang"), "new_referral", name=html.escape(user.first_name or "-")),
                )
            except TelegramError:
                pass

    admin = await is_admin(context, user.id)
    if admin:
        return

    if row["is_banned"]:
        await _say(update, t(lang, "banned") if lang else t_all("banned"))
        raise ApplicationHandlerStop

    if await db.get_setting("maintenance") == "1":
        await _say(update, t(lang, "maintenance") if lang else t_all("maintenance"))
        raise ApplicationHandlerStop

    # Let the "Verify" button through; everything else needs membership first.
    query = update.callback_query
    if query and query.data == "verify_join":
        return

    missing = await membership.missing_channels(context, user.id)
    if missing:
        await _say(
            update,
            t(lang, "join_required") if lang else t_all("join_required"),
            join_keyboard(norm_lang(lang), missing, bilingual=not lang),
        )
        raise ApplicationHandlerStop
