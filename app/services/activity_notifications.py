import asyncio
import html
import inspect
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import ReplyParameters

from app.db.mongo import get_db
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository

logger = logging.getLogger(__name__)

TERMINAL_ACTIVITY_STATUSES = {
    "game_started",
    "finished",
    "payment_collection",
    "closed",
    "cancelled",
}

_game_locks: dict[str, asyncio.Lock] = {}


def _get_game_lock(game_id: str) -> asyncio.Lock:
    lock = _game_locks.get(game_id)
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if lock is not None and running_loop is not None:
        bound_loop = getattr(lock, "_loop", None)
        if bound_loop is not None and bound_loop is not running_loop:
            lock = None

    if lock is None:
        lock = asyncio.Lock()
        _game_locks[game_id] = lock
    return lock


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def get_group_card_entries(game: dict | None) -> list[dict]:
    """Возвращает уникальные записи карточек игры только для групповых чатов (chat_id < 0)."""
    if not game:
        return []

    raw_entries = list(game.get("messages") or [])
    if not raw_entries and game.get("chat_id") is not None and game.get("message_id") is not None:
        raw_entries = [{"chat_id": game["chat_id"], "message_id": game["message_id"]}]

    dedup: dict[int, dict] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        chat_id = entry.get("chat_id")
        if isinstance(chat_id, int) and not isinstance(chat_id, bool) and chat_id < 0:
            dedup[chat_id] = entry
    return list(dedup.values())


def find_promoted_participants(before: list[dict], after: list[dict]) -> list[dict]:
    """Возвращает участников, которые перешли из резерва в основной состав."""
    reserve_ids = {
        str(p["_id"])
        for p in before
        if p.get("_id") is not None and p.get("status") == "reserve"
    }
    if not reserve_ids:
        return []
    return [
        p
        for p in after
        if p.get("_id") is not None and str(p["_id"]) in reserve_ids and p.get("status") == "confirmed"
    ]


def format_activity_notification(
    event: str,
    *,
    actor_name: str,
    confirmed_count: int,
    max_players: int,
    reserve_count: int = 0,
    friend_name: str | None = None,
    result_status: str | None = None,
    promoted_names: list[str] | None = None,
) -> str:
    """Форматирует короткое HTML-уведомление об изменении состава игры."""
    actor = html.escape(str(actor_name or ""))
    friend = html.escape(str(friend_name)) if friend_name else ""

    counts = f"<b>{confirmed_count}/{max_players}</b>"
    if reserve_count > 0 and (result_status == "reserve" or confirmed_count >= max_players):
        counts += f" (резерв: {reserve_count})"

    milestone = ""
    if event in {"join", "add_friend"} and result_status == "confirmed":
        if confirmed_count >= max_players:
            milestone = " — 🔥 <b>Состав собран!</b>"
        elif max_players == 15 and confirmed_count == 10:
            milestone = " — ⚽ <b>Уже есть 5х5!</b>"

    if event == "join":
        if result_status == "reserve":
            text = f"🟡 <b>{actor}</b> в резерве — {counts}"
        else:
            text = f"✅ <b>{actor}</b> записался — {counts}{milestone}"
    elif event == "add_friend":
        if result_status == "reserve":
            text = f"🟡 <b>{actor}</b> добавил друга <b>{friend}</b> в резерв — {counts}"
        else:
            text = f"👥 <b>{actor}</b> добавил друга <b>{friend}</b> — {counts}{milestone}"
    elif event == "decline":
        text = f"❌ <b>{actor}</b> не сможет — {counts}"
    elif event == "cancel_friend":
        if friend:
            text = f"❌ <b>{actor}</b> отменил друга <b>{friend}</b> — {counts}"
        else:
            text = f"❌ <b>{actor}</b> отменил друга — {counts}"
    else:
        raise ValueError(f"Unknown activity event: {event}")

    names = [html.escape(str(name)) for name in (promoted_names or []) if name]
    if len(names) == 1:
        text += f"\n⬆️ <b>{names[0]}</b> перешёл из резерва в основу!"
    elif len(names) > 1:
        text += f"\n⬆️ Из резерва в основу: <b>{', '.join(names)}</b>!"

    return text


async def notify_roster_activity(
    bot,
    game_id: str,
    event: str,
    *,
    actor_name: str,
    friend_name: str | None = None,
    result_status: str | None = None,
    promoted_names: list[str] | None = None,
    db=None,
) -> None:
    """Отправляет уведомление об активе в привязанные группы реплаем на карточку и удаляет предыдущее."""
    if bot is None:
        return

    async with _get_game_lock(game_id):
        database = db or get_db()
        game_repo = GameRepository(database)
        game = await _maybe_await(game_repo.get(game_id))
        if not game or game.get("status") in TERMINAL_ACTIVITY_STATUSES:
            return

        group_entries = get_group_card_entries(game)
        if not group_entries:
            return

        participants = await _maybe_await(ParticipantRepository(database).list_by_game(game_id))
        if not isinstance(participants, list):
            return

        confirmed_count = sum(1 for p in participants if p.get("status") == "confirmed")
        reserve_count = sum(1 for p in participants if p.get("status") == "reserve")
        max_players = game.get("max_players", 15)

        text = format_activity_notification(
            event,
            actor_name=actor_name,
            confirmed_count=confirmed_count,
            max_players=max_players,
            reserve_count=reserve_count,
            friend_name=friend_name,
            result_status=result_status,
            promoted_names=promoted_names,
        )

        prev_map = dict(game.get("activity_messages") or {})

        async def _notify_chat(entry: dict) -> None:
            chat_id = entry["chat_id"]
            card_msg_id = entry.get("message_id")
            prev_msg_id = prev_map.get(str(chat_id))
            if prev_msg_id is None:
                prev_msg_id = prev_map.get(chat_id)

            reply_params = (
                ReplyParameters(message_id=card_msg_id, allow_sending_without_reply=True)
                if card_msg_id
                else None
            )
            try:
                sent = await _maybe_await(
                    bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="HTML",
                        reply_parameters=reply_params,
                    )
                )
            except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter, Exception) as e:
                logger.warning("Failed to send activity notification to chat %s: %s", chat_id, e)
                return

            new_msg_id = getattr(sent, "message_id", None) if sent is not None else None
            if new_msg_id:
                await _maybe_await(game_repo.set_activity_message_id(game_id, chat_id, new_msg_id))
                if prev_msg_id and prev_msg_id != new_msg_id:
                    try:
                        await _maybe_await(bot.delete_message(chat_id=chat_id, message_id=prev_msg_id))
                    except (TelegramBadRequest, TelegramForbiddenError, Exception) as e:
                        logger.debug(
                            "Failed to delete previous activity message %s in chat %s: %s",
                            prev_msg_id,
                            chat_id,
                            e,
                        )

        await asyncio.gather(*(_notify_chat(entry) for entry in group_entries), return_exceptions=True)


async def clear_activity_notifications(
    bot,
    game: dict | str,
    *,
    chat_ids: list[int] | None = None,
    db=None,
) -> None:
    """Удаляет висячие уведомления об активе в группах и очищает ссылки в БД."""
    if bot is None:
        return

    game_id = str(game["_id"]) if isinstance(game, dict) else str(game)
    if isinstance(game, dict) and not game.get("activity_messages"):
        return

    async with _get_game_lock(game_id):
        database = db or get_db()
        game_repo = GameRepository(database)
        game_doc = game if isinstance(game, dict) else await _maybe_await(game_repo.get(game_id))
        if not game_doc:
            return

        prev_map = dict(game_doc.get("activity_messages") or {})
        if not prev_map:
            return

        target_chat_set = set(chat_ids) if chat_ids is not None else None
        targets: list[tuple[int, int]] = []
        for cid_key, msg_id in prev_map.items():
            try:
                cid_int = int(cid_key)
            except (TypeError, ValueError):
                continue
            if target_chat_set is not None and cid_int not in target_chat_set:
                continue
            if msg_id:
                targets.append((cid_int, int(msg_id)))

        if not targets:
            return

        async def _delete_target(cid_int: int, msg_id: int) -> None:
            try:
                await _maybe_await(bot.delete_message(chat_id=cid_int, message_id=msg_id))
            except (TelegramBadRequest, TelegramForbiddenError, Exception) as e:
                logger.debug("Failed to delete activity message %s in chat %s: %s", msg_id, cid_int, e)

        await asyncio.gather(*(_delete_target(cid_int, msg_id) for cid_int, msg_id in targets), return_exceptions=True)

        if chat_ids is None:
            await _maybe_await(game_repo.clear_activity_message_id(game_id))
        else:
            for cid_int, _ in targets:
                await _maybe_await(game_repo.clear_activity_message_id(game_id, cid_int))
