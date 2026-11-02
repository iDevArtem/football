import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import pytest
from aiogram.exceptions import TelegramBadRequest

from app.services.render import (
    format_game_header,
    format_game_message,
    format_game_rich_blocks,
    format_game_rich_html,
)
from app.services.rich_message import (
    InputRichBlockMap,
    InputRichMessage,
    SendRichMessage,
    EditMessageRich,
    build_game_rich_message,
    send_game_message,
    edit_game_message,
)


class TestRichMessage(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.game_with_loc = {
            "_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"),
            "title": "Футбол в зале",
            "status": "registration_open",
            "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            "max_players": 15,
            "hourly_rate": 600,
            "duration_minutes": 90,
            "location": {
                "title": "Пед. Универ",
                "address": "ул. Шевченка 1",
                "latitude": 48.5145,
                "longitude": 32.2619,
            },
        }
        self.game_without_loc = {
            "_id": ObjectId("64a8b79f2e3d4c5b6a7b8c9d"),
            "title": "Футбол без локации",
            "status": "registration_open",
            "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            "max_players": 15,
            "hourly_rate": 600,
            "duration_minutes": 90,
        }
        self.participants = [
            {"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c01"), "display_name": "Игрок 1", "status": "confirmed", "type": "user"},
            {"_id": ObjectId("64a8b79f2e3d4c5b6a7b8c02"), "display_name": "Игрок 2", "status": "confirmed", "type": "user"},
        ]

    def test_duration_icon_in_header_and_message(self):
        header = format_game_header(self.game_with_loc, 2)
        self.assertIn("⏱️ Длительность: <b>90 мин</b>", header)

        msg = format_game_message(self.game_with_loc, self.participants)
        self.assertIn("⏱️ Длительность: <b>90 мин</b>", msg)

    def test_input_rich_block_map_model(self):
        block = InputRichBlockMap(
            location={"latitude": 48.5145, "longitude": 32.2619},
            zoom=15,
            width=600,
            height=260,
        )
        self.assertEqual(block.type, "map")
        self.assertEqual(block.location.latitude, 48.5145)
        self.assertEqual(block.location.longitude, 32.2619)
        self.assertEqual(block.zoom, 15)
        self.assertEqual(block.width, 600)
        self.assertEqual(block.height, 260)

    def test_format_game_rich_blocks_with_location(self):
        blocks = format_game_rich_blocks(self.game_with_loc, self.participants)
        self.assertIsNotNone(blocks)
        self.assertEqual(len(blocks), 3)

        # Block 0: paragraph with header
        self.assertEqual(blocks[0]["type"], "paragraph")
        self.assertIn("Футбол в зале", blocks[0]["text"])
        self.assertIn("⏱️ Длительность: <b>90 мин</b>", blocks[0]["text"])
        self.assertIn("Пед. Универ", blocks[0]["text"])

        # Block 1: map
        self.assertEqual(blocks[1]["type"], "map")
        self.assertEqual(blocks[1]["location"]["latitude"], 48.5145)
        self.assertEqual(blocks[1]["location"]["longitude"], 32.2619)
        self.assertEqual(blocks[1]["zoom"], 15)

        # Block 2: paragraph with roster
        self.assertEqual(blocks[2]["type"], "paragraph")
        self.assertIn("Основной состав: <b>2 / 15</b>", blocks[2]["text"])
        self.assertIn("Игрок 1", blocks[2]["text"])

    def test_format_game_rich_blocks_without_location(self):
        blocks = format_game_rich_blocks(self.game_without_loc, self.participants)
        self.assertIsNone(blocks)

    def test_format_game_rich_html(self):
        html = format_game_rich_html(self.game_with_loc, self.participants)
        self.assertIsNotNone(html)
        self.assertIn("📍 <b>Пед. Универ</b>", html)
        self.assertIn("maps.google.com", html)
        self.assertIn("Футбол в зале", html)
        self.assertIn("Основной состав: <b>2 / 15</b>", html)

        html_none = format_game_rich_html(self.game_without_loc, self.participants)
        self.assertIsNone(html_none)

    def test_build_game_rich_message(self):
        msg = build_game_rich_message(self.game_with_loc, self.participants)
        self.assertIsNotNone(msg)
        self.assertIn("blocks", msg)
        self.assertEqual(len(msg["blocks"]), 3)

        msg_none = build_game_rich_message(self.game_without_loc, self.participants)
        self.assertIsNone(msg_none)

    async def test_send_game_message_calls_send_message_directly(self):
        bot = AsyncMock()
        mock_result = MagicMock(message_id=999)
        bot.send_message = AsyncMock(return_value=mock_result)

        sent = await send_game_message(bot, chat_id=-1001, game=self.game_with_loc, participants=self.participants)
        self.assertEqual(sent.message_id, 999)
        bot.send_message.assert_called_once()
        call_kwargs = bot.send_message.call_args[1]
        self.assertEqual(call_kwargs["chat_id"], -1001)
        self.assertIn("Пед. Универ", call_kwargs["text"])

    async def test_send_game_message_via_message_answer(self):
        bot = AsyncMock()
        msg_obj = AsyncMock()
        msg_obj.answer = AsyncMock(return_value=MagicMock(message_id=888))

        sent = await send_game_message(
            bot, chat_id=-1001, game=self.game_with_loc, participants=self.participants, message=msg_obj
        )
        self.assertEqual(sent.message_id, 888)
        msg_obj.answer.assert_called_once()
        self.assertIn("Пед. Универ", msg_obj.answer.call_args[1]["text"])

    async def test_send_game_message_without_location_calls_send_message_directly(self):
        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=MagicMock(message_id=777))

        sent = await send_game_message(bot, chat_id=-1001, game=self.game_without_loc, participants=self.participants)
        self.assertEqual(sent.message_id, 777)
        bot.send_message.assert_called_once()

    async def test_edit_game_message_calls_edit_message_text(self):
        bot = AsyncMock()
        mock_result = MagicMock(message_id=101)
        bot.edit_message_text = AsyncMock(return_value=mock_result)

        edited = await edit_game_message(bot, chat_id=-1001, message_id=101, game=self.game_with_loc, participants=self.participants)
        self.assertEqual(edited.message_id, 101)
        bot.edit_message_text.assert_called_once()
        call_kwargs = bot.edit_message_text.call_args[1]
        self.assertEqual(call_kwargs["chat_id"], -1001)
        self.assertEqual(call_kwargs["message_id"], 101)
        self.assertIn("Пед. Универ", call_kwargs["text"])

    async def test_edit_game_message_not_modified_returns_true(self):
        bot = AsyncMock()
        bot.edit_message_text = AsyncMock(
            side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: message is not modified")
        )

        res = await edit_game_message(bot, chat_id=-1001, message_id=102, game=self.game_with_loc, participants=self.participants)
        self.assertTrue(res)
