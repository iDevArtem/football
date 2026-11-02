import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.bot.keyboards import verify_roster_keyboard
from app.repositories.payments import PaymentRepository
from app.bot.handlers import execute_start_payments, toggle_roster_verification, PENDING_ROSTER_VERIFICATIONS


def test_verify_roster_keyboard():
    game_id = "6724123456789abcdef01234"
    p1_id = "6724123456789abcdef01235"
    p2_id = "6724123456789abcdef01236"
    confirmed = [
        {"_id": ObjectId(p1_id), "display_name": "Иван", "type": "player"},
        {"_id": ObjectId(p2_id), "display_name": "Петр", "type": "friend"},
    ]

    # Without excluded
    kb = verify_roster_keyboard(game_id, confirmed, excluded_ids=set())
    rows = kb.inline_keyboard
    assert len(rows) == 4  # 2 players + 1 proceed + 1 back
    assert rows[0][0].text == "✅ Иван"
    assert rows[0][0].callback_data == f"vr:{game_id}:{p1_id}"
    assert rows[1][0].text == "✅ 👥 Петр"
    assert rows[2][0].text == "➡️ К расчету (2 чел)"
    assert rows[2][0].callback_data == f"admin:{game_id}:pay_dur_menu"

    # With p1 excluded
    kb_ex = verify_roster_keyboard(game_id, confirmed, excluded_ids={p1_id})
    rows_ex = kb_ex.inline_keyboard
    assert rows_ex[0][0].text == "🚫 Иван (не играл)"
    assert rows_ex[1][0].text == "✅ 👥 Петр"
    assert rows_ex[2][0].text == "➡️ К расчету (1 чел)"

    # Verify all callback lengths <= 64 bytes
    for row in rows_ex:
        for btn in row:
            assert len(btn.callback_data.encode("utf-8")) <= 64


@pytest.mark.asyncio
async def test_ensure_for_game_with_excluded():
    db = MagicMock()
    game_id = "6724123456789abcdef01234"
    p1_id = ObjectId()
    p2_id = ObjectId()
    participants = [
        {"_id": p1_id, "status": "confirmed"},
        {"_id": p2_id, "status": "confirmed"},
    ]

    async def async_cursor():
        for p in participants:
            yield p

    db.participants.find = MagicMock(return_value=async_cursor())
    db.payments.find_one = AsyncMock(return_value=None)
    db.payments.update_one = AsyncMock()

    pay_repo = PaymentRepository(db)
    # p2 is excluded
    await pay_repo.ensure_for_game(game_id, amount=75, excluded_participant_ids={str(p2_id)})

    assert db.payments.update_one.call_count == 2
    calls = db.payments.update_one.call_args_list

    # Call for p1 (playing)
    call_p1 = calls[0]
    filter_p1 = call_p1[0][0]
    update_p1 = call_p1[0][1]
    assert filter_p1["participant_id"] == p1_id
    assert update_p1["$set"]["amount"] == 75
    assert update_p1["$set"]["status"] == "pending"
    assert update_p1["$set"]["confirmed_by_admin"] is False

    # Call for p2 (excluded / not played)
    call_p2 = calls[1]
    filter_p2 = call_p2[0][0]
    update_p2 = call_p2[0][1]
    assert filter_p2["participant_id"] == p2_id
    assert update_p2["$set"]["amount"] == 0
    assert update_p2["$set"]["status"] == "not_played"
    assert update_p2["$set"]["confirmed_by_admin"] is True


@pytest.mark.asyncio
async def test_execute_start_payments_with_excluded():
    db = MagicMock()
    game_id = "6724123456789abcdef01234"
    p1_id = ObjectId()
    p2_id = ObjectId()
    mock_game = {
        "_id": ObjectId(game_id),
        "title": "Матч 5х5",
        "hourly_rate": 600,
        "status": "game_started",
    }
    participants = [
        {"_id": p1_id, "status": "confirmed"},
        {"_id": p2_id, "status": "confirmed"},
    ]

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.GameRepository") as mock_game_repo_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_repo_cls, \
         patch("app.bot.handlers.PaymentRepository") as mock_pay_repo_cls, \
         patch("app.bot.handlers.SettingsRepository") as mock_settings_repo_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock):

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        mock_game_repo_cls.return_value = game_repo

        part_repo = MagicMock()
        part_repo.list_by_game = AsyncMock(return_value=participants)
        part_repo.count_confirmed = AsyncMock(return_value=2)
        mock_part_repo_cls.return_value = part_repo

        pay_repo = MagicMock()
        pay_repo.ensure_for_game = AsyncMock()
        mock_pay_repo_cls.return_value = pay_repo

        settings_repo = MagicMock()
        settings_repo.set_default_payment_details = AsyncMock()
        mock_settings_repo_cls.return_value = settings_repo

        db.games.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        bot = MagicMock()

        # 90 min at 600 грн/ч = 900 грн. 2 подтверждено, но p2 исключен -> 1 играющий -> 900 грн
        await execute_start_payments(
            bot=bot,
            game_id=game_id,
            minutes=90,
            card_number="4441 2222 3333 4444",
            recipient="Олег",
            excluded_participant_ids={str(p2_id)},
        )

        update_call = db.games.update_one.call_args[0][1]["$set"]
        assert update_call["price"] == 900
        pay_repo.ensure_for_game.assert_called_once_with(game_id, 900, excluded_participant_ids={str(p2_id)})


@pytest.mark.asyncio
async def test_toggle_roster_verification_callback():
    admin_id = 999
    game_id = "6724123456789abcdef01234"
    p1_id = "6724123456789abcdef01235"
    db = MagicMock()

    async def async_cursor():
        yield {"_id": ObjectId(p1_id), "display_name": "Игрок 1", "status": "confirmed"}

    cursor_mock = MagicMock()
    cursor_mock.sort = MagicMock(return_value=async_cursor())
    db.participants.find = MagicMock(return_value=cursor_mock)

    callback = MagicMock()
    callback.from_user.id = admin_id
    callback.data = f"vr:{game_id}:{p1_id}"
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    PENDING_ROSTER_VERIFICATIONS.clear()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.is_admin", return_value=True):
        # 1st toggle: excludes p1
        await toggle_roster_verification(callback)
        assert p1_id in PENDING_ROSTER_VERIFICATIONS[admin_id]["excluded_ids"]
        callback.message.edit_text.assert_called_once()

        # 2nd toggle: un-excludes p1
        await toggle_roster_verification(callback)
        assert p1_id not in PENDING_ROSTER_VERIFICATIONS[admin_id]["excluded_ids"]
