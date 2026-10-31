import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from app.bot.handlers import update_game_message


class AsyncIterator:
    def __init__(self, items):
        self.items = items
    def __aiter__(self):
        self._iter = iter(self.items)
        return self
    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class TestUpdateGameMessage(unittest.IsolatedAsyncioTestCase):
    @patch("app.bot.handlers.get_db")
    async def test_update_game_message_broadcasts_to_all_messages(self, mock_get_db):
        db = MagicMock()
        db.participants.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=AsyncIterator([]))))
        mock_get_db.return_value = db
        
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"
        game = {
            "_id": ObjectId(game_id),
            "title": "Футбол",
            "start_at": MagicMock(strftime=lambda fmt: "20:00" if "%H" in fmt else "01.11.2026"),
            "teams_count": 3,
            "players_per_team": 6,
            "max_players": 18,
            "price": 200,
            "status": "registration_open",
            "friends_allowed": False,
            "messages": [
                {"chat_id": -1001, "message_id": 10},
                {"chat_id": -1002, "message_id": 20},
                {"chat_id": -1003, "message_id": 30},
            ]
        }
        
        await update_game_message(bot, game)
        
        self.assertEqual(bot.edit_message_text.call_count, 3)
        called_chat_ids = {call.kwargs["chat_id"] for call in bot.edit_message_text.call_args_list}
        self.assertEqual(called_chat_ids, {-1001, -1002, -1003})


if __name__ == "__main__":
    unittest.main()
