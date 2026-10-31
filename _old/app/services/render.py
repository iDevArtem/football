from html import escape


def game_id(game: dict) -> str:
    return str(game["_id"])


def status_text(status: str) -> str:
    return {
        "registration_open": "запись открыта",
        "friends_allowed": "друзья открыты",
        "registration_closed": "запись закрыта",
        "payment_collection": "сбор оплат",
        "cancelled": "игра отменена",
        "closed": "закрыта",
        "full": "состав набран",
    }.get(status, status)


def format_game_message(game: dict, participants: list[dict], payments: list[dict] | None = None) -> str:
    status = game.get("status", "registration_open")

    confirmed = [p for p in participants if p["status"] == "confirmed"]
    reserve = [p for p in participants if p["status"] == "reserve"]
    declined = [p for p in participants if p["status"] == "declined"]

    payment_by_participant_id = {}
    if payments:
        payment_by_participant_id = {str(p["participant_id"]): p for p in payments}

    start_at = game["start_at"]
    date_text = start_at.strftime("%d.%m.%Y")
    time_text = start_at.strftime("%H:%M")
    friends_text = "открыты" if game.get("friends_allowed") else "закрыты до 00:00"

    prefix = "❌ " if status == "cancelled" else "⚽ "
    lines = [
        f"{prefix}<b>{escape(game['title'])}</b>",
        "",
        f"Статус: <b>{escape(status_text(status))}</b>",
    ]
    if status == "cancelled" and game.get("cancel_reason"):
        lines.append(f"Причина: <b>{escape(game['cancel_reason'])}</b>")

    lines += [
        f"Дата: <b>{date_text}</b>",
        f"Время: <b>{time_text}</b>",
        f"Формат: <b>{game['teams_count']} × {game['players_per_team']}</b>",
        f"Нужно игроков: <b>{game['max_players']}</b>",
        f"Цена: <b>{game['price']} грн</b>",
        "",
        f"✅ Основной состав: <b>{len(confirmed)} / {game['max_players']}</b>",
        f"🟡 Резерв: <b>{len(reserve)}</b>",
        f"👥 Друзья: <b>{friends_text}</b>",
        "",
    ]

    if status == "payment_collection":
        paid_count = 0
        not_played_count = 0
        pending_count = 0

        lines.append("<b>Основной состав и оплата:</b>")
        if confirmed:
            for index, participant in enumerate(confirmed, 1):
                mark = "👥" if participant["type"] == "friend" else "•"
                payment = payment_by_participant_id.get(str(participant["_id"]))
                payment_status = payment.get("status") if payment else "pending"
                if payment_status == "paid":
                    pay_mark = "✅ оплатил"
                    paid_count += 1
                elif payment_status == "not_played":
                    pay_mark = "🚫 не играл"
                    not_played_count += 1
                else:
                    pay_mark = "❌ не оплатил"
                    pending_count += 1
                lines.append(f"{index}. {mark} {escape(participant['display_name'])} — <b>{pay_mark}</b>")
        else:
            lines.append("—")
        lines += [
            "",
            f"💳 Оплатили: <b>{paid_count}</b>",
            f"🚫 Не играли: <b>{not_played_count}</b>",
            f"❌ Не оплатили: <b>{pending_count}</b>",
            "",
        ]
    elif confirmed:
        lines.append("<b>Основной состав:</b>")
        for index, p in enumerate(confirmed, 1):
            mark = "👥" if p["type"] == "friend" else "•"
            lines.append(f"{index}. {mark} {escape(p['display_name'])}")
        lines.append("")

    if reserve:
        lines.append("<b>Резерв:</b>")
        for index, p in enumerate(reserve, 1):
            mark = "👥" if p["type"] == "friend" else "•"
            lines.append(f"{index}. {mark} {escape(p['display_name'])}")
        lines.append("")

    if declined:
        lines.append(f"❌ Отказались: {len(declined)}")
        lines.append("")

    if status == "payment_collection":
        lines.append("Сбор оплат начат. Нажмите кнопку ниже: оплатил или не играл.")
    elif status == "cancelled":
        lines.append("Игра отменена. Кнопки записи отключены.")
    elif status == "registration_closed":
        lines.append("Запись закрыта админом.")
    elif game.get("friends_allowed"):
        lines.append("Можно добавить до 3 друзей от одного участника.")
    else:
        lines.append("До 00:00 записываются только участники группы.")

    return "\n".join(lines).strip()


def format_game_payment_message(game: dict, participants: list[dict], payments: list[dict]) -> str:
    payment_by_participant_id = {str(p["participant_id"]): p for p in payments}
    confirmed = [p for p in participants if p.get("status") == "confirmed"]
    paid = []
    not_played = []
    pending = []

    for participant in confirmed:
        payment = payment_by_participant_id.get(str(participant["_id"]))
        payment_status = payment.get("status") if payment else "pending"
        name = participant["display_name"]
        if payment_status == "paid":
            paid.append(name)
        elif payment_status == "not_played":
            not_played.append(name)
        else:
            pending.append(name)

    lines = [
        f"💳 <b>Сбор оплат за игру</b>",
        "",
        f"Игра: <b>{escape(game['title'])}</b>",
        f"Сумма: <b>{game['price']} грн</b>",
        "",
        f"✅ Оплатили: <b>{len(paid)}</b>",
    ]
    lines += [f"{i}. {escape(name)}" for i, name in enumerate(paid, 1)] or ["—"]
    lines += ["", f"🚫 Не играли: <b>{len(not_played)}</b>"]
    lines += [f"{i}. {escape(name)}" for i, name in enumerate(not_played, 1)] or ["—"]
    lines += ["", f"❌ Не оплатили: <b>{len(pending)}</b>"]
    lines += [f"{i}. {escape(name)}" for i, name in enumerate(pending, 1)] or ["—"]
    lines += ["", "Нажмите кнопку ниже, чтобы отметить оплату или указать, что вы не играли."]
    return "\n".join(lines).strip()


def format_payments_message(game: dict, payments: list[dict]) -> str:
    paid = []
    not_played = []
    pending = []
    for payment in payments:
        name = payment["participant"]["display_name"]
        if payment["status"] == "paid":
            paid.append(name)
        elif payment["status"] == "not_played":
            not_played.append(name)
        else:
            pending.append(name)

    lines = [
        f"💳 <b>Оплата: {escape(game['title'])}</b>",
        "",
        f"Сумма: <b>{game['price']} грн</b>",
        "",
        f"✅ Оплатили: <b>{len(paid)}</b>",
    ]
    lines += [f"• {escape(name)}" for name in paid] or ["—"]
    lines += ["", f"🚫 Не играли: <b>{len(not_played)}</b>"]
    lines += [f"• {escape(name)}" for name in not_played] or ["—"]
    lines += ["", f"❌ Не оплатили: <b>{len(pending)}</b>"]
    lines += [f"• {escape(name)}" for name in pending] or ["—"]
    return "\n".join(lines)
