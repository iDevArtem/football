---
name: roster-management
description: Manage, simulate, and verify game lifecycles, roster normalizations, reserve promotions, friends limit rules, and payment collection in Football Telegram Bot.
---

# Управление составом и жизненным циклом игр (Roster Management)

Скилл описывает бизнес-логику управления матчем, алгоритм пересчета состава (`normalize_roster`), правила резерва и добавления друзей, а также способы проверки сценариев.

---

## 1. Концепция жизненного цикла игры

1. **Создание матча**:
   - Админ вводит `/new_game YYYY-MM-DD HH:MM teams_count players_per_team price duration_minutes friends_open_after_hours`.
   - Вместимость: `max_players = teams_count * players_per_team`.
   - Статус: `registration_open`.
   - `friends_allowed: False`, время открытия: `friends_allowed_after = now + hours`.

2. **Запись игроков («Буду» / «Не буду»)**:
   - Пока число подтвержденных `< max_players`, статус игрока — `confirmed`.
   - Когда состав набран, новые игроки получают статус `reserve` и встают в очередь по возрастанию `position`.
   - При отказе игрока из основы (`decline_player`) первый игрок из `reserve` автоматически становится `confirmed`.

3. **Открытие друзей**:
   - Автоматически по таймеру через планировщик `open_friends_job` (если состав не полон).
   - Либо вручную админом через команду `/open_friends` или админ-меню.
   - Правило лимита: один участник может добавить не более 3 друзей.
   - Друзья участвуют в общей очереди `position` наравне с обычными игроками.

4. **Изменение формата (`update_format`)**:
   - Админ может изменить `teams_count` или `players_per_team`.
   - Новый `max_players` автоматически пересчитывает границу:
     - При уменьшении лимита последние из основы перемещаются в резерв.
     - При увеличении лимита первые из резерва переводятся в основной состав.

5. **Сбор оплат (`payment_collection`)**:
   - Запускается командой `/payments` или кнопкой в меню.
   - Фиксирует участников основы в коллекции `payments`.
   - Игроки и админы отмечают `paid` или `not_played`.

---

## 2. Сценарий тестирования логики состава (Python-скрипт)

Для проверки корректности пересчета очереди без отправки реальных сообщений в Telegram можно выполнить скрипт:

```python
import asyncio
from datetime import datetime, timezone
from app.db.mongo import init_mongo, close_mongo
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository

class MockUser:
    def __init__(self, uid, name):
        self.id = uid
        self.full_name = name
        self.username = f"user_{uid}"

async def test_roster_flow():
    db = await init_mongo()
    game_repo = GameRepository(db)
    part_repo = ParticipantRepository(db)

    # 1. Создаем игру на 4 игрока (2 команды x 2 игрока)
    game = await game_repo.create_game(
        chat_id=-100123456789,
        title="Тестовая игра",
        start_at=datetime.now(timezone.utc),
        teams_count=2,
        players_per_team=2,
        price=100,
        duration_minutes=90,
        friends_open_after_hours=6,
        created_by=999,
    )
    game_id = str(game["_id"])
    print(f"Игра создана: {game_id}, макс игроков: {game['max_players']}")

    # 2. Записываем 5 игроков (4 в основу, 1 в резерв)
    users = [MockUser(i, f"Игрок {i}") for i in range(1, 6)]
    for u in users:
        await part_repo.join_player(game, u)

    participants = await part_repo.list_by_game(game_id)
    confirmed = [p for p in participants if p["status"] == "confirmed"]
    reserve = [p for p in participants if p["status"] == "reserve"]
    print(f"Основа ({len(confirmed)}): {[p['display_name'] for p in confirmed]}")
    print(f"Резерв ({len(reserve)}): {[p['display_name'] for p in reserve]}")
    assert len(confirmed) == 4
    assert len(reserve) == 1

    # 3. Игрок 1 отказывается -> резерв должен автоматически продвинуться в основу
    await part_repo.decline_player(game_id, users[0])
    participants = await part_repo.list_by_game(game_id)
    confirmed = [p for p in participants if p["status"] == "confirmed"]
    print(f"После отказа Игрока 1 основа: {[p['display_name'] for p in confirmed]}")
    assert any(p["display_name"] == "Игрок 5" for p in confirmed)

    # Очистка тестовых данных
    await db.games.delete_one({"_id": game["_id"]})
    await db.participants.delete_many({"game_id": game["_id"]})
    await close_mongo()
    print("Тест успешно завершен!")

if __name__ == "__main__":
    asyncio.run(test_roster_flow())
```

---

## 3. Критерии верификации
- Количество `confirmed` строго не превышает `max_players`.
- Порядок в `confirmed` строго следует возрастанию `position`.
- При отказе игрока из основы первый участник из `reserve` продвигается в `confirmed`.
- При уменьшении лимита игроков лишние игроки основы с наибольшим `position` уходят в `reserve`.
