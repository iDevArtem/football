# app/repositories — Слой доступа к данным (DAL)

Каталог содержит классы-репозитории, инкапсулирующие все запросы к коллекциям MongoDB (`users`, `games`, `participants`, `payments`).

---

## 📁 Структура

- `chats.py` — `ChatRepository`: реестр групп бота, отслеживание активности и статусов.
- `users.py` — `UserRepository`: сохранение и обновление профилей пользователей Telegram.
- `games.py` — `GameRepository`: создание, мультигрупповые связи (`messages`), изменение формата, дат, статусов и фильтрация игр.
- `participants.py` — `ParticipantRepository`: запись игроков, добавление/отмена друзей, управление очередью и нормализация состава.
- `payments.py` — `PaymentRepository`: учет оплат, фиксация статусов (оплатил / не играл) и агрегация с данными участников.

---

## 🏛 Репозитории и их контракты

### 0. `ChatRepository`
- `upsert_chat(chat_id, title, chat_type)`: добавление или обновление группы в реестре при событиях бота или сообщениях в группе.
- `list_active_chats()`: список всех активных групп для меню рассылки.
- `set_active_status(chat_id, is_active)`: деактивация группы, если бота удалили или заблокировали.

### 1. `UserRepository`
- `upsert_from_telegram(tg_user, is_admin=False) -> dict`: сохраняет `telegram_id`, `username`, `first_name`, `last_name`, `role` (`admin` или `player`) и временные метки `created_at` / `updated_at`.

### 2. `GameRepository`
- **Жизненный цикл статусов игры**:
  - `registration_open` (запись открыта) -> `friends_allowed` (добавление друзей доступно) -> `full` (состав заполнен) -> `registration_closed` (запись закрыта админом) -> `payment_collection` (сбор оплат) -> `closed` (завершена).
  - Игра в любой момент может перейти в `cancelled` (отменена) и быть возвращена через `restore_game`.
- `ACTIVE_STATUSES`: `["registration_open", "registration_closed", "friends_allowed", "full", "payment_collection"]`.
- `get_active_for_chat(chat_id)`: последняя игра в активном статусе.
- `get_manageable_for_chat(chat_id)`: последняя игра, включая `cancelled` (для возможности восстановления).
- `update_format(game_id, teams_count, players_per_team)`: пересчитывает `max_players = teams_count * players_per_team`. После вызова этого метода обязательно должен вызываться `normalize_roster()`!
- `games_to_open_friends()`: поиск игр с `friends_allowed: False`, статусом `registration_open` и наступившим `friends_allowed_after <= now`.

### 3. `ParticipantRepository`
Ключевой репозиторий бизнес-логики записи и очередей:
- **Поле `position`**: строго возрастающий порядковый номер (`next_position()`), определяющий очередь записи.
- **Алгоритм нормализации состава (`normalize_roster`)**:
  ```python
  cursor = self.db.participants.find({
      "game_id": ObjectId(game_id),
      "status": {"$in": ["confirmed", "reserve"]}
  }).sort("position", 1)
  ```
  - Первые `max_players` записей по возрастанию `position` получают статус `confirmed`.
  - Все последующие получают статус `reserve`.
  - Вызывается при каждом добавлении, отказе, отмене друга и смене формата матча.
- **Повторная запись после отказа**:
  - Если игрок имел статус `declined` или `removed` и снова нажал «Буду», ему присваивается новый `next_position()`, чтобы он встал в конец очереди и не вытеснял тех, кто записался раньше.
- **Лимит друзей**:
  - `count_friends_by_user(game_id, telegram_id)` проверяет, чтобы один участник имел не более 3 активных друзей (`status: confirmed | reserve`).

### 4. `PaymentRepository`
- `ensure_for_game(game_id, amount)`: создает заготовки в коллекции `payments` с начальным статусом `pending` для всех участников со статусом `confirmed`.
- `mark_paid_by_user(game_id, telegram_id) -> bool` / `mark_not_played_by_user()`:
  - Игрок подтверждает статус своей оплаты.
  - Проверка результата выполняется по `result.matched_count > 0` (а не `modified_count`), так как повторный клик на уже выбранный статус является валидным подтверждением.
- `mark_by_participant_id(game_id, participant_id, status, actor_id, is_admin)`:
  - Позволяет игроку менять статус оплаты **своих друзей** (`added_by_telegram_id == actor_id`).
  - Администратор может менять статус оплаты любого участника.
- `list_by_game(game_id)`: агрегация через `$lookup` к коллекции `participants` для получения полного списка с именами участников, отсортированного по `position`.

---

## ⚠️ Правила модификации репозиториев

1. Никаких прямых вызовов `aiogram` внутри репозиториев.
2. Не смешивайте `$set` и `$setOnInsert` для одного и того же поля в одном документе update — MongoDB выбросит исключение.
3. Всегда следите за консистентностью статусов `confirmed` / `reserve` через вызов `normalize_roster()`.
