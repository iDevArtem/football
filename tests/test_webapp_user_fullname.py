import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.auth import create_access_token, decode_access_token
from app.config.settings import get_settings
from app.api.routers.games import UserProxy
from tests.test_auth import create_valid_init_data, create_valid_widget_data, BOT_TOKEN


@pytest.fixture
def test_app():
    from app.api.routers.games import router as games_router
    from app.api.routers.auth import router as auth_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(games_router, prefix="/api/games")
    return app


def test_user_proxy_full_name():
    # User with first_name and last_name
    u1 = UserProxy(telegram_id=1, first_name="Ivan", last_name="Ivanov", username="ivanov")
    assert u1.full_name == "Ivan Ivanov"

    # User with only first_name
    u2 = UserProxy(telegram_id=2, first_name="Petr", username="petr")
    assert u2.full_name == "Petr"

    # User with extra whitespace
    u3 = UserProxy(telegram_id=3, first_name="  Anna  ", last_name="  Karenina  ")
    assert u3.full_name == "Anna Karenina"

    # User with empty names
    u4 = UserProxy(telegram_id=4, first_name="", last_name="")
    assert u4.full_name == ""


@pytest.mark.asyncio
async def test_join_game_passes_full_name_from_token(test_app):
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "max_players": 15,
        "status": "registration_open",
    }
    mock_participant = {
        "_id": ObjectId("6724123456789abcdef01235"),
        "game_id": ObjectId(game_id),
        "telegram_id": 111,
        "status": "confirmed",
        "position": 1,
        "display_name": "Ivan Ivanov",
    }

    token = create_access_token(
        {
            "sub": "111",
            "telegram_id": 111,
            "first_name": "Ivan",
            "last_name": "Ivanov",
            "username": "ivanov",
            "role": "player",
        },
        secret=get_settings().jwt_secret,
    )

    with patch("app.api.routers.games.get_db") as mock_get_db, \
         patch("app.api.routers.games.GameRepository") as mock_repo_cls, \
         patch("app.api.routers.games.ParticipantRepository") as mock_part_cls, \
         patch("app.api.routers.games.update_game_message", new_callable=AsyncMock):
        mock_get_db.return_value = MagicMock()
        repo_instance = MagicMock()
        repo_instance.get_by_id = AsyncMock(return_value=mock_game)
        mock_repo_cls.return_value = repo_instance

        part_instance = MagicMock()
        part_instance.join_player = AsyncMock(return_value=mock_participant)
        mock_part_cls.return_value = part_instance

        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(f"/api/games/{game_id}/join", headers=headers)
            assert res.status_code == 200

        # Verify join_player was called with tg_user that has full_name == "Ivan Ivanov"
        call_args = part_instance.join_player.call_args
        tg_user_arg = call_args[0][1]
        assert tg_user_arg.full_name == "Ivan Ivanov"


@pytest.mark.asyncio
async def test_join_game_fallback_to_user_repo_for_last_name(test_app):
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "max_players": 15,
        "status": "registration_open",
    }
    mock_participant = {
        "_id": ObjectId("6724123456789abcdef01235"),
        "game_id": ObjectId(game_id),
        "telegram_id": 222,
        "status": "confirmed",
        "position": 1,
        "display_name": "Alex Smith",
    }

    # Old token without last_name
    token = create_access_token(
        {
            "sub": "222",
            "telegram_id": 222,
            "first_name": "Alex",
            "username": "alex",
            "role": "player",
        },
        secret=get_settings().jwt_secret,
    )

    with patch("app.api.routers.games.get_db") as mock_get_db, \
         patch("app.api.routers.games.GameRepository") as mock_repo_cls, \
         patch("app.api.routers.games.ParticipantRepository") as mock_part_cls, \
         patch("app.api.routers.games.UserRepository") as mock_user_cls, \
         patch("app.api.routers.games.update_game_message", new_callable=AsyncMock):
        mock_get_db.return_value = MagicMock()
        repo_instance = MagicMock()
        repo_instance.get_by_id = AsyncMock(return_value=mock_game)
        mock_repo_cls.return_value = repo_instance

        part_instance = MagicMock()
        part_instance.join_player = AsyncMock(return_value=mock_participant)
        mock_part_cls.return_value = part_instance

        user_repo_instance = MagicMock()
        user_repo_instance.get_by_telegram_id = AsyncMock(return_value={
            "telegram_id": 222,
            "first_name": "Alex",
            "last_name": "Smith",
            "username": "alex",
        })
        mock_user_cls.return_value = user_repo_instance

        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(f"/api/games/{game_id}/join", headers=headers)
            assert res.status_code == 200

        call_args = part_instance.join_player.call_args
        tg_user_arg = call_args[0][1]
        assert tg_user_arg.full_name == "Alex Smith"


@pytest.mark.asyncio
async def test_auth_tma_includes_last_name_in_jwt(test_app):
    init_data = create_valid_init_data(
        {"id": 333, "first_name": "Leo", "last_name": "Messi", "username": "messi"},
        bot_token=get_settings().bot_token,
    )

    with patch("app.api.routers.auth.get_db") as mock_get_db, \
         patch("app.api.routers.auth.UserRepository") as mock_user_cls:
        mock_get_db.return_value = MagicMock()
        user_repo = MagicMock()
        user_repo.upsert_from_telegram = AsyncMock(return_value={})
        mock_user_cls.return_value = user_repo

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post("/api/auth/tma", json={"init_data": init_data})
            assert res.status_code == 200
            token = res.json()["access_token"]
            payload = decode_access_token(token, get_settings().jwt_secret)
            assert payload.get("last_name") == "Messi"
            assert payload.get("first_name") == "Leo"


@pytest.mark.asyncio
async def test_auth_widget_includes_last_name_in_jwt(test_app):
    data = create_valid_widget_data(
        {"id": 444, "first_name": "Cristiano", "last_name": "Ronaldo", "username": "cr7"},
        bot_token=get_settings().bot_token,
    )
    # create_valid_widget_data doesn't by default put last_name into hash calculation unless in dict
    # Let's recreate properly signed widget data with last_name:
    import hashlib, hmac
    widget_dict = {
        "id": "444",
        "first_name": "Cristiano",
        "last_name": "Ronaldo",
        "username": "cr7",
        "auth_date": data["auth_date"],
    }
    check_str = "\n".join(f"{k}={v}" for k, v in sorted(widget_dict.items()) if v)
    secret_key = hashlib.sha256(get_settings().bot_token.encode("utf-8")).digest()
    widget_dict["hash"] = hmac.new(secret_key, check_str.encode("utf-8"), hashlib.sha256).hexdigest()

    with patch("app.api.routers.auth.get_db") as mock_get_db, \
         patch("app.api.routers.auth.UserRepository") as mock_user_cls:
        mock_get_db.return_value = MagicMock()
        user_repo = MagicMock()
        user_repo.upsert_from_telegram = AsyncMock(return_value={})
        mock_user_cls.return_value = user_repo

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post("/api/auth/widget", json=widget_dict)
            assert res.status_code == 200
            token = res.json()["access_token"]
            payload = decode_access_token(token, get_settings().jwt_secret)
            assert payload.get("last_name") == "Ronaldo"
            assert payload.get("first_name") == "Cristiano"


@pytest.mark.asyncio
async def test_get_me_fallbacks_to_db_for_last_name(test_app):
    token = create_access_token(
        {
            "sub": "555",
            "telegram_id": 555,
            "first_name": "Luka",
            "username": "modric",
            "role": "player",
        },
        secret=get_settings().jwt_secret,
    )

    with patch("app.api.routers.auth.get_db") as mock_get_db, \
         patch("app.api.routers.auth.UserRepository") as mock_user_cls:
        mock_get_db.return_value = MagicMock()
        user_repo = MagicMock()
        user_repo.get_by_telegram_id = AsyncMock(return_value={
            "telegram_id": 555,
            "first_name": "Luka",
            "last_name": "Modric",
        })
        mock_user_cls.return_value = user_repo

        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.get("/api/auth/me", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data.get("last_name") == "Modric"
            assert data.get("first_name") == "Luka"
