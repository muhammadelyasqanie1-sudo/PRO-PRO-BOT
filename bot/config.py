"""Runtime settings, read from environment variables (Railway -> Variables)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # optional: load a local .env file during development
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_id: int
    db_path: Path
    log_level: str = "INFO"
    broadcast_rate: float = 20.0  # messages per second (Telegram limit is ~30)
    join_cache_seconds: int = 120  # how long a successful membership check is trusted


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Add it in Railway -> Variables.")

    try:
        owner_id = int(os.getenv("OWNER_ID", "0").strip() or "0")
    except ValueError:
        owner_id = 0
    if owner_id <= 0:
        raise RuntimeError("OWNER_ID must be your numeric Telegram user ID.")

    db_path = Path(os.getenv("DB_PATH", "data/bot.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        rate = float(os.getenv("BROADCAST_RATE", "20"))
    except ValueError:
        rate = 20.0
    rate = min(max(rate, 1.0), 30.0)

    return Settings(
        bot_token=token,
        owner_id=owner_id,
        db_path=db_path,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        broadcast_rate=rate,
    )
