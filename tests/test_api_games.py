# tests/test_api_games.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.auth import create_access_token
from app.config.settings import get_settings


@pytest.fixture
def test_app():
    from app.api.routers.games import router as games_router
    from app.api.routers.admin import router as admin_router
    from app.api.routers.auth import router as auth_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(games_router, prefix="/api/games")
    app.include_router(admin_router, prefix="/api/admin")
    return app


@pytest.fixture
def player_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "111", "telegram_id": 111, "first_name": "Player1", "username": "player1", "role": "player"},
        secret=secret,
    )


@pytest.fixture
def admin_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "999", "telegram_id": 999, "first_name": "Admin1", "username": "admin1", "role": "admin"},
        secret=secret,
    )


@pytest.mark.asyncio
async def test_get_public_games(test_app):
    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "title": "⚽ Футбол 5х5",
        "start_at": datetime.now(timezone.utc),
        "status": "registration_open",
        "max_players": 15,
        "friends_allowed": False,
        "duration_minutes": 90,
        "hourly_rate": 600,
        "price": 0,
    }
    with patch("app.api.routers.games.get_db") as mock_get_db, \
         patch("app.api.routers.games.GameRepository") as mock_repo_cls, \
         patch("app.api.routers.games.ParticipantRepository") as mock_part_cls:
        mock_get_db.return_value = MagicMock()
        repo_instance = MagicMock()
        repo_instance.list_active_games = AsyncMock(return_value=[mock_game])
        mock_repo_cls.return_value = repo_instance

        part_instance = MagicMock()
        part_instance.count_confirmed = AsyncMock(return_value=10)
        part_instance.list_by_game = AsyncMock(return_value=[])
        mock_part_cls.return_value = part_instance

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.get("/api/games")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 1
            assert data[0]["id"] == "6724123456789abcdef01234"
            assert data[0]["title"] == "⚽ Футбол 5х5"


@pytest.mark.asyncio
async def test_join_game(test_app, player_token):
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
    }

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

        headers = {"Authorization": f"Bearer {player_token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(f"/api/games/{game_id}/join", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "confirmed"


@pytest.mark.asyncio
async def test_admin_only_forbidden_for_player(test_app, player_token):
    game_id = "6724123456789abcdef01234"
    headers = {"Authorization": f"Bearer {player_token}"}
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        res = await client.post(f"/api/admin/games/{game_id}/cancel", json={"reason": "Rain"}, headers=headers)
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_cancel_success(test_app, admin_token):
    game_id = "6724123456789abcdef01234"
    mock_game = {"_id": ObjectId(game_id), "status": "registration_open"}
    with patch("app.api.routers.admin.get_db") as mock_get_db, \
         patch("app.api.routers.admin.GameRepository") as mock_repo_cls, \
         patch("app.api.routers.admin.update_game_message", new_callable=AsyncMock):
        mock_get_db.return_value = MagicMock()
        repo_instance = MagicMock()
        repo_instance.get_by_id = AsyncMock(return_value=mock_game)
        repo_instance.cancel_game = AsyncMock(return_value=True)
        mock_repo_cls.return_value = repo_instance

        headers = {"Authorization": f"Bearer {admin_token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(f"/api/admin/games/{game_id}/cancel", json={"reason": "Rain"}, headers=headers)
            assert res.status_code == 200
            assert res.json()["status"] == "cancelled"
