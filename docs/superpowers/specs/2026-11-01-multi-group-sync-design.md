# Спецификация: Рассылка приглашений по группам и синхронизация в реальном времени

- **Дата:** 2026-11-01
- **Статус:** Согласовано (Ready for Implementation Planning)
- **Проект:** Football Telegram Bot

---

## 1. Контекст и цели

### 1.1 Проблема
В текущей реализации карточка игры жестко привязана к одному групповому чату (`chat_id` и `message_id`). Создать игру можно только в группе. Если аудитория разбита на несколько чатов (например, «Основной состав», «Резерв», «Пятничный футбол»), админу приходится вручную пересылать сообщения или создавать несколько игр, что приводит к рассинхронизации состава, очередей и оплат.

### 1.2 Цель
1. Предоставить администраторам возможность создавать игру прямо в личных сообщениях с ботом (`/new_game`).
2. Предоставить удобный интерактивный интерфейс выбора групп для публикации карточки матча.
3. Обеспечить полную мгновенную двустороннюю синхронизацию карточек во всех группах: любое действие участника или администратора (запись, отказ, добавление друга, изменение времени/формата, отмена игры, сбор оплат) мгновенно обновляет сообщения во всех связанных чатах.

---

## 2. Модель данных (MongoDB)

### 2.1 Новая коллекция `chats` (Реестр групп)
Хранит группы и супергруппы, в которых состоит бот.

```json
{
  "_id": ObjectId("..."),
  "chat_id": -100123456789,
  "title": "Футбольный клуб (Основа)",
  "type": "supergroup",
  "is_active": true,
  "created_at": ISODate("2026-11-01T12:00:00Z"),
  "updated_at": ISODate("2026-11-01T12:00:00Z")
}
```

* **Индексы**: `chat_id` (`unique=True`).
* **Пополнение**:
  - Хэндлер `ChatMemberUpdated` (`my_chat_member`): фиксирует добавление бота в группу, выдачу прав или удаление (`is_active = False`).
  - Fallback-мидлварь или хэндлер: при любом сообщении/команде в групповом чате профиль группы автоматически обновляется в коллекции `chats`.

### 2.2 Обновление коллекции `games`
Удаляются устаревшие одиночные поля `chat_id` и `message_id`. Единственным источником связей становится массив `messages`:

```json
{
  "_id": ObjectId("..."),
  "title": "Футбол",
  "start_at": ISODate("2026-11-05T18:00:00Z"),
  "status": "registration_open",
  "teams_count": 3,
  "players_per_team": 6,
  "max_players": 18,
  "price": 200,
  "duration_minutes": 90,
  "friends_open_after_hours": 6,
  "friends_allowed": false,
  "friends_allowed_after": ISODate("2026-11-01T18:00:00Z"),
  "created_by": 123456789,
  "messages": [
    {
      "chat_id": -100123456789,
      "message_id": 450,
      "chat_title": "Футбольный клуб (Основа)",
      "added_at": ISODate("2026-11-01T12:05:00Z")
    },
    {
      "chat_id": -100987654321,
      "message_id": 780,
      "chat_title": "Футбольный клуб (Резерв)",
      "added_at": ISODate("2026-11-01T12:06:00Z")
    }
  ],
  "created_at": ISODate("..."),
  "updated_at": ISODate("...")
}
```

* **Индексы**: `messages.chat_id` для быстрого поиска активных игр по чату.

---

## 3. Пользовательский интерфейс и сценарии (UX)

### 3.1 Создание игры в ЛС (`/new_game`)
1. Админ отправляет в личные сообщения боту:
   `/new_game YYYY-MM-DD HH:MM teams_count players_per_team price duration_minutes friends_open_after_hours`
2. Бот валидирует аргументы и сохраняет игру в БД с `messages: []`.
3. Бот отправляет админу в ЛС предпросмотр карточки игры с клавиатурой публикации:
   ```text
   ⚽ Игра создана! Выберите группы для публикации:
   [ 📢 Опубликовать во всех ]
   [ ➕ Футбольный клуб (Основа) ]
   [ ➕ Футбольный клуб (Резерв) ]
   [ ⚙️ Управление игрой ]
   ```
4. При клике на `➕ [Название группы]`:
   - Бот отправляет интерактивное сообщение карточки игры в целевой чат.
   - Записывает объект `{chat_id, message_id, chat_title, added_at}` в массив `messages` игры.
   - Кнопка группы меняется на `[ ✅ Название группы ]`.
5. При клике на `📢 Опубликовать во всех`:
   - Бот отправляет карточку во все активные группы из коллекции `chats`.
   - Все кнопки групп переходят в состояние `✅`.

### 3.2 Управление публикацией из админ-меню игры
- В существующую клавиатуру `admin_game_keyboard` добавляется кнопка: `📢 Публикация в группах`.
- Нажатие открывает меню со списком групп:
  - Группы с `✅` (уже опубликовано): при нажатии бот удаляет карточку из этой группы и исключает её из `messages` игры.
  - Группы с `➕`: при нажатии карточка публикуется в группу и добавляется в `messages`.

### 3.3 Взаимодействие игроков
- Игроки в любой группе видят абсолютно идентичный список основного состава и резерва.
- Нажатие `✅ Буду`, `❌ Не буду`, `➕ Добавить друга`, `➖ Отменить друга` в любой группе инициирует синхронное обновление карточки во всех группах из массива `messages`.
- Нажатие `⚙️ Управление` админом в любой группе по-прежнему тихо открывает меню в ЛС админу.

---

## 4. Архитектура синхронизации и обработка ошибок

### 4.1 Параллельный движок обновления (`update_game_message`)
Функция обновления сообщений полностью изолирована и выполняется асинхронно:

```python
async def update_game_message(bot: Bot, game: dict) -> None:
    db = get_db()
    game_id = str(game["_id"])
    participants = await ParticipantRepository(db).list_by_game(game_id)
    payments = []
    if game.get("status") == "payment_collection":
        payments = await PaymentRepository(db).list_by_game(game_id)

    text = format_game_message(game, participants, payments)
    reply_markup = game_keyboard(game_id, game.get("friends_allowed", False), game.get("status"))

    messages = game.get("messages", [])
    if not messages:
        return

    tasks = [
        _update_single_message(bot, game_id, msg["chat_id"], msg["message_id"], text, reply_markup)
        for msg in messages
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
```

### 4.2 Обработка исключений каждого чата (`_update_single_message`)
- `TelegramBadRequest`:
  - `message is not modified`: игнорируется (штатная ситуация).
  - `message to edit not found` / `message can't be edited`: карточка в группе была удалена вручную -> бот вызывает `game_repo.remove_linked_message(game_id, chat_id, message_id)`.
- `TelegramForbiddenError`:
  - Бота выгнали из группы или заблокировали -> бот вызывает `game_repo.remove_linked_message(...)` и `chat_repo.set_active_status(chat_id, False)`.
- Ошибки в одном чате не прерывают обновление в остальных чатах (`return_exceptions=True`).

### 4.3 Планировщик (`scheduler.py`)
Функция `open_friends_job` обновляет статус в БД и вызывает `await update_game_message(bot, game)`. Все связанные чаты одновременно получают обновленную карточку с открытыми кнопками добавления друзей.

---

## 5. Затрагиваемые компоненты и файлы

1. **`app/db/mongo.py`**:
   - Добавление индексов для `chats.chat_id` и `games.messages.chat_id`.
2. **`app/repositories/chats.py`** *(новый файл)*:
   - `ChatRepository`: методы `upsert_chat`, `list_active_chats`, `set_active_status`.
3. **`app/repositories/games.py`**:
   - Обновление `create_game`: инициализация `messages: []`.
   - Новые методы: `add_linked_message()`, `remove_linked_message()`.
   - Обновление `get_active_for_chat(chat_id)`: фильтрация по `{"messages.chat_id": chat_id}`.
4. **`app/bot/keyboards.py`**:
   - Новая функция `broadcast_groups_keyboard(game_id, chats, linked_chat_ids)`.
   - Добавление кнопки `📢 Публикация в группах` в `admin_game_keyboard`.
5. **`app/bot/handlers.py`**:
   - Разрешение создания `/new_game` в личных сообщениях с ботом для админов.
   - Хэндлер события `my_chat_member` для отслеживания групп.
   - Обработчики callback-запросов публикации: `admin:<game_id>:broadcast_menu`, `admin:<game_id>:publish:<chat_id>`, `admin:<game_id>:unpublish:<chat_id>`, `admin:<game_id>:publish_all`.
   - Обновление функции `update_game_message()`.
6. **`app/services/scheduler.py`**:
   - Переход на вызов `update_game_message()` вместо одиночного `bot.edit_message_text`.

---

## 6. Стратегия тестирования и верификации
1. **Интеграционный тест репозиториев**:
   - Создание игры в ЛС -> добавление нескольких привязанных чатов -> проверка `get_active_for_chat` для каждого из чатов.
2. **Тест параллельной синхронизации**:
   - Симуляция вызова `update_game_message` с несколькими сообщениями -> проверка отсутствия гонок и блокировок.
3. **Тест устойчивости к сбоям**:
   - Проверка сценария, когда одно из сообщений возвращает `TelegramBadRequest` (удалено), а второе успешно обновляется.
