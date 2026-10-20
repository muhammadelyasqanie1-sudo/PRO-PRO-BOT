"""Owner-only controls for managed API keys and point adjustments."""
from __future__ import annotations

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..utils import get_db, get_settings, is_owner
from ..keyboards import back_keyboard

esc = html.escape


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, arg: str) -> None:
    q = update.callback_query
    uid = q.from_user.id
    if not is_owner(context, uid):
        await q.edit_message_text("Only the bot owner can manage API keys and points.", reply_markup=back_keyboard())
        return
    db = get_db(context)

    if action == "api_keys":
        keys = await db.list_api_keys()
        rows = []
        if keys:
            lines = []
            for item in keys:
                status = "🟢 Active" if item["active"] else "⚪ Disabled"
                lines.append(f"• <b>{esc(item['name'])}</b> — {status} (ID {item['id']})")
                rows.append([
                    InlineKeyboardButton(
                        f"{'⏸ Disable' if item['active'] else '▶️ Enable'} #{item['id']}",
                        callback_data=f"adm:api_toggle:{item['id']}",
                    ),
                    InlineKeyboardButton("🗑 Delete", callback_data=f"adm:api_del:{item['id']}"),
                ])
            body = "\n".join(lines)
        else:
            body = "No API keys have been added yet."
        rows.append([InlineKeyboardButton("➕ Add API key", callback_data="adm:api_add")])
        rows.append([InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")])
        await q.edit_message_text(
            "🔑 <b>API key management</b>\n\n" + body +
            "\n\nKeys are never shown in full. Active keys are tried in order.",
            reply_markup=InlineKeyboardMarkup(rows),
        )
    elif action == "api_add":
        context.user_data["state"] = "api_add"
        await q.edit_message_text(
            "Send API key as <code>Name | API_KEY</code>.\n"
            "The full key will be hidden after saving.\n\nSend /cancel to abort.",
            reply_markup=back_keyboard(),
        )
    elif action == "api_toggle":
        await db.toggle_api_key(int(arg))
        await _show_api_keys(q, context)
    elif action == "api_del":
        await db.delete_api_key(int(arg))
        await _show_api_keys(q, context)
    elif action == "points":
        owner = await db.get_user(get_settings(context).owner_id)
        balance = owner.get("points", 0) if owner else 0
        rows = [
            [InlineKeyboardButton("➕ Give points", callback_data="adm:points_add")],
            [InlineKeyboardButton("➖ Remove points", callback_data="adm:points_sub")],
            [InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")],
        ]
        await q.edit_message_text(
            f"⭐ <b>Points management</b>\n\n👑 Owner balance: <b>{balance}</b>\n"
            "🎁 Referral reward: <b>1 point per valid invite</b>",
            reply_markup=InlineKeyboardMarkup(rows),
        )
    elif action in ("points_add", "points_sub"):
        context.user_data["state"] = action
        verb = "add" if action == "points_add" else "remove"
        await q.edit_message_text(
            f"Send <code>USER_ID | AMOUNT</code> to {verb} points.\n\nSend /cancel to abort.",
            reply_markup=back_keyboard(),
        )


async def _show_api_keys(q, context: ContextTypes.DEFAULT_TYPE) -> None:
    keys = await get_db(context).list_api_keys()
    rows = []
    if keys:
        lines = []
        for item in keys:
            status = "🟢 Active" if item["active"] else "⚪ Disabled"
            lines.append(f"• <b>{esc(item['name'])}</b> — {status} (ID {item['id']})")
            rows.append([
                InlineKeyboardButton(
                    f"{'⏸ Disable' if item['active'] else '▶️ Enable'} #{item['id']}",
                    callback_data=f"adm:api_toggle:{item['id']}",
                ),
                InlineKeyboardButton("🗑 Delete", callback_data=f"adm:api_del:{item['id']}"),
            ])
        body = "\n".join(lines)
    else:
        body = "No API keys have been added yet."
    rows.append([InlineKeyboardButton("➕ Add API key", callback_data="adm:api_add")])
    rows.append([InlineKeyboardButton("⬅️ Admin panel", callback_data="adm:home")])
    await q.edit_message_text(
        "🔑 <b>API key management</b>\n\n" + body +
        "\n\nKeys are never shown in full. Active keys are tried in order.",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def handle_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    msg = update.effective_message
    uid = update.effective_user.id
    db = get_db(context)
    text = (msg.text or "").strip()
    if not is_owner(context, uid):
        context.user_data.pop("state", None)
        return

    if state == "api_add":
        name, sep, api_key = text.partition("|")
        name, api_key = name.strip(), api_key.strip()
        if not sep or not name or len(name) > 60 or len(api_key) < 8:
            await msg.reply_text("Invalid format. Send <code>Name | API_KEY</code>, or /cancel.")
            return
        if not await db.add_api_key(name, api_key):
            await msg.reply_text("That API key is already saved. Send a different key or /cancel.")
            return
        context.user_data.pop("state", None)
        await msg.reply_text("✅ API key saved and activated. The full key will not be displayed.", reply_markup=back_keyboard())
        return

    if state in ("points_add", "points_sub"):
        target_text, sep, amount_text = text.partition("|")
        if not sep:
            parts = text.split()
            if len(parts) != 2:
                await msg.reply_text("Use <code>USER_ID | AMOUNT</code>, or /cancel.")
                return
            target_text, amount_text = parts
        target_text, amount_text = target_text.strip(), amount_text.strip()
        if not target_text.isdigit() or not amount_text.isdigit() or int(amount_text) <= 0:
            await msg.reply_text("User ID and positive amount are required. Try again or /cancel.")
            return
        target_id, amount = int(target_text), int(amount_text)
        if not await db.get_user(target_id):
            await msg.reply_text("User not found. They must start the bot first.")
            return
        delta = amount if state == "points_add" else -amount
        if not await db.adjust_points(target_id, delta, "admin_adjustment", actor_id=uid):
            await msg.reply_text("Could not apply the change. The user may not have enough points.")
            return
        context.user_data.pop("state", None)
        current = await db.get_user(target_id)
        await msg.reply_text(
            f"✅ Points updated for <code>{target_id}</code>. New balance: <b>{current['points']}</b>.",
            reply_markup=back_keyboard(),
        )
