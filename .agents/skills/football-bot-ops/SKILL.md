---
name: football-bot-ops
description: Run, test, monitor, and troubleshoot the Football Telegram Bot and its MongoDB container in development and production environments.
---

# Football Bot — Операционные процедуры и запуск

Скилл содержит пошаговые инструкции по запуску, проверке конфигурации, просмотру логов и диагностике неполадок бота и базы данных MongoDB.

---

## 1. Подготовка окружения

1. Убедитесь, что файл конфигурации `.env` существует:
   ```bash
   cp .env.example .env
   ```
2. Проверьте обязательные параметры:
   - `BOT_TOKEN`: действительный токен от `@BotFather`.
   - `ADMIN_TELEGRAM_IDS`: ваш числовой Telegram ID (можно узнать через `@userinfobot`).
   - `MONGO_URL`: `mongodb://mongodb:27017` (для Docker) или `mongodb://localhost:27017` (для локального запуска).

---

## 2. Запуск через Docker Compose (Рекомендуемый способ)

1. **Сборка и запуск в фоновом режиме**:
   ```bash
   docker compose up --build -d
   ```
2. **Просмотр статуса контейнеров**:
   ```bash
   docker compose ps
   ```
3. **Чтение логов в реальном времени**:
   ```bash
   docker compose logs -f bot
   ```
4. **Остановка сервисов**:
   ```bash
   docker compose down
   ```

---

## 3. Локальный запуск для разработки

1. **Запустите только MongoDB в контейнере**:
   ```bash
   docker compose up -d mongodb
   ```
2. **Активируйте виртуальное окружение и установите зависимости**:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Запустите бота**:
   ```bash
   python -m app.main
   ```

---

## 4. Проверка работоспособности и синтаксиса (Smoke Test)

Для быстрой проверки корректности кода без запуска Telegram polling:
```bash
./.venv/bin/python -c "
import app.main
from app.config.settings import get_settings
settings = get_settings()
print(f'Config OK! Timezone: {settings.default_timezone}, Admin IDs count: {len(settings.admin_ids)}')
"
```

---

## 5. Типичные проблемы и их устранение

### 1. `pymongo.errors.ServerSelectionTimeoutError`
- **Причина**: бот не может подключиться к MongoDB.
- **Решение**:
  - При запуске в Docker проверьте, что `MONGO_URL=mongodb://mongodb:27017`.
  - При локальном запуске проверьте, что `MONGO_URL=mongodb://localhost:27017` и контейнер с MongoDB запущен (`docker ps`).

### 2. `aiogram.exceptions.TelegramUnauthorizedError`
- **Причина**: неверный или отозванный `BOT_TOKEN`.
- **Решение**: проверьте токен в `.env`, при необходимости перевыпустите через `@BotFather`.

### 3. Бот не реагирует на команду `/new_game` в личке
- **Причина**: игра должна создаваться исключительно в группе/супергруппе. В личке бот выводит сообщение об ошибке.
