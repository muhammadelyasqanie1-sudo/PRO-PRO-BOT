"""Run with:  python tests/test_db.py   (needs only aiosqlite)"""
import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as U

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.db import Database  # noqa: E402


async def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "t.db")
        await db.connect()

        a, new, counted = await db.touch_user(U(id=1, first_name="Ali", username="ali"))
        assert new and not counted and a["referrals"] == 0

        # referral: counted once, only for new users, never for self / unknown referrer
        b, new, counted = await db.touch_user(U(id=2, first_name="Bob", username=None), referrer_id=1)
        assert new and counted and b["referrer_id"] == 1
        assert (await db.get_user(1))["referrals"] == 1
        _, new, counted = await db.touch_user(U(id=2, first_name="Bob", username=None), referrer_id=1)
        assert not new and not counted and (await db.get_user(1))["referrals"] == 1
        _, _, counted = await db.touch_user(U(id=3, first_name="C", username="c"), referrer_id=3)
        assert not counted
        _, _, counted = await db.touch_user(U(id=4, first_name="D", username="d"), referrer_id=999)
        assert not counted

        # lang / ban / broadcast targets
        await db.set_lang(1, "dr")
        assert (await db.get_user(1))["lang"] == "dr"
        await db.set_banned(2, True)
        await db.set_active(3, False)
        assert await db.broadcast_targets() == [1, 4]

        # lookup
        assert (await db.find_user("@ALI"))["id"] == 1
        assert (await db.find_user("2"))["first_name"] == "Bob"
        assert await db.find_user("nobody") is None

        # stats
        s = await db.stats()
        assert s["total"] == 4 and s["banned"] == 1 and s["active"] == 3 and s["today"] == 4, s
        assert s["referrals"] == 1 and s["langs"]["dr"] == 1, s

        # admins, channels, settings
        await db.add_admin(7)
        assert await db.is_admin(7) and await db.list_admins() == [7]
        assert await db.remove_admin(7) == 1 and not await db.is_admin(7)
        await db.add_channel(-100123, "News", "https://t.me/news")
        assert (await db.list_channels())[0]["title"] == "News"
        assert await db.remove_channel(-100123) == 1 and await db.list_channels() == []
        assert await db.get_setting("maintenance") == ""
        await db.set_setting("maintenance", "1")
        await db.set_setting("maintenance", "0")
        assert await db.get_setting("maintenance") == "0"

        # number stock and OTP deduplication
        assert await db.add_phone_number("WhatsApp", "United States", "+12025550123")
        assert not await db.add_phone_number("WhatsApp", "United States", "+12025550123")
        stock = await db.list_available_numbers()
        assert len(stock) == 1 and stock[0]["number"] == "+12025550123"
        assert await db.assign_phone_number(stock[0]["id"], 1)
        assert await db.assigned_users_for_number("+12025550123") == [1]
        assert await db.save_otp_once("provider-msg-1", "+12025550123", "Your code is 123456", "2026-10-19T12:00:00Z")
        assert not await db.save_otp_once("provider-msg-1", "+12025550123", "Your code is 123456", "2026-10-19T12:00:00Z")

        await db.close()
    print("db tests passed")


asyncio.run(main())
