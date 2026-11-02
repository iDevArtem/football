import pytest
from app.bot.keyboards import (
    game_keyboard,
    admin_game_keyboard,
    card_confirmation_keyboard,
)


def test_game_keyboard_game_started():
    kb = game_keyboard("6724123456789abcdef01234", friends_allowed=True, status="game_started")
    assert kb is not None
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "⚙️ Управление" in buttons
    assert "✅ Буду" not in buttons
    assert "❌ Не буду" not in buttons
    assert "➕ Добавить друга" not in buttons


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
