import unittest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from bson import ObjectId

from app.repositories.games import GameRepository
from app.repositories.settings import SettingsRepository
from app.services.render import format_game_message
from app.bot.keyboards import admin_game_keyboard
from app.api.routers.games import serialize_game


class TestGameLocation(unittest.IsolatedAsyncioTestCase):
    async def test_settings_default_location(self):
        db = MagicMock()
        db.settings = MagicMock()
        db.settings.find_one = AsyncMock(return_value=None)
        db.settings.update_one = AsyncMock()

        repo = SettingsRepository(db)
        loc = await repo.get_default_location()
        self.assertIsNone(loc)

        # Set location
        new_loc = {
            "title": "Арена Спорт",
            "address": "ул. Полевая, 10",
            "latitude": 50.4501,
            "longitude": 30.5234,
        }
        await repo.set_default_location(
            title=new_loc["title"],
            address=new_loc["address"],
            latitude=new_loc["latitude"],
            longitude=new_loc["longitude"],
        )
        db.settings.update_one.assert_called_once()
        call_args = db.settings.update_one.call_args[0]
        self.assertEqual(call_args[0], {"_id": "default_location"})
        self.assertEqual(call_args[1]["$set"]["title"], "Арена Спорт")
        self.assertEqual(call_args[1]["$set"]["latitude"], 50.4501)

        # Retrieve when exists in db
        db.settings.find_one = AsyncMock(return_value={
            "_id": "default_location",
            "title": "Арена Спорт",
            "address": "ул. Полевая, 10",
            "latitude": 50.4501,
            "longitude": 30.5234,
        })
        retrieved = await repo.get_default_location()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["title"], "Арена Спорт")
        self.assertEqual(retrieved["latitude"], 50.4501)

    async def test_create_game_with_location(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId("64a8b79f2e3d4c5b6a7b8c9d")))

        repo = GameRepository(db)
        loc = {
            "title": "Олимпийский",
            "address": "ул. Большая Васильковская, 55",
            "latitude": 50.4334,
            "longitude": 30.5219,
        }
        game = await repo.create_game(
            title="Футбол",
            start_at=datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            created_by=123,
            location=loc,
        )
        self.assertEqual(game["location"], loc)

    async def test_update_location(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.update_one = AsyncMock()

        repo = GameRepository(db)
        loc = {
            "title": "Динамо",
            "address": "ул. Грушевского, 3",
            "latitude": 50.4512,
            "longitude": 30.5345,
        }
        await repo.update_location("64a8b79f2e3d4c5b6a7b8c9d", loc)
        db.games.update_one.assert_called_once()
        filter_arg = db.games.update_one.call_args[0][0]
        update_arg = db.games.update_one.call_args[0][1]
        self.assertEqual(filter_arg, {"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d")})
        self.assertEqual(update_arg["$set"]["location"], loc)

    async def test_add_linked_message_with_venue_id(self):
        db = MagicMock()
        db.games = MagicMock()
        db.games.update_one = AsyncMock()

        repo = GameRepository(db)
        await repo.add_linked_message(
            game_id="64a8b79f2e3d4c5b6a7b8c9d",
            chat_id=-1001,
            message_id=200,
            chat_title="Football Chat",
            venue_message_id=201,
        )
        db.games.update_one.assert_called_once()
        push_dict = db.games.update_one.call_args[0][1]["$push"]["messages"]
        self.assertEqual(push_dict["chat_id"], -1001)
        self.assertEqual(push_dict["message_id"], 200)
        self.assertEqual(push_dict["venue_message_id"], 201)

    def test_render_game_message_with_location(self):
        game = {
            "_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"),
            "title": "Футбол",
            "status": "registration_open",
            "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            "max_players": 15,
            "hourly_rate": 600,
            "duration_minutes": 90,
            "location": {
                "title": "Стадион Чемпион",
                "address": "ул. Спортивная, 5",
                "latitude": 50.4501,
                "longitude": 30.5234,
            },
        }
        text = format_game_message(game, [])
        self.assertIn("📍 Место: <a href=\"https://maps.google.com/?q=50.4501,30.5234\"><b>Стадион Чемпион</b></a> (ул. Спортивная, 5)", text)

    def test_render_game_message_without_location(self):
        game = {
            "_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"),
            "title": "Футбол",
            "status": "registration_open",
            "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            "max_players": 15,
            "hourly_rate": 600,
            "duration_minutes": 90,
        }
        text = format_game_message(game, [])
        self.assertNotIn("📍 Место:", text)

    def test_admin_keyboard_has_location_button(self):
        kb = admin_game_keyboard("64a8b79f2e3d4c5b6a7b8c9d", friends_allowed=False, status="registration_open")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        loc_btns = [b for b in buttons if b.callback_data == "admin:64a8b79f2e3d4c5b6a7b8c9d:edit_location"]
        self.assertEqual(len(loc_btns), 1)
        self.assertIn("Локация", loc_btns[0].text)

    def test_serialize_game_includes_location(self):
        loc = {
            "title": "Арена",
            "address": "ул. Мира, 1",
            "latitude": 50.1,
            "longitude": 30.2,
        }
        game = {
            "_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"),
            "title": "Футбол",
            "status": "registration_open",
            "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            "location": loc,
        }
        serialized = serialize_game(game, 0)
        self.assertIn("location", serialized)
        self.assertEqual(serialized["location"], loc)

    def test_parse_location_input(self):
        from app.utils.location import parse_location_input
        # 2 parts: lat, lng
        res = parse_location_input("50.4501, 30.5234")
        self.assertIsNotNone(res)
        self.assertEqual(res["latitude"], 50.4501)
        self.assertEqual(res["longitude"], 30.5234)
        self.assertEqual(res["title"], "Футбольное поле")

        # 3 parts: title, lat, lng
        res = parse_location_input("Арена Чемпион, 50.4501, 30.5234")
        self.assertIsNotNone(res)
        self.assertEqual(res["title"], "Арена Чемпион")
        self.assertEqual(res["latitude"], 50.4501)
        self.assertEqual(res["longitude"], 30.5234)

        # 4 parts: title, address, lat, lng
        res = parse_location_input("Арена Чемпион, ул. Полевая 5, 50.4501, 30.5234")
        self.assertIsNotNone(res)
        self.assertEqual(res["title"], "Арена Чемпион")
        self.assertEqual(res["address"], "ул. Полевая 5")
        self.assertEqual(res["latitude"], 50.4501)
        self.assertEqual(res["longitude"], 30.5234)

        # Invalid
        self.assertIsNone(parse_location_input("invalid string"))
        self.assertIsNone(parse_location_input("not, a, number, here"))

    async def test_apply_location_update(self):
        from app.bot.handlers import _apply_location_update
        db = MagicMock()
        db.games = MagicMock()
        db.games.update_one = AsyncMock()
        db.games.find_one = AsyncMock(return_value={
            "_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"),
            "title": "Футбол",
            "status": "registration_open",
            "messages": [],
            "location": {
                "title": "Арена",
                "address": "ул. Полевая, 1",
                "latitude": 50.45,
                "longitude": 30.52,
            },
        })
        db.settings = MagicMock()
        db.settings.update_one = AsyncMock()

        message = MagicMock()
        message.bot = MagicMock()
        message.answer = AsyncMock()

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"game_id": "64a8b79f2e3d4c5b6a7b8c9d"})
        state.clear = AsyncMock()

        from unittest.mock import patch
        with patch("app.bot.handlers.get_db", return_value=db), \
             patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update:
            await _apply_location_update(message, state, {
                "title": "Арена",
                "address": "ул. Полевая, 1",
                "latitude": 50.45,
                "longitude": 30.52,
            })
            db.games.update_one.assert_called_once()
            db.settings.update_one.assert_called_once()
            state.clear.assert_called_once()
            mock_update.assert_called_once()
            message.answer.assert_called_once()
            self.assertIn("Локация сохранена", message.answer.call_args[0][0])

    def test_game_keyboard_has_map_button(self):
        from app.bot.keyboards import game_keyboard
        loc = {
            "title": "Стадион Чемпион",
            "address": "ул. Спортивная, 5",
            "latitude": 50.4501,
            "longitude": 30.5234,
        }
        kb = game_keyboard("64a8b79f2e3d4c5b6a7b8c9d", friends_allowed=False, location=loc)
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        map_btns = [b for b in buttons if b.text == "📍 На карте"]
        self.assertEqual(len(map_btns), 1)
        self.assertEqual(map_btns[0].url, "https://maps.google.com/?q=50.4501,30.5234")

    async def test_new_game_single_message_with_link_preview(self):
        from app.bot.handlers import new_game
        from unittest.mock import patch

        message = MagicMock()
        message.from_user = MagicMock(id=111, first_name="Admin", username="admin")
        message.chat = MagicMock(id=-100123, type="supergroup", title="Football Group")
        message.text = "/new_game 2026-11-06 19:00"
        message.bot = MagicMock()
        message.bot.send_venue = AsyncMock()
        message.reply = AsyncMock()
        message.answer = AsyncMock(return_value=MagicMock(message_id=444))
        message.delete = AsyncMock()

        db = MagicMock()
        db.users = MagicMock()
        db.users.update_one = AsyncMock()
        db.users.find_one = AsyncMock(return_value={"telegram_id": 111, "role": "admin"})
        db.chats = MagicMock()
        db.chats.update_one = AsyncMock()
        db.games = MagicMock()
        db.games.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId("64a8b79f2e3d4c5b6a7b8c9d")))
        db.games.update_one = AsyncMock()
        db.settings = MagicMock()
        # Default location exists
        db.settings.find_one = AsyncMock(return_value={
            "_id": "default_location",
            "title": "Арена",
            "address": "ул. Полевая, 1",
            "latitude": 50.45,
            "longitude": 30.52,
        })

        with patch("app.bot.handlers.is_admin", return_value=True), \
             patch("app.bot.handlers.get_db", return_value=db):
            await new_game(message)
            # Only single message sent, send_venue is NOT called
            message.bot.send_venue.assert_not_called()
            message.answer.assert_called_once()
            call_kwargs = message.answer.call_args[1]
            self.assertIn("link_preview_options", call_kwargs)
            preview_opt = call_kwargs["link_preview_options"]
            self.assertFalse(preview_opt.is_disabled)
            self.assertTrue(preview_opt.prefer_small_media)
            self.assertFalse(preview_opt.prefer_large_media)
            self.assertEqual(preview_opt.url, "https://maps.google.com/?q=50.45,30.52")
