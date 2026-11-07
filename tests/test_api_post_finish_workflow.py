import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.auth import create_access_token
from app.config.settings import get_settings


@pytest.fixture
def app():
    from app.api.routers.games import router as games_router
    from app.api.routers.admin import router as admin_router
    from app.api.routers.auth import router as auth_router

    application = FastAPI()
    application.include_router(auth_router, prefix="/api/auth")
    application.include_router(games_router, prefix="/api/games")
    application.include_router(admin_router, prefix="/api/admin")
    return application


@pytest.fixture
def admin_token():
    return create_access_token(
        {"sub": "999", "telegram_id": 999, "first_name": "Admin", "role": "admin"},
        secret=get_settings().jwt_secret,
    )


@pytest.fixture
def player_token():
    return create_access_token(
        {"sub": "111", "telegram_id": 111, "first_name": "Player", "role": "player"},
        secret=get_settings().jwt_secret,
    )


@pytest.mark.asyncio
async def test_start_payment_fails_if_game_not_finished(app, admin_token):
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "status": "game_started",
        "hourly_rate": 600,
    }

    with patch("app.api.routers.admin.get_db") as mock_db, \
         patch("app.api.routers.admin.GameRepository") as mock_game_repo:
        repo = MagicMock()
        repo.get = AsyncMock(return_value=mock_game)
        mock_game_repo.return_value = repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/games/{game_id}/payment/start",
                json={"duration_minutes": 90},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res.status_code == 400
            assert "завершения игры" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_finish_and_close_endpoints(app, admin_token):
    game_id = "6724123456789abcdef01234"
    game_state = {
        "_id": ObjectId(game_id),
        "status": "game_started",
        "hourly_rate": 600,
    }

    db = MagicMock()
    db.games.update_one = AsyncMock()

    with patch("app.api.routers.admin.get_db", return_value=db), \
         patch("app.api.routers.admin.GameRepository") as mock_game_repo, \
         patch("app.api.routers.admin.update_game_message", new_callable=AsyncMock):

        repo = MagicMock()
        async def mock_get(gid):
            return game_state
        repo.get = AsyncMock(side_effect=mock_get)

        async def mock_finish(gid, finish_note=None):
            game_state["status"] = "finished"
            game_state["finish_note"] = finish_note
        repo.finish_game = AsyncMock(side_effect=mock_finish)

        async def mock_close(gid):
            game_state["status"] = "closed"
        repo.close_game = AsyncMock(side_effect=mock_close)

        mock_game_repo.return_value = repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Finish game
            res_finish = await client.post(
                f"/api/admin/games/{game_id}/finish",
                json={"finish_note": "Счет 5:3"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res_finish.status_code == 200
            assert res_finish.json()["status"] == "finished"
            assert game_state["status"] == "finished"
            assert game_state["finish_note"] == "Счет 5:3"

            # 2. Close game
            res_close = await client.post(
                f"/api/admin/games/{game_id}/close",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res_close.status_code == 200
            assert res_close.json()["status"] == "closed"
            assert game_state["status"] == "closed"


@pytest.mark.asyncio
async def test_player_cannot_join_or_leave_when_finished(app, player_token):
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "status": "finished",
    }

    with patch("app.api.routers.games.get_db"), \
         patch("app.api.routers.games.GameRepository") as mock_game_repo:
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=mock_game)
        mock_game_repo.return_value = repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_join = await client.post(
                f"/api/games/{game_id}/join",
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert res_join.status_code == 400

            res_leave = await client.post(
                f"/api/games/{game_id}/leave",
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert res_leave.status_code == 400
