import unittest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from bson import ObjectId
from app.repositories.games import GameRepository


class TestNewGameShort(unittest.IsolatedAsyncioTestCase):
    async def test_create_game_defaults(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId("64a8b79f2e3d4c5b6a7b8c9d")))

        repo = GameRepository(db)
        game = await repo.create_game(
            title="Футбол",
            start_at=datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            created_by=123,
        )

        self.assertEqual(game["max_players"], 15)
        self.assertEqual(game["hourly_rate"], 600)
        self.assertEqual(game["duration_minutes"], 90)
        self.assertEqual(game["price"], 0)
        self.assertEqual(game["friends_open_after_hours"], 6)


if __name__ == "__main__":
    unittest.main()
