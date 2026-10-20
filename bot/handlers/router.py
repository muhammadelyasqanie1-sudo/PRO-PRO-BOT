from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..utils import is_admin
from . import admin, user


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Single entry point for non-command private messages."""
    msg = update.effective_message
    if msg is None or update.effective_user is None:
        return

    state = context.user_data.get("state")
    if state:
        if await is_admin(context, update.effective_user.id):
            await admin.handle_state(update, context, state)
            return
        context.user_data.pop("state", None)  # stale state for a non-admin

    if msg.text:
        await user.route_text(update, context)
