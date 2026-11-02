import unittest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from pymongo import ReturnDocument
from app.repositories.participants import ParticipantRepository
from app.repositories.games import GameRepository
from app.db.mongo import create_indexes


class TestRosterAtomic(unittest.IsolatedAsyncioTestCase):
    async def test_create_game_sets_last_position(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId("64a8b79f2e3d4c5b6a7b8c9d")))

        game_repo = GameRepository(db)
        from datetime import datetime, timezone
        game = await game_repo.create_game(
            title="Футбол",
            start_at=datetime.now(timezone.utc),
            created_by=123,
        )
        self.assertEqual(game.get("last_position"), 0)
        inserted_doc = db.games.insert_one.call_args[0][0]
        self.assertEqual(inserted_doc.get("last_position"), 0)

    async def test_next_position_atomic_increment(self):
        db = MagicMock()
        db.games = MagicMock()
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"
        # When game already has last_position: 5, increment returns 6
        db.games.find_one_and_update = AsyncMock(return_value={"_id": ObjectId(game_id), "last_position": 6})

        repo = ParticipantRepository(db)
        pos = await repo.next_position(game_id)
        self.assertEqual(pos, 6)
        db.games.find_one_and_update.assert_called_once_with(
            {"_id": ObjectId(game_id)},
            {"$inc": {"last_position": 1}},
            return_document=ReturnDocument.AFTER,
        )

    async def test_next_position_fallback_seeds_from_participants(self):
        db = MagicMock()
        db.games = MagicMock()
        db.participants = MagicMock()
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"

        # Game exists but lacks last_position
        db.games.find_one_and_update = AsyncMock(return_value={"_id": ObjectId(game_id)})
        # Last participant was position 12
        db.participants.find_one = AsyncMock(return_value={"position": 12})
        db.games.update_one = AsyncMock()

        repo = ParticipantRepository(db)
        pos = await repo.next_position(game_id)
        self.assertEqual(pos, 13)
        db.games.update_one.assert_called_once_with(
            {"_id": ObjectId(game_id)},
            {"$set": {"last_position": 13}},
        )

    async def test_create_indexes_has_partial_unique(self):
        db = MagicMock()
        db.users = MagicMock()
        db.chats = MagicMock()
        db.games = MagicMock()
        db.participants = MagicMock()
        db.payments = MagicMock()

        db.users.create_index = AsyncMock()
        db.chats.create_index = AsyncMock()
        db.games.create_index = AsyncMock()
        db.participants.create_index = AsyncMock()
        db.payments.create_index = AsyncMock()

        await create_indexes(db)

        # Check call arguments on participants.create_index
        calls = db.participants.create_index.call_args_list
        # Should have unique=True with partial filter for player
        player_index_call = None
        for call in calls:
            keys = call[0][0]
            if keys == [("game_id", 1), ("telegram_id", 1)]:
                player_index_call = call
                break

        self.assertIsNotNone(player_index_call, "Index for (game_id, telegram_id) should exist")
        self.assertTrue(player_index_call.kwargs.get("unique"))
        self.assertEqual(
            player_index_call.kwargs.get("partialFilterExpression"),
            {"type": "player", "telegram_id": {"$type": "number"}},
        )
