"""Admin panel section: teach the bot animated (Premium) custom emoji."""
from __future__ import annotations

import html
import logging
import re

from telegram import InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from .. import emoji as pe
from ..keyboards import _btn, back_keyboard, ib
from ..utils import get_db, is_admin

log = logging.getLogger(__name__)
esc = html.escape

ACTIONS = ("pe", "pe_toggle", "pe_add", "pe_pack", "pe_list", "pe_preview", "pe_reset", "pe_reset_yes")
STATES = ("pe_add", "pe_pack")


def _home_text() -> str:
    state = "ON 🟢" if pe.REGISTRY.enabled else "OFF 🔴"
    return (
        "🎭 <b>Premium Emoji / ایموجی های زنده</b>\n\n"
        f"Status: <b>{state}</b>  ·  Saved emoji: <b>{len(pe.REGISTRY.map)}</b>\n\n"
        "1. Tap <b>Add animated emoji</b> and send me messages that contain Telegram Premium animated emoji "
        "(you need Premium to send them), or tap <b>Add from pack</b> and send an emoji-pack link.\n"
        "2. From then on every matching plain emoji in the bot's messages, and the first emoji of every button, "
        "is shown as the animated one.\n\n"
        "Note: Animated button icons are shown only when the <b>bot owner</b> has Telegram Premium. "
        "If Telegram refuses, the bot automatically falls back to normal emoji."
    )


def _home_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("✨ Add animated emoji", "adm:pe_add"), _btn("📦 Add from pack", "adm:pe_pack")],
            [_btn("👁 Preview", "adm:pe_preview"), _btn("📋 List", "adm:pe_list")],
            [ib(f"Premium emoji: {'ON 🟢' if pe.REGISTRY.enabled else 'OFF 🔴'}", "success", callback_data="adm:pe_toggle")],
            [_btn("🗑 Reset all", "adm:pe_reset")],
            [_btn("⬅ Admin panel / پنل مدیریت", "adm:home")],
        ]
    )


async def _save(context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    await db.set_setting(pe.SETTING_MAP, pe.REGISTRY.dump())
    await db.set_setting(pe.SETTING_ON, "1" if pe.REGISTRY.enabled else "0")


async def _edit(q, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await q.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not await is_admin(context, q.from_user.id):
        await q.answer("Not authorized.", show_alert=True)
        return
    await q.answer()
    action = (q.data or "").split(":", 1)[1].partition(":")[0]
    if action not in ACTIONS:
        return
    if action != "pe_add" and action != "pe_pack":
        context.user_data.pop("state", None)

    if action == "pe":
        await _edit(q, _home_text(), _home_markup())

    elif action == "pe_toggle":
        pe.REGISTRY.enabled = not pe.REGISTRY.enabled
        await _save(context)
        await _edit(q, _home_text(), _home_markup())

    elif action == "pe_add":
        context.user_data["state"] = "pe_add"
        await _edit(
            q,
            "✨ Send me one or more messages containing <b>animated Premium emoji</b>.\n"
            "Every animated emoji found is saved and replaces its normal version in the bot.\n\n"
            "Send /cancel when you are done.",
            back_to_pe(),
        )

    elif action == "pe_pack":
        context.user_data["state"] = "pe_pack"
        await _edit(
            q,
            "📦 Send an emoji-pack link such as <code>https://t.me/addemoji/PackName</code>.\n"
            "Emoji already saved are kept; new ones are added.\n\nSend /cancel to abort.",
            back_to_pe(),
        )

    elif action == "pe_list":
        if not pe.REGISTRY.map:
            body = "Nothing saved yet."
        else:
            body = "  ".join(f"{k}→<code>{v[-6:]}</code>" for k, v in list(pe.REGISTRY.map.items())[:80])
        await _edit(q, "📋 <b>Saved emoji</b> (plain → id tail)\n\n" + body, back_to_pe())

    elif action == "pe_preview":
        if not pe.REGISTRY.map:
            await _edit(q, "Nothing saved yet — add animated emoji first.", back_to_pe())
            return
        sample = " ".join(list(pe.REGISTRY.map)[:40])
        await q.message.reply_text("🎭 Preview:\n\n" + sample)

    elif action == "pe_reset":
        await _edit(
            q,
            "🗑 Remove <b>all</b> saved animated emoji?",
            InlineKeyboardMarkup([[_btn("✅ Yes, reset", "adm:pe_reset_yes"), _btn("❌ Cancel", "adm:pe")]]),
        )

    elif action == "pe_reset_yes":
        pe.REGISTRY.map = {}
        await _save(context)
        await _edit(q, "✅ All saved emoji removed.\n\n" + _home_text(), _home_markup())


def back_to_pe() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("⬅ Premium Emoji", "adm:pe")]])


_PACK_RE = re.compile(r"(?:addemoji/|^)([A-Za-z0-9_]{3,64})/?$")


async def handle_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    msg = update.effective_message
    if state == "pe_add":
        found: dict[str, str] = {}
        parsed = {}
        parsed.update(msg.parse_entities(types=["custom_emoji"]))
        parsed.update(msg.parse_caption_entities(types=["custom_emoji"]))
        for ent, fallback in parsed.items():
            if ent.custom_emoji_id and fallback:
                found[pe.norm(fallback)] = ent.custom_emoji_id
        if not found:
            await msg.reply_text(
                "I found no animated emoji in that message. Send a message with Premium animated emoji, "
                "or /cancel to stop.",
                reply_markup=back_to_pe(),
            )
            return
        pe.REGISTRY.map.update(found)
        await _save(context)
        await msg.reply_text(
            f"✅ Saved {len(found)} emoji: {' '.join(found)}\nTotal: <b>{len(pe.REGISTRY.map)}</b>. "
            "Send more, or /cancel when done.",
            reply_markup=back_to_pe(),
        )
        return

    if state == "pe_pack":
        text = (msg.text or "").strip().split("?")[0].rstrip("/")
        m = _PACK_RE.search(text)
        if not m:
            await msg.reply_text("Send a link like https://t.me/addemoji/PackName", reply_markup=back_to_pe())
            return
        try:
            pack = await context.bot.get_sticker_set(m.group(1))
        except TelegramError as exc:
            await msg.reply_text(f"❌ Could not read that pack: {esc(str(exc))}", reply_markup=back_to_pe())
            return
        added = 0
        for st in pack.stickers:
            if st.custom_emoji_id and st.emoji:
                key = pe.norm(st.emoji)
                if key not in pe.REGISTRY.map:
                    pe.REGISTRY.map[key] = st.custom_emoji_id
                    added += 1
        context.user_data.pop("state", None)
        await _save(context)
        await msg.reply_text(
            f"✅ Pack <b>{esc(pack.title)}</b>: {added} new emoji saved. Total: <b>{len(pe.REGISTRY.map)}</b>.",
            reply_markup=_home_markup(),
        )
