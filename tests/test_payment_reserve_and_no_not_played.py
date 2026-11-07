import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from app.bot.keyboards import game_keyboard, payment_keyboard, friends_payment_keyboard, verify_roster_keyboard
from app.repositories.payments import PaymentRepository
from app.services.render import format_game_roster, format_game_message


def test_payment_keyboards_no_not_played_buttons():
    game_id = "6724123456789abcdef01234"
    kb = game_keyboard(game_id, friends_allowed=False, status="payment_collection")
    assert kb is not None
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "💳 Оплатил" in texts
    assert "🚫 Не играл" not in texts
    assert f"pay:{game_id}:not_played" not in callbacks

    kb_simple = payment_keyboard(game_id)
    texts_simple = [btn.text for row in kb_simple.inline_keyboard for btn in row]
    callbacks_simple = [btn.callback_data for row in kb_simple.inline_keyboard for btn in row]
    assert "💳 Оплатил" in texts_simple
    assert "🚫 Не играл" not in texts_simple
    assert f"pay:{game_id}:not_played" not in callbacks_simple


def test_friends_payment_keyboard_no_not_played_button():
    game_id = "6724123456789abcdef01234"
    friend1_id = ObjectId()
    friend2_id = ObjectId()
    friends = [
        {"_id": friend1_id, "display_name": "Друг 1"},
        {"_id": friend2_id, "display_name": "Друг 2"},
    ]
    payments_map = {
        str(friend1_id): {"status": "pending"},
        str(friend2_id): {"status": "not_played"},
    }
    kb = friends_payment_keyboard(game_id, friends, payments_map)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    # No "🚫 Не играл" buttons
    assert not any("Не играл" in t for t in texts)
    assert not any(cb.endswith(":n") for cb in callbacks)

    # For friend1 (pending), we have "✅ Оплатил"
    assert f"pf:{friend1_id}:p" in callbacks

    # For friend2 (not_played, set by admin), "✅ Оплатил" should NOT be available
    assert f"pf:{friend2_id}:p" not in callbacks
    assert any("🚫" in t and "Друг 2" in t for t in texts)


def test_verify_roster_keyboard_includes_reserve_default_excluded():
    game_id = "6724123456789abcdef01234"
    p1 = {"_id": ObjectId("6724123456789abcdef00001"), "display_name": "Иван", "status": "confirmed", "type": "player"}
    p2 = {"_id": ObjectId("6724123456789abcdef00002"), "display_name": "Петр", "status": "confirmed", "type": "friend"}
    p3 = {"_id": ObjectId("6724123456789abcdef00003"), "display_name": "Сергей", "status": "reserve", "type": "player"}

    # participants list has confirmed + reserve
    all_participants = [p1, p2, p3]
    # Reserve p3 is excluded by default
    excluded_ids = {"6724123456789abcdef00003"}

    kb = verify_roster_keyboard(game_id, all_participants, excluded_ids=excluded_ids)
    rows = kb.inline_keyboard
    # 3 participants + proceed button + back button = 5 rows
    assert len(rows) == 5

    # p1 confirmed & included
    assert rows[0][0].text == "✅ Иван"
    # p2 friend confirmed & included
    assert rows[1][0].text == "✅ 👥 Петр"
    # p3 reserve excluded
    assert rows[2][0].text == "🚫 Сергей (резерв, не играл)"
    # count of playing is 2
    assert rows[3][0].text == "➡️ К расчету (2 чел)"

    # If admin toggles p3 to included
    kb_included = verify_roster_keyboard(game_id, all_participants, excluded_ids=set())
    rows_inc = kb_included.inline_keyboard
    assert rows_inc[2][0].text == "✅ Сергей (резерв)"
    assert rows_inc[3][0].text == "➡️ К расчету (3 чел)"


def test_format_game_roster_payment_status_shows_reserve_not_played():
    from datetime import datetime, timezone
    game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "title": "Матч",
        "status": "payment_collection",
        "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
        "duration_minutes": 90,
        "hourly_rate": 600,
        "total_cost": 900,
        "price": 450,
        "max_players": 15,
    }
    p1_id = ObjectId()
    p2_id = ObjectId()
    participants = [
        {"_id": p1_id, "display_name": "Игрок 1", "status": "confirmed", "type": "player"},
        {"_id": p2_id, "display_name": "Игрок 2", "status": "reserve", "type": "player"},
    ]
    payments = [
        {"participant_id": p1_id, "status": "paid", "amount": 450},
        {"participant_id": p2_id, "status": "not_played", "amount": 0},
    ]

    roster_text = format_game_roster(game, participants, payments)
    assert "<b>Основной состав и оплата:</b>" in roster_text
    assert "• Игрок 1 — <b>✅ оплатил</b>" in roster_text
    assert "<b>Резерв:</b>" in roster_text
    assert "• Игрок 2 — <b>🚫 не играл</b>" in roster_text
    assert "🚫 Не играли: <b>1</b>" in roster_text
    assert "💳 Оплатили: <b>1</b>" in roster_text
