import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from aiogram.types import CallbackQuery

from app.bot.handlers import admin_callback


@pytest.mark.asyncio
async def test_pub_and_repub_sends_actual_payments():
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "title": "⚽ Футбол 5х5",
        "status": "payment_collection",
        "price": 60,
        "max_players": 15,
        "messages": [
            {"chat_id": -100111, "message_id": 555, "chat_title": "Основной чат"},
        ],
    }
    mock_participants = [
        {"_id": ObjectId("6724123456789abcdef00001"), "display_name": "Иван", "status": "confirmed", "type": "player"},
        {"_id": ObjectId("6724123456789abcdef00002"), "display_name": "Петр", "status": "confirmed", "type": "player"},
    ]
    mock_payments = [
        {"participant_id": ObjectId("6724123456789abcdef00001"), "status": "paid"},
        {"participant_id": ObjectId("6724123456789abcdef00002"), "status": "not_played"},
    ]
    chats = [
        {"chat_id": -100111, "title": "Основной чат", "type": "supergroup"},
        {"chat_id": -100222, "title": "Второй чат", "type": "supergroup"},
    ]

    db = MagicMock()
    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_cls, \
         patch("app.bot.handlers.PaymentRepository") as mock_pay_cls, \
         patch("app.bot.handlers.ChatRepository") as mock_chat_cls, \
         patch("app.bot.handlers.send_game_message", new_callable=AsyncMock) as mock_send_msg, \
         patch("app.bot.handlers.render_broadcast_menu", new_callable=AsyncMock) as mock_render_menu:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.add_linked_message = AsyncMock()
        game_repo.remove_linked_message = AsyncMock()
        mock_game_cls.return_value = game_repo

        part_repo = MagicMock()
        part_repo.list_by_game = AsyncMock(return_value=mock_participants)
        mock_part_cls.return_value = part_repo

        pay_repo = MagicMock()
        pay_repo.list_by_game = AsyncMock(return_value=mock_payments)
        mock_pay_cls.return_value = pay_repo

        chat_repo = MagicMock()
        chat_repo.list_active_chats = AsyncMock(return_value=chats)
        mock_chat_cls.return_value = chat_repo

        mock_send_msg.return_value = MagicMock(message_id=777)

        # 1. Test pub to second chat (not yet linked)
        cb1 = MagicMock()
        cb1.data = f"admin:{game_id}:pub:-100222"
        cb1.from_user = MagicMock(id=999)
        cb1.message = MagicMock(chat=MagicMock(type="private"))
        cb1.bot = MagicMock()
        cb1.bot.delete_message = AsyncMock()
        cb1.answer = AsyncMock()
        state = AsyncMock()

        await admin_callback(cb1, state)
        mock_send_msg.assert_awaited_once()
        assert mock_send_msg.call_args.kwargs.get("payments") == mock_payments
        assert mock_send_msg.call_args[0][1] == -100222
        game_repo.add_linked_message.assert_awaited_once_with(game_id, -100222, 777, "Второй чат")
        cb1.answer.assert_awaited_once_with("Опубликовано в Второй чат")

        # 2. Test repub to first chat (already linked)
        mock_send_msg.reset_mock()
        game_repo.add_linked_message.reset_mock()
        cb2 = MagicMock()
        cb2.data = f"admin:{game_id}:repub:-100111"
        cb2.from_user = MagicMock(id=999)
        cb2.message = MagicMock(chat=MagicMock(type="private"))
        cb2.bot = MagicMock()
        cb2.bot.delete_message = AsyncMock()
        cb2.answer = AsyncMock()

        await admin_callback(cb2, state)
        mock_send_msg.assert_awaited_once()
        assert mock_send_msg.call_args.kwargs.get("payments") == mock_payments
        assert mock_send_msg.call_args[0][1] == -100111
        # Checks old message deletion
        cb2.bot.delete_message.assert_awaited_once_with(chat_id=-100111, message_id=555)
        game_repo.remove_linked_message.assert_awaited_once_with(game_id, -100111)
        game_repo.add_linked_message.assert_awaited_once_with(game_id, -100111, 777, "Основной чат")
        cb2.answer.assert_awaited_once_with("Переотправлено вниз в Основной чат")
