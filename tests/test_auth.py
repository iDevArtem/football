# tests/test_auth.py
import hmac
import hashlib
import time
import urllib.parse
import json
import pytest
from app.api.auth import validate_init_data, validate_widget_data, create_access_token, decode_access_token

BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
JWT_SECRET = "test-jwt-secret-key-at-least-32-chars-long"

def create_valid_init_data(user_dict, bot_token=BOT_TOKEN, auth_date=None):
    if auth_date is None:
        auth_date = int(time.time())
    data = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user_dict, separators=(",", ":"))
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    data["hash"] = hash_val
    return urllib.parse.urlencode(data)

def create_valid_widget_data(user_dict, bot_token=BOT_TOKEN, auth_date=None):
    if auth_date is None:
        auth_date = int(time.time())
    data = {
        "id": str(user_dict["id"]),
        "first_name": user_dict.get("first_name", ""),
        "username": user_dict.get("username", ""),
        "auth_date": str(auth_date),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()) if v)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    data["hash"] = hash_val
    return data

def test_validate_init_data_success():
    init_data = create_valid_init_data({"id": 111, "first_name": "Leo", "username": "messi"})
    parsed = validate_init_data(init_data, BOT_TOKEN)
    assert parsed["user"]["id"] == 111
    assert parsed["user"]["username"] == "messi"

def test_validate_init_data_tampered():
    init_data = create_valid_init_data({"id": 111, "first_name": "Leo"}) + "tampered"
    with pytest.raises(ValueError, match="Invalid signature"):
        validate_init_data(init_data, BOT_TOKEN)

def test_validate_init_data_expired():
    old_time = int(time.time()) - 100000
    init_data = create_valid_init_data({"id": 111, "first_name": "Leo"}, auth_date=old_time)
    with pytest.raises(ValueError, match="Data expired"):
        validate_init_data(init_data, BOT_TOKEN)

def test_validate_widget_data_success():
    data = create_valid_widget_data({"id": 222, "first_name": "Cristiano", "username": "cr7"})
    parsed = validate_widget_data(data, BOT_TOKEN)
    assert parsed["id"] == 222
    assert parsed["first_name"] == "Cristiano"

def test_validate_widget_data_tampered():
    data = create_valid_widget_data({"id": 222, "first_name": "Cristiano"})
    data["hash"] = "invalid_hash"
    with pytest.raises(ValueError, match="Invalid signature"):
        validate_widget_data(data, BOT_TOKEN)

def test_jwt_lifecycle():
    token = create_access_token({"sub": "123", "role": "admin"}, secret=JWT_SECRET, expires_days=1)
    payload = decode_access_token(token, secret=JWT_SECRET)
    assert payload["sub"] == "123"
    assert payload["role"] == "admin"


@pytest.mark.asyncio
async def test_auth_config_endpoint():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/auth/config")
        assert res.status_code == 200
        data = res.json()
        assert "bot_username" in data
        assert "webapp_url" in data
