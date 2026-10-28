"""Premium (animated) custom emoji support.

Telegram only lets a bot use custom emoji by their numeric ID, and the IDs cannot be guessed.
The admin teaches the bot the IDs by sending animated emoji (or a pack link) in the admin panel;
the bot stores ``unicode emoji -> custom emoji id`` in the settings table.

Once an emoji is mapped, every outgoing message automatically:
  * renders it as an animated emoji in the text (``<tg-emoji emoji-id=...>``), and
  * shows it as the icon of buttons whose label starts with it (``icon_custom_emoji_id``).

Everything is best-effort: if Telegram rejects a message with custom emoji (for example the
bot owner has no Premium), the message is re-sent in its plain form.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ExtBot

log = logging.getLogger(__name__)

SETTING_MAP = "premium_emoji_map"
SETTING_ON = "premium_emoji_on"

_VS16 = "️"
_ZWJ = "‍"

# Emoji we try to recognise in text. Order matters only for readability.
_EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"  # flags
    "|[#*0-9]️?⃣"  # keycaps
    "|(?:[\U0001F000-\U0001FAFF←-⇿⌀-⏿①-⓿■-➿"
    "⤀-⥿⬀-⯿〰〽㊗㊙©®‼⁉™ℹ]"
    "[️\U0001F3FB-\U0001F3FF]?"
    "(?:‍[\U0001F000-\U0001FAFF♀♂⚕-⚖✈❤][️]?)*))"
)
_TAG_RE = re.compile(r"(<[^>]*>)")


def norm(emoji: str) -> str:
    """Key used for the map: the emoji without variation selectors."""
    return emoji.replace(_VS16, "")


def extract_emoji(text: str) -> list[str]:
    return [m.group(0) for m in _EMOJI_RE.finditer(text or "")]


def strip_leading_emoji(text: str) -> str:
    """'🔥 Hello' -> 'Hello'. Used to match reply-keyboard presses whose icon moved to a button icon."""
    s = (text or "").strip()
    m = _EMOJI_RE.match(s)
    while m:
        s = s[m.end():].lstrip()
        m = _EMOJI_RE.match(s)
    return s


class PremiumEmoji:
    """Process-wide registry of unicode emoji -> custom emoji id."""

    def __init__(self) -> None:
        self.map: dict[str, str] = {}
        self.enabled: bool = False

    def load(self, raw_map: str | None, raw_on: str | None) -> None:
        try:
            data = json.loads(raw_map or "{}")
            self.map = {norm(k): str(v) for k, v in data.items() if str(v).isdigit()}
        except (ValueError, AttributeError):
            self.map = {}
        self.enabled = (raw_on or "1") == "1"

    def dump(self) -> str:
        return json.dumps(self.map, ensure_ascii=False)

    def active(self) -> bool:
        return self.enabled and bool(self.map)

    # ---------------------------------------------------------- text
    def text(self, html_text: str) -> str:
        if not self.active() or not html_text:
            return html_text
        out: list[str] = []
        skip = 0  # depth of <tg-emoji>/<code>/<pre> we are inside of
        for part in _TAG_RE.split(html_text):
            if part.startswith("<") and part.endswith(">"):
                low = part.lower()
                if re.match(r"<(tg-emoji|code|pre)\b", low):
                    skip += 1
                elif re.match(r"</(tg-emoji|code|pre)\b", low):
                    skip = max(0, skip - 1)
                out.append(part)
            elif skip:
                out.append(part)
            else:
                out.append(_EMOJI_RE.sub(self._repl, part))
        return "".join(out)

    def _repl(self, m: re.Match) -> str:
        emoji = m.group(0)
        cid = self.map.get(norm(emoji))
        if not cid:
            return emoji
        return f'<tg-emoji emoji-id="{cid}">{emoji}</tg-emoji>'

    # ------------------------------------------------------- markup
    def button_icon(self, label: str) -> tuple[str | None, str]:
        """Return (custom_emoji_id, label_without_that_emoji) for a button label."""
        m = _EMOJI_RE.match(label or "")
        if not m:
            return None, label
        cid = self.map.get(norm(m.group(0)))
        if not cid:
            return None, label
        rest = label[m.end():].lstrip()
        return cid, rest

    def markup(self, markup: Any) -> Any:
        """Return a decorated deep copy of an inline / reply keyboard (others are untouched)."""
        if not self.active() or not isinstance(markup, (InlineKeyboardMarkup, ReplyKeyboardMarkup)):
            return markup
        rows = markup.inline_keyboard if isinstance(markup, InlineKeyboardMarkup) else markup.keyboard
        changed = False
        new_rows = []
        for row in rows:
            new_row = []
            for btn in row:
                label = btn.text if hasattr(btn, "text") else str(btn)
                cid, rest = self.button_icon(label)
                if cid and rest:
                    new_row.append(_clone_button(btn, rest, cid))
                    changed = True
                else:
                    new_row.append(btn)
            new_rows.append(new_row)
        if not changed:
            return markup
        if isinstance(markup, InlineKeyboardMarkup):
            return InlineKeyboardMarkup(new_rows)
        return ReplyKeyboardMarkup(
            new_rows,
            resize_keyboard=markup.resize_keyboard,
            one_time_keyboard=markup.one_time_keyboard,
            selective=markup.selective,
            input_field_placeholder=markup.input_field_placeholder,
            is_persistent=markup.is_persistent,
        )


def _clone_button(btn: Any, new_text: str, icon_id: str) -> Any:
    """Rebuild a keyboard button with new text plus the custom-emoji icon (style is preserved)."""
    data = btn.to_dict()
    data["text"] = new_text
    data["icon_custom_emoji_id"] = icon_id
    return type(btn).de_json(data, None)


REGISTRY = PremiumEmoji()


async def reload(db) -> None:
    REGISTRY.load(await db.get_setting(SETTING_MAP, "{}"), await db.get_setting(SETTING_ON, "1"))


_TEXT_ENDPOINTS = {
    "sendMessage": "text",
    "editMessageText": "text",
    "sendPhoto": "caption",
    "sendVideo": "caption",
    "sendDocument": "caption",
    "sendAnimation": "caption",
    "editMessageCaption": "caption",
}
_MARKUP_ENDPOINTS = set(_TEXT_ENDPOINTS) | {"editMessageReplyMarkup"}


class PremiumBot(ExtBot):
    """ExtBot that upgrades plain emoji to the admin-configured animated ones when possible."""

    __slots__ = ()  # keeps the layout identical to ExtBot so an existing bot can be switched over

    async def _do_post(self, endpoint, data, **kwargs):  # type: ignore[override]
        if not REGISTRY.active() or endpoint not in _MARKUP_ENDPOINTS:
            return await super()._do_post(endpoint, data, **kwargs)
        fancy = dict(data)
        try:
            field = _TEXT_ENDPOINTS.get(endpoint)
            if field and isinstance(fancy.get(field), str) and str(fancy.get("parse_mode", "")).upper() == "HTML":
                fancy[field] = REGISTRY.text(fancy[field])
            if "reply_markup" in fancy:
                fancy["reply_markup"] = REGISTRY.markup(fancy["reply_markup"])
        except Exception:  # decoration must never break a send
            log.exception("emoji decoration failed; sending plain")
            return await super()._do_post(endpoint, data, **kwargs)
        if fancy == data:
            return await super()._do_post(endpoint, data, **kwargs)
        try:
            return await super()._do_post(endpoint, fancy, **kwargs)
        except BadRequest as exc:
            msg = str(exc).lower()
            if "not modified" in msg:
                raise
            if any(w in msg for w in ("emoji", "entit", "icon", "button", "can't parse", "premium")):
                log.warning("Premium emoji rejected (%s); falling back to plain emoji", exc)
                return await super()._do_post(endpoint, data, **kwargs)
            raise
