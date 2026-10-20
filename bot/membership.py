"""Force-join (required channel membership) checks, with a short positive cache."""
from __future__ import annotations

import logging
import time

from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .utils import get_db, get_settings

log = logging.getLogger(__name__)

_OK = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


async def _is_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramError as exc:
        # Misconfiguration (bot is not admin there, wrong ID) or a network hiccup:
        # fail open so a broken setting never locks every user out.
        log.warning("Cannot check membership in %s (is the bot an admin there?): %s", chat_id, exc)
        return True
    if member.status in _OK:
        return True
    return member.status == ChatMemberStatus.RESTRICTED and bool(getattr(member, "is_member", False))


async def missing_channels(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> list[dict]:
    cache: dict[int, float] = context.bot_data.setdefault("join_cache", {})
    now = time.monotonic()
    if cache.get(user_id, 0) > now:
        return []

    channels = await get_db(context).list_channels()
    missing = [c for c in channels if not await _is_member(context.bot, c["chat_id"], user_id)]

    if not missing:
        if len(cache) > 5000:  # prune expired entries
            for uid in [u for u, exp in cache.items() if exp <= now]:
                cache.pop(uid, None)
        cache[user_id] = now + get_settings(context).join_cache_seconds
    return missing


def forget(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    context.bot_data.setdefault("join_cache", {}).pop(user_id, None)
