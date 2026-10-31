# Спецификация: Telegram Mini App & Веб-панель управления (football.idev.wtf)

## 1. Введение и цели

Проект расширяет существующий асинхронный Telegram-бот на Python (aiogram 3 + MongoDB) до полноценного веб-сервиса с Telegram Mini App и публичной веб-афишей на домене `football.idev.wtf`.

### Основные цели
1. **Публичная афиша (`https://football.idev.wtf/`)**: открытая веб-страница со списком актуальных и архивных матчей, статусом набора (основа / резерв), форматом игры и ссылками на Telegram-чаты и бота.
2. **Личный кабинет и админка (`https://football.idev.wtf/app`)**:
   - Единое веб-приложение (SPA на React + Vite + Tailwind CSS).
   - В Telegram Mini App: открывается прямо из бота по ссылке `https://football.idev.wtf/app`, выполняет бесшовную автоматическую авторизацию через `Telegram.WebApp.initData`.
   - В обычном браузере: авторизация через официальный Telegram Login Widget.
3. **Разграничение прав (RBAC)**:
   - **Игроки (`player`)**: запись/отмена записи на открытые игры, добавление/удаление друзей (до 3), отметка статуса оплаты («Оплатил» / «Не играл»).
   - **Организаторы (`admin`, список из `ADMIN_TELEGRAM_IDS`)**: создание и редактирование игр, ручная смена состава (основа ↔ резерв ↔ удаление), принудительное открытие/закрытие набора друзей, запуск сбора оплат с расчетом стоимости (1.5ч / 2.0ч), подтверждение оплат и рассылка карточек по привязанным Telegram-группам.
4. **Мгновенная синхронизация (Web ↔ Telegram чаты)**:
   - Любое действие в вебе мгновенно и параллельно обновляет карточки сообщений во всех группах игры через существующий механизм бота `update_game_message`.
5. **Инфраструктура**:
   - Развертывание в Docker Swarm за существующим Traefik v3 с TLS через Let's Encrypt, Cloudflare IP Whitelist и сетью `traefik-public`.

---

## 2. Архитектура и маршрутизация

### 2.1 Единый асинхронный процесс (FastAPI + aiogram)

Приложение работает как единый Python-сервис под управлением `uvicorn`:
- **FastAPI**: обслуживает REST API (`/api/*`) и раздает статические файлы скомпилированного React-приложения.
- **aiogram `Dispatcher` & `Bot`**: запускаются в `lifespan` контексте FastAPI в фоновом таске (polling).
- **APScheduler**: запускается в `lifespan` для периодической проверки открытия набора друзей.
- **MongoDB**: единое асинхронное подключение `AsyncIOMotorClient`, используемое существующими репозиториями (`GameRepository`, `ParticipantRepository`, `ChatRepository`, `PaymentRepository`, `UserRepository`).

### 2.2 Маршруты URL

| Путь | Назначение | Доступ |
|------|------------|--------|
| `GET /` | Публичная страница (афиша матчей, правила, ссылки) | Доступно всем без авторизации |
| `GET /app` | Кабинет игрока / Панель админа (SPA) | Авторизованные пользователи (редирект на вход, если гость) |
| `GET /app/*` | Внутренние маршруты SPA (например, `/app/game/:id`) | SPA HTML fallback |
| `POST /api/auth/tma` | Обмен `initData` Mini App на JWT сессию | Публичный эндпоинт Telegram |
| `POST /api/auth/widget` | Обмен данных Telegram Login Widget на JWT | Публичный эндпоинт |
| `GET /api/me` | Данные текущего пользователя и его роль | Авторизованный |
| `GET /api/games` | Список игр | Публичный |
| `GET /api/games/{id}` | Детали игры и состав | Публичный (приватные поля скрыты) |
| `POST /api/games/{id}/join` | Записаться на игру | Игрок / Админ |
| `POST /api/games/{id}/leave` | Отменить запись | Игрок / Админ |
| `POST /api/games/{id}/friends` | Добавить друга | Игрок / Админ |
| `DELETE /api/games/{id}/friends/{participant_id}` | Удалить своего друга | Игрок / Админ |
| `POST /api/games/{id}/payment/status` | Отметить оплату / не играл | Игрок / Админ |
| `POST /api/admin/games` | Создать новый матч | Только админ |
| `PATCH /api/admin/games/{id}` | Редактировать матч | Только админ |
| `POST /api/admin/games/{id}/cancel` | Отменить матч | Только админ |
| `POST /api/admin/games/{id}/friends/toggle` | Открыть/закрыть набор друзей | Только админ |
| `POST /api/admin/games/{id}/payment/start` | Начать сбор оплат (1.5ч / 2ч) | Только админ |
| `PATCH /api/admin/games/{id}/participants/{participant_id}` | Изменить статус участника (основа/резерв/оплата) | Только админ |
| `GET /api/admin/chats` | Список Telegram-чатов | Только админ |
| `POST /api/admin/games/{id}/publish` | Опубликовать/обновить игру в чатах | Только админ |

---

## 3. Авторизация и безопасность (Dual Telegram Auth)

### 3.1 Telegram Mini App (`/api/auth/tma`)
1. Клиент в Mini App извлекает `window.Telegram.WebApp.initData`.
2. Бэкенд парсит query string и извлекает поле `hash`.
3. Оставшиеся поля сортируются по алфавиту в строку вида `k1=v1\nk2=v2`.
4. Вычисляется `secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)`.
5. Вычисляется `signature = HMAC_SHA256(key=secret_key, msg=data_check_string)`.
6. Если `signature.hex() == hash` и `auth_date` не старше 24 часов:
   - Данные пользователя валидны.
   - Пользователь сохраняется/обновляется в `UserRepository`.
   - Проверяется принадлежность `user.id` к `ADMIN_TELEGRAM_IDS` для установки роли (`admin` или `player`).
   - Генерируется JWT токен со сроком действия 30 дней.

### 3.2 Telegram Login Widget (`/api/auth/widget`)
1. Виджет на сайте возвращает параметры: `id`, `first_name`, `last_name`, `username`, `photo_url`, `auth_date`, `hash`.
2. Бэкенд формирует строку проверки из всех полей кроме `hash` в алфавитном порядке.
3. Вычисляется `secret_key = SHA256(BOT_TOKEN)`.
4. Вычисляется `signature = HMAC_SHA256(key=secret_key, msg=data_check_string)`.
5. Если `signature.hex() == hash`, генерируется JWT аналогично п. 3.1.

---

## 4. Спецификация API и Модели данных

### 4.1 JWT Payload
```json
{
  "sub": "12345678",
  "telegram_id": 12345678,
  "first_name": "Иван",
  "username": "ivan_player",
  "role": "player",
  "exp": 1793500000
}
```

### 4.2 Модели запросов и ответов

#### Схема игры (`GameResponse`)
```json
{
  "id": "6724123456789abcdef01234",
  "title": "⚽ Футбол 5х5",
  "start_at": "2026-11-06T19:00:00Z",
  "status": "registration_open",
  "max_players": 15,
  "confirmed_count": 12,
  "reserve_count": 0,
  "format_description": "5х5 с заменами",
  "friends_allowed": false,
  "friends_allowed_after": "2026-11-06T15:00:00Z",
  "duration_minutes": 90,
  "hourly_rate": 600,
  "price_per_player": 60,
  "payment_details": {
    "card_number": "4149 **** **** 1234",
    "recipient": "Организатор"
  },
  "participants": [
    {
      "id": "6724123456789abcdef01235",
      "user_id": 12345678,
      "name": "Иван",
      "username": "ivan_player",
      "status": "confirmed",
      "position": 1,
      "is_friend": false,
      "parent_user_id": null,
      "payment_status": "unpaid"
    }
  ],
  "linked_chats": [
    {
      "chat_id": -100123456789,
      "title": "Футбольный чат Вторник"
    }
  ]
}
```

---

## 5. Фронтенд Архитектура (React + Vite + Tailwind)

### 5.1 Структура проекта фронтенда
```text
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api/
    │   └── client.ts             # Axios/fetch с Bearer JWT
    ├── hooks/
    │   ├── useTelegram.ts        # Обертка над window.Telegram.WebApp (expand, haptic, theme)
    │   └── useAuth.ts            # Контекст сессии пользователя
    ├── components/
    │   ├── Navbar.tsx            # Навигация, статус авторизации, кнопка Telegram Login
    │   ├── GameCard.tsx          # Карточка матча на афише
    │   ├── RosterList.tsx        # Списки основы и резерва
    │   ├── FriendsModal.tsx      # Модальное окно добавления/удаления друга
    │   ├── PaymentBox.tsx        # Реквизиты, кнопка копирования карты и отметка оплаты
    │   └── AdminControls.tsx     # Панель управления организатора
    └── pages/
        ├── PublicSchedule.tsx    # Главная страница (/)
        └── CabinetPage.tsx       # Личный кабинет игрока и админа (/app)
```

### 5.2 Интеграция с Telegram WebApp SDK
- Скрипт `https://telegram.org/js/telegram-web-app.js` подключается в `index.html`.
- `useTelegram` инициализирует `WebApp`:
  - Вызывает `WebApp.ready()` и `WebApp.expand()`.
  - Применяет цвета темы Telegram (`themeParams.bg_color`, `themeParams.text_color`).
  - Предоставляет хелперы для `HapticFeedback.notificationOccurred()` и `impactOccurred()`.
  - Автоматически проверяет наличие `initData`: если не пустая, автоматически отправляет на `/api/auth/tma` и переходит в `/app`.

---

## 6. Деплой и Инфраструктура (Docker Swarm & Traefik)

### 6.1 Multi-Stage Dockerfile
```dockerfile
# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend Runtime
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app
COPY --from=frontend-builder /build/dist ./app/static
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.2 Docker Swarm Stack (`docker-compose.swarm.yml`)

Стек адаптирован под существующую конфигурацию сервера (Traefik v3.6, сеть `traefik-public`, Cloudflare IP Whitelist, Let's Encrypt resolver):

```yaml
services:
  app:
    image: football-bot:local
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - MONGO_URL=mongodb://mongo:27017/football_bot
      - ADMIN_TELEGRAM_IDS=${ADMIN_TELEGRAM_IDS}
      - WEBAPP_URL=https://football.idev.wtf
      - JWT_SECRET=${JWT_SECRET}
      - CARD_NUMBER=${CARD_NUMBER}
      - CARD_RECIPIENT=${CARD_RECIPIENT}
    networks:
      - traefik-public
      - football-internal
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
      labels:
        - "traefik.enable=true"
        - "traefik.swarm.network=traefik-public"
        - "traefik.http.routers.football.rule=Host(`football.idev.wtf`)"
        - "traefik.http.routers.football.entrypoints=websecure"
        - "traefik.http.routers.football.tls=true"
        - "traefik.http.routers.football.tls.certresolver=letsencrypt"

        # Cloudflare IP Whitelist Middleware
        - "traefik.http.middlewares.football-cloudflare-only.ipwhitelist.sourcerange=173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,2400:cb00::/32,2606:4700::/32,2803:f800::/32,2405:b500::/32,2405:8100::/32,2a06:98c0::/29,2c0f:f248::/32"
        - "traefik.http.routers.football.middlewares=football-cloudflare-only"

        - "traefik.http.services.football.loadbalancer.server.port=8000"

  mongo:
    image: mongo:8.0
    networks:
      - football-internal
    volumes:
      - football-mongo-data:/data/db
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      restart_policy:
        condition: on-failure

networks:
  traefik-public:
    external: true
  football-internal:
    driver: overlay
    attachable: true

volumes:
  football-mongo-data:
```

> **Примечание по репликам**: `replicas: 1` для сервиса `app` является обязательным, так как бот работает в режиме polling с очередью задач и планировщиком. При наличии двух реплик Telegram Bot API возвращал бы ошибку конфликта `getUpdates`.

---

## 7. План тестирования и верификации

1. **Тестирование авторизации**:
   - Unit-тесты для функции валидации `Telegram.WebApp.initData` (корректный HMAC-SHA256, истекший срок `auth_date`, невалидный хеш).
   - Unit-тесты для Telegram Login Widget хеша.
2. **Тестирование API**:
   - `test_join_and_leave_game`: запись игрока, проверка очереди `position`, отмена записи и автоматическое продвижение резервиста в основу.
   - `test_friends_limits`: добавление до 3 друзей, блокировка добавления сверх лимита, блокировка когда друзья закрыты.
   - `test_sync_update_message`: вызов `update_game_message` в фоне при каждом действии через mock `Bot`.
   - `test_admin_security`: попытка выполнения админских эндпоинтов обычным пользователем возвращает HTTP 403 Forbidden.
3. **E2E верификация фронтенда**:
   - Сборка фронтенда `npm run build` завершается без ошибок TypeScript и линтера.
   - SPA корректно рендерит `/` без токена и переключается на `/app` при наличии токена.
