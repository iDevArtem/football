from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, timezone

from app.config.settings import get_settings
from app.db.mongo import get_db
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository
from app.repositories.payments import PaymentRepository
from app.repositories.users import UserRepository
from app.bot.keyboards import game_keyboard, friends_cancel_keyboard, payment_keyboard, admin_game_keyboard, admin_confirm_keyboard
from app.services.render import format_game_message, format_payments_message
from app.utils.dates import parse_date_time

router = Router()


class AddFriendState(StatesGroup):
    waiting_name = State()


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


async def update_game_message(bot, game: dict) -> None:
    db = get_db()
    game_id = str(game["_id"])
    participants = await ParticipantRepository(db).list_by_game(game_id)
    payments = []
    if game.get("status") == "payment_collection":
        payments = await PaymentRepository(db).list_by_game(game_id)
    text = format_game_message(game, participants, payments)
    try:
        await bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["message_id"],
            text=text,
            reply_markup=game_keyboard(game_id, game.get("friends_allowed", False), game.get("status")),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass


async def get_active_game_or_reply(message: Message) -> dict | None:
    db = get_db()
    game = await GameRepository(db).get_manageable_for_chat(message.chat.id)
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


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        "⚽ Бот для записи на футбол.\n\n"
        "Игру нужно создавать в группе, где стоит бот.\n\n"
        "Команда создания:\n"
        "<code>/new_game 2026-06-12 20:00 3 6 200</code>\n\n"
        "Формат: дата время команды игроков_в_команде цена\n\n"
        "Управление активной игрой:\n"
        "<code>/game_settings</code>",
        parse_mode="HTML",
    )


@router.message(Command("new_game"))
async def new_game(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply("❌ Создавать игру может только админ.")
        return
    if not is_group_chat(message):
        await message.reply("❌ Игру нужно создавать в группе, а не в личке с ботом.")
        return

    parts = message.text.split()
    if len(parts) != 6:
        await message.reply(
            "Формат команды:\n"
            "<code>/new_game 2026-06-12 20:00 3 6 200</code>\n\n"
            "Дата Время Команды ИгроковВКоманде Цена",
            parse_mode="HTML",
        )
        return

    _, date_raw, time_raw, teams_raw, players_raw, price_raw = parts
    try:
        teams_count = int(teams_raw)
        players_per_team = int(players_raw)
        price = int(price_raw)
        if teams_count <= 0 or players_per_team <= 0 or price < 0:
            raise ValueError
        start_at = parse_date_time(date_raw, time_raw, get_settings().default_timezone)
    except Exception:
        await message.reply("❌ Не смог разобрать команду. Проверь дату, время и числа.")
        return

    db = get_db()
    await UserRepository(db).upsert_from_telegram(message.from_user, is_admin=True)
    game_repo = GameRepository(db)
    game = await game_repo.create_game(
        chat_id=message.chat.id,
        title="Футбол",
        start_at=start_at,
        teams_count=teams_count,
        players_per_team=players_per_team,
        price=price,
        created_by=message.from_user.id,
    )
    sent = await message.answer(
        format_game_message(game, []),
        reply_markup=game_keyboard(str(game["_id"]), False, game.get("status")),
        parse_mode="HTML",
    )
    await game_repo.set_message_id(str(game["_id"]), sent.message_id)


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
        await message.reply("❌ Только админ.")
        return
    game = await get_active_game_or_reply(message)
    if not game:
        return
    await message.reply(
        "⚙️ Управление активной игрой\n\n"
        "Редактирование командами:\n"
        "<code>/edit_date 2026-06-19 20:00</code>\n"
        "<code>/edit_price 250</code>\n"
        "<code>/edit_teams 3</code>\n"
        "<code>/edit_players 7</code>\n"
        "<code>/close_friends</code>\n\n"
        "Быстрые действия:",
        reply_markup=admin_game_keyboard(str(game["_id"]), friends_allowed=game.get("friends_allowed", False), status=game.get("status")),
        parse_mode="HTML",
    )


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
        await message.reply("Формат: <code>/edit_date 2026-06-19 20:00</code>", parse_mode="HTML")
        return
    try:
        start_at = parse_date_time(parts[1], parts[2], get_settings().default_timezone)
    except Exception:
        await message.reply("❌ Не смог разобрать дату и время.")
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
    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_active_for_chat(message.chat.id)
    if not game:
        await message.reply("Активной игры нет.")
        return
    pay_repo = PaymentRepository(db)
    await pay_repo.ensure_for_game(str(game["_id"]), game["price"])
    await game_repo.set_status(str(game["_id"]), "payment_collection")
    game = await game_repo.get(str(game["_id"]))
    await update_game_message(message.bot, game)
    # Отдельное сообщение оплаты больше не создаем.
    # Главное сообщение игры теперь меняет текст и кнопки на «Оплатил / Не играл».


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback(callback: CallbackQuery) -> None:
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
        """Админское меню не должно заменять главное сообщение игры."""
        fresh = await game_repo.get(game_id)
        text = "⚙️ Управление активной игрой"
        markup = admin_markup(fresh)

        is_main_game_message = callback.message and callback.message.message_id == fresh.get("message_id")
        if force_new or is_main_game_message:
            await callback.message.answer(text, reply_markup=markup)
            return

        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            try:
                await callback.message.edit_reply_markup(reply_markup=markup)
            except TelegramBadRequest:
                pass

    async def edit_admin_message(text: str, markup) -> None:
        """Confirm-экраны показываем только в админском служебном сообщении."""
        fresh = await game_repo.get(game_id)
        is_main_game_message = callback.message and callback.message.message_id == fresh.get("message_id")
        if is_main_game_message:
            await callback.message.answer(text, reply_markup=markup)
            return
        await callback.message.edit_text(text, reply_markup=markup)

    if action == "settings":
        await show_or_refresh_admin_message(force_new=True)
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
        await edit_admin_message(
            "Начать сбор оплат? После этого запись будет отключена.",
            admin_confirm_keyboard(game_id, "payments"),
        )
        await callback.answer()
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
            await callback.answer("Друзей можно добавлять только после 00:00 дня игры", show_alert=True)
            return
        count = await participants_repo.count_friends_by_user(game_id, callback.from_user.id)
        if count >= 3:
            await callback.answer("Нельзя добавить больше 3 друзей", show_alert=True)
            return
        await state.set_state(AddFriendState.waiting_name)
        prompt = await callback.message.answer("Введите имя друга одним сообщением:")
        await state.update_data(game_id=game_id, prompt_chat_id=prompt.chat.id, prompt_message_id=prompt.message_id)
        await callback.answer()
        return

    if action == "cancel_friend":
        friends = await participants_repo.list_friends_by_user(game_id, callback.from_user.id)
        if not friends:
            await callback.answer("У тебя нет добавленных друзей для отмены", show_alert=True)
            return
        await callback.message.answer(
            "Выбери друга, которого нужно отменить:",
            reply_markup=friends_cancel_keyboard(game_id, friends),
        )
        await callback.answer()
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


@router.message(AddFriendState.waiting_name)
async def add_friend_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    game_id = data.get("game_id")
    friend_name = message.text.strip()

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
        await state.clear()
        return

    if game.get("status") in {"cancelled", "registration_closed", "payment_collection"}:
        await cleanup_friend_input(message, data)
        await temporary_reply(message, "❌ Сейчас нельзя добавлять друзей.")
        await state.clear()
        return

    if not can_add_friends_now(game):
        await cleanup_friend_input(message, data)
        await temporary_reply(message, "❌ Друзей можно добавлять только после 00:00 дня игры.")
        await state.clear()
        return

    participants_repo = ParticipantRepository(db)
    count = await participants_repo.count_friends_by_user(game_id, message.from_user.id)
    if count >= 3:
        await cleanup_friend_input(message, data)
        await temporary_reply(message, "❌ Нельзя добавить больше 3 друзей.")
        await state.clear()
        return

    participant = await participants_repo.add_friend(game, message.from_user.id, friend_name)
    await state.clear()
    await cleanup_friend_input(message, data)
    game = await GameRepository(db).get(game_id)
    await update_game_message(message.bot, game)
    await temporary_reply(message, "✅ Друг добавлен" if participant["status"] == "confirmed" else "🟡 Друг добавлен в резерв")


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
