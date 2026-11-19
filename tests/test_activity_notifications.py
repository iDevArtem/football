from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import ReplyParameters
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.auth import create_access_token
from app.api.sync import sync_activity_notification
from app.bot.handlers import (
    admin_callback,
    friend_callback,
    game_callback,
    process_friend_name,
    update_game_message,
)
from app.config.settings import get_settings
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository
from app.services.activity_notifications import (
    clear_activity_notifications,
    find_promoted_participants,
    format_activity_notification,
    get_group_card_entries,
    notify_roster_activity,
)


def _sample_game(
    *,
    game_id: str | None = None,
    status: str = "registration_open",
    max_players: int = 15,
    messages: list[dict] | None = None,
    activity_messages: dict | None = None,
) -> dict:
    gid = ObjectId(game_id) if game_id else ObjectId()
    doc = {
        "_id": gid,
        "title": "⚽ Футбол 5х5",
        "start_at": datetime.now(timezone.utc) + timedelta(days=1),
        "status": status,
        "max_players": max_players,
        "hourly_rate": 600,
        "duration_minutes": 90,
        "friends_allowed": True,
        "friends_allowed_after": datetime.now(timezone.utc) - timedelta(hours=1),
        "messages": messages
        if messages is not None
        else [
            {"chat_id": -1001, "message_id": 101, "chat_title": "Группа 1"},
        ],
    }
    if activity_messages is not None:
        doc["activity_messages"] = activity_messages
    return doc


# ---------------------------------------------------------------------------
# 1. Pure helpers & formatting
# ---------------------------------------------------------------------------


def test_format_activity_notification_join_regular_and_milestones():
    regular = format_activity_notification(
        "join",
        actor_name="Иван",
        confirmed_count=5,
        max_players=15,
        result_status="confirmed",
    )
    assert regular == "✅ <b>Иван</b> записался — <b>5/15</b>"

    five_v_five = format_activity_notification(
        "join",
        actor_name="Иван",
        confirmed_count=10,
        max_players=15,
        result_status="confirmed",
    )
    assert five_v_five == "✅ <b>Иван</b> записался — <b>10/15</b> — ⚽ <b>Уже есть 5х5!</b>"

    # Non-15 limit should NOT emit "Уже есть 5х5!" at 10
    custom_10_of_12 = format_activity_notification(
        "join",
        actor_name="Иван",
        confirmed_count=10,
        max_players=12,
        result_status="confirmed",
    )
    assert custom_10_of_12 == "✅ <b>Иван</b> записался — <b>10/12</b>"

    full_15 = format_activity_notification(
        "join",
        actor_name="Иван",
        confirmed_count=15,
        max_players=15,
        result_status="confirmed",
    )
    assert full_15 == "✅ <b>Иван</b> записался — <b>15/15</b> — 🔥 <b>Состав собран!</b>"

    full_custom = format_activity_notification(
        "join",
        actor_name="Иван",
        confirmed_count=10,
        max_players=10,
        result_status="confirmed",
    )
    assert full_custom == "✅ <b>Иван</b> записался — <b>10/10</b> — 🔥 <b>Состав собран!</b>"


def test_format_activity_notification_reserve_and_friends():
    reserve_join = format_activity_notification(
        "join",
        actor_name="Иван",
        confirmed_count=15,
        max_players=15,
        reserve_count=1,
        result_status="reserve",
    )
    assert reserve_join == "🟡 <b>Иван</b> в резерве — <b>15/15</b> (резерв: 1)"

    friend_confirmed = format_activity_notification(
        "add_friend",
        actor_name="Иван",
        friend_name="Саша",
        confirmed_count=10,
        max_players=15,
        result_status="confirmed",
    )
    assert friend_confirmed == "👥 <b>Иван</b> добавил друга <b>Саша</b> — <b>10/15</b> — ⚽ <b>Уже есть 5х5!</b>"

    friend_full = format_activity_notification(
        "add_friend",
        actor_name="Иван",
        friend_name="Саша",
        confirmed_count=15,
        max_players=15,
        result_status="confirmed",
    )
    assert friend_full == "👥 <b>Иван</b> добавил друга <b>Саша</b> — <b>15/15</b> — 🔥 <b>Состав собран!</b>"

    friend_reserve = format_activity_notification(
        "add_friend",
        actor_name="Иван",
        friend_name="Саша",
        confirmed_count=15,
        max_players=15,
        reserve_count=2,
        result_status="reserve",
    )
    assert friend_reserve == "🟡 <b>Иван</b> добавил друга <b>Саша</b> в резерв — <b>15/15</b> (резерв: 2)"


def test_format_activity_notification_decline_cancel_and_promotions():
    decline_plain = format_activity_notification(
        "decline",
        actor_name="Иван",
        confirmed_count=4,
        max_players=15,
    )
    assert decline_plain == "❌ <b>Иван</b> не сможет — <b>4/15</b>"

    decline_promo = format_activity_notification(
        "decline",
        actor_name="Иван",
        confirmed_count=15,
        max_players=15,
        reserve_count=1,
        promoted_names=["Петя"],
    )
    assert decline_promo == (
        "❌ <b>Иван</b> не сможет — <b>15/15</b> (резерв: 1)\n"
        "⬆️ <b>Петя</b> перешёл из резерва в основу!"
    )

    cancel_friend_promo = format_activity_notification(
        "cancel_friend",
        actor_name="Иван",
        friend_name="Саша",
        confirmed_count=15,
        max_players=15,
        promoted_names=["Петя", "Олег"],
    )
    assert cancel_friend_promo == (
        "❌ <b>Иван</b> отменил друга <b>Саша</b> — <b>15/15</b>\n"
        "⬆️ Из резерва в основу: <b>Петя, Олег</b>!"
    )

    cancel_friend_no_name = format_activity_notification(
        "cancel_friend",
        actor_name="Иван",
        confirmed_count=5,
        max_players=15,
    )
    assert cancel_friend_no_name == "❌ <b>Иван</b> отменил друга — <b>5/15</b>"


def test_format_activity_notification_escapes_html():
    text = format_activity_notification(
        "cancel_friend",
        actor_name="<script>alert(1)</script>",
        friend_name="A & B > C",
        confirmed_count=15,
        max_players=15,
        promoted_names=["<b>Hacker</b>"],
    )
    assert "<script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "A &amp; B &gt; C" in text
    assert "&lt;b&gt;Hacker&lt;/b&gt;" in text


def test_get_group_card_entries_filters_dm_and_dedups():
    assert get_group_card_entries(None) == []

    game = {
        "messages": [
            {"chat_id": 777, "message_id": 10},  # private DM
            {"chat_id": -1001, "message_id": 20},
            {"chat_id": -1002, "message_id": 30},
            {"chat_id": -1001, "message_id": 25},  # duplicate group -> keeps latest
        ]
    }
    entries = get_group_card_entries(game)
    assert entries == [
        {"chat_id": -1001, "message_id": 25},
        {"chat_id": -1002, "message_id": 30},
    ]

    legacy_group = {"chat_id": -1009, "message_id": 99, "messages": []}
    assert get_group_card_entries(legacy_group) == [{"chat_id": -1009, "message_id": 99}]

    legacy_dm = {"chat_id": 12345, "message_id": 99, "messages": []}
    assert get_group_card_entries(legacy_dm) == []


def test_find_promoted_participants():
    id1, id2, id3 = ObjectId(), ObjectId(), ObjectId()
    before = [
        {"_id": id1, "status": "confirmed", "display_name": "A"},
        {"_id": id2, "status": "reserve", "display_name": "B"},
        {"_id": id3, "status": "reserve", "display_name": "C"},
    ]
    after = [
        {"_id": id1, "status": "declined", "display_name": "A"},
        {"_id": id2, "status": "confirmed", "display_name": "B"},
        {"_id": id3, "status": "reserve", "display_name": "C"},
    ]
    promoted = find_promoted_participants(before, after)
    assert [p["display_name"] for p in promoted] == ["B"]


# ---------------------------------------------------------------------------
# 2. Repository methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_activity_message_and_get_player():
    db = MagicMock()
    db.games.update_one = AsyncMock()
    db.participants.find_one = AsyncMock(return_value={"_id": ObjectId(), "status": "confirmed"})

    game_id = str(ObjectId())
    game_repo = GameRepository(db)
    await game_repo.set_activity_message_id(game_id, -1001, 555)
    db.games.update_one.assert_awaited_once_with(
        {"_id": ObjectId(game_id)},
        {"$set": {"activity_messages.-1001": 555}},
    )

    db.games.update_one.reset_mock()
    await game_repo.clear_activity_message_id(game_id, -1001)
    db.games.update_one.assert_awaited_once_with(
        {"_id": ObjectId(game_id)},
        {"$unset": {"activity_messages.-1001": ""}},
    )

    db.games.update_one.reset_mock()
    await game_repo.clear_activity_message_id(game_id)
    db.games.update_one.assert_awaited_once_with(
        {"_id": ObjectId(game_id)},
        {"$unset": {"activity_messages": ""}},
    )

    part_repo = ParticipantRepository(db)
    res = await part_repo.get_player(game_id, 42)
    assert res["status"] == "confirmed"
    db.participants.find_one.assert_awaited_once_with({
        "game_id": ObjectId(game_id),
        "telegram_id": 42,
        "type": "player",
    })


# ---------------------------------------------------------------------------
# 3. Delivery, replacement, multigroup & error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_roster_activity_replies_saves_and_deletes_previous():
    game_id = str(ObjectId())
    game = _sample_game(
        game_id=game_id,
        messages=[
            {"chat_id": 777, "message_id": 10},  # DM card should be ignored
            {"chat_id": -1001, "message_id": 101},
            {"chat_id": -1002, "message_id": 202},
        ],
        activity_messages={"-1001": 901, "-1002": 902, "777": 999},
    )
    participants = [
        {"_id": ObjectId(), "status": "confirmed", "display_name": "Иван"},
    ]

    db = MagicMock()
    db.games.find_one = AsyncMock(return_value=game)
    db.games.update_one = AsyncMock()

    bot = MagicMock()
    call_order = []

    async def fake_send_message(**kwargs):
        call_order.append(("send", kwargs["chat_id"]))
        return MagicMock(message_id=1000 + abs(kwargs["chat_id"]))

    async def fake_delete_message(**kwargs):
        call_order.append(("delete", kwargs["chat_id"], kwargs["message_id"]))

    bot.send_message = AsyncMock(side_effect=fake_send_message)
    bot.delete_message = AsyncMock(side_effect=fake_delete_message)

    with patch("app.services.activity_notifications.ParticipantRepository") as mock_part_cls:
        mock_part_cls.return_value.list_by_game = AsyncMock(return_value=participants)

        await notify_roster_activity(
            bot,
            game_id,
            "join",
            actor_name="Иван",
            result_status="confirmed",
            db=db,
        )

    assert bot.send_message.call_count == 2
    sent_by_chat = {call.kwargs["chat_id"]: call.kwargs for call in bot.send_message.call_args_list}
    assert set(sent_by_chat.keys()) == {-1001, -1002}
    assert 777 not in sent_by_chat

    for cid, expected_card_id in [(-1001, 101), (-1002, 202)]:
        kwargs = sent_by_chat[cid]
        assert kwargs["parse_mode"] == "HTML"
        assert kwargs["text"] == "✅ <b>Иван</b> записался — <b>1/15</b>"
        assert isinstance(kwargs["reply_parameters"], ReplyParameters)
        assert kwargs["reply_parameters"].message_id == expected_card_id
        assert kwargs["reply_parameters"].allow_sending_without_reply is True

    # Saved both new IDs
    assert db.games.update_one.await_count == 2
    # Deleted both previous activity messages (and not DM)
    deleted = {(c.kwargs["chat_id"], c.kwargs["message_id"]) for c in bot.delete_message.call_args_list}
    assert deleted == {(-1001, 901), (-1002, 902)}
    # Send happened before delete for each chat
    for cid in (-1001, -1002):
        send_idx = next(i for i, item in enumerate(call_order) if item == ("send", cid))
        del_idx = next(i for i, item in enumerate(call_order) if item[0] == "delete" and item[1] == cid)
        assert send_idx < del_idx


@pytest.mark.asyncio
async def test_notify_roster_activity_skips_terminal_statuses():
    for status in ("game_started", "finished", "payment_collection", "closed", "cancelled"):
        game_id = str(ObjectId())
        game = _sample_game(game_id=game_id, status=status)
        db = MagicMock()
        db.games.find_one = AsyncMock(return_value=game)
        bot = MagicMock()
        bot.send_message = AsyncMock()

        await notify_roster_activity(
            bot,
            game_id,
            "join",
            actor_name="Иван",
            result_status="confirmed",
            db=db,
        )
        bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_roster_activity_handles_telegram_errors_gracefully():
    game_id = str(ObjectId())
    game = _sample_game(
        game_id=game_id,
        messages=[
            {"chat_id": -1001, "message_id": 101},
            {"chat_id": -1002, "message_id": 202},
        ],
        activity_messages={"-1001": 901, "-1002": 902},
    )
    participants = [{"_id": ObjectId(), "status": "confirmed", "display_name": "Иван"}]

    db = MagicMock()
    db.games.find_one = AsyncMock(return_value=game)
    db.games.update_one = AsyncMock()

    bot = MagicMock()

    async def send_side_effect(**kwargs):
        if kwargs["chat_id"] == -1001:
            raise TelegramForbiddenError(method=MagicMock(), message="bot kicked")
        return MagicMock(message_id=2222)

    bot.send_message = AsyncMock(side_effect=send_side_effect)
    bot.delete_message = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="message can't be deleted")
    )

    with patch("app.services.activity_notifications.ParticipantRepository") as mock_part_cls:
        mock_part_cls.return_value.list_by_game = AsyncMock(return_value=participants)
        # Should not raise even when one chat fails send_message and delete_message raises BadRequest
        await notify_roster_activity(
            bot,
            game_id,
            "join",
            actor_name="Иван",
            result_status="confirmed",
            db=db,
        )

    # -1002 still persisted and attempted cleanup
    db.games.update_one.assert_awaited_once_with(
        {"_id": ObjectId(game_id)},
        {"$set": {"activity_messages.-1002": 2222}},
    )
    bot.delete_message.assert_awaited_once_with(chat_id=-1002, message_id=902)

    # Also verify TelegramRetryAfter doesn't raise
    bot.send_message = AsyncMock(
        side_effect=TelegramRetryAfter(method=MagicMock(), message="Flood", retry_after=10)
    )
    with patch("app.services.activity_notifications.ParticipantRepository") as mock_part_cls:
        mock_part_cls.return_value.list_by_game = AsyncMock(return_value=participants)
        await notify_roster_activity(
            bot,
            game_id,
            "join",
            actor_name="Иван",
            result_status="confirmed",
            db=db,
        )


# ---------------------------------------------------------------------------
# 4. Cleanup tests (clear_activity_notifications, update_game_message, admin)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_activity_notifications_all_and_single_chat():
    game_id = str(ObjectId())
    game = _sample_game(
        game_id=game_id,
        activity_messages={"-1001": 801, "-1002": 802},
    )
    db = MagicMock()
    db.games.update_one = AsyncMock()
    bot = MagicMock()
    bot.delete_message = AsyncMock()

    # Single chat cleanup
    await clear_activity_notifications(bot, game, chat_ids=[-1001], db=db)
    bot.delete_message.assert_awaited_once_with(chat_id=-1001, message_id=801)
    db.games.update_one.assert_awaited_once_with(
        {"_id": ObjectId(game_id)},
        {"$unset": {"activity_messages.-1001": ""}},
    )

    # All chats cleanup
    bot.delete_message.reset_mock()
    db.games.update_one.reset_mock()
    await clear_activity_notifications(bot, game, db=db)
    assert {(c.kwargs["chat_id"], c.kwargs["message_id"]) for c in bot.delete_message.call_args_list} == {
        (-1001, 801),
        (-1002, 802),
    }
    db.games.update_one.assert_awaited_once_with(
        {"_id": ObjectId(game_id)},
        {"$unset": {"activity_messages": ""}},
    )


@pytest.mark.asyncio
async def test_update_game_message_clears_only_on_terminal_status():
    game_id = str(ObjectId())
    open_game = _sample_game(
        game_id=game_id,
        status="registration_open",
        activity_messages={"-1001": 801},
    )
    started_game = _sample_game(
        game_id=game_id,
        status="game_started",
        activity_messages={"-1001": 801},
    )

    db = MagicMock()
    bot = MagicMock()
    bot.edit_message_text = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_cls, \
         patch("app.bot.handlers.clear_activity_notifications", new_callable=AsyncMock) as mock_clear:
        mock_part_cls.return_value.list_by_game = AsyncMock(return_value=[])

        await update_game_message(bot, open_game)
        mock_clear.assert_not_called()

        await update_game_message(bot, started_game)
        mock_clear.assert_awaited_once_with(bot, started_game)


@pytest.mark.asyncio
async def test_admin_repub_and_unpub_clear_activity_notifications():
    game_id = str(ObjectId())
    game = _sample_game(
        game_id=game_id,
        messages=[{"chat_id": -1001, "message_id": 101, "chat_title": "Чат 1"}],
        activity_messages={"-1001": 901},
    )
    db = MagicMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.is_admin", return_value=True), \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_cls, \
         patch("app.bot.handlers.ChatRepository") as mock_chat_cls, \
         patch("app.bot.handlers.send_game_message", new_callable=AsyncMock, return_value=MagicMock(message_id=505)), \
         patch("app.bot.handlers.render_broadcast_menu", new_callable=AsyncMock), \
         patch("app.bot.handlers.clear_activity_notifications", new_callable=AsyncMock) as mock_clear:
        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value=game)
        game_repo.remove_linked_message = AsyncMock()
        game_repo.add_linked_message = AsyncMock()
        mock_game_cls.return_value = game_repo

        mock_part_cls.return_value.list_by_game = AsyncMock(return_value=[])
        mock_chat_cls.return_value.list_active_chats = AsyncMock(
            return_value=[{"chat_id": -1001, "title": "Чат 1"}]
        )

        cb = MagicMock()
        cb.from_user = MagicMock(id=999)
        cb.message = MagicMock(chat=MagicMock(type="private"))
        cb.bot = MagicMock()
        cb.bot.delete_message = AsyncMock()
        cb.answer = AsyncMock()
        state = AsyncMock()

        cb.data = f"admin:{game_id}:repub:-1001"
        await admin_callback(cb, state)
        mock_clear.assert_awaited_once_with(cb.bot, game, chat_ids=[-1001])

        mock_clear.reset_mock()
        cb.data = f"admin:{game_id}:unpub:-1001"
        await admin_callback(cb, state)
        mock_clear.assert_awaited_once_with(cb.bot, game, chat_ids=[-1001])


# ---------------------------------------------------------------------------
# 5. Bot handler tests (join / decline / friends)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_game_callback_join_notifies_only_when_not_previously_active():
    game_id = str(ObjectId())
    game = _sample_game(game_id=game_id)
    db = MagicMock()

    user = MagicMock(id=111, full_name="Иван Петров", username="ivan")
    cb = MagicMock()
    cb.data = f"game:{game_id}:join"
    cb.from_user = user
    cb.bot = MagicMock()
    cb.answer = AsyncMock()
    state = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.is_admin", return_value=False), \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_cls, \
         patch("app.bot.handlers.UserRepository") as mock_user_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock), \
         patch("app.bot.handlers.notify_roster_activity", new_callable=AsyncMock) as mock_notify:
        mock_game_cls.return_value.get = AsyncMock(return_value=game)
        mock_user_cls.return_value.upsert_from_telegram = AsyncMock()

        part_repo = MagicMock()
        part_repo.join_player = AsyncMock(return_value={"status": "confirmed", "display_name": "Иван Петров"})
        mock_part_cls.return_value = part_repo

        # 1. First join -> notifies
        part_repo.get_player = AsyncMock(return_value=None)
        await game_callback(cb, state)
        mock_notify.assert_awaited_once_with(
            cb.bot,
            game_id,
            "join",
            actor_name="Иван Петров",
            result_status="confirmed",
        )

        # 2. Repeat join while already confirmed -> does NOT notify
        mock_notify.reset_mock()
        part_repo.get_player = AsyncMock(return_value={"status": "confirmed"})
        await game_callback(cb, state)
        mock_notify.assert_not_called()

        # 3. Repeat join while already in reserve -> does NOT notify
        part_repo.get_player = AsyncMock(return_value={"status": "reserve"})
        await game_callback(cb, state)
        mock_notify.assert_not_called()

        # 4. Re-join after having declined -> notifies
        part_repo.get_player = AsyncMock(return_value={"status": "declined"})
        await game_callback(cb, state)
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_game_callback_decline_notifies_with_promotion_and_skips_inactive():
    game_id = str(ObjectId())
    game = _sample_game(game_id=game_id)
    db = MagicMock()

    p_ivan_id = ObjectId()
    p_petya_id = ObjectId()
    before = [
        {"_id": p_ivan_id, "telegram_id": 111, "type": "player", "status": "confirmed", "display_name": "Иван"},
        {"_id": p_petya_id, "telegram_id": 222, "type": "player", "status": "reserve", "display_name": "Петя"},
    ]
    after = [
        {"_id": p_ivan_id, "telegram_id": 111, "type": "player", "status": "declined", "display_name": "Иван"},
        {"_id": p_petya_id, "telegram_id": 222, "type": "player", "status": "confirmed", "display_name": "Петя"},
    ]

    user = MagicMock(id=111, full_name="Иван", username="ivan")
    cb = MagicMock()
    cb.data = f"game:{game_id}:decline"
    cb.from_user = user
    cb.bot = MagicMock()
    cb.answer = AsyncMock()
    state = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.is_admin", return_value=False), \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_cls, \
         patch("app.bot.handlers.UserRepository") as mock_user_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock), \
         patch("app.bot.handlers.notify_roster_activity", new_callable=AsyncMock) as mock_notify:
        mock_game_cls.return_value.get = AsyncMock(return_value=game)
        mock_user_cls.return_value.upsert_from_telegram = AsyncMock()

        part_repo = MagicMock()
        part_repo.decline_player = AsyncMock()
        mock_part_cls.return_value = part_repo

        # 1. Previously confirmed -> notifies with promoted_names=["Петя"]
        part_repo.list_by_game = AsyncMock(side_effect=[before, after])
        await game_callback(cb, state)
        mock_notify.assert_awaited_once_with(
            cb.bot,
            game_id,
            "decline",
            actor_name="Иван",
            promoted_names=["Петя"],
        )

        # 2. User already declined / never joined -> does NOT notify
        mock_notify.reset_mock()
        part_repo.list_by_game = AsyncMock(return_value=after)
        await game_callback(cb, state)
        mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_friend_add_and_cancel_handlers_notify():
    game_id = str(ObjectId())
    friend_id = ObjectId()
    petya_id = ObjectId()
    game = _sample_game(game_id=game_id)
    db = MagicMock()

    # 1. process_friend_name
    msg = MagicMock()
    msg.text = "Саша"
    msg.from_user = MagicMock(id=111, full_name="Иван", username="ivan")
    msg.bot = MagicMock()
    state = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_cls, \
         patch("app.bot.handlers.cleanup_friend_input", new_callable=AsyncMock), \
         patch("app.bot.handlers.temporary_reply", new_callable=AsyncMock), \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock), \
         patch("app.bot.handlers.notify_roster_activity", new_callable=AsyncMock) as mock_notify:
        mock_game_cls.return_value.get = AsyncMock(return_value=game)
        part_repo = MagicMock()
        part_repo.count_friends_by_user = AsyncMock(return_value=0)
        part_repo.add_friend = AsyncMock(return_value={"status": "confirmed", "display_name": "Саша"})
        mock_part_cls.return_value = part_repo

        await process_friend_name(msg, state, {"game_id": game_id})
        mock_notify.assert_awaited_once_with(
            msg.bot,
            game_id,
            "add_friend",
            actor_name="Иван",
            friend_name="Саша",
            result_status="confirmed",
        )

    # 2. friend_callback (cancel_friend with promotion)
    before = [
        {"_id": friend_id, "type": "friend", "status": "confirmed", "display_name": "Саша"},
        {"_id": petya_id, "type": "player", "status": "reserve", "display_name": "Петя"},
    ]
    after = [
        {"_id": petya_id, "type": "player", "status": "confirmed", "display_name": "Петя"},
    ]

    cb = MagicMock()
    cb.data = f"fc:{friend_id}"
    cb.from_user = MagicMock(id=111, full_name="Иван", username="ivan")
    cb.message = MagicMock()
    cb.message.delete = AsyncMock()
    cb.bot = MagicMock()
    cb.answer = AsyncMock()

    with patch("app.bot.handlers.get_db", return_value=db), \
         patch("app.bot.handlers.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.ParticipantRepository") as mock_part_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock), \
         patch("app.bot.handlers.notify_roster_activity", new_callable=AsyncMock) as mock_notify:
        mock_game_cls.return_value.get = AsyncMock(return_value=game)
        part_repo = MagicMock()
        part_repo.get = AsyncMock(return_value={"_id": friend_id, "game_id": ObjectId(game_id)})
        part_repo.list_by_game = AsyncMock(side_effect=[before, after])
        part_repo.cancel_friend = AsyncMock(return_value=True)
        mock_part_cls.return_value = part_repo

        await friend_callback(cb)
        mock_notify.assert_awaited_once_with(
            cb.bot,
            game_id,
            "cancel_friend",
            actor_name="Иван",
            friend_name="Саша",
            promoted_names=["Петя"],
        )


# ---------------------------------------------------------------------------
# 6. Mini App API endpoints & sync helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_join_leave_and_friends_trigger_activity_notifications():
    from app.api.routers.games import router as games_router

    app = FastAPI()
    app.include_router(games_router, prefix="/api/games")

    secret = get_settings().jwt_secret
    token = create_access_token(
        {
            "sub": "111",
            "telegram_id": 111,
            "first_name": "Иван",
            "last_name": "Петров",
            "username": "ivan",
            "role": "player",
        },
        secret=secret,
    )
    headers = {"Authorization": f"Bearer {token}"}

    game_id = str(ObjectId())
    friend_id = str(ObjectId())
    p_ivan_id = ObjectId()
    p_petya_id = ObjectId()
    game = _sample_game(game_id=game_id)

    mock_bot = MagicMock()
    db = MagicMock()
    game_repo = MagicMock()
    game_repo.get_by_id = AsyncMock(return_value=game)
    game_repo.get = AsyncMock(return_value=game)

    part_repo = MagicMock()
    part_repo.join_player = AsyncMock(
        return_value={"_id": p_ivan_id, "status": "confirmed", "position": 1, "display_name": "Иван Петров"}
    )
    part_repo.decline_player = AsyncMock()
    part_repo.count_friends_by_user = AsyncMock(return_value=0)
    part_repo.add_friend = AsyncMock(
        return_value={
            "_id": ObjectId(friend_id),
            "game_id": ObjectId(game_id),
            "telegram_id": None,
            "type": "friend",
            "status": "confirmed",
            "added_by_telegram_id": 111,
            "display_name": "Саша",
            "position": 2,
        }
    )
    part_repo.cancel_friend = AsyncMock(return_value=True)

    with patch("app.api.routers.games.get_db", return_value=db), \
         patch("app.api.routers.games.GameRepository", return_value=game_repo), \
         patch("app.api.routers.games.ParticipantRepository", return_value=part_repo), \
         patch("app.api.routers.games.get_bot", return_value=mock_bot), \
         patch("app.api.routers.games.update_game_message", new_callable=AsyncMock), \
         patch("app.api.routers.games.trigger_sync"), \
         patch("app.api.routers.games.trigger_activity_notification") as mock_trigger:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Join when not previously active -> triggers notification
            part_repo.list_by_game = AsyncMock(return_value=[])
            res = await client.post(f"/api/games/{game_id}/join", headers=headers)
            assert res.status_code == 200
            mock_trigger.assert_called_once_with(
                game_id,
                "join",
                actor_name="Иван Петров",
                result_status="confirmed",
            )

            # 2. Repeat join when already confirmed -> does NOT trigger
            mock_trigger.reset_mock()
            part_repo.list_by_game = AsyncMock(
                return_value=[{"_id": p_ivan_id, "telegram_id": 111, "type": "player", "status": "confirmed"}]
            )
            res = await client.post(f"/api/games/{game_id}/join", headers=headers)
            assert res.status_code == 200
            mock_trigger.assert_not_called()

            # 3. Leave when previously confirmed -> triggers decline with promotion
            before_leave = [
                {"_id": p_ivan_id, "telegram_id": 111, "type": "player", "status": "confirmed", "display_name": "Иван Петров"},
                {"_id": p_petya_id, "telegram_id": 222, "type": "player", "status": "reserve", "display_name": "Петя"},
            ]
            after_leave = [
                {"_id": p_ivan_id, "telegram_id": 111, "type": "player", "status": "declined", "display_name": "Иван Петров"},
                {"_id": p_petya_id, "telegram_id": 222, "type": "player", "status": "confirmed", "display_name": "Петя"},
            ]
            part_repo.list_by_game = AsyncMock(side_effect=[before_leave, after_leave])
            res = await client.post(f"/api/games/{game_id}/leave", headers=headers)
            assert res.status_code == 200
            mock_trigger.assert_called_once_with(
                game_id,
                "decline",
                actor_name="Иван Петров",
                promoted_names=["Петя"],
            )

            # 4. Leave when not active -> does NOT trigger
            mock_trigger.reset_mock()
            part_repo.list_by_game = AsyncMock(return_value=after_leave)
            res = await client.post(f"/api/games/{game_id}/leave", headers=headers)
            assert res.status_code == 200
            mock_trigger.assert_not_called()

            # 5. Add friend -> triggers add_friend
            res = await client.post(
                f"/api/games/{game_id}/friends",
                json={"friend_name": "Саша"},
                headers=headers,
            )
            assert res.status_code == 200
            mock_trigger.assert_called_once_with(
                game_id,
                "add_friend",
                actor_name="Иван Петров",
                friend_name="Саша",
                result_status="confirmed",
            )

            # 6. Delete friend -> triggers cancel_friend with promotion
            mock_trigger.reset_mock()
            before_del = [
                {"_id": ObjectId(friend_id), "type": "friend", "status": "confirmed", "display_name": "Саша"},
                {"_id": p_petya_id, "type": "player", "status": "reserve", "display_name": "Петя"},
            ]
            after_del = [
                {"_id": p_petya_id, "type": "player", "status": "confirmed", "display_name": "Петя"},
            ]
            part_repo.list_by_game = AsyncMock(side_effect=[before_del, after_del])
            res = await client.delete(f"/api/games/{game_id}/friends/{friend_id}", headers=headers)
            assert res.status_code == 200
            mock_trigger.assert_called_once_with(
                game_id,
                "cancel_friend",
                actor_name="Иван Петров",
                friend_name="Саша",
                promoted_names=["Петя"],
            )


@pytest.mark.asyncio
async def test_sync_activity_notification_swallows_exceptions():
    bot = MagicMock()
    with patch("app.api.sync.get_bot", return_value=bot), \
         patch("app.services.activity_notifications.notify_roster_activity", side_effect=RuntimeError("boom")), \
         patch("app.api.sync.logger") as mock_logger:
        await sync_activity_notification("game123", "join", actor_name="Иван")
        mock_logger.exception.assert_called_once()
