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


@pytest.mark.asyncio
async def test_leave_game_and_status_guard(test_app, player_token):
    game_id = "6724123456789abcdef01234"
    # 1. Successful leave during registration_open
    mock_game_open = {"_id": ObjectId(game_id), "status": "registration_open", "max_players": 15}
    with patch("app.api.routers.games.get_db") as mock_get_db, \
         patch("app.api.routers.games.GameRepository") as mock_repo_cls, \
         patch("app.api.routers.games.ParticipantRepository") as mock_part_cls, \
         patch("app.api.routers.games.update_game_message", new_callable=AsyncMock):
        mock_get_db.return_value = MagicMock()
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=mock_game_open)
        mock_repo_cls.return_value = repo

        part = MagicMock()
        part.decline_player = AsyncMock()
        mock_part_cls.return_value = part

        headers = {"Authorization": f"Bearer {player_token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(f"/api/games/{game_id}/leave", headers=headers)
            assert res.status_code == 200
            assert res.json()["status"] == "declined"
            part.decline_player.assert_called_once()

    # 2. Blocked leave during payment_collection
    mock_game_pay = {"_id": ObjectId(game_id), "status": "payment_collection", "max_players": 15}
    with patch("app.api.routers.games.get_db") as mock_get_db, \
         patch("app.api.routers.games.GameRepository") as mock_repo_cls:
        mock_get_db.return_value = MagicMock()
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=mock_game_pay)
        mock_repo_cls.return_value = repo

        headers = {"Authorization": f"Bearer {player_token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(f"/api/games/{game_id}/leave", headers=headers)
            assert res.status_code == 400
            assert "Action not permitted" in res.json()["detail"]


@pytest.mark.asyncio
async def test_friends_limits_enforced(test_app, player_token):
    game_id = "6724123456789abcdef01234"
    mock_game = {"_id": ObjectId(game_id), "status": "registration_open", "friends_allowed": True}
    with patch("app.api.routers.games.get_db") as mock_get_db, \
         patch("app.api.routers.games.GameRepository") as mock_repo_cls, \
         patch("app.api.routers.games.ParticipantRepository") as mock_part_cls:
        mock_get_db.return_value = MagicMock()
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=mock_game)
        mock_repo_cls.return_value = repo

        part = MagicMock()
        # User already has 3 friends
        part.count_friends_by_user = AsyncMock(return_value=3)
        mock_part_cls.return_value = part

        headers = {"Authorization": f"Bearer {player_token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(f"/api/games/{game_id}/friends", json={"friend_name": "Friend 4"}, headers=headers)
            assert res.status_code == 400
            assert "Maximum 3 friends" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_participant_status_reorder(test_app, admin_token):
    game_id = "6724123456789abcdef01234"
    part_id = "6724123456789abcdef01235"
    mock_part = {"_id": ObjectId(part_id), "game_id": ObjectId(game_id), "status": "reserve"}

    with patch("app.api.routers.admin.get_db") as mock_get_db, \
         patch("app.api.routers.admin.ParticipantRepository") as mock_part_cls, \
         patch("app.api.routers.admin.update_game_message", new_callable=AsyncMock):
        mock_get_db.return_value = MagicMock()
        part_repo = MagicMock()
        part_repo.get = AsyncMock(return_value=mock_part)
        part_repo.move_to_confirmed = AsyncMock()
        mock_part_cls.return_value = part_repo

        headers = {"Authorization": f"Bearer {admin_token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.patch(
                f"/api/admin/games/{game_id}/participants/{part_id}",
                json={"status": "confirmed"},
                headers=headers,
            )
            assert res.status_code == 200
            part_repo.move_to_confirmed.assert_called_once_with(game_id, part_id)


@pytest.mark.asyncio
async def test_admin_edit_max_players_triggers_normalization(test_app, admin_token):
    game_id = "6724123456789abcdef01234"
    mock_game = {"_id": ObjectId(game_id), "max_players": 15, "status": "registration_open"}

    with patch("app.api.routers.admin.get_db") as mock_get_db, \
         patch("app.api.routers.admin.GameRepository") as mock_game_cls, \
         patch("app.api.routers.admin.ParticipantRepository") as mock_part_cls, \
         patch("app.api.routers.admin.trigger_sync"):
        mock_db = MagicMock()
        mock_db.games.update_one = AsyncMock()
        mock_get_db.return_value = mock_db

        game_repo = MagicMock()
        game_repo.get_by_id = AsyncMock(return_value=mock_game)
        mock_game_cls.return_value = game_repo

        part_repo = MagicMock()
        part_repo.normalize_roster = AsyncMock()
        mock_part_cls.return_value = part_repo

        headers = {"Authorization": f"Bearer {admin_token}"}
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.patch(
                f"/api/admin/games/{game_id}",
                json={"max_players": 10},
                headers=headers,
            )
            assert res.status_code == 200
            assert res.json()["status"] == "updated"
            part_repo.normalize_roster.assert_called_once_with(game_id, 10)

