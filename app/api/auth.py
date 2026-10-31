import hmac
import hashlib
import time
import urllib.parse
import json
from datetime import datetime, timezone, timedelta
import jwt


def validate_init_data(init_data_raw: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """
    Validates Telegram WebApp initData string using HMAC-SHA256 according to Telegram specifications:
    secret_key = HMAC_SHA256(b"WebAppData", bot_token)
    hash = HMAC_SHA256(secret_key, data_check_string).hex()
    """
    parsed = urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True)
    data_dict = dict(parsed)

    hash_val = data_dict.pop("hash", None)
    if not hash_val:
        raise ValueError("Missing hash parameter")

    auth_date = data_dict.get("auth_date")
    if not auth_date:
        raise ValueError("Missing auth_date parameter")

    try:
        auth_timestamp = int(auth_date)
    except ValueError:
        raise ValueError("Invalid auth_date format")

    if time.time() - auth_timestamp > max_age_seconds:
        raise ValueError("Data expired")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(hash_val, expected_hash):
        raise ValueError("Invalid signature")

    result = dict(data_dict)
    if "user" in result:
        try:
            result["user"] = json.loads(result["user"])
        except Exception:
            pass

    return result


def validate_widget_data(data: dict, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """
    Validates Telegram Login Widget data:
    secret_key = SHA256(bot_token)
    hash = HMAC_SHA256(secret_key, data_check_string).hex()
    """
    data_copy = dict(data)
    hash_val = data_copy.pop("hash", None)
    if not hash_val:
        raise ValueError("Missing hash parameter")

    auth_date = data_copy.get("auth_date")
    if not auth_date:
        raise ValueError("Missing auth_date parameter")

    try:
        auth_timestamp = int(auth_date)
    except ValueError:
        raise ValueError("Invalid auth_date format")

    if time.time() - auth_timestamp > max_age_seconds:
        raise ValueError("Data expired")

    # Data check string is key=value joined by \n sorted alphabetically, non-empty values
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_copy.items()) if v is not None and v != "")
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(hash_val, expected_hash):
        raise ValueError("Invalid signature")

    # Ensure id is integer
    if "id" in data_copy:
        data_copy["id"] = int(data_copy["id"])

    return data_copy


def create_access_token(data: dict, secret: str, expires_days: int = 30) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])
