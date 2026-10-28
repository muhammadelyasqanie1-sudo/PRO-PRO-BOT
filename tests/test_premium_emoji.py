"""Run with:  python tests/test_premium_emoji.py   (needs python-telegram-bot + aiosqlite)"""
import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as U

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import telegram  # noqa: E402
from telegram import CopyTextButton, Message, MessageEntity, Chat, User  # noqa: E402
from telegram.error import BadRequest  # noqa: E402
from telegram.ext import Defaults  # noqa: E402

from bot import emoji as pe  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.handlers import emoji_admin  # noqa: E402
from bot import i18n, premium_setup  # noqa: E402
from bot.i18n import MENU_LOOKUP  # noqa: E402
from bot.keyboards import ib, menu_keyboard  # noqa: E402

R = pe.REGISTRY


def test_text_and_markup() -> None:
    R.load('{"\U0001F525":"111","\U0001F4F1":"222"}', "1")
    out = R.text("\U0001F525 <b>a \U0001F4F1</b> <code>\U0001F525</code> ❤")
    assert out.count("<tg-emoji") == 2 and "<code>\U0001F525</code>" in out
    assert R.text(out) == out  # idempotent: never nests
    m = menu_keyboard("en", False)
    d = R.markup(m).to_dict()["keyboard"]
    assert d[0][0]["text"] == "\U0001F4F2 GET NUMBER" and "icon_custom_emoji_id" not in d[0][0]
    R.load('{"\U0001F4F2":"333"}', "1")
    d = R.markup(m).to_dict()["keyboard"]
    assert d[0][0]["text"] == "GET NUMBER" and d[0][0]["style"] == "primary"
    assert d[0][0]["icon_custom_emoji_id"] == "333"
    # copy-text button keeps its payload
    from telegram import InlineKeyboardMarkup
    mk = InlineKeyboardMarkup([[ib("\U0001F4F2 x", "success", copy_text=CopyTextButton(text="abc"))]])
    b = R.markup(mk).to_dict()["inline_keyboard"][0][0]
    assert b["copy_text"] == {"text": "abc"} and b["icon_custom_emoji_id"] == "333" and b["style"] == "success"
    R.load("{}", "1")
    assert R.markup(m) is m and R.text("\U0001F525") == "\U0001F525"
    R.load('{"\U0001F525":"1"}', "0")
    assert R.text("\U0001F525") == "\U0001F525"


def test_setup() -> None:
    from telegram.ext import ApplicationBuilder

    premium_setup._style_menu()
    premium_setup._style_menu()  # idempotent
    assert i18n.STRINGS["en"]["menu_numbers"] == "\U0001F4F2 GET NUMBER"
    premium_setup._wrap_admin_keyboard()
    from bot import keyboards

    owner = keyboards.admin_panel_keyboard(False, True).to_dict()["inline_keyboard"]
    assert any(b["callback_data"] == "adm:pe" for r in owner for b in r)
    other = keyboards.admin_panel_keyboard(False, False).to_dict()["inline_keyboard"]
    assert not any(b.get("callback_data") == "adm:pe" for r in other for b in r)
    app = ApplicationBuilder().token("123:ABC").build()
    premium_setup.install_on(app)
    assert isinstance(app.bot, pe.PremiumBot) and app.bot.token == "123:ABC"
    assert -2 in app.handlers and len(app.handlers[-2]) == 2


def test_routing() -> None:
    assert MENU_LOOKUP.get("\U0001F4F2 GET NUMBER") == "menu_numbers"
    assert MENU_LOOKUP.get("GET NUMBER") == "menu_numbers"  # icon moved to the button
    assert MENU_LOOKUP.get("Admin Panel") == "menu_admin"
    assert MENU_LOOKUP.get("hello") is None


async def test_bot_fallback() -> None:
    sent = []
    fail_first = {"on": True}

    async def fake(self, endpoint, data, **kw):
        sent.append((endpoint, dict(data)))
        if fail_first["on"] and "tg-emoji" in str(data.get("text", "")):
            raise BadRequest("Bad Request: can't parse entities: unsupported custom emoji")
        return {"ok": True}

    orig = telegram.Bot._do_post
    telegram.Bot._do_post = fake
    try:
        R.load('{"\U0001F525":"111"}', "1")
        bot = pe.PremiumBot("123:ABC", defaults=Defaults(parse_mode="HTML"))
        await bot._do_post("sendMessage", {"chat_id": 1, "text": "\U0001F525 hi", "parse_mode": "HTML"})
        assert len(sent) == 2 and "tg-emoji" in sent[0][1]["text"] and sent[1][1]["text"] == "\U0001F525 hi"
        sent.clear()
        fail_first["on"] = False
        await bot._do_post("sendMessage", {"chat_id": 1, "text": "\U0001F525 hi", "parse_mode": "HTML"})
        assert len(sent) == 1 and "tg-emoji" in sent[0][1]["text"]
        sent.clear()
        await bot._do_post("sendMessage", {"chat_id": 1, "text": "<b>no emoji</b>", "parse_mode": "HTML"})
        await bot._do_post("getMe", {})
        assert len(sent) == 2 and sent[0][1]["text"] == "<b>no emoji</b>"
    finally:
        telegram.Bot._do_post = orig
        R.load("{}", "1")


async def test_admin_learns() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "t.db")
        await db.connect()
        ctx = U(bot_data={"db": db}, user_data={"state": "pe_add"}, bot=None)
        text = "a \U0001F525 b \U0001F600"  # utf16 offsets 2..4 and 7..9
        ents = [
            MessageEntity("custom_emoji", 2, 2, custom_emoji_id="555"),
            MessageEntity("custom_emoji", 7, 2, custom_emoji_id="666"),
        ]
        replies = []
        msg = Message(1, None, Chat(1, "private"), from_user=User(1, "a", False), text=text, entities=ents)

        async def reply_text(t, **kw):
            replies.append(t)

        msg.set_bot(None)
        # Message is frozen: wrap in a light proxy exposing what the handler uses.
        proxy = U(
            parse_entities=msg.parse_entities,
            parse_caption_entities=msg.parse_caption_entities,
            reply_text=reply_text,
        )
        upd = U(effective_message=proxy)
        await emoji_admin.handle_state(upd, ctx, "pe_add")
        assert R.map == {"\U0001F525": "555", "\U0001F600": "666"}, R.map
        await pe.reload(db)
        assert R.map == {"\U0001F525": "555", "\U0001F600": "666"}
        R.load("{}", "1")
        await db.close()


if __name__ == "__main__":
    test_setup()
    test_text_and_markup()
    test_routing()
    asyncio.run(test_bot_fallback())
    asyncio.run(test_admin_learns())
    print("premium emoji tests OK")
