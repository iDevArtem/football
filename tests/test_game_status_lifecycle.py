import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from app.repositories.games import GameRepository, ACTIVE_STATUSES


def test_active_statuses_includes_finished_and_excludes_closed():
    assert "finished" in ACTIVE_STATUSES
    assert "payment_collection" in ACTIVE_STATUSES
    assert "closed" not in ACTIVE_STATUSES
    assert "cancelled" not in ACTIVE_STATUSES


@pytest.mark.asyncio
async def test_close_game_sets_closed_status_and_closed_at():
    db = MagicMock()
    db.games.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    repo = GameRepository(db)

    game_id = str(ObjectId())
    await repo.close_game(game_id)

    db.games.update_one.assert_called_once()
    call_args = db.games.update_one.call_args[0]
    filter_arg, update_arg = call_args[0], call_args[1]["$set"]
    assert filter_arg == {"_id": ObjectId(game_id)}
    assert update_arg["status"] == "closed"
    assert "closed_at" in update_arg
    assert "updated_at" in update_arg


@pytest.mark.asyncio
async def test_try_mark_all_paid_notified_atomic():
    db = MagicMock()
    # First call matches document (was False or not set)
    db.games.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    repo = GameRepository(db)

    game_id = str(ObjectId())
    first_attempt = await repo.try_mark_all_paid_notified(game_id)
    assert first_attempt is True

    # Check query used atomic filter
    call_args = db.games.update_one.call_args[0]
    filter_arg, update_arg = call_args[0], call_args[1]["$set"]
    assert filter_arg == {"_id": ObjectId(game_id), "all_paid_notified": {"$ne": True}}
    assert update_arg == {"all_paid_notified": True}

    # Second call returns modified_count=0 (already notified)
    db.games.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
    second_attempt = await repo.try_mark_all_paid_notified(game_id)
    assert second_attempt is False


@pytest.mark.asyncio
async def test_guards_prevent_modifying_finished_or_closed_games():
    db = MagicMock()
    repo = GameRepository(db)

    game_id = str(ObjectId())
    # Mock game in finished status
    repo.get = AsyncMock(return_value={"_id": ObjectId(game_id), "status": "finished"})
    db.games.update_one = AsyncMock()

    await repo.open_registration(game_id)
    await repo.close_friends(game_id)
    db.games.update_one.assert_not_called()

    # Mock game in closed status
    repo.get = AsyncMock(return_value={"_id": ObjectId(game_id), "status": "closed"})
    await repo.open_registration(game_id)
    await repo.close_friends(game_id)
    db.games.update_one.assert_not_called()
