# Telegram Mini App & Web Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram Mini App and public web schedule on `football.idev.wtf` with dual Telegram authorization, player/admin roles, and real-time synchronization with the Telegram bot and group chats.

**Architecture:** A unified FastAPI + aiogram 3 service running in a single asynchronous process. FastAPI handles REST API and serves the compiled React SPA, while aiogram polling and APScheduler run in FastAPI's lifespan. All actions taken in the Web/Mini App trigger existing Telegram message updates across group chats in real time.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, aiogram 3, PyMongo, PyJWT, Cryptography, React 18, Vite, Tailwind CSS, Lucide React, Docker Swarm, Traefik v3.

**Spec:** `docs/superpowers/specs/2026-11-01-telegram-mini-app-web-design.md`

## Global Constraints

- Python version floor: 3.12 (in `.venv`).
- aiogram version: 3.13.1.
- Telegram Bot API token verification: HMAC-SHA256 signature algorithm strictly complying with official Telegram WebApp and Login Widget specifications.
- Domain and Routing: `football.idev.wtf/` serves public schedule/landing; `football.idev.wtf/app` serves the SPA cabinet and admin panel; `football.idev.wtf/api/*` serves REST API endpoints.
- Swarm deploy constraint: `replicas: 1` for the `app` container to ensure single-instance polling safety and avoid `getUpdates` conflicts with Telegram.

## Review Focus

1. **Telegram `initData` tampering or expiration**: requests with mismatched HMAC or `auth_date` older than 86400s must be rejected with HTTP 401.
2. **Unauthorized admin action**: players attempting to invoke `/api/admin/*` must receive HTTP 403 Forbidden.
3. **Reserve promotion on web cancellation**: when a player cancels their registration (`leave`) via web, the first player from reserve must be automatically promoted to confirmed, and Telegram chat messages must update immediately.
4. **Friends quota enforcement**: players cannot add more than 3 friends, and cannot add friends if `friends_allowed` is false.
5. **SPA routing fallback**: direct browser navigation to `/app` or `/app/*` must return the React `index.html` with HTTP 200, not a 404.

---

### Task 1: Dependencies and Settings Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `app/config/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: Existing environment variables from `.env`.
- Produces: `Settings.webapp_url: str`, `Settings.jwt_secret: str`, `Settings.card_number: str`, `Settings.card_recipient: str`.

- [ ] **Step 1: Write test for new settings configuration**

```python
# tests/test_settings.py
def test_new_settings_fields():
    from app.config.settings import Settings
    s = Settings(
        bot_token="test_token",
        admin_telegram_ids=[12345],
        webapp_url="https://football.idev.wtf",
        jwt_secret="super-secret-key-32-chars-minimum-length!",
        card_number="4149 0000 0000 0000",
        card_recipient="Организатор"
    )
    assert s.webapp_url == "https://football.idev.wtf"
    assert s.jwt_secret == "super-secret-key-32-chars-minimum-length!"
    assert s.card_number == "4149 0000 0000 0000"
    assert s.card_recipient == "Организатор"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_settings.py -v`
Expected: FAIL with ValidationError or attribute missing.

- [ ] **Step 3: Update `requirements.txt` and `app/config/settings.py`**

Add to `requirements.txt`:
```text
fastapi==0.115.4
uvicorn[standard]==0.32.0
pyjwt==2.9.0
cryptography==43.0.3
```
Add fields to `Settings` class in `app/config/settings.py` with reasonable defaults (`webapp_url: str = "https://football.idev.wtf"`, `jwt_secret: str = "change-me-secret-key"`, `card_number: str = ""`, `card_recipient: str = ""`).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_settings.py -v`
Expected: PASS

---

### Task 2: Dual Telegram Authentication & JWT Security Module

**Files:**
- Create: `app/api/auth.py`
- Create: `app/api/dependencies.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `Settings.bot_token`, `Settings.jwt_secret`, `Settings.admin_telegram_ids`.
- Produces:
  - `validate_init_data(init_data: str, bot_token: str) -> dict`
  - `validate_widget_data(data: dict, bot_token: str) -> dict`
  - `create_access_token(data: dict) -> str`
  - `get_current_user(token: str) -> dict` (FastAPI dependency)
  - `require_admin(user: dict) -> dict` (FastAPI dependency)

- [ ] **Step 1: Write tests for authentication algorithms and failure modes**

```python
# tests/test_auth.py
import hmac
import hashlib
import time
import urllib.parse
import pytest
from app.api.auth import validate_init_data, validate_widget_data, create_access_token

BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"

def create_valid_init_data(user_dict, bot_token=BOT_TOKEN, auth_date=None):
    if auth_date is None:
        auth_date = int(time.time())
    import json
    data = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user_dict, separators=(",", ":"))
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    data["hash"] = hash_val
    return urllib.parse.urlencode(data)

def test_validate_init_data_success():
    init_data = create_valid_init_data({"id": 111, "first_name": "Leo", "username": "messi"})
    parsed = validate_init_data(init_data, BOT_TOKEN)
    assert parsed["user"]["id"] == 111
    assert parsed["user"]["username"] == "messi"

def test_validate_init_data_tampered():
    init_data = create_valid_init_data({"id": 111, "first_name": "Leo"}) + "tampered"
    with pytest.raises(ValueError, match="Invalid signature"):
        validate_init_data(init_data, BOT_TOKEN)

def test_validate_init_data_expired():
    old_time = int(time.time()) - 100000
    init_data = create_valid_init_data({"id": 111, "first_name": "Leo"}, auth_date=old_time)
    with pytest.raises(ValueError, match="Data expired"):
        validate_init_data(init_data, BOT_TOKEN)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pytest tests/test_auth.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `app/api/auth.py` and `app/api/dependencies.py`**

Implement cryptographic verification for both Mini App (`initData`) and Login Widget (`auth_date`, `hash`), plus JWT creation and decoding with PyJWT. In `dependencies.py`, implement `get_current_user` checking bearer token from headers and `require_admin` ensuring `user["role"] == "admin"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_auth.py -v`
Expected: PASS

---

### Task 3: REST API Endpoints for Games, Roster, Payments & Admin

**Files:**
- Create: `app/api/routers/games.py`
- Create: `app/api/routers/admin.py`
- Create: `app/api/routers/auth.py`
- Test: `tests/test_api_games.py`

**Interfaces:**
- Consumes: `GameRepository`, `ParticipantRepository`, `ChatRepository`, `PaymentRepository`, `UserRepository`, `update_game_message`.
- Produces: FastAPI router mounted at `/api`.

- [ ] **Step 1: Write integration tests for API endpoints**

```python
# tests/test_api_games.py
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_get_public_games(app_client):
    response = await app_client.get("/api/games")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_join_and_leave_game(app_client, auth_player_token, test_game_id):
    headers = {"Authorization": f"Bearer {auth_player_token}"}
    # Join
    res_join = await app_client.post(f"/api/games/{test_game_id}/join", headers=headers)
    assert res_join.status_code == 200
    assert res_join.json()["status"] in ["confirmed", "reserve"]

    # Leave
    res_leave = await app_client.post(f"/api/games/{test_game_id}/leave", headers=headers)
    assert res_leave.status_code == 200

@pytest.mark.asyncio
async def test_admin_only_endpoint_forbidden_for_player(app_client, auth_player_token, test_game_id):
    headers = {"Authorization": f"Bearer {auth_player_token}"}
    res = await app_client.post(f"/api/admin/games/{test_game_id}/cancel", json={"reason": "Rain"}, headers=headers)
    assert res.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pytest tests/test_api_games.py -v`
Expected: FAIL with 404 or connection error.

- [ ] **Step 3: Implement routers and message sync**

In `app/api/routers/games.py` and `app/api/routers/admin.py`:
- Use existing repositories for all database reads and updates.
- Wrap `asyncio.create_task(update_game_message(bot, game_id))` upon any state modification.
- Handle friends addition (limit 3, `friends_allowed` check).
- Handle payment status update and duration calculation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_api_games.py -v`
Expected: PASS

---

### Task 4: Unified Application Lifecycle & Static File Mounting

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_main_app.py`

**Interfaces:**
- Consumes: aiogram `Bot`, `Dispatcher`, `FastAPI`, `setup_scheduler`.
- Produces: ASGI application `app` in `app.main:app`.

- [ ] **Step 1: Write test for FastAPI app startup and routing**

```python
# tests/test_main_app.py
from fastapi.testclient import TestClient
from app.main import app

def test_api_ping():
    client = TestClient(app)
    response = client.get("/api/me")
    # Without token, should return 401
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_main_app.py -v`
Expected: FAIL (app object not found or not FastAPI).

- [ ] **Step 3: Implement `app/main.py` with FastAPI Lifespan**

- Create `app = FastAPI(title="Football Bot & Mini App", lifespan=lifespan)`.
- In `lifespan`:
  - `await init_mongo()`
  - Start `asyncio.create_task(dp.start_polling(bot))`
  - Start `scheduler = setup_scheduler(bot)`
  - Yield
  - Shutdown: `scheduler.shutdown()`, `await dp.stop_polling()`, `await bot.session.close()`, `await close_mongo()`.
- Mount `/api` routers.
- Mount `StaticFiles` for `/static` and a catch-all route `/{full_path:path}` serving `app/static/index.html` (SPA fallback).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_main_app.py -v`
Expected: PASS

---

### Task 5: React SPA Frontend Implementation

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/hooks/useTelegram.ts`
- Create: `frontend/src/hooks/useAuth.tsx`
- Create: `frontend/src/pages/PublicSchedule.tsx`
- Create: `frontend/src/pages/CabinetPage.tsx`
- Create: `frontend/src/components/Navbar.tsx`
- Create: `frontend/src/components/GameCard.tsx`
- Create: `frontend/src/components/RosterList.tsx`
- Create: `frontend/src/components/FriendsModal.tsx`
- Create: `frontend/src/components/PaymentBox.tsx`
- Create: `frontend/src/components/AdminControls.tsx`

**Interfaces:**
- Consumes: REST API at `/api/*`, Telegram WebApp JS library (`window.Telegram.WebApp`).
- Produces: Production build bundle in `frontend/dist/`.

- [ ] **Step 1: Scaffold React Vite TypeScript Tailwind project**

Configure `package.json` with React 18, Vite, Tailwind CSS, Lucide React, and `@types/telegram-web-app`.

- [ ] **Step 2: Implement Telegram hooks and Auth Context**

Implement `useTelegram` managing viewport expansion (`expand()`), haptics, theme parameters, and extracting `initData`.
Implement `useAuth` storing JWT in `localStorage`, auto-authenticating when inside Telegram, and exposing login modal for Web widget.

- [ ] **Step 3: Implement Components and Pages**

1. `PublicSchedule.tsx`: Clean match cards, progress bar, roster list, "Войти через Telegram" button, "Чат матча" link.
2. `CabinetPage.tsx`: Player action buttons ("Записаться", "Отказаться"), friends management modal, payment card box with copy button and status toggles.
3. `AdminControls.tsx`: Match creation modal, roster drag/reorder/kick, friends registration toggle, payment collection starter.

- [ ] **Step 4: Build frontend bundle and verify static build**

Run: `cd frontend && npm install && npm run build`
Expected: Successful compile into `frontend/dist/` without TypeScript or bundle errors.

---

### Task 6: Docker Swarm Deployment & Multi-Stage Dockerfile

**Files:**
- Modify: `Dockerfile`
- Create: `docker-compose.swarm.yml`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: Frontend code, backend code, server's Traefik v3 and `traefik-public` network.
- Produces: Deployable Swarm stack matching production specifications.

- [ ] **Step 1: Write Multi-Stage Dockerfile**

Create multi-stage build:
1. `node:20-alpine` builds `frontend` to `dist`.
2. `python:3.12-slim` installs requirements and copies `dist` to `/app/app/static`.

- [ ] **Step 2: Create `docker-compose.swarm.yml`**

Include:
- Service `app` with `replicas: 1`.
- Traefik labels: `traefik.swarm.network=traefik-public`, `Host(`football.idev.wtf`)`, `tls.certresolver=letsencrypt`, `cloudflare-only` middleware, port 8000.
- Networks: `traefik-public` (external: true) and `football-internal` (overlay, attachable: true).
- Service `mongo` with `node.role == manager` constraint.

- [ ] **Step 3: Test local Docker build**

Run: `docker build -t football-bot:test .`
Expected: Build finishes with exit code 0.

---

## Plan Review & Verification Checklist

- [ ] All API endpoints match the design spec.
- [ ] TMA `initData` and Web Widget auth are cryptographically verified.
- [ ] Telegram message updates trigger concurrently with Web mutations.
- [ ] Frontend responsive on both mobile Telegram Mini App and desktop browser.
- [ ] Swarm configuration matches server Traefik v3 setup.
