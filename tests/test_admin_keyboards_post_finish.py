import pytest
from app.bot.keyboards import (
    admin_game_keyboard,
    admin_post_finish_keyboard,
    admin_confirm_keyboard,
    game_keyboard,
)


def test_admin_keyboard_hides_payment_collection_before_finished():
    for st in ["registration_open", "friends_allowed", "game_started", "registration_closed"]:
        kb = admin_game_keyboard("gid", friends_allowed=False, status=st)
        texts = [b.text for row in kb.inline_keyboard for b in row]
        assert "💳 Начать сбор оплат" not in texts
        assert "🏁 Завершить игру" in texts


def test_admin_keyboard_in_finished_status():
    kb = admin_game_keyboard("gid", friends_allowed=False, status="finished")
    assert kb is not None
    texts = [b.text for row in kb.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "💳 Начать сбор оплат" in texts
    assert "admin:gid:confirm_payments" in callbacks
    assert "🏁 Завершить игру" not in texts


def test_admin_keyboard_in_payment_collection():
    kb = admin_game_keyboard("gid", friends_allowed=False, status="payment_collection")
    assert kb is not None
    texts = [b.text for row in kb.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "💳 Начать сбор оплат" not in texts
    assert "🏁 Завершить игру" not in texts
    assert "✅ Завершить сбор оплат" in texts
    assert "admin:gid:confirm_close_payments" in callbacks


def test_admin_keyboard_in_closed_and_cancelled():
    assert admin_game_keyboard("gid", friends_allowed=False, status="closed") is None
    assert admin_game_keyboard("gid", friends_allowed=False, status="cancelled") is None


def test_admin_post_finish_keyboard():
    kb = admin_post_finish_keyboard("gid")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "💳 Начать сбор оплат" in texts
    assert "admin:gid:confirm_payments" in callbacks
    assert "⚙️ Меню игры" in texts
    assert "admin:gid:settings" in callbacks


def test_admin_confirm_keyboard_close_payments():
    kb = admin_confirm_keyboard("gid", "close_payments")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "✅ Да, завершить сбор оплат" in texts
    assert "admin:gid:do_close_payments" in callbacks


def test_game_keyboard_in_finished_and_closed():
    # Regular users in groups should have no buttons when finished or closed
    assert game_keyboard("gid", friends_allowed=False, status="finished") is None
    assert game_keyboard("gid", friends_allowed=False, status="closed") is None
