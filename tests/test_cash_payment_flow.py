import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.bot.keyboards import admin_game_keyboard, admin_post_finish_keyboard
from app.repositories.payments import PaymentRepository
from app.services.render import format_game_message


def test_admin_keyboards_cash_button_present():
    game_id = "6724123456789abcdef01234"
    kb_game = admin_game_keyboard(game_id, friends_allowed=False, status="finished")
    assert kb_game is not None
    texts = [b.text for row in kb_game.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in kb_game.inline_keyboard for b in row]
    assert "💵 Оплата наличными" in texts
    assert f"admin:{game_id}:confirm_cash_payments" in callbacks

    kb_post = admin_post_finish_keyboard(game_id)
    texts_post = [b.text for row in kb_post.inline_keyboard for b in row]
    callbacks_post = [b.callback_data for row in kb_post.inline_keyboard for b in row]
    assert "💵 Оплата наличными" in texts_post
    assert f"admin:{game_id}:confirm_cash_payments" in callbacks_post

    for row in kb_game.inline_keyboard + kb_post.inline_keyboard:
        for b in row:
            assert len(b.callback_data.encode("utf-8")) <= 64


def test_render_cash_closed_game():
    from datetime import datetime, timezone
    game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "title": "Футбол в пятницу",
        "status": "closed",
        "payment_method": "cash",
        "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
        "duration_minutes": 90,
        "hourly_rate": 600,
        "total_cost": 900,
        "price": 60,
        "max_players": 15,
    }
    p1_id = ObjectId()
    p2_id = ObjectId()
    participants = [
        {"_id": p1_id, "display_name": "Иван", "status": "confirmed", "type": "player"},
        {"_id": p2_id, "display_name": "Петр", "status": "confirmed", "type": "player"},
    ]
    payments = [
        {"participant_id": p1_id, "status": "paid", "amount": 60, "payment_method": "cash"},
        {"participant_id": p2_id, "status": "not_played", "amount": 0, "payment_method": "cash"},
    ]

    msg = format_game_message(game, participants, payments)
    assert "💵 Аренда поля: <b>900 грн</b> — по <b>60 грн</b> с игрока (наличные)" in msg
    assert "✅ Оплата наличными зафиксирована. Всем спасибо за игру!" in msg
    assert "• Иван — <b>✅ оплатил</b>" in msg
    assert "• Петр — <b>🚫 не играл</b>" in msg


@pytest.mark.asyncio
async def test_record_cash_payments_in_payment_repo():
    db = MagicMock()
    game_id = "6724123456789abcdef01234"
    p1_id = ObjectId()
    p2_id = ObjectId()
    participants = [
        {"_id": p1_id, "status": "confirmed"},
        {"_id": p2_id, "status": "confirmed"},
    ]

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=participants)
    db.participants.find = MagicMock(return_value=mock_cursor)
    db.payments.update_one = AsyncMock()

    pay_repo = PaymentRepository(db)
    await pay_repo.record_cash_payments(game_id, amount=60, excluded_participant_ids={str(p2_id)})

    assert db.payments.update_one.call_count == 2
    calls = db.payments.update_one.call_args_list

    # p1 (playing)
    call_p1 = calls[0]
    assert call_p1[0][0]["participant_id"] == p1_id
    assert call_p1[0][1]["$set"]["status"] == "paid"
    assert call_p1[0][1]["$set"]["amount"] == 60
    assert call_p1[0][1]["$set"]["payment_method"] == "cash"
    assert call_p1[0][1]["$set"]["confirmed_by_admin"] is True

    # p2 (excluded / not played)
    call_p2 = calls[1]
    assert call_p2[0][0]["participant_id"] == p2_id
    assert call_p2[0][1]["$set"]["status"] == "not_played"
    assert call_p2[0][1]["$set"]["amount"] == 0
    assert call_p2[0][1]["$set"]["payment_method"] == "cash"
    assert call_p2[0][1]["$set"]["confirmed_by_admin"] is True


@pytest.mark.asyncio
async def test_execute_cash_close_game():
    from app.bot.handlers import execute_cash_close_game
    db = MagicMock()
    game_id = "6724123456789abcdef01234"
    p1_id = ObjectId()
    p2_id = ObjectId()

    game_doc = {
        "_id": ObjectId(game_id),
        "title": "Игра 1",
        "status": "finished",
        "hourly_rate": 600,
        "friends_allowed": False,
    }
    participants = [
        {"_id": p1_id, "status": "confirmed"},
        {"_id": p2_id, "status": "confirmed"},
    ]

    db.games.find_one = AsyncMock(return_value=game_doc)
    db.games.update_one = AsyncMock()

    async def async_cursor(*args, **kwargs):
        for p in participants:
            yield p

    mock_find = MagicMock()
    mock_find.sort = MagicMock(return_value=async_cursor())
    mock_find.to_list = AsyncMock(return_value=participants)
    db.participants.find = MagicMock(return_value=mock_find)
    db.participants.count_documents = AsyncMock(return_value=2)
    db.payments.update_one = AsyncMock()

    bot = AsyncMock()
    edit_message_fn = AsyncMock()
    callback = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update_msg:
        await execute_cash_close_game(
            bot=bot,
            game_id=game_id,
            minutes=90,
            edit_message_fn=edit_message_fn,
            callback=callback,
            excluded_participant_ids={str(p2_id)},
        )

        # Check game update in db
        db.games.update_one.assert_awaited_once()
        game_update = db.games.update_one.call_args[0][1]["$set"]
        assert game_update["status"] == "closed"
        assert game_update["payment_method"] == "cash"
        assert game_update["duration_minutes"] == 90
        assert game_update["total_cost"] == 900
        assert game_update["price"] == 900  # 1 player playing -> 900 / 1 = 900

        mock_update_msg.assert_awaited_once()
        edit_message_fn.assert_awaited_once()
        msg_text = edit_message_fn.call_args[0][0]
        assert "Игра закрыта (оплата наличными)" in msg_text
        assert "900 грн" in msg_text
        callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_callback_cash_payment_flow():
    from app.bot.handlers import admin_callback, PENDING_ROSTER_VERIFICATIONS
    admin_id = 12345
    game_id = "6724123456789abcdef01234"
    p1_id = ObjectId()
    participants = [{"_id": p1_id, "display_name": "Игрок", "status": "confirmed"}]

    db = MagicMock()
    async def async_cursor(*args, **kwargs):
        for p in participants:
            yield p

    mock_find = MagicMock()
    mock_find.sort = MagicMock(return_value=async_cursor())
    db.participants.find = MagicMock(return_value=mock_find)
    db.participants.count_documents = AsyncMock(return_value=1)

    game_doc = {
        "_id": ObjectId(game_id),
        "title": "Матч",
        "status": "finished",
        "hourly_rate": 600,
        "friends_allowed": False,
    }
    db.games.find_one = AsyncMock(return_value=game_doc)

    callback = MagicMock()
    callback.from_user.id = admin_id
    callback.data = f"admin:{game_id}:confirm_cash_payments"
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = MagicMock()

    PENDING_ROSTER_VERIFICATIONS.clear()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.execute_cash_close_game", new_callable=AsyncMock) as mock_close:

        # Step 1: confirm_cash_payments
        await admin_callback(callback, state)
        assert admin_id in PENDING_ROSTER_VERIFICATIONS
        assert PENDING_ROSTER_VERIFICATIONS[admin_id]["is_cash"] is True
        callback.message.edit_text.assert_called_once()
        assert "Проверка состава (оплата наличными)" in callback.message.edit_text.call_args[0][0]

        # Step 2: pay_dur_menu
        callback.data = f"admin:{game_id}:pay_dur_menu"
        callback.message.edit_text.reset_mock()
        await admin_callback(callback, state)
        callback.message.edit_text.assert_called_once()
        text_dur = callback.message.edit_text.call_args[0][0]
        assert "Оплата наличными" in text_dur
        kb_dur = callback.message.edit_text.call_args[1]["reply_markup"]
        back_btn = kb_dur.inline_keyboard[-1][0]
        assert back_btn.callback_data == f"admin:{game_id}:confirm_cash_payments"

        # Step 3: paydur:90
        callback.data = f"admin:{game_id}:paydur:90"
        await admin_callback(callback, state)
        mock_close.assert_awaited_once()
        assert mock_close.call_args[0][1] == game_id
        assert mock_close.call_args[0][2] == 90

