import pytest
from datetime import datetime, timezone
from app.services.render import format_game_message, format_game_roster, status_text


def test_status_text_closed():
    assert status_text("closed") == "закрыта"


def test_render_payment_collection_preserves_finish_note():
    game = {
        "title": "Футбол 5х5",
        "start_at": datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc),
        "status": "payment_collection",
        "finish_note": "Синие победили 5:3! Всем спасибо за игру!",
        "hourly_rate": 600,
        "duration_minutes": 90,
        "price": 200,
        "total_cost": 900,
        "payment_details": {"card_number": "4441 1111 2222 3333", "recipient": "Олег"},
    }
    participants = [
        {"_id": "p1", "display_name": "Игрок 1", "status": "confirmed", "type": "player"},
    ]
    payments = [
        {"participant_id": "p1", "status": "paid"},
    ]
    msg = format_game_message(game, participants, payments)
    assert "Синие победили 5:3! Всем спасибо за игру!" in msg
    assert "4441 1111 2222 3333" in msg
    assert "Оплатили: <b>1</b>" in msg


def test_render_closed_game_shows_final_thanks_and_no_card():
    game = {
        "title": "Футбол 5х5",
        "start_at": datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc),
        "status": "closed",
        "finish_note": "Синие победили 5:3!",
        "hourly_rate": 600,
        "duration_minutes": 90,
        "price": 200,
        "total_cost": 900,
        "payment_details": {"card_number": "4441 1111 2222 3333", "recipient": "Олег"},
    }
    participants = [
        {"_id": "p1", "display_name": "Игрок 1", "status": "confirmed", "type": "player"},
    ]
    payments = [
        {"participant_id": "p1", "status": "paid"},
    ]
    msg = format_game_message(game, participants, payments)
    assert "Синие победили 5:3!" in msg
    assert "4441 1111 2222 3333" not in msg
    assert "Сбор оплат завершён" in msg
    assert "Оплатили: <b>1</b>" in msg
