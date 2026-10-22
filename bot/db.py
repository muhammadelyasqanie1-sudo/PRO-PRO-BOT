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
    points      INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS pending_provider_numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    country TEXT NOT NULL DEFAULT 'Unknown',
    range_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    service TEXT,
    imported_at TEXT NOT NULL,
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_provider_status ON pending_provider_numbers(status, id DESC);
CREATE TABLE IF NOT EXISTS otp_messages (
    provider_key TEXT PRIMARY KEY,
    number TEXT NOT NULL,
    message TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    api_key TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS points_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    actor_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_points_ledger_user ON points_ledger(user_id, id DESC);
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
        # Migrate existing databases created before points were introduced.
        async with self.conn.execute("PRAGMA table_info(users)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        if "points" not in columns:
            await self.conn.execute("ALTER TABLE users ADD COLUMN points INTEGER NOT NULL DEFAULT 0")
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
                    "UPDATE users SET referrals = referrals + 1, points = points + 10 WHERE id = ?", (ref,)
                )
                await self.conn.execute(
                    "INSERT INTO points_ledger(user_id,delta,reason,actor_id,created_at) VALUES(?,10,'referral',?,?)",
                    (ref, user.id, now),
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

    async def add_phone_numbers_bulk(self, service: str, country: str, numbers: list[str]) -> tuple[int, int]:
        """Insert a batch of numbers, ignoring any number already stored.

        Returns (added, already_in_database). The UNIQUE constraint on number
        is the final protection against duplicates, including concurrent imports.
        """
        assert self.conn is not None
        added = 0
        duplicates = 0
        now = _now()
        async with self.conn.execute("BEGIN"):
            for number in numbers:
                cur = await self.conn.execute(
                    "INSERT OR IGNORE INTO phone_numbers(service,country,number,status,created_at) "
                    "VALUES(?,?,?,'available',?)",
                    (service, country, number, now),
                )
                if cur.rowcount == 1:
                    added += 1
                else:
                    duplicates += 1
                await cur.close()
        await self.conn.commit()
        return added, duplicates

    async def list_active_services(self) -> list[str]:
        return [v.strip() for v in (await self.get_setting("active_services")).split("\n") if v.strip()]

    async def toggle_service_active(self, service: str) -> bool:
        """Toggle a service's visibility to users; return its new active state."""
        service = service.strip()[:40]
        values = await self.list_active_services()
        match = next((v for v in values if v.casefold() == service.casefold()), None)
        if match:
            values = [v for v in values if v.casefold() != service.casefold()]
            active = False
        else:
            values.append(service)
            active = True
        await self.set_setting("active_services", "\n".join(values))
        return active

    async def list_phone_number_services(self) -> list[str]:
        rows = await self._all("SELECT DISTINCT service FROM phone_numbers ORDER BY service COLLATE NOCASE")
        return [str(r["service"]) for r in rows]

    async def list_available_numbers(self, service: str | None = None, country: str | None = None, services: list[str] | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM phone_numbers WHERE status='available'"
        params: list[Any] = []
        if services is not None:
            if not services:
                return []
            sql += " AND service IN (" + ",".join("?" for _ in services) + ")"
            params.extend(services)
        elif service:
            sql += " AND service=?"; params.append(service)
        if country:
            sql += " AND country=?"; params.append(country)
        sql += " ORDER BY id DESC LIMIT 50"
        return await self._all(sql, tuple(params))

    async def add_pending_provider_numbers(self, records: list[dict[str, str]]) -> tuple[int, int]:
        """Store newly discovered provider numbers for explicit admin review."""
        assert self.conn is not None
        added = duplicates = 0
        now = _now()
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            for record in records:
                number = (record.get("number") or "").strip()
                if not number:
                    continue
                country = (record.get("country") or "Unknown").strip()[:60] or "Unknown"
                range_name = (record.get("range_name") or "").strip()[:120]
                cur_existing = await self.conn.execute("SELECT 1 FROM phone_numbers WHERE number=? LIMIT 1", (number[:30],))
                already_live = await cur_existing.fetchone()
                await cur_existing.close()
                if already_live:
                    duplicates += 1
                    continue
                cur = await self.conn.execute(
                    "INSERT OR IGNORE INTO pending_provider_numbers(number,country,range_name,status,imported_at) VALUES(?,?,?,'pending',?)",
                    (number[:30], country, range_name, now),
                )
                if cur.rowcount == 1:
                    added += 1
                else:
                    duplicates += 1
                await cur.close()
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise
        return added, duplicates

    async def list_pending_provider_numbers(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._all("SELECT * FROM pending_provider_numbers WHERE status='pending' ORDER BY id LIMIT ?", (max(1, min(limit, 50)),))

    async def get_pending_provider_number(self, pending_id: int) -> Optional[dict[str, Any]]:
        return await self._one("SELECT * FROM pending_provider_numbers WHERE id=? AND status='pending'", (pending_id,))

    async def review_provider_number(self, pending_id: int, service: str) -> str:
        """Approve into the live stock or mark duplicate; never overwrites existing stock."""
        assert self.conn is not None
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            item = await self._one("SELECT * FROM pending_provider_numbers WHERE id=? AND status='pending'", (pending_id,))
            if not item:
                await self.conn.rollback()
                return "missing"
            now = _now()
            cur = await self.conn.execute(
                "INSERT OR IGNORE INTO phone_numbers(service,country,number,status,created_at) VALUES(?,?,?,'available',?)",
                (service[:40], item["country"][:60], item["number"], now),
            )
            inserted = cur.rowcount == 1
            await cur.close()
            status = "approved" if inserted else "duplicate"
            await self.conn.execute(
                "UPDATE pending_provider_numbers SET status=?,service=?,reviewed_at=? WHERE id=? AND status='pending'",
                (status, service[:40], now, pending_id),
            )
            await self.conn.commit()
            return status
        except Exception:
            await self.conn.rollback()
            raise

    async def reject_provider_number(self, pending_id: int) -> bool:
        return await self._exec("UPDATE pending_provider_numbers SET status='rejected',reviewed_at=? WHERE id=? AND status='pending'", (_now(), pending_id)) == 1

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
 
    # ---------- points / referrals ----------
    async def ensure_owner_points(self, owner_id: int, initial_points: int = 100000) -> None:
        """Grant the owner a one-time top-up to the configured minimum balance."""
        assert self.conn is not None
        marker = await self.get_setting("owner_initial_points_granted_v3")
        if marker == "1":
            return
        now = _now()
        await self.conn.execute(
            "INSERT OR IGNORE INTO users(id,first_name,username,joined_at,last_seen,points) VALUES(?,?,?,?,?,0)",
            (owner_id, "Bot owner", "", now, now),
        )
        current_owner = await self.get_user(owner_id)
        bonus = max(0, initial_points - int(current_owner.get("points", 0) if current_owner else 0))
        if bonus:
            await self.conn.execute(
                "UPDATE users SET points = points + ? WHERE id = ?", (bonus, owner_id)
            )
            await self.conn.execute(
                "INSERT INTO points_ledger(user_id,delta,reason,actor_id,created_at) VALUES(?,?,'owner_100000_bonus',?,?)",
                (owner_id, bonus, owner_id, now),
            )
        await self.conn.execute(
            "INSERT INTO settings(key,value) VALUES('owner_initial_points_granted_v3','1') "
            "ON CONFLICT(key) DO UPDATE SET value='1'"
        )
        await self.conn.commit()


    async def claim_daily_points(self, user_id: int, amount: int = 15) -> tuple[bool, int]:
        """Grant the daily reward once per UTC day."""
        assert self.conn is not None
        user = await self.get_user(user_id)
        if not user or user["is_banned"]:
            return False, int(user.get("points", 0)) if user else 0
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"daily_points:{user_id}"
        if await self.get_setting(key) == today:
            return False, int(user.get("points", 0))
        now = _now()
        await self.conn.execute("UPDATE users SET points = points + ? WHERE id = ?", (amount, user_id))
        await self.conn.execute(
            "INSERT INTO points_ledger(user_id,delta,reason,actor_id,created_at) VALUES(?,?,'daily_bonus',?,?)",
            (user_id, amount, user_id, now),
        )
        await self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, today),
        )
        await self.conn.commit()
        updated = await self.get_user(user_id)
        return True, int(updated.get("points", 0)) if updated else amount

    async def adjust_points(self, user_id: int, delta: int, reason: str, actor_id: int | None = None) -> bool:
        """Apply a point change; negative changes cannot create a negative balance."""
        assert self.conn is not None
        if delta == 0 or abs(delta) > 1_000_000_000 or not await self.get_user(user_id):
            return False
        now = _now()
        if delta < 0:
            cur = await self.conn.execute(
                "UPDATE users SET points = points + ? WHERE id = ? AND points >= ?",
                (delta, user_id, -delta),
            )
        else:
            cur = await self.conn.execute(
                "UPDATE users SET points = points + ? WHERE id = ?", (delta, user_id)
            )
        changed = cur.rowcount == 1
        await cur.close()
        if changed:
            await self.conn.execute(
                "INSERT INTO points_ledger(user_id,delta,reason,actor_id,created_at) VALUES(?,?,?,?,?)",
                (user_id, delta, reason[:100], actor_id, now),
            )
        await self.conn.commit()
        return changed

    async def transfer_points(self, sender_id: int, recipient_id: int, amount: int) -> bool:
        """Atomic user-to-user transfer; both ledger rows commit together."""
        if sender_id == recipient_id or amount <= 0 or amount > 1_000_000_000:
            return False
        assert self.conn is not None
        sender = await self.get_user(sender_id)
        recipient = await self.get_user(recipient_id)
        if not sender or not recipient or sender["is_banned"] or recipient["is_banned"]:
            return False
        now = _now()
        try:
            await self.conn.execute("BEGIN IMMEDIATE")
            cur = await self.conn.execute(
                "UPDATE users SET points = points - ? WHERE id = ? AND points >= ?",
                (amount, sender_id, amount),
            )
            if cur.rowcount != 1:
                await cur.close()
                await self.conn.rollback()
                return False
            await cur.close()
            await self.conn.execute("UPDATE users SET points = points + ? WHERE id = ?", (amount, recipient_id))
            await self.conn.execute(
                "INSERT INTO points_ledger(user_id,delta,reason,actor_id,created_at) VALUES(?,?,?,?,?)",
                (sender_id, -amount, f"transfer_to:{recipient_id}", recipient_id, now),
            )
            await self.conn.execute(
                "INSERT INTO points_ledger(user_id,delta,reason,actor_id,created_at) VALUES(?,?,?,?,?)",
                (recipient_id, amount, f"transfer_from:{sender_id}", sender_id, now),
            )
            await self.conn.commit()
            return True
        except Exception:
            await self.conn.rollback()
            raise

    async def points_history(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        return await self._all(
            "SELECT delta,reason,actor_id,created_at FROM points_ledger WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, max(1, min(limit, 50))),
        )

    # ---------- API key management ----------
    async def list_api_keys(self) -> list[dict[str, Any]]:
        return await self._all("SELECT id,name,active,created_at FROM api_keys ORDER BY id")

    async def list_active_api_keys(self) -> list[dict[str, Any]]:
        return await self._all("SELECT id,name,api_key,active FROM api_keys WHERE active=1 ORDER BY id")

    async def add_api_key(self, name: str, api_key: str) -> bool:
        try:
            await self._exec(
                "INSERT INTO api_keys(name,api_key,active,created_at) VALUES(?,?,1,?)",
                (name[:60], api_key.strip(), _now()),
            )
            return True
        except aiosqlite.IntegrityError:
            return False

    async def toggle_api_key(self, key_id: int) -> int:
        return await self._exec("UPDATE api_keys SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (key_id,))

    async def delete_api_key(self, key_id: int) -> int:
        return await self._exec("DELETE FROM api_keys WHERE id=?", (key_id,))

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
