import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from aiogram.types import InlineKeyboardMarkup


@pytest.mark.asyncio
async def test_finish_game_transitions_to_post_finish_prompt_without_deleting_menu():
    from app.bot.handlers import admin_finish_game_content

    photo_mock = MagicMock(file_id="tg_photo_123")
    message = MagicMock()
    message.from_user.id = 999
    message.chat.id = 999
    message.media_group_id = None
    message.photo = [photo_mock]
    message.video = None
    message.text = None
    message.caption = "Победа 5:3!"
    message.delete = AsyncMock()
    message.bot = MagicMock()
    message.bot.edit_message_text = AsyncMock()
    message.answer = AsyncMock()

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "game_id": "6724123456789abcdef01234",
        "admin_message_id": 5555,
    })
    state.clear = AsyncMock()

    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "status": "game_started",
        "messages": [{"chat_id": -100111, "message_id": 1}],
    }

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db"), \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update, \
         patch("app.bot.handlers.broadcast_media_report", new_callable=AsyncMock) as mock_broadcast:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.finish_game = AsyncMock()

        with patch("app.bot.handlers.GameRepository", return_value=game_repo):
            await admin_finish_game_content(message, state)

        # Message with photo in PM should be deleted
        message.delete.assert_called_once()
        # Game finished in repo
        game_repo.finish_game.assert_called_once()
        # Admin menu message should NOT be deleted, it should be EDITED to post-finish prompt
        message.bot.delete_message.assert_not_called()
        message.bot.edit_message_text.assert_called_once()
        call_kwargs = message.bot.edit_message_text.call_args.kwargs
        assert call_kwargs["message_id"] == 5555
        assert "Игра завершена" in call_kwargs["text"]
        assert "сбору оплат" in call_kwargs["text"]
        reply_markup = call_kwargs["reply_markup"]
        assert isinstance(reply_markup, InlineKeyboardMarkup)
        btn_texts = [b.text for row in reply_markup.inline_keyboard for b in row]
        assert "💳 Начать сбор оплат" in btn_texts


@pytest.mark.asyncio
async def test_check_and_notify_all_paid_sends_pm_with_close_button():
    from app.bot.handlers import check_and_notify_all_paid

    bot = MagicMock()
    bot.send_message = AsyncMock()

    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "created_by": 999,
        "status": "payment_collection",
        "title": "Футбол",
    }
    participants = [
        {"_id": ObjectId("6724123456789abcdef01111"), "status": "confirmed"},
        {"_id": ObjectId("6724123456789abcdef02222"), "status": "confirmed"},
    ]
    payments = [
        {"participant_id": ObjectId("6724123456789abcdef01111"), "status": "paid"},
        {"participant_id": ObjectId("6724123456789abcdef02222"), "status": "paid"},
    ]

    with patch("app.bot.handlers.get_db") as mock_db:
        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.try_mark_all_paid_notified = AsyncMock(return_value=True)

        part_repo = MagicMock()
        part_repo.list_by_game = AsyncMock(return_value=participants)

        pay_repo = MagicMock()
        pay_repo.list_by_game = AsyncMock(return_value=payments)

        with patch("app.bot.handlers.GameRepository", return_value=game_repo), \
             patch("app.bot.handlers.ParticipantRepository", return_value=part_repo), \
             patch("app.bot.handlers.PaymentRepository", return_value=pay_repo):

            await check_and_notify_all_paid(bot, game_id)

            bot.send_message.assert_called_once()
            call_kwargs = bot.send_message.call_args.kwargs
            assert call_kwargs["chat_id"] == 999
            assert "Все игроки отметили оплату" in call_kwargs["text"]
            btn_texts = [b.text for row in call_kwargs["reply_markup"].inline_keyboard for b in row]
            assert "✅ Завершить сбор оплат" in btn_texts


@pytest.mark.asyncio
async def test_close_payments_sets_closed_status_and_deletes_admin_menu():
    from app.bot.handlers import admin_callback

    callback = MagicMock()
    callback.data = "admin:6724123456789abcdef01234:do_close_payments"
    callback.from_user.id = 999
    callback.message = MagicMock()
    callback.message.chat.type = "private"
    callback.message.delete = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()

    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "status": "payment_collection",
        "messages": [],
    }

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db"), \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.close_game = AsyncMock()

        with patch("app.bot.handlers.GameRepository", return_value=game_repo):
            await admin_callback(callback, state)

        game_repo.close_game.assert_called_once_with("6724123456789abcdef01234")
        mock_update.assert_called_once()
        callback.message.delete.assert_called_once()
        callback.answer.assert_called_once_with("Сбор оплат завершён ✅")


@pytest.mark.asyncio
async def test_payments_command_requires_finished_status():
    from app.bot.handlers import payments

    message = MagicMock()
    message.from_user.id = 999
    message.chat.type = "private"
    message.reply = AsyncMock()
    message.answer = AsyncMock()

    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "status": "game_started",
        "hourly_rate": 600,
    }

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_active_game_or_reply", return_value=mock_game):

        await payments(message)
        message.reply.assert_called_once()
        assert "Сначала завершите игру" in message.reply.call_args[0][0]
