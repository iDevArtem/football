from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def game_keyboard(
    game_id: str,
    friends_allowed: bool,
    status: str = "registration_open",
    location: dict | None = None,
) -> InlineKeyboardMarkup | None:
    rows = []

    if status == "payment_collection":
        rows.append([
            InlineKeyboardButton(text="💳 Оплатил", callback_data=f"pay:{game_id}:paid"),
        ])
        rows.append([
            InlineKeyboardButton(text="👥 Оплата друзей", callback_data=f"pay:{game_id}:friends"),
        ])
    elif status not in {"cancelled", "registration_closed", "closed", "game_started", "finished"}:
        rows.append([
            InlineKeyboardButton(text="✅ Буду", callback_data=f"game:{game_id}:join"),
            InlineKeyboardButton(text="❌ Не буду", callback_data=f"game:{game_id}:decline"),
        ])
        if friends_allowed:
            rows.append([
                InlineKeyboardButton(text="➕ Добавить друга", callback_data=f"game:{game_id}:add_friend"),
                InlineKeyboardButton(text="➖ Отменить друга", callback_data=f"game:{game_id}:cancel_friend"),
            ])

    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_game_keyboard(game_id: str, *, friends_allowed: bool, status: str) -> InlineKeyboardMarkup | None:
    if status in {"cancelled", "closed"}:
        return None

    if status == "finished":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Начать сбор оплат", callback_data=f"admin:{game_id}:confirm_payments")],
            [InlineKeyboardButton(text="💵 Оплата наличными", callback_data=f"admin:{game_id}:confirm_cash_payments")],
            [InlineKeyboardButton(text="📢 Публикация в группах", callback_data=f"admin:{game_id}:broadcast_menu")],
            [InlineKeyboardButton(text="❌ Отменить игру", callback_data=f"admin:{game_id}:confirm_cancel")],
        ])

    if status == "payment_collection":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить сбор оплат", callback_data=f"admin:{game_id}:confirm_close_payments")],
            [InlineKeyboardButton(text="📢 Публикация в группах", callback_data=f"admin:{game_id}:broadcast_menu")],
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
            InlineKeyboardButton(text="⏱️ Длительность", callback_data=f"admin:{game_id}:edit_duration"),
            InlineKeyboardButton(text="👥 Таймер друзей", callback_data=f"admin:{game_id}:edit_friends_hours"),
        ],
        [
            InlineKeyboardButton(text="📍 Локация", callback_data=f"admin:{game_id}:edit_location"),
            InlineKeyboardButton(text="📢 Публикация в группах", callback_data=f"admin:{game_id}:broadcast_menu"),
        ],
    ]

    if status != "game_started":
        rows.append([InlineKeyboardButton(text=friends_text, callback_data=f"admin:{game_id}:{friends_action}")])
        rows.append([InlineKeyboardButton(text=close_text, callback_data=f"admin:{game_id}:{close_action}")])
        rows.append([InlineKeyboardButton(text="▶️ Начать игру", callback_data=f"admin:{game_id}:start_game")])

    rows.append([InlineKeyboardButton(text="🏁 Завершить игру", callback_data=f"admin:{game_id}:finish_game")])
    rows.append([InlineKeyboardButton(text="❌ Отменить игру", callback_data=f"admin:{game_id}:confirm_cancel")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_post_finish_keyboard(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Начать сбор оплат", callback_data=f"admin:{game_id}:confirm_payments")],
        [InlineKeyboardButton(text="💵 Оплата наличными", callback_data=f"admin:{game_id}:confirm_cash_payments")],
        [InlineKeyboardButton(text="⚙️ Меню игры", callback_data=f"admin:{game_id}:settings")],
    ])


def admin_cancel_edit_keyboard(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin:{game_id}:settings")],
    ])


def admin_finish_game_keyboard(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏁 Завершить без медиа/текста", callback_data=f"admin:{game_id}:do_finish_nocomment")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin:{game_id}:settings")],
    ])


def card_confirmation_keyboard(game_id: str, duration_minutes: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оставить эту карту", callback_data=f"admin:{game_id}:card_keep:{duration_minutes}")],
        [InlineKeyboardButton(text="✏️ Изменить карту", callback_data=f"admin:{game_id}:card_edit:{duration_minutes}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:{game_id}:pay_dur_menu")],
    ])


def broadcast_groups_keyboard(game_id: str, chats: list[dict], linked_chat_ids: set[int]) -> InlineKeyboardMarkup:
    has_linked = any(c["chat_id"] in linked_chat_ids for c in chats)
    top_row = [
        InlineKeyboardButton(text="📢 Опубликовать во всех", callback_data=f"admin:{game_id}:pub_all")
    ]
    if has_linked:
        top_row.append(
            InlineKeyboardButton(text="🔄 Переотправить во всех", callback_data=f"admin:{game_id}:repub_all")
        )
    rows = [top_row]

    for chat in chats:
        cid = chat["chat_id"]
        title = chat.get("title", str(cid))
        if cid in linked_chat_ids:
            rows.append([
                InlineKeyboardButton(text=f"✅ {title}", callback_data=f"admin:{game_id}:unpub:{cid}"),
                InlineKeyboardButton(text="🔄 Вниз", callback_data=f"admin:{game_id}:repub:{cid}"),
            ])
        else:
            rows.append([InlineKeyboardButton(text=f"➕ {title}", callback_data=f"admin:{game_id}:pub:{cid}")])
    rows.append([InlineKeyboardButton(text="⚙️ Меню игры", callback_data=f"admin:{game_id}:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_confirm_keyboard(game_id: str, action: str) -> InlineKeyboardMarkup:
    labels = {
        "close_registration": "🔒 Да, закрыть запись",
        "open_registration": "🔓 Да, открыть запись",
        "cancel": "❌ Да, отменить игру",
        "payments": "💳 Да, начать сбор оплат",
        "close_payments": "✅ Да, завершить сбор оплат",
    }
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=labels.get(action, "✅ Подтвердить"), callback_data=f"admin:{game_id}:do_{action}")],
        [InlineKeyboardButton(text="Назад", callback_data=f"admin:{game_id}:settings")],
    ])


def payment_duration_keyboard(game_id: str, hourly_rate: int = 600, back_action: str = "confirm_payments") -> InlineKeyboardMarkup:
    cost_90 = int(1.5 * hourly_rate)
    cost_120 = int(2.0 * hourly_rate)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"⏱ 1.5 часа ({cost_90} грн)", callback_data=f"admin:{game_id}:paydur:90"),
            InlineKeyboardButton(text=f"⏱ 2.0 часа ({cost_120} грн)", callback_data=f"admin:{game_id}:paydur:120"),
        ],
        [InlineKeyboardButton(text="Назад", callback_data=f"admin:{game_id}:{back_action}")],
    ])


def verify_roster_keyboard(game_id: str, participants: list[dict], excluded_ids: set[str] | None = None) -> InlineKeyboardMarkup:
    excluded = excluded_ids or set()
    rows = []
    for participant in participants:
        p_id = str(participant["_id"])
        name = participant.get("display_name", "Игрок")
        is_reserve = participant.get("status") == "reserve"
        is_friend = participant.get("type") in ("friend", "guest")
        mark = "👥 " if is_friend else ""
        reserve_suffix = ", не играл" if is_reserve else ""
        reserve_mark = " (резерв)" if is_reserve else ""

        if p_id in excluded:
            if is_reserve:
                btn_text = f"🚫 {mark}{name} (резерв, не играл)"
            else:
                btn_text = f"🚫 {mark}{name} (не играл)"
        else:
            btn_text = f"✅ {mark}{name}{reserve_mark}"
        rows.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"vr:{game_id}:{p_id}")
        ])
    playing_count = len(participants) - len(excluded)
    rows.append([
        InlineKeyboardButton(
            text=f"➡️ К расчету ({playing_count} чел)",
            callback_data=f"admin:{game_id}:pay_dur_menu",
        )
    ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=f"admin:{game_id}:settings")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def friends_cancel_keyboard(game_id: str, friends: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for friend in friends:
        rows.append([
            InlineKeyboardButton(
                text=f"➖ {friend['display_name']}",
                callback_data=f"fc:{friend['_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"fc_back:{game_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_keyboard(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатил", callback_data=f"pay:{game_id}:paid")],
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
            rows.append([InlineKeyboardButton(text=f"{status_text} {friend['display_name']} (оплачено)", callback_data="noop")])
        elif status == "not_played":
            status_text = "🚫"
            rows.append([InlineKeyboardButton(text=f"{status_text} {friend['display_name']} (не играл)", callback_data="noop")])
        else:
            status_text = "❌"
            rows.append([InlineKeyboardButton(text=f"{status_text} {friend['display_name']}", callback_data="noop")])
            rows.append([
                InlineKeyboardButton(text="✅ Оплатил", callback_data=f"pf:{participant_id}:p"),
            ])
    rows.append([InlineKeyboardButton(text="Закрыть", callback_data=f"pfc:{game_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
