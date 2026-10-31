# app/config — Конфигурация и переменные окружения

Каталог содержит логику загрузки, валидации и предоставления настроек приложения с использованием `pydantic-settings`.

---

## 📁 Структура

- `settings.py` — класс настроек `Settings`, парсинг `.env` и фабрика `get_settings()`.
- `__init__.py` — экспорт функций модуля.

---

## ⚙️ Переменные окружения (`Settings`)

| Переменная | Тип | По умолчанию | Описание |
|---|---|---|---|
| `BOT_TOKEN` | `str` | *обязательно* | Токен бота от `@BotFather`. |
| `MONGO_URL` | `str` | `mongodb://localhost:27017` | Строка подключения к MongoDB. В docker-compose: `mongodb://mongodb:27017`. |
| `MONGO_DB_NAME` | `str` | `football_bot` | Имя базы данных в MongoDB. |
| `DEFAULT_TIMEZONE` | `str` | `Europe/Kyiv` | Временная зона по умолчанию для парсинга и отображения дат игр. |
| `ADMIN_TELEGRAM_IDS`| `str` | `""` | Список Telegram ID администраторов через запятую (например: `"123456789,987654321"`). |

---

## 🔑 Особенности реализации

1. **Кэширование настроек (`@lru_cache`)**:
   - Функция `get_settings()` обернута в `@lru_cache`, благодаря чему файл `.env` читается ровно один раз при старте.
   - Во всех модулях настройки импортируются единообразно:
     ```python
     from app.config.settings import get_settings
     settings = get_settings()
     ```

2. **Парсинг ID администраторов**:
   - Свойство `admin_ids` преобразует строку `ADMIN_TELEGRAM_IDS` в множество чисел `set[int]`, игнорируя пробелы и нечисловые значения:
     ```python
     @property
     def admin_ids(self) -> set[int]:
         result: set[int] = set()
         for raw in self.admin_telegram_ids.split(","):
             raw = raw.strip()
             if raw.isdigit():
                 result.add(int(raw))
         return result
     ```

---

## 💡 Рекомендации при добавлении новых настроек

- Все новые конфигурационные параметры следует объявлять как поля класса `Settings` с аннотацией типов.
- Если параметр не является обязательным, всегда задавайте дефолтное значение.
- Не храните секреты в коде — обновляйте `.env.example` при добавлении новых переменных.
