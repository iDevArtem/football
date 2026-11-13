import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.bot.handlers import payment_callback, friend_payment_callback


@pytest.mark.asyncio
async def test_payment_callback_paid_uses_object_id():
    game_id = "6724123456789abcdef01234"
    user_id = 123456789
    participant_id = ObjectId("6724123456789abcdef09999")

    db = MagicMock()
    db.participants.find_one = AsyncMock(return_value={
        "_id": participant_id,
        "game_id": ObjectId(game_id),
        "telegram_id": user_id,
        "type": "player",
        "status": "confirmed",
    })
    db.payments.find_one = AsyncMock(return_value=None)

    mock_game = {
        "_id": ObjectId(game_id),
        "title": "Футбол",
        "status": "payment_collection",
    }

    callback = MagicMock()
    callback.data = f"pay:{game_id}:paid"
    callback.from_user.id = user_id
    callback.bot = MagicMock()
    callback.answer = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.GameRepository") as mock_game_repo_cls, \
         patch("app.bot.handlers.PaymentRepository") as mock_pay_repo_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock), \
         patch("app.bot.handlers.check_and_notify_all_paid", new_callable=AsyncMock):

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        mock_game_repo_cls.return_value = game_repo

        pay_repo = MagicMock()
        pay_repo.mark_paid_by_user = AsyncMock(return_value=True)
        mock_pay_repo_cls.return_value = pay_repo

        await payment_callback(callback)

        db.participants.find_one.assert_called_once_with({
            "game_id": ObjectId(game_id),
            "telegram_id": user_id,
            "type": "player",
            "status": {"$in": ["confirmed", "reserve"]},
        })
        callback.answer.assert_called_with("✅ Оплата отмечена")


@pytest.mark.asyncio
async def test_friend_payment_callback_uses_object_id():
    game_id = "6724123456789abcdef01234"
    user_id = 123456789
    participant_id = "6724123456789abcdef09999"

    db = MagicMock()
    db.payments.find_one = AsyncMock(return_value=None)

    mock_game = {
        "_id": ObjectId(game_id),
        "title": "Футбол",
        "status": "payment_collection",
    }
    mock_participant = {
        "_id": ObjectId(participant_id),
        "game_id": ObjectId(game_id),
        "created_by": user_id,
        "type": "friend",
        "status": "confirmed",
        "display_name": "Друг 1",
    }

    callback = MagicMock()
    callback.data = f"pf:{participant_id}:p"
    callback.from_user.id = user_id
    callback.bot = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.answer = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.GameRepository") as mock_game_repo_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_repo_cls, \
         patch("app.bot.handlers.PaymentRepository") as mock_pay_repo_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock), \
         patch("app.bot.handlers.check_and_notify_all_paid", new_callable=AsyncMock), \
         patch("app.bot.handlers.is_admin", return_value=False):

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        mock_game_repo_cls.return_value = game_repo

        part_repo = MagicMock()
        part_repo.get = AsyncMock(return_value=mock_participant)
        part_repo.list_friends_by_user = AsyncMock(return_value=[mock_participant])
        mock_part_repo_cls.return_value = part_repo

        pay_repo = MagicMock()
        pay_repo.mark_by_participant_id = AsyncMock(return_value=True)
        pay_repo.list_by_game = AsyncMock(return_value=[])
        mock_pay_repo_cls.return_value = pay_repo

        await friend_payment_callback(callback)

        db.payments.find_one.assert_called_once_with({
            "game_id": ObjectId(game_id),
            "participant_id": ObjectId(participant_id),
        })
        callback.answer.assert_called_with("Оплата друга обновлена")
