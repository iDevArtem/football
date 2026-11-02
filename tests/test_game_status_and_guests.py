import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from datetime import datetime, timezone
from app.repositories.games import GameRepository, ACTIVE_STATUSES
from app.repositories.participants import ParticipantRepository
from app.repositories.settings import SettingsRepository


@pytest.mark.asyncio
async def test_game_started_status_and_payment_details():
    assert "game_started" in ACTIVE_STATUSES

    db = MagicMock()
    db.games = MagicMock()
    game_id = "6724123456789abcdef01234"

    # mock get
    db.games.find_one = AsyncMock(return_value={
        "_id": ObjectId(game_id),
        "status": "game_started",
        "payment_details": {"card_number": "4441 1111 2222 3333", "recipient": "Иван И."}
    })
    # mock update_one
    db.games.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))

    game_repo = GameRepository(db)
    ok = await game_repo.set_status(game_id, "game_started")
    assert ok is True

    ok_card = await game_repo.set_payment_details(game_id, "4441 1111 2222 3333", "Иван И.")
    assert ok_card is True

    updated = await game_repo.get(game_id)
    assert updated["status"] == "game_started"
    assert updated["payment_details"]["card_number"] == "4441 1111 2222 3333"


@pytest.mark.asyncio
async def test_settings_repository_fallback_and_update():
    db = MagicMock()
    db.settings = MagicMock()
    # first call returns None -> falls back to settings
    db.settings.find_one = AsyncMock(return_value=None)
    db.settings.update_one = AsyncMock(return_value=MagicMock(matched_count=1))

    settings_repo = SettingsRepository(db)
    details = await settings_repo.get_default_payment_details()
    assert "card_number" in details

    await settings_repo.set_default_payment_details("1234 5678 9012 3456", "Петр П.")
    db.settings.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_add_guest_participant():
    db = MagicMock()
    db.games = MagicMock()
    db.participants = MagicMock()
    game_id = "6724123456789abcdef01234"

    inserted_id = ObjectId("6724123456789abcdef09999")
    db.games.find_one_and_update = AsyncMock(return_value={"_id": ObjectId(game_id), "last_position": 7})
    db.participants.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inserted_id))
    db.participants.find_one = AsyncMock(return_value={
        "_id": inserted_id,
        "type": "guest",
        "status": "confirmed",
        "display_name": "Саня (гость)",
        "position": 7,
        "added_by_telegram_id": 123,
        "telegram_id": None,
    })

    game = {"_id": ObjectId(game_id), "title": "Guest Game"}
    part_repo = ParticipantRepository(db)

    guest = await part_repo.add_guest(game, "Саня (гость)", added_by_telegram_id=123)
    assert guest["type"] == "guest"
    assert guest["status"] == "confirmed"
    assert guest["display_name"] == "Саня (гость)"
    assert guest["position"] == 7
    assert guest["added_by_telegram_id"] == 123
    assert guest["telegram_id"] is None
