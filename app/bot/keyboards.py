from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def game_keyboard(game_id: str, friends_allowed: bool, status: str = "registration_open") -> InlineKeyboardMarkup | None:
    rows = []

    if status == "payment_collection":
        rows.append([
            InlineKeyboardButton(text="💳 Оплатил", callback_data=f"pay:{game_id}:paid"),
            InlineKeyboardButton(text="🚫 Не играл", callback_data=f"pay:{game_id}:not_played"),
        ])
        rows.append([
            InlineKeyboardButton(text="👥 Оплата друзей", callback_data=f"pay:{game_id}:friends"),
        ])
    elif status not in {"cancelled", "registration_closed", "closed", "game_started"}:
        rows.append([
            InlineKeyboardButton(text="✅ Буду", callback_data=f"game:{game_id}:join"),
            InlineKeyboardButton(text="❌ Не буду", callback_data=f"game:{game_id}:decline"),
        ])
        if friends_allowed:
            rows.append([
                InlineKeyboardButton(text="➕ Добавить друга", callback_data=f"game:{game_id}:add_friend"),
                InlineKeyboardButton(text="➖ Отменить друга", callback_data=f"game:{game_id}:cancel_friend"),
            ])

    rows.append([InlineKeyboardButton(text="⚙️ Управление", callback_data=f"admin:{game_id}:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_game_keyboard(game_id: str, *, friends_allowed: bool, status: str) -> InlineKeyboardMarkup:
    if status == "cancelled":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Вернуть игру", callback_data=f"admin:{game_id}:confirm_restore")],
        ])

    close_text = "🔓 Открыть запись" if status == "registration_closed" else "🔒 Закрыть запись"
    close_action = "confirm_open_registration" if status == "registration_closed" else "confirm_close_registration"
    friends_text = "👥 Закрыть друзей" if friends_allowed else "👥 Открыть друзей"
    friends_action = "close_friends" if friends_allowed else "open_friends"
    
    rows = [
        [
            InlineKeyboardButton(text="📅 Дата", callback_data=f"admin:{game_id}:edit_date"),
            InlineKeyboardButton(text="💰 Цена", callback_data=f"admin:{game_id}:edit_price"),
        ],
        [
            InlineKeyboardButton(text="👥 Команды", callback_data=f"admin:{game_id}:edit_teams"),
            InlineKeyboardButton(text="🏃 Игроки", callback_data=f"admin:{game_id}:edit_players"),
        ],
        [
            InlineKeyboardButton(text="⏱ Длительность", callback_data=f"admin:{game_id}:edit_duration"),
            InlineKeyboardButton(text="👥 Таймер друзей", callback_data=f"admin:{game_id}:edit_friends_hours"),
        ],
        [InlineKeyboardButton(text="📢 Публикация в группах", callback_data=f"admin:{game_id}:broadcast_menu")],
    ]

    if status not in {"game_started", "payment_collection"}:
        rows.append([InlineKeyboardButton(text=friends_text, callback_data=f"admin:{game_id}:{friends_action}")])
        rows.append([InlineKeyboardButton(text=close_text, callback_data=f"admin:{game_id}:{close_action}")])
        rows.append([InlineKeyboardButton(text="▶️ Начать игру", callback_data=f"admin:{game_id}:start_game")])

    rows.append([InlineKeyboardButton(text="💳 Начать сбор оплат", callback_data=f"admin:{game_id}:confirm_payments")])
    rows.append([InlineKeyboardButton(text="❌ Отменить игру", callback_data=f"admin:{game_id}:confirm_cancel")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_confirmation_keyboard(game_id: str, duration_minutes: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оставить эту карту", callback_data=f"admin:{game_id}:card_keep:{duration_minutes}")],
        [InlineKeyboardButton(text="✏️ Изменить карту", callback_data=f"admin:{game_id}:card_edit:{duration_minutes}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:{game_id}:confirm_payments")],
    ])


def broadcast_groups_keyboard(game_id: str, chats: list[dict], linked_chat_ids: set[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📢 Опубликовать во всех", callback_data=f"admin:{game_id}:pub_all")]
    ]
    for chat in chats:
        cid = chat["chat_id"]
        title = chat.get("title", str(cid))
        if cid in linked_chat_ids:
            btn_text = f"✅ {title}"
            callback = f"admin:{game_id}:unpub:{cid}"
        else:
            btn_text = f"➕ {title}"
            callback = f"admin:{game_id}:pub:{cid}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=callback)])
    rows.append([InlineKeyboardButton(text="⚙️ Меню игры", callback_data=f"admin:{game_id}:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_confirm_keyboard(game_id: str, action: str) -> InlineKeyboardMarkup:
    labels = {
        "close_registration": "🔒 Да, закрыть запись",
        "open_registration": "🔓 Да, открыть запись",
        "cancel": "❌ Да, отменить игру",
        "restore": "↩️ Да, вернуть игру",
        "payments": "💳 Да, начать сбор оплат",
    }
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=labels.get(action, "✅ Подтвердить"), callback_data=f"admin:{game_id}:do_{action}")],
        [InlineKeyboardButton(text="Назад", callback_data=f"admin:{game_id}:settings")],
    ])


def payment_duration_keyboard(game_id: str, hourly_rate: int = 600) -> InlineKeyboardMarkup:
    cost_90 = int(1.5 * hourly_rate)
    cost_120 = int(2.0 * hourly_rate)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"⏱ 1.5 часа ({cost_90} грн)", callback_data=f"admin:{game_id}:paydur:90"),
            InlineKeyboardButton(text=f"⏱ 2.0 часа ({cost_120} грн)", callback_data=f"admin:{game_id}:paydur:120"),
        ],
        [InlineKeyboardButton(text="Назад", callback_data=f"admin:{game_id}:settings")],
    ])


def friends_cancel_keyboard(game_id: str, friends: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for friend in friends:
        rows.append([
            InlineKeyboardButton(
                text=f"➖ {friend['display_name']}",
                callback_data=f"friend:{game_id}:{friend['_id']}:cancel",
            )
        ])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"friend:{game_id}:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_keyboard(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатил", callback_data=f"pay:{game_id}:paid")],
            [InlineKeyboardButton(text="🚫 Не играл", callback_data=f"pay:{game_id}:not_played")],
        ]
    )


def friends_payment_keyboard(game_id: str, friends: list[dict], payments_by_participant_id: dict[str, dict]) -> InlineKeyboardMarkup:
    """Кнопки оплаты друзей.

    Важно: Telegram callback_data ограничен 64 байтами.
    Поэтому нельзя класть в callback_data одновременно game_id и participant_id.
    Используем только participant_id, а game_id достаем из participant в обработчике.
    """
    rows = []
    for friend in friends:
        participant_id = str(friend["_id"])
        payment = payments_by_participant_id.get(participant_id)
        status = payment.get("status") if payment else "pending"
        if status == "paid":
            status_text = "✅"
        elif status == "not_played":
            status_text = "🚫"
        else:
            status_text = "❌"
        rows.append([InlineKeyboardButton(text=f"{status_text} {friend['display_name']}", callback_data="noop")])
        rows.append([
            InlineKeyboardButton(text="✅ Оплатил", callback_data=f"pf:{participant_id}:p"),
            InlineKeyboardButton(text="🚫 Не играл", callback_data=f"pf:{participant_id}:n"),
        ])
    rows.append([InlineKeyboardButton(text="Закрыть", callback_data=f"pfc:{game_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
