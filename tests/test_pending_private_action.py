import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone, timedelta

from app.bot.handlers import (
    process_pending_private_action,
    PENDING_PRIVATE_ACTIONS,
    PENDING_FRIEND_INPUTS,
)


class TestPendingPrivateAction(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        PENDING_PRIVATE_ACTIONS.clear()
        PENDING_FRIEND_INPUTS.clear()

    @patch("app.bot.handlers.get_db")
    async def test_add_friend_auto_prompt_on_start(self, mock_get_db):
        user_id = 777
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"
        PENDING_PRIVATE_ACTIONS[user_id] = {
            "type": "add_friend",
            "game_id": game_id,
        }

        db = MagicMock()
        mock_get_db.return_value = db

        # Mock game
        now = datetime.now(timezone.utc)
        game_doc = {
            "_id": ObjectId(game_id),
            "status": "friends_allowed",
            "friends_allowed": True,
            "friends_allowed_after": now - timedelta(hours=1),
        }
        db.games.find_one = AsyncMock(return_value=game_doc)
        db.participants.count_documents = AsyncMock(return_value=0)

        message = MagicMock()
        message.chat.type = "private"
        message.from_user = MagicMock(id=user_id)
        prompt_msg = MagicMock(chat=MagicMock(id=user_id), message_id=555)
        message.answer = AsyncMock(return_value=prompt_msg)

        handled = await process_pending_private_action(message)
        self.assertTrue(handled)
        message.answer.assert_called_once_with("Введите имя друга одним сообщением:")
        self.assertIn(user_id, PENDING_FRIEND_INPUTS)
        self.assertEqual(PENDING_FRIEND_INPUTS[user_id]["game_id"], game_id)
        self.assertEqual(PENDING_FRIEND_INPUTS[user_id]["prompt_message_id"], 555)


if __name__ == "__main__":
    unittest.main()
