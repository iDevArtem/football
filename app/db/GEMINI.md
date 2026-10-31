# app/db — Слой подключения к MongoDB и индексы

Каталог отвечает за асинхронное подключение к MongoDB через `PyMongo 4.x` (`AsyncMongoClient`), создание индексов и управление жизненным циклом базы данных.

---

## 📁 Структура

- `mongo.py` — функции `init_mongo()`, `get_db()`, `close_mongo()` и `create_indexes()`.
- `__init__.py` — экспорт функций модуля.

---

## 🔌 Управление подключением

1. **Инициализация (`init_mongo`)**:
   - Вызывается один раз при старте приложения в `app/main.py`.
   - Создает глобальный экземпляр `AsyncMongoClient(settings.mongo_url)`.
   - Выбирает базу данных `settings.mongo_db_name`.
   - Вызывает `create_indexes(db)` для гарантии консистентности структуры.
2. **Получение экземпляра (`get_db`)**:
   - Возвращает активный объект базы данных.
   - Выбрасывает `RuntimeError("MongoDB is not initialized")`, если база еще не инициализирована.
3. **Завершение работы (`close_mongo`)**:
   - Вызывается в блоке `finally` в `main.py` для корректного закрытия пула соединений клиента.

---

## 📑 Индексы коллекций (`create_indexes`)

Для обеспечения быстродействия и гарантии целостности данных при старте создаются следующие индексы:

| Коллекция | Поля индекса | Опции | Зачем нужен |
|---|---|---|---|
| `users` | `telegram_id` | `unique=True` | Быстрый поиск и уникальность профиля игрока |
| `games` | `[("chat_id", 1), ("status", 1)]` | — | Быстрый выбор активной/управляемой игры в чате |
| `games` | `"start_at"` | — | Сортировка и фильтрация по времени матча |
| `participants` | `[("game_id", 1), ("telegram_id", 1)]` | — | Проверка записи игрока на конкретную игру |
| `participants` | `[("game_id", 1), ("added_by_telegram_id", 1), ("type", 1)]` | — | Быстрый подсчет и выборка друзей пользователя (лимит до 3) |
| `payments` | `[("game_id", 1), ("participant_id", 1)]` | `unique=True` | Гарантия одной записи об оплате на участника в матче |

---

## ⚠️ Правила работы с PyMongo AsyncMongoClient

1. **`ObjectId`**:
   - Поля `_id`, `game_id` и `participant_id` хранятся как `bson.ObjectId`.
   - При выборке и обновлении по строковому ID всегда оборачивайте его: `ObjectId(raw_id)`.
2. **Даты и таймзоны**:
   - В базу все даты должны сохраняться **только в UTC** (`datetime.now(timezone.utc)`).
   - MongoDB сохраняет datetime в UTC без явной метки tzinfo. При извлечении учитывайте необходимость приведения к tz-aware виду перед сравнением.
3. **Асинхронные курсоры**:
   - При итерации по результатам `find()` используйте синтаксис:
     ```python
     cursor = db.participants.find({"game_id": ObjectId(game_id)})
     items = [doc async for doc in cursor]
     ```
   - Для агрегации:
     ```python
     cursor = await db.payments.aggregate(pipeline)
     results = [doc async for doc in cursor]
     ```
