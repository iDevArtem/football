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
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "999", "telegram_id": 999, "first_name": "Admin1", "role": "admin"},
        secret=secret,
    )


@pytest.fixture
def player_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "111", "telegram_id": 111, "first_name": "Player1", "role": "player"},
        secret=secret,
    )


@pytest.fixture
def other_player_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "222", "telegram_id": 222, "first_name": "Player2", "role": "player"},
        secret=secret,
    )


@pytest.mark.asyncio
async def test_admin_start_game_and_block_join(app, admin_token, player_token):
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "title": "Матч 5х5",
        "status": "game_started",
        "messages": [],
    }
    with patch("app.api.routers.admin.get_db") as mock_admin_db, \
         patch("app.api.routers.games.get_db") as mock_games_db, \
         patch("app.api.routers.admin.GameRepository") as mock_admin_game_repo_cls, \
         patch("app.api.routers.games.GameRepository") as mock_games_repo_cls, \
         patch("app.api.routers.admin.update_game_message", new_callable=AsyncMock):

        repo = MagicMock()
        repo.get = AsyncMock(return_value=mock_game)
        repo.set_status = AsyncMock(return_value=True)
        mock_admin_game_repo_cls.return_value = repo

        games_repo = MagicMock()
        games_repo.get_by_id = AsyncMock(return_value=mock_game)
        mock_games_repo_cls.return_value = games_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Admin starts game
            res = await client.post(
                f"/api/admin/games/{game_id}/start",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "game_started"

            # 2. Player attempts to join during game_started -> 400
            join_res = await client.post(
                f"/api/games/{game_id}/join",
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert join_res.status_code == 400


@pytest.mark.asyncio
async def test_admin_add_guest(app, admin_token):
    game_id = "6724123456789abcdef01234"
    guest_id = ObjectId("6724123456789abcdef09999")
    mock_game = {"_id": ObjectId(game_id), "title": "Матч", "max_players": 15, "messages": []}
    mock_guest = {
        "_id": guest_id,
        "type": "guest",
        "status": "confirmed",
        "display_name": "Игорь (гость)",
        "position": 5,
        "added_by_telegram_id": 999,
        "telegram_id": None,
    }
    with patch("app.api.routers.admin.get_db"), \
         patch("app.api.routers.admin.GameRepository") as mock_game_repo_cls, \
         patch("app.api.routers.admin.ParticipantRepository") as mock_part_repo_cls, \
         patch("app.api.routers.admin.update_game_message", new_callable=AsyncMock):

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        mock_game_repo_cls.return_value = game_repo

        part_repo = MagicMock()
        part_repo.add_guest = AsyncMock(return_value=mock_guest)
        mock_part_repo_cls.return_value = part_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/games/{game_id}/participants/guest",
                json={"display_name": "Игорь (гость)"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["type"] == "guest"
            assert data["display_name"] == "Игорь (гость)"


@pytest.mark.asyncio
async def test_admin_start_payment_with_card(app, admin_token):
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "title": "Матч",
        "hourly_rate": 600,
        "messages": [],
    }
    with patch("app.api.routers.admin.get_db") as mock_db, \
         patch("app.api.routers.admin.GameRepository") as mock_game_repo_cls, \
         patch("app.api.routers.admin.ParticipantRepository") as mock_part_repo_cls, \
         patch("app.api.routers.admin.PaymentRepository") as mock_pay_repo_cls, \
         patch("app.api.routers.admin.SettingsRepository") as mock_settings_repo_cls, \
         patch("app.api.routers.admin.update_game_message", new_callable=AsyncMock):

        db = MagicMock()
        db.games.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        mock_db.return_value = db

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        mock_game_repo_cls.return_value = game_repo

        part_repo = MagicMock()
        part_repo.count_confirmed = AsyncMock(return_value=10)
        mock_part_repo_cls.return_value = part_repo

        pay_repo = MagicMock()
        pay_repo.ensure_for_game = AsyncMock()
        mock_pay_repo_cls.return_value = pay_repo

        settings_repo = MagicMock()
        settings_repo.set_default_payment_details = AsyncMock()
        mock_settings_repo_cls.return_value = settings_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/games/{game_id}/payment/start",
                json={
                    "duration_minutes": 90,
                    "card_number": "4441 2222 3333 4444",
                    "card_recipient": "Тест Т."
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "payment_collection"
            settings_repo.set_default_payment_details.assert_called_once_with(
                "4441 2222 3333 4444", "Тест Т."
            )


@pytest.mark.asyncio
async def test_friend_payment_authorization(app, player_token, other_player_token):
    game_id = "6724123456789abcdef01234"
    friend_id = "6724123456789abcdef09999"

    with patch("app.api.routers.games.get_db") as mock_db, \
         patch("app.api.routers.games.PaymentRepository") as mock_pay_repo_cls:

        pay_repo = MagicMock()
        # Returns True when player 111 updates their own friend
        # Returns False when player 222 tries to update player 111's friend
        async def mock_mark(game_id, participant_id, status, actor_telegram_id, is_admin=False):
            if actor_telegram_id == 111:
                return True
            return False

        pay_repo.mark_by_participant_id = AsyncMock(side_effect=mock_mark)
        mock_pay_repo_cls.return_value = pay_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Player 111 pays for friend -> OK
            ok_res = await client.post(
                f"/api/games/{game_id}/payment/status",
                json={"participant_id": friend_id, "status": "paid"},
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert ok_res.status_code == 200
            assert ok_res.json()["status"] == "paid"

            # Player 222 tries to update Player 111's friend -> 403
            err_res = await client.post(
                f"/api/games/{game_id}/payment/status",
                json={"participant_id": friend_id, "status": "paid"},
                headers={"Authorization": f"Bearer {other_player_token}"},
            )
            assert err_res.status_code == 403
