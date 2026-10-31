# app — Ядро приложения Football Bot

Каталог `app/` содержит исходный код бота, разделенный на слои по принципам чистой архитектуры: конфигурация, база данных, репозитории (доступ к данным), сервисы (бизнес-логика и рендеринг), бот (интерфейс Telegram) и утилиты.

---

## 📌 Структура модуля

```text
app/
├── main.py            # Точка входа в приложение и управление жизненным циклом
├── config/            # Настройки и переменные окружения (Pydantic Settings)
├── db/                # Подключение к MongoDB, пул соединений, индексы
├── repositories/      # Слой DAL (Data Access Layer) с Mongo-запросами
├── services/          # Рендеринг текста карточки и фоновый планировщик
├── bot/               # Хэндлеры команд, inline-кнопок, FSM и клавиатуры
└── utils/             # Функции для парсинга дат и работы с часовыми поясами
```

---

## 🔄 Жизненный цикл (`app/main.py`)

Запуск приложения выполняется функцией `main()`:
1. **Инициализация логгирования**: `logging.basicConfig(level=logging.INFO)`.
2. **Загрузка конфигурации**: `get_settings()` (кэшируется через `@lru_cache`).
3. **Подключение к БД**: `await init_mongo()` создает синглтон клиента и накладывает индексы.
4. **Создание экземпляров aiogram**: `Bot(token=...)` и `Dispatcher(storage=MemoryStorage())`.
5. **Подключение роутеров**: `dp.include_router(router)` из `app.bot.handlers`.
6. **Запуск планировщика**: `scheduler = setup_scheduler(bot)` (APScheduler).
7. **Polling**: `await dp.start_polling(bot)`.
8. **Graceful Shutdown**:
   - `scheduler.shutdown(wait=False)`
   - `await close_mongo()`
   - `await bot.session.close()`

---

## 📐 Правила проектирования и зависимости слоев

1. **Однонаправленный поток зависимостей**:
   - `bot` -> зависит от `services`, `repositories`, `config`, `db`, `utils`.
   - `services` -> зависят от `repositories`, `db`, `bot.keyboards` (для обновления сообщения из scheduler).
   - `repositories` -> зависят только от `db` (и bson/ObjectId). Не должны зависеть от aiogram или bot!
   - `db` -> зависит только от `config`.
   - `config` и `utils` -> не зависят от других модулей проекта.

2. **Работа с базой данных**:
   - Всегда использовать `get_db()` для получения экземпляра базы данных.
   - Операции с БД выполняются только через классы репозиториев (`UserRepository`, `GameRepository`, `ParticipantRepository`, `PaymentRepository`).
   - Все методы репозиториев — асинхронные (`async def`).

3. **Логирование и обработка ошибок**:
   - Использовать `logging.getLogger(__name__)`.
   - Ошибки Telegram API (удаление уже удаленного сообщения, редактирование неизмененного текста) перехватывать точечно: `TelegramBadRequest`, `TelegramForbiddenError`.

---

## 🧪 Проверка работоспособности

Быстрая проверка корректности всех модулей и импортов:
```bash
./.venv/bin/python -c "import app.main; print('app modules loaded successfully')"
```
