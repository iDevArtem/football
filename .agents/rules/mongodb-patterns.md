# Правила работы с MongoDB и PyMongo AsyncMongoClient

Этот набор правил регламентирует работу с базой данных, коллекциями, запросами и моделями данных в проекте.

---

## 1. Типизация идентификаторов (`ObjectId`)

- В коллекциях MongoDB поля идентификаторов (`_id`, `game_id`, `participant_id`) имеют тип `bson.ObjectId`.
- Любой строковый ID из callback-запроса или аргументов функции перед подстановкой в фильтр запроса обязан быть преобразован:
  ```python
  from bson import ObjectId
  query = {"_id": ObjectId(game_id)}
  ```
- Никогда не передавайте сырую строку в фильтр по `_id` — запрос вернет `None`.

---

## 2. Разделение `$set` и `$setOnInsert`

- MongoDB строго запрещает указывать одно и то же поле одновременно в секциях `$set` и `$setOnInsert` в рамках одной операции `update_one(..., upsert=True)`. Это приведет к исключению `WriteError: Conflict between $set and $setOnInsert`.
- При создании или обновлении участников (`participants`):
  - Сначала проверьте наличие документа через `find_one()`.
  - При наличии — выполняйте `update_one({"$set": ...})`.
  - При отсутствии — создавайте документ через `insert_one()`.

---

## 3. Инвариант нормализации состава (`normalize_roster`)

- Очередность участников определяется полем `position` (автоинкремент).
- Любое действие, изменяющее состав участников или формат матча:
  - Запись игрока (`join_player`)
  - Отказ игрока (`decline_player`)
  - Добавление друга (`add_friend`)
  - Отмена друга (`cancel_friend`)
  - Изменение формата (`update_format`)
  **ОБЯЗАНО** завершаться вызовом:
  ```python
  await self.normalize_roster(game_id, max_players)
  ```
- Алгоритм гарантирует, что первые `max_players` участников по возрастанию `position` имеют статус `confirmed`, а остальные — `reserve`.

---

## 4. Смещение в конец очереди при повторной записи

- Если участник ранее имел статус `declined` или `removed` и снова нажимает «Буду», ему **обязательно** присваивается новая позиция в очереди:
  ```python
  update_doc["position"] = await self.next_position(game_id)
  ```
- Это предотвращает ситуацию, когда отказавшийся игрок восстанавливает старое место и вытесняет тех, кто записался после него.

---

## 5. Временные метки и часовые пояса

- Все системные поля времени (`created_at`, `updated_at`, `closed_at`, `friends_allowed_after`) сохраняются в базе данных строго в UTC:
  ```python
  from datetime import datetime, timezone
  now = datetime.now(timezone.utc)
  ```
- При извлечении даты из MongoDB убедитесь, что объект имеет tzinfo (`dt.replace(tzinfo=timezone.utc)`), перед сравнением с `datetime.now(timezone.utc)`.

---

## 6. Проверка результата обновления оплат

- При фиксации статуса оплаты (`mark_paid_by_user`, `mark_not_played_by_user`) проверяйте `result.matched_count > 0`, а не `result.modified_count`.
- Если игрок повторно нажимает кнопку «Оплатил», документ в БД не модифицируется (`modified_count == 0`), но `matched_count == 1`, что подтверждает корректность действия пользователя.
