import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone

from app.bot.keyboards import admin_game_keyboard, admin_cancel_edit_keyboard, admin_finish_game_keyboard
from app.services.render import format_game_message, status_text


def test_admin_keyboard_payment_collection_hides_pay_and_shows_finish():
    game_id = "6724123456789abcdef01234"
    kb = admin_game_keyboard(game_id, friends_allowed=False, status="payment_collection")
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "💳 Начать сбор оплат" not in buttons
    assert "🏁 Завершить игру" in buttons


def test_admin_keyboard_finish_game_available_in_active_statuses():
    game_id = "6724123456789abcdef01234"
    for st in ["registration_open", "game_started", "payment_collection"]:
        kb = admin_game_keyboard(game_id, friends_allowed=False, status=st)
        buttons = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "🏁 Завершить игру" in buttons, f"Missing in status {st}"


def test_admin_keyboard_cancelled_and_finished_returns_none():
    game_id = "6724123456789abcdef01234"
    assert admin_game_keyboard(game_id, friends_allowed=False, status="cancelled") is None
    assert admin_game_keyboard(game_id, friends_allowed=False, status="finished") is None


def test_admin_cancel_edit_keyboard():
    game_id = "6724123456789abcdef01234"
    kb = admin_cancel_edit_keyboard(game_id)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 1
    assert buttons[0].text == "⬅️ Отмена"
    assert buttons[0].callback_data == f"admin:{game_id}:settings"


def test_admin_finish_game_keyboard():
    game_id = "6724123456789abcdef01234"
    kb = admin_finish_game_keyboard(game_id)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    texts = [b.text for b in buttons]
    callbacks = [b.callback_data for b in buttons]
    assert "🏁 Завершить без медиа/текста" in texts
    assert "⬅️ Отмена" in texts
    assert f"admin:{game_id}:do_finish_nocomment" in callbacks
    assert f"admin:{game_id}:settings" in callbacks


def test_status_text_finished():
    assert status_text("finished") == "игра завершена 🏁"


def test_format_game_message_finished_with_note():
    game = {
        "title": "Футбол",
        "start_at": datetime.now(timezone.utc),
        "max_players": 15,
        "hourly_rate": 600,
        "duration_minutes": 90,
        "status": "finished",
        "finish_note": "Синие победили 5:3! Всем спасибо за игру!",
        "location": {"title": "Пед. Универ", "address": "ул. Шевченка 1"},
    }
    participants = [{"display_name": "Игрок 1", "status": "confirmed", "type": "user"}]
    msg = format_game_message(game, participants)
    assert "игра завершена 🏁" in msg
    assert "🏁 <b>Итоги матча:</b>" in msg
    assert "Синие победили 5:3! Всем спасибо за игру!" in msg


@pytest.mark.asyncio
async def test_game_repo_finish_game():
    from app.repositories.games import GameRepository

    db = MagicMock()
    db.games.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    repo = GameRepository(db)

    game_id = str(ObjectId())
    await repo.finish_game(
        game_id,
        finish_note="Счёт 4:2",
        media_items=[{"type": "photo", "file_id": "photo_file_123"}],
    )

    db.games.update_one.assert_called_once()
    call_args = db.games.update_one.call_args[0]
    filter_arg, update_arg = call_args[0], call_args[1]["$set"]

    assert filter_arg == {"_id": ObjectId(game_id)}
    assert update_arg["status"] == "finished"
    assert update_arg["finish_note"] == "Счёт 4:2"
    assert update_arg["media_items"] == [{"type": "photo", "file_id": "photo_file_123"}]


@pytest.mark.asyncio
async def test_admin_edit_value_in_place_deletes_msg_and_edits_admin_msg():
    from app.bot.handlers import admin_edit_value

    message = MagicMock()
    message.from_user.id = 111
    message.chat.id = 111
    message.text = "250"
    message.delete = AsyncMock()
    message.bot = MagicMock()
    message.bot.edit_message_text = AsyncMock()
    message.answer = AsyncMock()

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "game_id": "6724123456789abcdef01234",
        "edit_action": "edit_price",
        "admin_message_id": 4321,
    })
    state.clear = AsyncMock()

    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "status": "registration_open",
        "price": 200,
        "friends_allowed": False,
    }

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_db, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.update_price = AsyncMock()

        with patch("app.bot.handlers.GameRepository", return_value=game_repo):
            await admin_edit_value(message, state)

        # Must delete user's input message
        message.delete.assert_called_once()
        # Must update price in DB
        game_repo.update_price.assert_called_once_with("6724123456789abcdef01234", 250)
        # Must edit the admin message in place, not spawn a new one via answer!
        message.bot.edit_message_text.assert_called_once()
        call_kwargs = message.bot.edit_message_text.call_args.kwargs
        assert call_kwargs["message_id"] == 4321
        assert "Цена изменена" in call_kwargs["text"]
        message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_admin_finish_game_with_photo():
    from app.bot.handlers import admin_finish_game_content

    photo_mock = MagicMock(file_id="tg_photo_file_id")
    message = MagicMock()
    message.from_user.id = 111
    message.chat.id = 111
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
         patch("app.bot.handlers.get_db") as mock_db, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update, \
         patch("app.bot.handlers.broadcast_media_report", new_callable=AsyncMock) as mock_broadcast:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.finish_game = AsyncMock()

        with patch("app.bot.handlers.GameRepository", return_value=game_repo):
            await admin_finish_game_content(message, state)

        message.delete.assert_called_once()
        game_repo.finish_game.assert_called_once_with(
            "6724123456789abcdef01234",
            finish_note="Победа 5:3!",
            media_items=[{"type": "photo", "file_id": "tg_photo_file_id"}],
        )
        mock_update.assert_called_once()
        mock_broadcast.assert_called_once_with(
            message.bot,
            [-100111],
            [{"type": "photo", "file_id": "tg_photo_file_id"}],
        )
        message.bot.delete_message.assert_called_once_with(chat_id=111, message_id=5555)


@pytest.mark.asyncio
async def test_admin_finish_game_with_album_deduplication():
    import asyncio
    from app.bot.handlers import admin_finish_game_content

    messages = []
    for i in range(3):
        m = MagicMock()
        m.from_user.id = 111
        m.chat.id = 111
        m.media_group_id = "test_album_123"
        m.photo = [MagicMock(file_id=f"photo_{i}")]
        m.video = None
        m.text = None
        m.caption = "Победа 5:3!" if i == 0 else None
        m.delete = AsyncMock()
        m.bot = MagicMock()
        m.bot.edit_message_text = AsyncMock()
        m.answer = AsyncMock()
        messages.append(m)

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
         patch("app.bot.handlers.get_db") as mock_db, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update, \
         patch("app.bot.handlers.broadcast_media_report", new_callable=AsyncMock) as mock_broadcast:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.finish_game = AsyncMock()

        with patch("app.bot.handlers.GameRepository", return_value=game_repo):
            # Dispatch 3 concurrent messages of the same media group
            await asyncio.gather(
                admin_finish_game_content(messages[0], state),
                admin_finish_game_content(messages[1], state),
                admin_finish_game_content(messages[2], state),
            )

        # Game finished strictly ONCE!
        game_repo.finish_game.assert_called_once()
        call_args = game_repo.finish_game.call_args.kwargs
        assert call_args["finish_note"] == "Победа 5:3!"
        assert len(call_args["media_items"]) == 3
        # Broadcast media report called ONCE!
        mock_broadcast.assert_called_once()
        assert len(mock_broadcast.call_args[0][2]) == 3
        # All messages deleted
        for m in messages:
            m.delete.assert_called_once()
        messages[0].bot.delete_message.assert_called_once_with(chat_id=111, message_id=5555)


@pytest.mark.asyncio
async def test_edit_game_message_remains_text():
    from app.services.rich_message import edit_game_message

    bot = MagicMock()
    bot.edit_message_text = AsyncMock(return_value=True)

    game = {
        "title": "Футбол",
        "start_at": datetime.now(timezone.utc),
        "max_players": 15,
        "hourly_rate": 600,
        "duration_minutes": 90,
        "status": "finished",
        "finish_note": "Финал сезона",
    }
    participants = [{"display_name": "Игрок 1", "status": "confirmed", "type": "user"}]

    res = await edit_game_message(
        bot=bot,
        chat_id=12345,
        message_id=6789,
        game=game,
        participants=participants,
    )
    bot.edit_message_text.assert_called_once()
    assert "Финал сезона" in bot.edit_message_text.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_broadcast_media_report_album():
    from app.services.rich_message import broadcast_media_report
    from aiogram.types import InputMediaPhoto

    bot = MagicMock()
    bot.send_media_group = AsyncMock(return_value=[MagicMock()])
    bot.send_photo = AsyncMock()

    media_items = [
        {"type": "photo", "file_id": "photo_1"},
        {"type": "photo", "file_id": "photo_2"},
    ]
    await broadcast_media_report(bot, [-100123], media_items)

    bot.send_media_group.assert_called_once()
    assert bot.send_media_group.call_args.kwargs["chat_id"] == -100123
    media = bot.send_media_group.call_args.kwargs["media"]
    assert len(media) == 2
    assert isinstance(media[0], InputMediaPhoto)
    assert media[0].media == "photo_1"
    assert "Фотоотчет" in media[0].caption


@pytest.mark.asyncio
async def test_admin_do_cancel_deletes_management_menu():
    from app.bot.handlers import admin_callback

    callback = MagicMock()
    callback.data = "admin:6724123456789abcdef01234:do_cancel"
    callback.from_user.id = 111
    callback.message = MagicMock()
    callback.message.delete = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()

    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "status": "registration_open",
    }

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_db, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.cancel_game = AsyncMock()

        with patch("app.bot.handlers.GameRepository", return_value=game_repo):
            await admin_callback(callback, state)

        game_repo.cancel_game.assert_called_once()
        callback.message.delete.assert_called_once()
        callback.answer.assert_called_once_with("Игра отменена")


@pytest.mark.asyncio
async def test_admin_do_finish_nocomment_deletes_management_menu():
    from app.bot.handlers import admin_callback

    callback = MagicMock()
    callback.data = "admin:6724123456789abcdef01234:do_finish_nocomment"
    callback.from_user.id = 111
    callback.message = MagicMock()
    callback.message.delete = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()

    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "status": "game_started",
    }

    with patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.get_db") as mock_db, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update:

        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=mock_game)
        game_repo.finish_game = AsyncMock()

        with patch("app.bot.handlers.GameRepository", return_value=game_repo):
            await admin_callback(callback, state)

        game_repo.finish_game.assert_called_once_with("6724123456789abcdef01234")
        callback.message.delete.assert_called_once()
        callback.answer.assert_called_once_with("Игра завершена 🏁")


