import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from app.services.render import format_game_message
from app.bot.handlers import admin_callback, AdminEditState
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository


def test_render_friend_and_guest_icon():
    game = {
        "_id": ObjectId(),
        "title": "Футбол",
        "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
        "duration_minutes": 90,
        "hourly_rate": 600,
        "price": 100,
        "max_players": 15,
        "status": "registration_open",
        "friends_allowed": True,
    }
    participants = [
        {"_id": ObjectId(), "status": "confirmed", "type": "player", "display_name": "Artem"},
        {"_id": ObjectId(), "status": "confirmed", "type": "friend", "display_name": "Igor"},
        {"_id": ObjectId(), "status": "confirmed", "type": "guest", "display_name": "Sanya"},
        {"_id": ObjectId(), "status": "reserve", "type": "friend", "display_name": "Grisha"},
        {"_id": ObjectId(), "status": "reserve", "type": "player", "display_name": "Oleg"},
    ]

    text = format_game_message(game, participants)
    assert "1. • Artem" in text
    assert "2. 👥 Igor" in text
    assert "3. 👥 Sanya" in text
    assert "1. 👥 Grisha" in text
    assert "2. • Oleg" in text


def test_render_friend_and_guest_in_payment_collection():
    p_artem_id = ObjectId()
    p_igor_id = ObjectId()
    p_sanya_id = ObjectId()
    game = {
        "_id": ObjectId(),
        "title": "Футбол",
        "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
        "duration_minutes": 90,
        "hourly_rate": 600,
        "price": 100,
        "max_players": 15,
        "status": "payment_collection",
        "friends_allowed": True,
    }
    participants = [
        {"_id": p_artem_id, "status": "confirmed", "type": "player", "display_name": "Artem"},
        {"_id": p_igor_id, "status": "confirmed", "type": "friend", "display_name": "Igor"},
        {"_id": p_sanya_id, "status": "confirmed", "type": "guest", "display_name": "Sanya"},
    ]
    payments = [
        {"participant_id": p_artem_id, "status": "paid"},
        {"participant_id": p_igor_id, "status": "pending"},
        {"participant_id": p_sanya_id, "status": "not_played"},
    ]

    text = format_game_message(game, participants, payments)
    assert "1. • Artem — <b>✅ оплатил</b>" in text
    assert "2. 👥 Igor — <b>❌ не оплатил</b>" in text
    assert "3. 👥 Sanya — <b>🚫 не играл</b>" in text


@pytest.mark.asyncio
async def test_admin_callback_edit_duration_and_friends_hours():
    admin_id = 999999
    game_id = str(ObjectId())

    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=admin_id, user_id=admin_id)
    state = FSMContext(storage=storage, key=key)

    callback = MagicMock()
    callback.from_user.id = admin_id
    callback.data = f"admin:{game_id}:edit_duration"
    callback.message = MagicMock()
    callback.message.chat.id = admin_id
    callback.message.message_id = 42
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    mock_db = MagicMock()
    mock_db.games.find_one = AsyncMock(return_value={
        "_id": ObjectId(game_id),
        "status": "registration_open",
        "friends_allowed": False,
    })

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db", return_value=mock_db):
        await admin_callback(callback, state)

        callback.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == AdminEditState.waiting_value
        state_data = await state.get_data()
        assert state_data["edit_action"] == "edit_duration"
        assert state_data["game_id"] == game_id

        # Now test edit_friends_hours
        callback.answer.reset_mock()
        callback.data = f"admin:{game_id}:edit_friends_hours"
        await admin_callback(callback, state)

        callback.answer.assert_called_once()
        state_data2 = await state.get_data()
        assert state_data2["edit_action"] == "edit_friends_hours"


@pytest.mark.asyncio
async def test_api_add_and_remove_friend_updates_message():
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.api.routers.games import router as games_router
    from app.api.auth import create_access_token
    from app.config.settings import get_settings

    app = FastAPI()
    app.include_router(games_router, prefix="/api/games")

    token = create_access_token(
        {"sub": "111", "telegram_id": 111, "first_name": "Player1", "username": "player1", "role": "player"},
        secret=get_settings().jwt_secret,
    )
    headers = {"Authorization": f"Bearer {token}"}

    game_id = str(ObjectId())
    friend_part_id = str(ObjectId())
    mock_game = {
        "_id": ObjectId(game_id),
        "status": "registration_open",
        "friends_allowed": True,
        "max_players": 15,
    }

    mock_db = MagicMock()
    mock_game_repo = MagicMock()
    mock_game_repo.get_by_id = AsyncMock(return_value=mock_game)
    mock_game_repo.get = AsyncMock(return_value=mock_game)

    mock_part_repo = MagicMock()
    mock_part_repo.count_friends_by_user = AsyncMock(return_value=0)
    mock_part_repo.add_friend = AsyncMock(return_value={
        "_id": ObjectId(friend_part_id),
        "game_id": ObjectId(game_id),
        "telegram_id": None,
        "type": "friend",
        "status": "confirmed",
        "added_by_telegram_id": 111,
        "display_name": "Friend Bob",
        "position": 5,
    })
    mock_part_repo.cancel_friend = AsyncMock(return_value=True)

    mock_bot = MagicMock()
    mock_update_message = AsyncMock()

    with patch("app.api.routers.games.get_db", return_value=mock_db), \
         patch("app.api.routers.games.GameRepository", return_value=mock_game_repo), \
         patch("app.api.routers.games.ParticipantRepository", return_value=mock_part_repo), \
         patch("app.api.routers.games.get_bot", return_value=mock_bot), \
         patch("app.api.routers.games.update_game_message", mock_update_message):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Add friend
            res = await client.post(f"/api/games/{game_id}/friends", json={"friend_name": "Friend Bob"}, headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["type"] == "friend"
            assert data["display_name"] == "Friend Bob"
            mock_update_message.assert_called_once_with(mock_bot, mock_game)

            # Remove friend
            mock_update_message.reset_mock()
            res_del = await client.delete(f"/api/games/{game_id}/friends/{friend_part_id}", headers=headers)
            assert res_del.status_code == 200
            assert res_del.json()["status"] == "removed"
            mock_update_message.assert_called_once_with(mock_bot, mock_game)


@pytest.mark.asyncio
async def test_api_add_friend_fails_when_friends_not_allowed():
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.api.routers.games import router as games_router
    from app.api.auth import create_access_token
    from app.config.settings import get_settings

    app = FastAPI()
    app.include_router(games_router, prefix="/api/games")

    token = create_access_token(
        {"sub": "111", "telegram_id": 111, "first_name": "Player1", "username": "player1", "role": "player"},
        secret=get_settings().jwt_secret,
    )
    headers = {"Authorization": f"Bearer {token}"}

    game_id = str(ObjectId())
    mock_game = {
        "_id": ObjectId(game_id),
        "status": "registration_open",
        "friends_allowed": False,
        "max_players": 15,
    }

    mock_db = MagicMock()
    mock_game_repo = MagicMock()
    mock_game_repo.get_by_id = AsyncMock(return_value=mock_game)
    mock_part_repo = MagicMock()

    with patch("app.api.routers.games.get_db", return_value=mock_db), \
         patch("app.api.routers.games.GameRepository", return_value=mock_game_repo), \
         patch("app.api.routers.games.ParticipantRepository", return_value=mock_part_repo):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/api/games/{game_id}/friends", json={"friend_name": "Friend Bob"}, headers=headers)
            assert res.status_code == 400
            assert "Friends registration is not allowed yet" in res.json()["detail"]
