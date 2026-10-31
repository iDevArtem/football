import unittest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from bson import ObjectId
from app.repositories.games import GameRepository, ACTIVE_STATUSES


class TestGameRepositoryMultiGroup(unittest.IsolatedAsyncioTestCase):
    async def test_create_game_has_messages_array(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId("64a8b79f2e3d4c5b6a7b8c9d")))
        
        repo = GameRepository(db)
        game = await repo.create_game(
            title="Футбол",
            start_at=datetime.now(timezone.utc),
            teams_count=3,
            players_per_team=6,
            price=200,
            duration_minutes=90,
            friends_open_after_hours=6,
            created_by=123,
        )
        self.assertEqual(game["messages"], [])
        db.games.insert_one.assert_called_once()
        inserted_doc = db.games.insert_one.call_args[0][0]
        self.assertEqual(inserted_doc["messages"], [])

    async def test_add_and_remove_linked_message(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.update_one = AsyncMock()
        
        repo = GameRepository(db)
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"
        
        await repo.add_linked_message(game_id, -1001, 45, "Main Group")
        db.games.update_one.assert_called_once()
        call_filter, call_update = db.games.update_one.call_args[0]
        self.assertEqual(call_filter, {"_id": ObjectId(game_id)})
        self.assertIn("$push", call_update)
        self.assertEqual(call_update["$push"]["messages"]["chat_id"], -1001)
        self.assertEqual(call_update["$push"]["messages"]["message_id"], 45)
        self.assertEqual(call_update["$push"]["messages"]["chat_title"], "Main Group")

        db.games.update_one.reset_mock()
        await repo.remove_linked_message(game_id, -1001)
        db.games.update_one.assert_called_once()
        call_filter, call_update = db.games.update_one.call_args[0]
        self.assertEqual(call_filter, {"_id": ObjectId(game_id)})
        self.assertIn("$pull", call_update)
        self.assertEqual(call_update["$pull"]["messages"]["chat_id"], -1001)

    async def test_get_active_for_chat_queries_messages(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.find_one = AsyncMock(return_value={"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"), "title": "Футбол"})
        
        repo = GameRepository(db)
        game = await repo.get_active_for_chat(-1001)
        self.assertIsNotNone(game)
        
        db.games.find_one.assert_called_once()
        call_filter = db.games.find_one.call_args[0][0]
        self.assertEqual(call_filter["messages.chat_id"], -1001)
        self.assertEqual(call_filter["status"], {"$in": ACTIVE_STATUSES})


if __name__ == "__main__":
    unittest.main()
