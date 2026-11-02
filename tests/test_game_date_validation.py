import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from pydantic import ValidationError
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.routers.admin import CreateGameRequest, router as admin_router
from app.api.auth import create_access_token
from app.config.settings import get_settings
from app.bot.handlers import new_game, edit_date, admin_edit_value


@pytest.fixture
def admin_api_app():
    app = FastAPI()
    app.include_router(admin_router, prefix="/api/admin")
    return app


@pytest.fixture
def admin_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "999", "telegram_id": 999, "first_name": "Admin1", "username": "admin1", "role": "admin"},
        secret=secret,
    )


@pytest.mark.asyncio
async def test_new_game_rejects_past_date_short_format():
    message = MagicMock()
    message.from_user.id = 123
    message.text = "/new_game 2020-01-01 19:00"
    message.reply = AsyncMock()

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_get_db:
        await new_game(message)

        message.reply.assert_called_once_with("❌ Нельзя создать игру в прошлом.")
        mock_get_db.assert_not_called()


@pytest.mark.asyncio
async def test_new_game_rejects_past_date_long_format():
    message = MagicMock()
    message.from_user.id = 123
    message.text = "/new_game 2020-01-01 19:00 3 5 200 90 6"
    message.reply = AsyncMock()

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_get_db:
        await new_game(message)

        message.reply.assert_called_once_with("❌ Нельзя создать игру в прошлом.")
        mock_get_db.assert_not_called()


@pytest.mark.asyncio
async def test_new_game_accepts_future_date():
    message = MagicMock()
    message.from_user.id = 123
    message.text = "/new_game 2099-01-01 19:00"
    message.chat.type = "private"
    message.answer = AsyncMock()

    mock_game = {"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"), "title": "Футбол", "start_at": datetime(2099, 1, 1, 19, 0)}

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_get_db, \
         patch("app.bot.handlers.UserRepository") as mock_user_cls, \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.render_broadcast_menu", new_callable=AsyncMock):
        user_repo = MagicMock()
        user_repo.upsert_from_telegram = AsyncMock()
        mock_user_cls.return_value = user_repo

        game_repo = MagicMock()
        game_repo.create_game = AsyncMock(return_value=mock_game)
        mock_game_cls.return_value = game_repo

        await new_game(message)

        game_repo.create_game.assert_called_once()
        created_start_at = game_repo.create_game.call_args[1]["start_at"]
        assert created_start_at.year == 2099


@pytest.mark.asyncio
async def test_edit_date_rejects_past_date():
    message = MagicMock()
    message.from_user.id = 123
    message.text = "/edit_date 2020-01-01 19:00"
    message.reply = AsyncMock()

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_get_db:
        await edit_date(message)

        message.reply.assert_called_once()
        reply_text = message.reply.call_args[0][0]
        assert "прошл" in reply_text
        mock_get_db.assert_not_called()


@pytest.mark.asyncio
async def test_edit_date_accepts_future_date():
    message = MagicMock()
    message.from_user.id = 123
    message.chat.id = -100123
    message.text = "/edit_date 2099-01-01 19:00"
    message.answer = AsyncMock()
    message.bot = MagicMock()

    mock_game = {"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"), "title": "Футбол"}

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_get_db, \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock), \
         patch("app.bot.handlers.delete_message_safely", new_callable=AsyncMock):
        game_repo = MagicMock()
        game_repo.get_active_for_chat = AsyncMock(return_value=mock_game)
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.update_start_at = AsyncMock()
        mock_game_cls.return_value = game_repo

        await edit_date(message)

        game_repo.update_start_at.assert_called_once()
        updated_start_at = game_repo.update_start_at.call_args[0][1]
        assert updated_start_at.year == 2099


@pytest.mark.asyncio
async def test_admin_edit_value_rejects_past_date():
    message = MagicMock()
    message.from_user.id = 123
    message.text = "2020-01-01 19:00"
    message.answer = AsyncMock()

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"game_id": "64a8b79f2e3d4c5b6a7b8c9d", "edit_action": "edit_date"})
    state.clear = AsyncMock()

    mock_game = {"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"), "status": "registration_open"}

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_get_db, \
         patch("app.bot.handlers.GameRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=mock_game)
        mock_repo.update_start_at = AsyncMock()
        mock_repo_cls.return_value = mock_repo

        await admin_edit_value(message, state)

        message.answer.assert_called_once()
        answer_text = message.answer.call_args[0][0]
        assert "прошл" in answer_text
        mock_repo.update_start_at.assert_not_called()
        state.clear.assert_not_called()


def test_create_game_request_validation():
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    future_date = datetime.now(timezone.utc) + timedelta(days=1)

    # Past date must raise ValidationError
    with pytest.raises(ValidationError):
        CreateGameRequest(start_at=past_date)

    # Future date must succeed
    req = CreateGameRequest(start_at=future_date)
    assert req.start_at == future_date


@pytest.mark.asyncio
async def test_api_admin_create_game_validation(admin_api_app, admin_token):
    past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    headers = {"Authorization": f"Bearer {admin_token}"}

    async with AsyncClient(transport=ASGITransport(app=admin_api_app), base_url="http://test") as client:
        # Past date -> 422 Unprocessable Entity
        res_past = await client.post(
            "/api/admin/games",
            json={"title": "Test Game", "start_at": past_date},
            headers=headers,
        )
        assert res_past.status_code == 422
        assert "прошл" in res_past.text

        # Future date -> 200 OK
        with patch("app.api.routers.admin.get_db") as mock_get_db, \
             patch("app.api.routers.admin.GameRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.create_game = AsyncMock(return_value={"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d")})
            mock_repo_cls.return_value = mock_repo

            res_future = await client.post(
                "/api/admin/games",
                json={"title": "Test Game", "start_at": future_date},
                headers=headers,
            )
            assert res_future.status_code == 200
            assert res_future.json()["status"] == "created"
