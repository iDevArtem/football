import pytest
from app.bot.keyboards import (
    game_keyboard,
    admin_game_keyboard,
    card_confirmation_keyboard,
)


def test_game_keyboard_game_started():
    kb = game_keyboard("6724123456789abcdef01234", friends_allowed=True, status="game_started")
    assert kb is None


def test_game_keyboard_no_admin_button():
    kb = game_keyboard("6724123456789abcdef01234", friends_allowed=True, status="registration_open")
    assert kb is not None
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "⚙️ Управление" not in buttons
    assert "✅ Буду" in buttons
    assert "❌ Не буду" in buttons
    assert "➕ Добавить друга" in buttons


def test_admin_keyboard_start_game_and_payments():
    # Before game start: should have "▶️ Начать игру"
    kb_open = admin_game_keyboard("6724123456789abcdef01234", friends_allowed=False, status="registration_closed")
    buttons_open = [btn.text for row in kb_open.inline_keyboard for btn in row]
    assert "▶️ Начать игру" in buttons_open

    # During game_started: should have "💳 Начать сбор оплат"
    kb_live = admin_game_keyboard("6724123456789abcdef01234", friends_allowed=False, status="game_started")
    buttons_live = [btn.text for row in kb_live.inline_keyboard for btn in row]
    assert "💳 Начать сбор оплат" in buttons_live
    assert "▶️ Начать игру" not in buttons_live


def test_card_confirmation_keyboard():
    kb = card_confirmation_keyboard("6724123456789abcdef01234", 90)
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Оставить эту карту" in b for b in buttons)
    assert any("Изменить карту" in b for b in buttons)
    assert any("Назад" in b for b in buttons)


from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from app.bot.handlers import execute_start_payments

@pytest.mark.asyncio
async def test_execute_start_payments():
    db = MagicMock()
    game_id = "6724123456789abcdef01234"
    mock_game = {
        "_id": ObjectId(game_id),
        "title": "Матч 5х5",
        "hourly_rate": 600,
        "friends_allowed": False,
        "status": "game_started",
    }
    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.GameRepository") as mock_game_repo_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_repo_cls, \
         patch("app.bot.handlers.PaymentRepository") as mock_pay_repo_cls, \
         patch("app.bot.handlers.SettingsRepository") as mock_settings_repo_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update:
        
        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        mock_game_repo_cls.return_value = game_repo

        part_repo = MagicMock()
        part_repo.count_confirmed = AsyncMock(return_value=10)
        mock_part_repo_cls.return_value = part_repo

        pay_repo = MagicMock()
        pay_repo.ensure_for_game = AsyncMock()
        mock_pay_repo_cls.return_value = pay_repo

        settings_repo = MagicMock()
        settings_repo.set_default_payment_details = AsyncMock()
        mock_settings_repo_cls.return_value = settings_repo

        db.games.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        bot = MagicMock()

        await execute_start_payments(
            bot=bot,
            game_id=game_id,
            minutes=90,
            card_number="4441 2222 3333 4444",
            recipient="Олег О.",
        )

        # 90 min at 600 грн/час = 900 грн / 10 игроков = 90 грн/игрок
        update_call = db.games.update_one.call_args[0][1]["$set"]
        assert update_call["status"] == "payment_collection"
        assert update_call["duration_minutes"] == 90
        assert update_call["total_cost"] == 900
        assert update_call["price"] == 90
        assert update_call["payment_details"]["card_number"] == "4441 2222 3333 4444"
        assert update_call["payment_details"]["recipient"] == "Олег О."

        pay_repo.ensure_for_game.assert_called_once_with(game_id, 90)
        settings_repo.set_default_payment_details.assert_called_once_with("4441 2222 3333 4444", "Олег О.")
        mock_update.assert_called_once()


@pytest.mark.asyncio
async def test_admin_callback_does_not_edit_game_card():
    from app.bot.handlers import admin_callback
    from unittest.mock import AsyncMock, MagicMock, patch
    from bson import ObjectId

    game_id = str(ObjectId())
    user_id = 12345
    card_message_id = 999

    callback = MagicMock()
    callback.data = f"admin:{game_id}:settings"
    callback.from_user.id = user_id
    callback.message.chat.id = user_id
    callback.message.chat.type = "private"
    callback.message.message_id = card_message_id
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.bot = MagicMock()

    mock_game = {
        "_id": ObjectId(game_id),
        "status": "registration_open",
        "friends_allowed": False,
        "messages": [
            {"chat_id": user_id, "message_id": card_message_id, "chat_title": "Личные сообщения"}
        ],
    }

    state = AsyncMock()

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_get_db, \
         patch("app.bot.handlers.send_private_message", new_callable=AsyncMock) as mock_send_private:
        
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=mock_game)
        with patch("app.bot.handlers.GameRepository", return_value=mock_repo):
            await admin_callback(callback, state)

        # Must NOT edit the card message in place
        callback.message.edit_text.assert_not_called()
        # Must send private message instead
        mock_send_private.assert_called_once()
        callback.answer.assert_called_once()
