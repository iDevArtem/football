import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from datetime import datetime, timezone

from app.config.settings import get_settings
from app.db.mongo import get_db
from app.repositories.chats import ChatRepository
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository
from app.repositories.payments import PaymentRepository
from app.repositories.users import UserRepository
from app.bot.keyboards import (
    game_keyboard,
    friends_cancel_keyboard,
    payment_keyboard,
    admin_game_keyboard,
    admin_confirm_keyboard,
    friends_payment_keyboard,
    broadcast_groups_keyboard,
    payment_duration_keyboard,
)
from app.services.render import format_game_message, format_payments_message
from app.utils.dates import parse_date_time, now_tz

router = Router()
logger = logging.getLogger(__name__)

# FSM в aiogram по умолчанию привязан к паре user+chat.
# Когда кнопку нажимают в группе, а имя друга вводят в личке, state может не совпасть.
# Поэтому для приватного ввода друга держим короткое pending-состояние по user_id.
PENDING_FRIEND_INPUTS: dict[int, dict] = {}
# Когда пользователь нажал кнопку в группе, но бот еще не может писать ему в личку,
# сохраняем намерение и продолжаем после /start в личке.
PENDING_PRIVATE_ACTIONS: dict[int, dict] = {}


class AddFriendState(StatesGroup):
    waiting_name = State()


class AdminEditState(StatesGroup):
    waiting_value = State()


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def is_group_chat(message: Message) -> bool:
    return message.chat.type in ("group", "supergroup")


def can_add_friends_now(game: dict) -> bool:
    """Друзей можно добавлять только после 00:00 дня игры и только когда набор друзей открыт."""
    if not game.get("friends_allowed"):
        return False
    now = datetime.now(timezone.utc)
    friends_after = game["friends_allowed_after"]
    if friends_after.tzinfo is None:
        friends_after = friends_after.replace(tzinfo=timezone.utc)
    else:
        friends_after = friends_after.astimezone(timezone.utc)
    return now >= friends_after


async def _update_single_message(bot, game_repo, chat_repo, game_id: str, chat_id: int, message_id: int, text: str, reply_markup) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        err_text = str(e).lower()
        if "not modified" in err_text:
            return
        if "not found" in err_text or "deleted" in err_text or "can't be edited" in err_text:
            await game_repo.remove_linked_message(game_id, chat_id, message_id)
    except TelegramForbiddenError:
        await game_repo.remove_linked_message(game_id, chat_id, message_id)
        await chat_repo.set_active_status(chat_id, False)
    except TelegramRetryAfter as e:
        logger.warning(
            "Telegram flood limit for chat %s (message %s): retry after %s seconds",
            chat_id,
            message_id,
            getattr(e, "retry_after", None),
        )


async def update_game_message(bot, game: dict) -> None:
    db = get_db()
    game_id = str(game["_id"])
    participants = await ParticipantRepository(db).list_by_game(game_id)
    payments = []
    if game.get("status") == "payment_collection":
        payments = await PaymentRepository(db).list_by_game(game_id)
    text = format_game_message(game, participants, payments)
    reply_markup = game_keyboard(game_id, game.get("friends_allowed", False), game.get("status"))

    messages = list(game.get("messages", []))
    if not messages and game.get("chat_id") and game.get("message_id"):
        messages.append({"chat_id": game["chat_id"], "message_id": game["message_id"]})

    if not messages:
        return

    game_repo = GameRepository(db)
    chat_repo = ChatRepository(db)
    import asyncio
    tasks = [
        _update_single_message(bot, game_repo, chat_repo, game_id, m["chat_id"], m["message_id"], text, reply_markup)
        for m in messages
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


async def get_active_game_or_reply(message: Message) -> dict | None:
    db = get_db()
    game_repo = GameRepository(db)
    if is_group_chat(message):
        game = await game_repo.get_manageable_for_chat(message.chat.id)
    else:
        game = await game_repo.get_latest_manageable()
    if not game:
        await message.reply("Активной игры нет.")
        return None
    return game


async def delete_message_safely(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def temporary_reply(message: Message, text: str, *, seconds: int = 4) -> None:
    # Slash-команда не может показать Telegram alert. Alert доступен только для callback-кнопок.
    # Поэтому для команд удаляем команду и показываем короткое сообщение, которое затем удаляется.
    import asyncio
    try:
        sent = await message.answer(text)
        await asyncio.sleep(seconds)
        await sent.delete()
    except TelegramBadRequest:
        pass


async def cleanup_friend_input(message: Message, data: dict) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    prompt_chat_id = data.get("prompt_chat_id")
    prompt_message_id = data.get("prompt_message_id")
    if prompt_chat_id and prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=prompt_chat_id, message_id=prompt_message_id)
        except TelegramBadRequest:
            pass


async def send_private_message(bot, user_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id=user_id, text=text, **kwargs)
    except (TelegramForbiddenError, TelegramBadRequest):
        return None


async def send_private_admin_menu(bot, user_id: int, game: dict):
    game_id = str(game["_id"])
    return await send_private_message(
        bot,
        user_id,
        "⚙️ Управление игрой\n\n"
        "Все действия выполняются здесь, а в группе обновляется только основное сообщение игры.",
        reply_markup=admin_game_keyboard(
            game_id,
            friends_allowed=game.get("friends_allowed", False),
            status=game.get("status"),
        ),
    )


async def send_private_friends_payment_menu(bot, user_id: int, game_id: str):
    db = get_db()
    participants_repo = ParticipantRepository(db)
    pay_repo = PaymentRepository(db)

    friends = await participants_repo.list_friends_by_user(game_id, user_id)
    friends = [friend for friend in friends if friend.get("status") == "confirmed"]
    if not friends:
        return "no_friends"

    payments = await pay_repo.list_by_game(game_id)
    payments_by_participant_id = {str(payment["participant_id"]): payment for payment in payments}
    sent = await send_private_message(
        bot,
        user_id,
        "👥 Оплата друзей\n\nОтметь оплату или 'не играл' напротив нужного друга.",
        reply_markup=friends_payment_keyboard(game_id, friends, payments_by_participant_id),
    )
    return sent


async def process_pending_private_action(message: Message) -> bool:
    if message.chat.type != "private" or not message.from_user:
        return False

    action = PENDING_PRIVATE_ACTIONS.pop(message.from_user.id, None)
    if not action:
        return False

    if action.get("type") == "friends_payment":
        result = await send_private_friends_payment_menu(message.bot, message.from_user.id, action["game_id"])
        if result == "no_friends":
            await message.answer("У тебя нет друзей в основном составе этой игры.")
        elif not result:
            await message.answer("Не смог открыть оплату друзей. Попробуй нажать кнопку еще раз в группе.")
        return True

    if action.get("type") == "add_friend":
        game_id = action["game_id"]
        db = get_db()
        game = await GameRepository(db).get(game_id)
        if not game or game.get("status") in {"cancelled", "registration_closed", "payment_collection"}:
            await message.answer("Эта игра сейчас недоступна для записи друзей.")
            return True
        if not can_add_friends_now(game):
            await message.answer("Время добавления друзей для этой игры еще не наступило.")
            return True
        participants_repo = ParticipantRepository(db)
        count = await participants_repo.count_friends_by_user(game_id, message.from_user.id)
        if count >= 3:
            await message.answer("Нельзя добавить больше 3 друзей.")
            return True
        prompt = await message.answer("Введите имя друга одним сообщением:")
        pending_data = {
            "game_id": game_id,
            "prompt_chat_id": prompt.chat.id,
            "prompt_message_id": prompt.message_id,
        }
        PENDING_FRIEND_INPUTS[message.from_user.id] = pending_data
        return True

    return False


async def render_broadcast_menu(bot, user_id: int, game_id: str, message: Message | None = None) -> None:
    db = get_db()
    game_repo = GameRepository(db)
    chat_repo = ChatRepository(db)
    game = await game_repo.get(game_id)
    if not game:
        return
    chats = await chat_repo.list_active_chats()
    linked_ids = {m["chat_id"] for m in game.get("messages", [])}
    kb = broadcast_groups_keyboard(game_id, chats, linked_ids)
    text = (
        "📢 <b>Публикация игры в группах</b>\n\n"
        "Нажмите на группу, чтобы опубликовать (➕) или отозвать (✅) карточку матча:\n"
    )
    if not chats:
        text += "\n<i>Нет доступных групп. Добавьте бота в группу или напишите в ней сообщение.</i>"
    if message and message.chat.type == "private":
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except TelegramBadRequest:
            pass
    await send_private_message(bot, user_id, text, reply_markup=kb, parse_mode="HTML")


@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated) -> None:
    if event.chat.type in ("group", "supergroup"):
        db = get_db()
        chat_repo = ChatRepository(db)
        is_active = event.new_chat_member.status in ("member", "administrator")
        if is_active:
            await chat_repo.upsert_chat(event.chat.id, event.chat.title or "Группа", event.chat.type)
        else:
            await chat_repo.set_active_status(event.chat.id, False)


@router.message(Command("start"))
async def start(message: Message) -> None:
    if await process_pending_private_action(message):
        return

    await message.answer(
        "⚽ Бот для записи на футбол.\n\n"
        "Команда создания игры:\n"
        "<code>/new_game 2026-11-06 19:00</code>\n\n"
        "Формат: <code>/new_game ГГГГ-ММ-ДД ЧЧ:ММ</code>\n"
        "(по умолчанию: макс 15 чел, аренда 600 грн/час, 90 мин)",
        parse_mode="HTML",
    )


@router.message(Command("new_game"))
async def new_game(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Создавать игру может только админ.")
        return

    parts = message.text.split()
    if len(parts) == 3:
        _, date_raw, time_raw = parts
        try:
            start_at = parse_date_time(date_raw, time_raw, get_settings().default_timezone)
        except Exception:
            await message.reply("❌ Не смог разобрать дату и время. Пример:\n<code>/new_game 2026-11-06 19:00</code>", parse_mode="HTML")
            return
        game_kwargs = {
            "title": "Футбол",
            "start_at": start_at,
            "created_by": message.from_user.id,
        }
    elif len(parts) == 8:
        _, date_raw, time_raw, teams_raw, players_raw, price_raw, duration_minutes, friends_open_after_hours = parts
        try:
            teams_count = int(teams_raw)
            players_per_team = int(players_raw)
            price = int(price_raw)
            if teams_count <= 0 or players_per_team <= 0 or price < 0:
                raise ValueError
            start_at = parse_date_time(date_raw, time_raw, get_settings().default_timezone)
            duration_minutes = int(duration_minutes)
            friends_open_after_hours = int(friends_open_after_hours)
        except Exception:
            await message.reply("❌ Не смог разобрать команду. Проверь дату, время и числа.")
            return
        game_kwargs = {
            "title": "Футбол",
            "start_at": start_at,
            "teams_count": teams_count,
            "players_per_team": players_per_team,
            "price": price,
            "duration_minutes": duration_minutes,
            "friends_open_after_hours": friends_open_after_hours,
            "created_by": message.from_user.id,
        }
    else:
        await message.reply(
            "Формат команды:\n"
            "<code>/new_game 2026-11-06 19:00</code>\n\n"
            "Или с расширенными параметрами:\n"
            "<code>/new_game 2026-11-06 19:00 3 5 200 90 6</code>",
            parse_mode="HTML",
        )
        return

    if game_kwargs["start_at"] < now_tz(get_settings().default_timezone):
        await message.reply("❌ Нельзя создать игру в прошлом.")
        return

    db = get_db()
    await UserRepository(db).upsert_from_telegram(message.from_user, is_admin=True)
    game_repo = GameRepository(db)
    chat_repo = ChatRepository(db)

    is_group = is_group_chat(message)
    chat_id = message.chat.id if is_group else None

    game = await game_repo.create_game(
        chat_id=chat_id,
        **game_kwargs
    )
    game_id = str(game["_id"])

    if is_group:
        await chat_repo.upsert_chat(message.chat.id, message.chat.title or "Группа", message.chat.type)
        sent = await message.answer(
            format_game_message(game, []),
            reply_markup=game_keyboard(game_id, False, game.get("status")),
            parse_mode="HTML",
        )
        await game_repo.set_message_id(game_id, sent.message_id)
        await game_repo.add_linked_message(game_id, message.chat.id, sent.message_id, message.chat.title or "Группа")
        await delete_message_safely(message)
    else:
        await message.answer(
            format_game_message(game, []),
            parse_mode="HTML",
        )
        await render_broadcast_menu(message.bot, message.from_user.id, game_id)


@router.message(Command("current_game"))
async def current_game(message: Message) -> None:
    game = await get_active_game_or_reply(message)
    if not game:
        return
    await update_game_message(message.bot, game)
    await message.reply("✅ Сообщение игры обновлено.")


@router.message(Command("game_settings"))
async def game_settings(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await delete_message_safely(message)
        return
    db = get_db()
    game = await GameRepository(db).get_manageable_for_chat(message.chat.id)
    await delete_message_safely(message)
    if not game:
        await temporary_reply(message, "Активной игры нет.")
        return
    sent = await send_private_admin_menu(message.bot, message.from_user.id, game)
    if not sent:
        await temporary_reply(message, "❌ Напиши боту /start в личке, чтобы я мог открыть управление.")


@router.message(Command("open_friends"))
async def open_friends(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    await game_repo.open_friends(str(game["_id"]))
    game = await game_repo.get(str(game["_id"]))
    await update_game_message(message.bot, game)
    await message.reply("👥 Добавление друзей открыто.")


@router.message(Command("close_friends"))
async def close_friends(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    await game_repo.close_friends(str(game["_id"]))
    game = await game_repo.get(str(game["_id"]))
    await update_game_message(message.bot, game)
    await message.reply("👥 Добавление друзей закрыто.")


@router.message(Command("close_registration"))
async def close_registration(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    await delete_message_safely(message)
    await message.answer(
        "Подтвердить закрытие записи? Ее можно будет открыть обратно.",
        reply_markup=admin_confirm_keyboard(str(game["_id"]), "close_registration"),
    )


@router.message(Command("open_registration"))
async def open_registration(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    await game_repo.open_registration(str(game["_id"]))
    game = await game_repo.get(str(game["_id"]))
    await update_game_message(message.bot, game)
    await delete_message_safely(message)
    await temporary_reply(message, "🔓 Запись открыта.")


@router.message(Command("cancel_game"))
async def cancel_game(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    await delete_message_safely(message)
    await message.answer(
        "Подтвердить отмену игры? Ее можно будет вернуть позже.",
        reply_markup=admin_confirm_keyboard(str(game["_id"]), "cancel"),
    )


@router.message(Command("edit_date"))
async def edit_date(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.reply("Формат: <code>/edit_date 2026-11-06 19:00</code>", parse_mode="HTML")
        return
    try:
        start_at = parse_date_time(parts[1], parts[2], get_settings().default_timezone)
    except Exception:
        await message.reply("❌ Не смог разобрать дату и время.")
        return
    if start_at < now_tz(get_settings().default_timezone):
        await message.reply("❌ Нельзя перенести игру в прошлое.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    await game_repo.update_start_at(str(game["_id"]), start_at)
    game = await game_repo.get(str(game["_id"]))
    await update_game_message(message.bot, game)
    await delete_message_safely(message)
    await temporary_reply(message, "✅ Дата и время игры изменены.")


@router.message(Command("edit_price"))
async def edit_price(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("Формат: <code>/edit_price 250</code>", parse_mode="HTML")
        return
    try:
        price = int(parts[1])
        if price < 0:
            raise ValueError
    except Exception:
        await message.reply("❌ Цена должна быть числом.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    await game_repo.update_price(str(game["_id"]), price)
    game = await game_repo.get(str(game["_id"]))
    await update_game_message(message.bot, game)
    await delete_message_safely(message)
    await temporary_reply(message, "✅ Цена изменена.")


async def edit_format_value(message: Message, *, field: str) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        cmd = "/edit_teams 3" if field == "teams" else "/edit_players 7"
        await message.reply(f"Формат: <code>{cmd}</code>", parse_mode="HTML")
        return
    try:
        value = int(parts[1])
        if value <= 0:
            raise ValueError
    except Exception:
        await message.reply("❌ Значение должно быть положительным числом.")
        return
    db = get_db()
    game_repo = GameRepository(db)
    participant_repo = ParticipantRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    kwargs = {"teams_count": value} if field == "teams" else {"players_per_team": value}
    game = await game_repo.update_format(str(game["_id"]), **kwargs)
    await participant_repo.normalize_roster(str(game["_id"]), game["max_players"])
    game = await game_repo.get(str(game["_id"]))
    await update_game_message(message.bot, game)
    await delete_message_safely(message)
    await temporary_reply(message, "✅ Формат игры изменен, состав и резерв пересчитаны.")


@router.message(Command("edit_teams"))
async def edit_teams(message: Message) -> None:
    await edit_format_value(message, field="teams")


@router.message(Command("edit_players"))
async def edit_players(message: Message) -> None:
    await edit_format_value(message, field="players")


@router.message(Command("payments", "finish_game"))
async def payments(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только админ.")
        return
    game = await get_active_game_or_reply(message)
    if not game:
        return
    game_id = str(game["_id"])
    hourly_rate = game.get("hourly_rate", 600)
    sent = await send_private_message(
        message.bot,
        message.from_user.id,
        "⏱ <b>Сколько времени играли?</b>\n\nСтоимость аренды поля будет поделена поровну между игроками основы.",
        reply_markup=payment_duration_keyboard(game_id, hourly_rate),
        parse_mode="HTML",
    )
    if not sent:
        await temporary_reply(message, "❌ Напиши боту /start в личке, чтобы начать сбор оплат.")
    else:
        if is_group_chat(message):
            await delete_message_safely(message)


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, game_id, action = callback.data.split(":", 2)
    if not is_admin(callback.from_user.id):
        await callback.answer("Только админ", show_alert=True)
        return
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get(game_id)
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    def admin_markup(fresh: dict):
        return admin_game_keyboard(
            str(fresh["_id"]),
            friends_allowed=fresh.get("friends_allowed", False),
            status=fresh.get("status"),
        )

    async def show_or_refresh_admin_message(*, force_new: bool = False) -> None:
        fresh = await game_repo.get(game_id)
        text = (
            "⚙️ Управление игрой\n\n"
            "Все действия выполняются здесь, а в группе обновляется только основное сообщение игры."
        )
        markup = admin_markup(fresh)
        is_group_message = callback.message and callback.message.chat.type in ("group", "supergroup")
        if is_group_message:
            sent = await send_private_message(callback.bot, callback.from_user.id, text, reply_markup=markup)
            if sent:
                await callback.answer("Управление отправил в личку")
            else:
                await callback.answer("Напиши боту /start в личке, чтобы открыть управление", show_alert=True)
            return
        if force_new:
            await send_private_message(callback.bot, callback.from_user.id, text, reply_markup=markup)
            await callback.answer()
            return
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            try:
                await callback.message.edit_reply_markup(reply_markup=markup)
            except TelegramBadRequest:
                pass

    async def edit_admin_message(text: str, markup) -> None:
        is_group_message = callback.message and callback.message.chat.type in ("group", "supergroup")
        if is_group_message:
            sent = await send_private_message(callback.bot, callback.from_user.id, text, reply_markup=markup, parse_mode="HTML")
            if not sent:
                await callback.answer("Напиши боту /start в личке, чтобы открыть управление", show_alert=True)
            return
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

    if action == "settings":
        await show_or_refresh_admin_message(force_new=False)
        await callback.answer()
        return

    if action == "broadcast_menu":
        await render_broadcast_menu(callback.bot, callback.from_user.id, game_id, callback.message)
        await callback.answer()
        return

    if action == "pub_all":
        chat_repo = ChatRepository(db)
        chats = await chat_repo.list_active_chats()
        fresh = await game_repo.get(game_id)
        linked_ids = {m["chat_id"] for m in fresh.get("messages", [])}
        participants = await ParticipantRepository(db).list_by_game(game_id)
        text = format_game_message(fresh, participants)
        markup = game_keyboard(game_id, fresh.get("friends_allowed", False), fresh.get("status"))
        for chat in chats:
            cid = chat["chat_id"]
            if cid not in linked_ids:
                try:
                    sent = await callback.bot.send_message(
                        chat_id=cid,
                        text=text,
                        reply_markup=markup,
                        parse_mode="HTML",
                    )
                    await game_repo.add_linked_message(game_id, cid, sent.message_id, chat.get("title", str(cid)))
                except (TelegramBadRequest, TelegramForbiddenError):
                    await chat_repo.set_active_status(cid, False)
        await render_broadcast_menu(callback.bot, callback.from_user.id, game_id, callback.message)
        await callback.answer("Опубликовано во всех группах")
        return

    if action.startswith("pub:"):
        target_chat_id = int(action.split(":", 1)[1])
        chat_repo = ChatRepository(db)
        chats = await chat_repo.list_active_chats()
        chat_title = next((c.get("title", str(target_chat_id)) for c in chats if c["chat_id"] == target_chat_id), "Группа")
        fresh = await game_repo.get(game_id)
        participants = await ParticipantRepository(db).list_by_game(game_id)
        try:
            sent = await callback.bot.send_message(
                chat_id=target_chat_id,
                text=format_game_message(fresh, participants),
                reply_markup=game_keyboard(game_id, fresh.get("friends_allowed", False), fresh.get("status")),
                parse_mode="HTML",
            )
            await game_repo.add_linked_message(game_id, target_chat_id, sent.message_id, chat_title)
            await callback.answer(f"Опубликовано в {chat_title}")
        except (TelegramBadRequest, TelegramForbiddenError):
            await chat_repo.set_active_status(target_chat_id, False)
            await callback.answer("Не удалось отправить сообщение в чат", show_alert=True)
        await render_broadcast_menu(callback.bot, callback.from_user.id, game_id, callback.message)
        return

    if action.startswith("unpub:"):
        target_chat_id = int(action.split(":", 1)[1])
        fresh = await game_repo.get(game_id)
        for m in fresh.get("messages", []):
            if m["chat_id"] == target_chat_id:
                try:
                    await callback.bot.delete_message(chat_id=target_chat_id, message_id=m["message_id"])
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass
        await game_repo.remove_linked_message(game_id, target_chat_id)
        await render_broadcast_menu(callback.bot, callback.from_user.id, game_id, callback.message)
        await callback.answer("Удалено из группы")
        return

    if action in {"edit_date", "edit_price", "edit_teams", "edit_players"}:
        prompts = {
            "edit_date": "📅 Введите новую дату и время:\n<code>2026-11-06 19:00</code>",
            "edit_price": "💰 Введите новую цену числом:\n<code>250</code>",
            "edit_teams": "👥 Введите количество команд:\n<code>3</code>",
            "edit_players": "🏃 Введите игроков в команде:\n<code>6</code>",
        }
        await state.set_state(AdminEditState.waiting_value)
        await state.update_data(game_id=game_id, edit_action=action, admin_message_id=callback.message.message_id)
        await edit_admin_message(prompts[action], admin_game_keyboard(game_id, friends_allowed=game.get("friends_allowed", False), status=game.get("status")))
        await callback.answer()
        return

    if action == "confirm_cancel":
        await edit_admin_message(
            "Подтвердить отмену игры? Запись можно будет вернуть позже.",
            admin_confirm_keyboard(game_id, "cancel"),
        )
        await callback.answer()
        return

    if action == "confirm_close_registration":
        await edit_admin_message(
            "Подтвердить закрытие записи? Ее можно будет открыть обратно.",
            admin_confirm_keyboard(game_id, "close_registration"),
        )
        await callback.answer()
        return

    if action == "confirm_open_registration":
        await edit_admin_message(
            "Открыть запись обратно?",
            admin_confirm_keyboard(game_id, "open_registration"),
        )
        await callback.answer()
        return

    if action == "confirm_restore":
        await edit_admin_message(
            "Вернуть отмененную игру и снова открыть запись?",
            admin_confirm_keyboard(game_id, "restore"),
        )
        await callback.answer()
        return

    if action == "confirm_payments":
        hourly_rate = game.get("hourly_rate", 600)
        await edit_admin_message(
            "⏱ <b>Сколько времени играли?</b>\n\nСтоимость аренды поля будет поделена поровну между игроками основы.",
            payment_duration_keyboard(game_id, hourly_rate),
        )
        await callback.answer()
        return

    if action.startswith("paydur:"):
        minutes = int(action.split(":", 1)[1])
        hourly_rate = game.get("hourly_rate", 600)
        total_cost = int((minutes / 60) * hourly_rate)
        participants_repo = ParticipantRepository(db)
        confirmed_count = await participants_repo.count_confirmed(game_id)
        import math
        per_player = math.ceil(total_cost / confirmed_count) if confirmed_count > 0 else 0

        from bson import ObjectId
        await db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "status": "payment_collection",
                "duration_minutes": minutes,
                "total_cost": total_cost,
                "price": per_player,
                "updated_at": datetime.now(timezone.utc),
            }}
        )
        pay_repo = PaymentRepository(db)
        await pay_repo.ensure_for_game(game_id, per_player)
        fresh = await game_repo.get(game_id)
        await update_game_message(callback.bot, fresh)

        duration_hours = round(minutes / 60, 1)
        if duration_hours.is_integer():
            duration_hours = int(duration_hours)
        await edit_admin_message(
            f"✅ Сбор оплат начат!\n\n"
            f"Длительность: <b>{duration_hours} ч</b> ({minutes} мин)\n"
            f"Аренда поля: <b>{total_cost} грн</b>\n"
            f"Игроков в основе: <b>{confirmed_count}</b>\n"
            f"С каждого игрока: <b>{per_player} грн</b>\n\n"
            f"Карточки игры во всех группах обновлены.",
            admin_markup(fresh),
        )
        await callback.answer("Сбор оплат запущен!")
        return

    if action == "open_friends":
        await game_repo.open_friends(game_id)
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        await show_or_refresh_admin_message()
        await callback.answer("Друзья открыты")
        return

    if action == "close_friends":
        await game_repo.close_friends(game_id)
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        await show_or_refresh_admin_message()
        await callback.answer("Друзья закрыты")
        return

    if action == "do_close_registration":
        await game_repo.close_registration(game_id)
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        await show_or_refresh_admin_message()
        await callback.answer("Запись закрыта")
        return

    if action == "do_open_registration":
        await game_repo.open_registration(game_id)
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        await show_or_refresh_admin_message()
        await callback.answer("Запись открыта")
        return

    if action == "do_restore":
        await game_repo.restore_game(game_id)
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        await show_or_refresh_admin_message()
        await callback.answer("Игра возвращена")
        return

    if action == "do_payments":
        pay_repo = PaymentRepository(db)
        await pay_repo.ensure_for_game(game_id, game["price"])
        await game_repo.set_status(game_id, "payment_collection")
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        await show_or_refresh_admin_message()
        await callback.answer("Сбор оплат начат")
        return

    if action == "do_cancel":
        await game_repo.cancel_game(game_id, "отменено админом")
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        await show_or_refresh_admin_message()
        await callback.answer("Игра отменена")
        return

    await callback.answer("Неизвестное действие", show_alert=True)


@router.callback_query(F.data.startswith("game:"))
async def game_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, game_id, action = callback.data.split(":", 2)
    db = get_db()
    game_repo = GameRepository(db)
    participants_repo = ParticipantRepository(db)
    user_repo = UserRepository(db)

    game = await game_repo.get(game_id)
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    if game.get("status") == "cancelled":
        await callback.answer("Игра отменена", show_alert=True)
        return
    if game.get("status") == "registration_closed" and action in {"join", "add_friend"}:
        await callback.answer("Запись закрыта", show_alert=True)
        return
    if game.get("status") == "payment_collection" and action in {"join", "decline", "add_friend", "cancel_friend"}:
        await callback.answer("Игра уже в режиме оплаты", show_alert=True)
        return

    await user_repo.upsert_from_telegram(callback.from_user, is_admin=is_admin(callback.from_user.id))

    if action == "join":
        participant = await participants_repo.join_player(game, callback.from_user)
        await callback.answer("✅ Ты записан" if participant["status"] == "confirmed" else "🟡 Ты в резерве")
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        return

    if action == "decline":
        await participants_repo.decline_player(game_id, callback.from_user)
        await callback.answer("❌ Отметил, что ты не будешь")
        game = await game_repo.get(game_id)
        await update_game_message(callback.bot, game)
        return

    if action == "add_friend":
        if not can_add_friends_now(game):
            await callback.answer("Друзей пока нельзя добавлять. Смотри время открытия в сообщении игры", show_alert=True)
            return
        count = await participants_repo.count_friends_by_user(game_id, callback.from_user.id)
        if count >= 3:
            await callback.answer("Нельзя добавить больше 3 друзей", show_alert=True)
            return
        prompt = await send_private_message(callback.bot, callback.from_user.id, "Введите имя друга одним сообщением:")
        if not prompt:
            PENDING_PRIVATE_ACTIONS[callback.from_user.id] = {
                "type": "add_friend",
                "game_id": game_id,
            }
            await callback.answer("Нажми /start в личке с ботом, и я сразу запрошу имя друга!", show_alert=True)
            return
        pending_data = {"game_id": game_id, "prompt_chat_id": prompt.chat.id, "prompt_message_id": prompt.message_id}
        PENDING_FRIEND_INPUTS[callback.from_user.id] = pending_data
        # Оставляем FSM тоже: если стратегия хранения позволяет, сработает state-handler.
        await state.set_state(AddFriendState.waiting_name)
        await state.update_data(**pending_data)
        await callback.answer("Открыл ввод друга в личке")
        return

    if action == "cancel_friend":
        friends = await participants_repo.list_friends_by_user(game_id, callback.from_user.id)
        if not friends:
            await callback.answer("У тебя нет добавленных друзей для отмены", show_alert=True)
            return
        sent = await send_private_message(
            callback.bot,
            callback.from_user.id,
            "Выбери друга, которого нужно отменить:",
            reply_markup=friends_cancel_keyboard(game_id, friends),
        )
        if not sent:
            await callback.answer("Напиши боту /start в личке, чтобы отменить друга", show_alert=True)
            return
        await callback.answer("Открыл список друзей в личке")
        return


@router.callback_query(F.data.startswith("friend:"))
async def friend_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    db = get_db()
    game_repo = GameRepository(db)
    participants_repo = ParticipantRepository(db)

    if len(parts) == 3 and parts[2] == "back":
        game_id = parts[1]
        game = await game_repo.get(game_id)
        if game:
            await update_game_message(callback.bot, game)
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    if len(parts) != 4 or parts[3] != "cancel":
        await callback.answer("Некорректное действие", show_alert=True)
        return

    _, game_id, friend_id, _ = parts
    game = await game_repo.get(game_id)
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    if game.get("status") in {"cancelled", "payment_collection"}:
        await callback.answer("Отменить друга уже нельзя", show_alert=True)
        return

    ok = await participants_repo.cancel_friend(game_id, friend_id, callback.from_user.id)
    if not ok:
        await callback.answer("Не могу отменить этого друга", show_alert=True)
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    game = await game_repo.get(game_id)
    await update_game_message(callback.bot, game)
    await callback.answer("Друг отменен")


async def process_friend_name(message: Message, state: FSMContext | None, data: dict) -> None:
    game_id = data.get("game_id")
    friend_name = (message.text or "").strip()

    if len(friend_name) < 2:
        await temporary_reply(message, "Имя слишком короткое. Введите имя друга.")
        return
    if len(friend_name) > 64:
        await temporary_reply(message, "Имя слишком длинное. Введите короче.")
        return

    db = get_db()
    game = await GameRepository(db).get(game_id)
    if not game:
        await cleanup_friend_input(message, data)
        await temporary_reply(message, "Игра не найдена.")
        if state:
            await state.clear()
        PENDING_FRIEND_INPUTS.pop(message.from_user.id, None)
        return

    if game.get("status") in {"cancelled", "registration_closed", "payment_collection"}:
        await cleanup_friend_input(message, data)
        await temporary_reply(message, "❌ Сейчас нельзя добавлять друзей.")
        if state:
            await state.clear()
        PENDING_FRIEND_INPUTS.pop(message.from_user.id, None)
        return

    if not can_add_friends_now(game):
        await cleanup_friend_input(message, data)
        await temporary_reply(message, "❌ Друзей можно добавлять только после 00:00 дня игры.")
        if state:
            await state.clear()
        PENDING_FRIEND_INPUTS.pop(message.from_user.id, None)
        return

    participants_repo = ParticipantRepository(db)
    count = await participants_repo.count_friends_by_user(game_id, message.from_user.id)
    if count >= 3:
        await cleanup_friend_input(message, data)
        await temporary_reply(message, "❌ Нельзя добавить больше 3 друзей.")
        if state:
            await state.clear()
        PENDING_FRIEND_INPUTS.pop(message.from_user.id, None)
        return

    participant = await participants_repo.add_friend(game, message.from_user.id, friend_name)
    if state:
        await state.clear()
    PENDING_FRIEND_INPUTS.pop(message.from_user.id, None)
    await cleanup_friend_input(message, data)
    game = await GameRepository(db).get(game_id)
    await update_game_message(message.bot, game)
    await temporary_reply(message, "✅ Друг добавлен" if participant["status"] == "confirmed" else "🟡 Друг добавлен в резерв")


@router.message(AddFriendState.waiting_name)
async def add_friend_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await process_friend_name(message, state, data)


@router.message(F.chat.type == "private", lambda message: message.from_user.id in PENDING_FRIEND_INPUTS)
async def private_pending_friend_name(message: Message, state: FSMContext) -> None:
    data = PENDING_FRIEND_INPUTS.get(message.from_user.id)
    if not data:
        return
    await process_friend_name(message, state, data)


@router.message(AdminEditState.waiting_value)
async def admin_edit_value(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    game_id = data.get("game_id")
    edit_action = data.get("edit_action")
    raw = (message.text or "").strip()

    db = get_db()
    game_repo = GameRepository(db)
    participant_repo = ParticipantRepository(db)
    game = await game_repo.get(game_id)
    if not game:
        await message.answer("Игра не найдена.")
        await state.clear()
        return

    try:
        if edit_action == "edit_date":
            parts = raw.split()
            if len(parts) != 2:
                raise ValueError
            start_at = parse_date_time(parts[0], parts[1], get_settings().default_timezone)
            if start_at < now_tz(get_settings().default_timezone):
                await message.answer("❌ Нельзя перенести игру в прошлое. Попробуй еще раз.")
                return
            await game_repo.update_start_at(game_id, start_at)
            ok_text = "✅ Дата и время изменены."
        elif edit_action == "edit_price":
            price = int(raw)
            if price < 0:
                raise ValueError
            await game_repo.update_price(game_id, price)
            ok_text = "✅ Цена изменена."
        elif edit_action == "edit_duration":
            duration = int(raw)
            if duration <= 0:
                raise ValueError
            await game_repo.update_duration(game_id, duration)
            ok_text = "✅ Длительность игры изменена."
        elif edit_action == "edit_friends_hours":
            hours = int(raw)
            if hours < 0:
                raise ValueError
            await game_repo.update_friends_open_after_hours(game_id, hours)
            ok_text = "✅ Таймер открытия друзей изменен."
        elif edit_action == "edit_teams":
            teams = int(raw)
            if teams <= 0:
                raise ValueError
            game = await game_repo.update_format(game_id, teams_count=teams)
            await participant_repo.normalize_roster(game_id, game["max_players"])
            ok_text = "✅ Количество команд изменено."
        elif edit_action == "edit_players":
            players = int(raw)
            if players <= 0:
                raise ValueError
            game = await game_repo.update_format(game_id, players_per_team=players)
            await participant_repo.normalize_roster(game_id, game["max_players"])
            ok_text = "✅ Количество игроков изменено."
        else:
            raise ValueError
    except Exception:
        await message.answer("❌ Некорректное значение. Попробуй еще раз.")
        return

    await state.clear()
    game = await game_repo.get(game_id)
    await update_game_message(message.bot, game)
    await message.answer(
        ok_text,
        reply_markup=admin_game_keyboard(
            game_id,
            friends_allowed=game.get("friends_allowed", False),
            status=game.get("status"),
        ),
    )


@router.callback_query(F.data.startswith("pay:"))
async def payment_callback(callback: CallbackQuery) -> None:
    _, game_id, action = callback.data.split(":", 2)

    db = get_db()
    game_repo = GameRepository(db)
    pay_repo = PaymentRepository(db)

    game = await game_repo.get(game_id)
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    if game.get("status") != "payment_collection":
        await callback.answer("Сбор оплат еще не начат", show_alert=True)
        return

    if action == "friends":
        result = await send_private_friends_payment_menu(callback.bot, callback.from_user.id, game_id)
        if result == "no_friends":
            await callback.answer("У тебя нет друзей в основном составе", show_alert=True)
            return
        if not result:
            PENDING_PRIVATE_ACTIONS[callback.from_user.id] = {"type": "friends_payment", "game_id": game_id}
            await callback.answer("Напиши боту /start в личке — я сразу открою оплату друзей", show_alert=True)
            return
        await callback.answer("Открыл оплату друзей в личке")
        return

    if action == "paid":
        ok = await pay_repo.mark_paid_by_user(game_id, callback.from_user.id)
        answer_text = "✅ Оплата отмечена"
    elif action == "not_played":
        ok = await pay_repo.mark_not_played_by_user(game_id, callback.from_user.id)
        answer_text = "🚫 Отмечено: не играл"
    else:
        await callback.answer("Неизвестное действие", show_alert=True)
        return

    if not ok:
        await callback.answer("Ты не найден в основном составе этой игры", show_alert=True)
        return

    game = await game_repo.get(game_id)
    await update_game_message(callback.bot, game)
    await callback.answer(answer_text)


@router.callback_query(F.data.startswith("pfc:"))
async def friend_payment_close_callback(callback: CallbackQuery) -> None:
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("pf:"))
async def friend_payment_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    db = get_db()
    game_repo = GameRepository(db)
    pay_repo = PaymentRepository(db)
    participants_repo = ParticipantRepository(db)

    if len(parts) != 3:
        await callback.answer("Некорректное действие", show_alert=True)
        return

    _, participant_id, short_action = parts
    action_map = {"p": "paid", "n": "not_played"}
    action = action_map.get(short_action)
    if not action:
        await callback.answer("Некорректное действие", show_alert=True)
        return

    participant = await participants_repo.get(participant_id)
    if not participant:
        await callback.answer("Участник не найден", show_alert=True)
        return

    game_id = str(participant["game_id"])
    game = await game_repo.get(game_id)
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    if game.get("status") != "payment_collection":
        await callback.answer("Сбор оплат еще не начат", show_alert=True)
        return

    ok = await pay_repo.mark_by_participant_id(
        game_id,
        participant_id,
        action,
        callback.from_user.id,
        is_admin=is_admin(callback.from_user.id),
    )
    if not ok:
        await callback.answer("Не могу изменить оплату этого друга", show_alert=True)
        return

    game = await game_repo.get(game_id)
    await update_game_message(callback.bot, game)

    friends = await participants_repo.list_friends_by_user(game_id, callback.from_user.id)
    friends = [friend for friend in friends if friend.get("status") == "confirmed"]
    payments = await pay_repo.list_by_game(game_id)
    payments_by_participant_id = {str(payment["participant_id"]): payment for payment in payments}
    try:
        await callback.message.edit_reply_markup(
            reply_markup=friends_payment_keyboard(game_id, friends, payments_by_participant_id)
        )
    except TelegramBadRequest:
        pass
    await callback.answer("Оплата друга обновлена")


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()
