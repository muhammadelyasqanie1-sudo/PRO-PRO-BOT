from __future__ import annotations

from telegram.ext import ContextTypes

from .config import Settings
from .db import Database


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.bot_data["db"]


def get_settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.bot_data["settings"]


def is_owner(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    return user_id == get_settings(context).owner_id


async def is_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    return is_owner(context, user_id) or await get_db(context).is_admin(user_id)


def valid_url(value: str) -> bool:
    return value.startswith(("https://t.me/", "https://telegram.me/", "https://"))
