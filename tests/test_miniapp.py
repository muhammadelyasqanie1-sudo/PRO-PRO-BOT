"""Security tests for Telegram Mini App initData validation."""
import hashlib
import hmac
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.miniapp import validate_init_data  # noqa: E402

TOKEN = "123456:unit-test-token"


def signed_init_data(user_id: int = 123, auth_date: int = 1_700_000_000) -> str:
    values = {
        "auth_date": str(auth_date),
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def main() -> None:
    now = 1_700_000_100
    result = validate_init_data(signed_init_data(), TOKEN, now=now)
    assert result["user_id"] == 123
    assert result["user"]["first_name"] == "Test"

    tampered = signed_init_data().replace("first_name", "last_name")
    try:
        validate_init_data(tampered, TOKEN, now=now)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered initData must be rejected")

    try:
        validate_init_data(signed_init_data(auth_date=1_600_000_000), TOKEN, now=now)
    except ValueError as exc:
        assert "expired" in str(exc).lower()
    else:
        raise AssertionError("expired initData must be rejected")

    try:
        validate_init_data(signed_init_data() + "&auth_date=1700000000", TOKEN, now=now)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate initData fields must be rejected")

    print("miniapp auth tests passed")


if __name__ == "__main__":
    main()
