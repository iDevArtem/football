from html import escape


def game_id(game: dict) -> str:
    return str(game["_id"])


def status_text(status: str) -> str:
    return {
        "registration_open": "запись открыта",
        "friends_allowed": "друзья открыты",
        "registration_closed": "запись закрыта",
        "game_started": "игра началась ⚽",
        "payment_collection": "сбор оплат",
        "cancelled": "игра отменена",
        "closed": "закрыта",
        "full": "состав набран",
    }.get(status, status)


def _format_dt(value) -> str:
    if not value:
        return "не задано"
    return value.strftime("%d.%m.%Y %H:%M")


def dynamic_format_text(confirmed_count: int, max_players: int = 15) -> str:
    if max_players == 15:
        if confirmed_count < 10:
            return "⏳ Сбор состава (нужно от 10 чел для 5х5)"
        if confirmed_count == 10:
            return "⚽ 2 команды 5х5 (10 чел)"
        if confirmed_count in (11, 12):
            return f"⚽ 2 команды 5х5 (+{confirmed_count - 10} на замену)"
        if confirmed_count in (13, 14):
            return f"⚽ 3 команды ({confirmed_count} чел, с ротацией/заменами)"
        if confirmed_count == 15:
            return "🔥 3 команды 5х5 (15 чел — полный сбор!)"
        return f"🔥 3 команды 5х5 (основа 15, резерв {confirmed_count - 15})"

    if confirmed_count < max_players:
        return f"⏳ Сбор состава ({confirmed_count}/{max_players})"
    if confirmed_count == max_players:
        return f"🔥 Состав набран ({max_players} чел — сбор закрыт)"
    return f"🔥 Состав набран ({max_players} чел, резерв {confirmed_count - max_players})"


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

    prefix = "❌ " if status == "cancelled" else "⚽ "
    lines = [
        f"{prefix}<b>{escape(game['title'])}</b>",
        "",
        f"Статус: <b>{escape(status_text(status))}</b>",
    ]
    loc = game.get("location")
    if loc and (loc.get("title") or loc.get("address")):
        title_part = escape(loc.get("title", ""))
        addr_part = f" ({escape(loc.get('address', ''))})" if loc.get("address") else ""
        lines.append(f"📍 Место: <b>{title_part}</b>{addr_part}")
    if status == "cancelled" and game.get("cancel_reason"):
        lines.append(f"Причина: <b>{escape(game['cancel_reason'])}</b>")

    max_players = game.get("max_players", 15)
    hourly_rate = game.get("hourly_rate", 600)
    duration_min = game.get("duration_minutes", 90)
    duration_hours = round(duration_min / 60, 1)
    if duration_hours.is_integer():
        duration_hours = int(duration_hours)

    lines += [
        f"Дата: <b>{date_text}</b>",
        f"Время: <b>{time_text}</b>",
        f"Длительность: <b>{duration_min} мин ({duration_hours} ч)</b>",
        f"Формат: <b>{dynamic_format_text(len(confirmed), max_players)}</b>",
    ]

    if status == "payment_collection":
        total_cost = game.get("total_cost") or int((duration_min / 60) * hourly_rate)
        price_per_player = game.get("price", 0)
        lines.append(f"💳 Аренда поля: <b>{total_cost} грн ({duration_hours} ч)</b> — по <b>{price_per_player} грн</b> с игрока")
    else:
        lines.append(f"💰 Аренда поля: <b>{hourly_rate} грн/час</b> (делится на всех пришедших)")

    lines += [
        "",
        f"✅ Основной состав: <b>{len(confirmed)} / {max_players}</b>",
        f"🟡 Резерв: <b>{len(reserve)}</b>",
        "",
    ]

    if status == "payment_collection":
        paid_count = 0
        not_played_count = 0
        pending_count = 0

        lines.append("<b>Основной состав и оплата:</b>")
        if confirmed:
            for index, participant in enumerate(confirmed, 1):
                mark = "👥" if participant.get("type") in ("friend", "guest") else "•"
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

        pay_details = game.get("payment_details") or {}
        card_number = pay_details.get("card_number")
        recipient = pay_details.get("recipient")
        if card_number:
            recipient_str = f" ({escape(recipient)})" if recipient else ""
            lines.append(f"💳 Оплата на карту:\n<code>{escape(card_number)}</code>{recipient_str}\n(нажмите на номер, чтобы скопировать)")
            lines.append("")
    elif confirmed:
        lines.append("<b>Основной состав:</b>")
        for index, p in enumerate(confirmed, 1):
            mark = "👥" if p.get("type") in ("friend", "guest") else "•"
            lines.append(f"{index}. {mark} {escape(p['display_name'])}")
        lines.append("")

    if reserve:
        lines.append("<b>Резерв:</b>")
        for index, p in enumerate(reserve, 1):
            mark = "👥" if p.get("type") in ("friend", "guest") else "•"
            lines.append(f"{index}. {mark} {escape(p['display_name'])}")
        lines.append("")

    if declined:
        lines.append(f"❌ Отказались: {len(declined)}")
        lines.append("")

    if status == "game_started":
        lines.append("⚽ Матч начался! Запись и отмены заблокированы.")
    elif status == "payment_collection":
        lines.append("Сбор оплат начат. Нажмите кнопку ниже: оплатил или не играл.")
    elif status == "cancelled":
        lines.append("Игра отменена. Кнопки записи отключены.")
    elif status == "registration_closed":
        lines.append("Запись закрыта админом.")

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
