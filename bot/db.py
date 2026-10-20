"""SQLite storage (async). One connection shared by the whole bot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    first_name  TEXT    NOT NULL DEFAULT '',
    username    TEXT    NOT NULL DEFAULT '',
    lang        TEXT,
    referrer_id INTEGER,
    referrals   INTEGER NOT NULL DEFAULT 0,
    is_banned   INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    joined_at   TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_joined ON users(joined_at);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS admins (
    user_id  INTEGER PRIMARY KEY,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    chat_id INTEGER PRIMARY KEY,
    title   TEXT NOT NULL,
    link    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS phone_numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    country TEXT NOT NULL,
    number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'available',
    assigned_user_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phone_numbers_status ON phone_numbers(status, service, country);
CREATE TABLE IF NOT EXISTS otp_messages (
    provider_key TEXT PRIMARY KEY,
    number TEXT NOT NULL,
    message TEXT NOT NULL,
    received_at TEXT NOT NULL
);
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _now() -> str:
    return _iso(datetime.now(timezone.utc))


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    # ---------- helpers ----------
    async def _one(self, sql: str, params: tuple = ()) -> Optional[dict[str, Any]]:
        assert self.conn is not None
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        assert self.conn is not None
        async with self.conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def _exec(self, sql: str, params: tuple = ()) -> int:
        assert self.conn is not None
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        n = cur.rowcount
        await cur.close()
        return n

    # ---------- users ----------
    async def get_user(self, user_id: int) -> Optional[dict[str, Any]]:
        return await self._one("SELECT * FROM users WHERE id = ?", (user_id,))

    async def find_user(self, query: str) -> Optional[dict[str, Any]]:
        query = query.strip()
        if query.lstrip("-").isdigit():
            return await self.get_user(int(query))
        return await self._one(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (query.lstrip("@"),)
        )

    async def touch_user(
        self, user, referrer_id: Optional[int] = None
    ) -> tuple[dict[str, Any], bool, bool]:
        """Create the user if new, otherwise refresh name/last_seen.

        Returns (row, is_new, referral_counted).
        """
        assert self.conn is not None
        now = _now()
        name = (user.first_name or "")[:128]
        username = user.username or ""
        existing = await self.get_user(user.id)
        if existing is None:
            ref = None
            if referrer_id and referrer_id != user.id and await self.get_user(referrer_id):
                ref = referrer_id
            await self.conn.execute(
                "INSERT OR IGNORE INTO users (id, first_name, username, referrer_id, joined_at, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user.id, name, username, ref, now, now),
            )
            if ref:
                await self.conn.execute(
                    "UPDATE users SET referrals = referrals + 1 WHERE id = ?", (ref,)
                )
            await self.conn.commit()
            return await self.get_user(user.id), True, bool(ref)  # type: ignore[return-value]

        await self._exec(
            "UPDATE users SET first_name = ?, username = ?, last_seen = ?, is_active = 1 WHERE id = ?",
            (name, username, now, user.id),
        )
        return await self.get_user(user.id), False, False  # type: ignore[return-value]

    async def set_lang(self, user_id: int, lang: str) -> None:
        await self._exec("UPDATE users SET lang = ? WHERE id = ?", (lang, user_id))

    async def set_banned(self, user_id: int, banned: bool) -> int:
        return await self._exec(
            "UPDATE users SET is_banned = ? WHERE id = ?", (1 if banned else 0, user_id)
        )

    async def set_active(self, user_id: int, active: bool) -> None:
        await self._exec("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, user_id))

    async def broadcast_targets(self) -> list[int]:
        rows = await self._all("SELECT id FROM users WHERE is_active = 1 AND is_banned = 0 ORDER BY id")
        return [r["id"] for r in rows]

    async def stats(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        week = _iso(now - timedelta(days=7))
        row = await self._one(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(is_active = 1), 0) AS active, "
            "COALESCE(SUM(is_banned = 1), 0) AS banned, "
            "COALESCE(SUM(joined_at >= ?), 0) AS today, "
            "COALESCE(SUM(joined_at >= ?), 0) AS week, "
            "COALESCE(SUM(referrals), 0) AS referrals "
            "FROM users",
            (today, week),
        )
        langs = await self._all(
            "SELECT COALESCE(lang, '-') AS lang, COUNT(*) AS n FROM users GROUP BY lang ORDER BY n DESC"
        )
        row = row or {}
        row["langs"] = {r["lang"]: r["n"] for r in langs}
        return row

    # ---------- admins ----------
    async def is_admin(self, user_id: int) -> bool:
        return await self._one("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) is not None

    async def list_admins(self) -> list[int]:
        return [r["user_id"] for r in await self._all("SELECT user_id FROM admins ORDER BY added_at")]

    async def add_admin(self, user_id: int) -> None:
        await self._exec("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, _now()))

    async def remove_admin(self, user_id: int) -> int:
        return await self._exec("DELETE FROM admins WHERE user_id = ?", (user_id,))

    # ---------- force-join channels ----------
    async def list_channels(self) -> list[dict[str, Any]]:
        return await self._all("SELECT chat_id, title, link FROM channels ORDER BY rowid")

    async def add_channel(self, chat_id: int, title: str, link: str) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO channels (chat_id, title, link) VALUES (?, ?, ?)",
            (chat_id, title, link),
        )

    async def remove_channel(self, chat_id: int) -> int:
        return await self._exec("DELETE FROM channels WHERE chat_id = ?", (chat_id,))


    # ---------- manually managed phone-number inventory ----------
    async def add_phone_number(self, service: str, country: str, number: str) -> bool:
        try:
            await self._exec(
                "INSERT INTO phone_numbers(service,country,number,status,created_at) VALUES(?,?,?,'available',?)",
                (service, country, number, _now()),
            )
            return True
        except aiosqlite.IntegrityError:
            return False

    async def list_available_numbers(self, service: str | None = None, country: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM phone_numbers WHERE status='available'"
        params: list[Any] = []
        if service:
            sql += " AND service=?"; params.append(service)
        if country:
            sql += " AND country=?"; params.append(country)
        sql += " ORDER BY id DESC LIMIT 50"
        return await self._all(sql, tuple(params))

    async def get_phone_number(self, number_id: int) -> Optional[dict[str, Any]]:
        return await self._one("SELECT * FROM phone_numbers WHERE id=?", (number_id,))

    async def assign_phone_number(self, number_id: int, user_id: int) -> bool:
        return await self._exec(
            "UPDATE phone_numbers SET status='assigned', assigned_user_id=? WHERE id=? AND status='available'",
            (user_id, number_id),
        ) == 1

    async def delete_phone_number(self, number_id: int) -> int:
        return await self._exec("DELETE FROM phone_numbers WHERE id=? AND status='available'", (number_id,))

    async def save_otp_once(self, provider_key: str, number: str, message: str, received_at: str) -> bool:
        try:
            await self._exec("INSERT INTO otp_messages(provider_key,number,message,received_at) VALUES(?,?,?,?)",
                             (provider_key, number, message, received_at))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def assigned_users_for_number(self, number: str) -> list[int]:
        rows = await self._all("SELECT assigned_user_id FROM phone_numbers WHERE number=? AND status='assigned' AND assigned_user_id IS NOT NULL", (number,))
        return [int(r['assigned_user_id']) for r in rows]

    # ---------- key/value settings ----------
    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self._one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self._exec(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
