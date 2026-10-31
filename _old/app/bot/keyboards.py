from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def game_keyboard(game_id: str, friends_allowed: bool, status: str = "registration_open") -> InlineKeyboardMarkup | None:
    rows = []

    if status == "payment_collection":
        rows.append([
            InlineKeyboardButton(text="💳 Оплатил", callback_data=f"pay:{game_id}:paid"),
            InlineKeyboardButton(text="🚫 Не играл", callback_data=f"pay:{game_id}:not_played"),
        ])
    elif status not in {"cancelled", "registration_closed", "closed"}:
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=friends_text, callback_data=f"admin:{game_id}:{friends_action}")],
        [InlineKeyboardButton(text=close_text, callback_data=f"admin:{game_id}:{close_action}")],
        [InlineKeyboardButton(text="💳 Начать сбор оплат", callback_data=f"admin:{game_id}:confirm_payments")],
        [InlineKeyboardButton(text="❌ Отменить игру", callback_data=f"admin:{game_id}:confirm_cancel")],
    ])


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
