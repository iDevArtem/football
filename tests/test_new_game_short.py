import unittest
from unittest.mock import AsyncMock, MagicMock, patch
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

    async def test_new_game_in_private_chat_links_message_for_updates(self):
        from app.bot.handlers import new_game

        message = MagicMock()
        message.from_user.id = 777
        message.from_user.first_name = "Admin"
        message.chat.id = 777
        message.chat.type = "private"
        message.text = "/new_game 2099-11-06 19:00"
        message.bot = MagicMock()

        game_id = ObjectId("64a8b79f2e3d4c5b6a7b8c9d")
        mock_game = {
            "_id": game_id,
            "title": "Футбол",
            "start_at": datetime(2099, 11, 6, 19, 0, tzinfo=timezone.utc),
            "status": "registration_open",
            "max_players": 15,
            "hourly_rate": 600,
            "duration_minutes": 90,
            "friends_open_after_hours": 6,
            "location": None,
        }

        sent_msg = MagicMock(message_id=999)

        with patch("app.bot.handlers.is_admin", return_value=True), \
             patch("app.bot.handlers.get_db") as mock_get_db, \
             patch("app.bot.handlers.UserRepository") as mock_user_cls, \
             patch("app.bot.handlers.GameRepository") as mock_game_cls, \
             patch("app.bot.handlers.SettingsRepository") as mock_settings_cls, \
             patch("app.bot.handlers.send_game_message", new_callable=AsyncMock) as mock_send_game_msg, \
             patch("app.bot.handlers.render_broadcast_menu", new_callable=AsyncMock) as mock_render_broadcast:

            user_repo = MagicMock()
            user_repo.upsert_from_telegram = AsyncMock()
            mock_user_cls.return_value = user_repo

            game_repo = MagicMock()
            game_repo.create_game = AsyncMock(return_value=mock_game)
            game_repo.add_linked_message = AsyncMock()
            mock_game_cls.return_value = game_repo

            settings_repo = MagicMock()
            settings_repo.get_default_location = AsyncMock(return_value=None)
            mock_settings_cls.return_value = settings_repo

            mock_send_game_msg.return_value = sent_msg

            await new_game(message)

            mock_send_game_msg.assert_called_once()
            call_kwargs = mock_send_game_msg.call_args[1]
            self.assertIsNotNone(call_kwargs.get("reply_markup"), "Game card in private chat must have reply_markup")

            game_repo.add_linked_message.assert_called_once_with(
                str(game_id),
                777,
                999,
                "Личные сообщения",
            )
            mock_render_broadcast.assert_called_once_with(message.bot, 777, str(game_id))


if __name__ == "__main__":
    unittest.main()

