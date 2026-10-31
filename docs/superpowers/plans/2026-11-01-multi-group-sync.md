# Multi-Group Broadcast and Real-Time Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement multi-group game publishing and instant bidirectional synchronization across all linked Telegram group chats.

**Architecture:** A new `chats` collection stores all groups where the bot is present. The `games` collection replaces single `chat_id` and `message_id` fields with a `messages` array of `{chat_id, message_id, chat_title, added_at}`. Admin creates games in direct messages or group chats, selects target groups to publish via inline buttons, and an asynchronous parallel updater (`asyncio.gather`) keeps all linked cards in sync across all chats whenever any action occurs.

**Tech Stack:** Python 3.12, aiogram 3.13.1, MongoDB 8.0 (PyMongo 4.10 `AsyncMongoClient`), APScheduler 3.10.4.

**Spec:** `docs/superpowers/specs/2026-11-01-multi-group-sync-design.md`

## Global Constraints
- Telegram Bot API `callback_data` must strictly stay under 64 bytes.
- All MongoDB dates stored in UTC (`datetime.now(timezone.utc)`).
- HTML message templates must escape all dynamic user strings via `html.escape()`.
- Error handling must gracefully isolate individual chat failures (`TelegramBadRequest`, `TelegramForbiddenError`) without aborting updates to other chats.

## Review Focus
1. `callback_data` for group publishing buttons exceeding 64 bytes when chat IDs or game IDs are long.
2. Bot attempting to edit a card in a group where it was kicked or the message was manually deleted.
3. Roster normalization (`normalize_roster`) maintaining a single unified queue across all chats.
4. Active game lookup (`get_active_for_chat`) correctly finding the game from any of its linked `messages.chat_id`.
5. Background auto-opening of friends updating all linked group chats in parallel.

---

### Task 1: Database Indexes and Chat Repository

**Files:**
- Modify: `app/db/mongo.py:31-37`
- Create: `app/repositories/chats.py`
- Create: `tests/test_chats_repo.py`

**Interfaces:**
- Produces: `ChatRepository.upsert_chat(chat_id: int, title: str, chat_type: str) -> dict`
- Produces: `ChatRepository.list_active_chats() -> list[dict]`
- Produces: `ChatRepository.set_active_status(chat_id: int, is_active: bool) -> None`

- [ ] **Step 1: Write the failing test for `ChatRepository`**

```python
# tests/test_chats_repo.py
import pytest
from mongomock_motor import AsyncMongoMockClient
from app.repositories.chats import ChatRepository

@pytest.mark.asyncio
async def test_upsert_and_list_chats():
    client = AsyncMongoMockClient()
    db = client["test_db"]
    repo = ChatRepository(db)

    await repo.upsert_chat(-1001, "Main Group", "supergroup")
    await repo.upsert_chat(-1002, "Reserve Group", "supergroup")
    
    chats = await repo.list_active_chats()
    assert len(chats) == 2
    assert chats[0]["chat_id"] == -1001

    await repo.set_active_status(-1002, False)
    active = await repo.list_active_chats()
    assert len(active) == 1
    assert active[0]["chat_id"] == -1001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_chats_repo.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.repositories.chats'` (or missing package).

- [ ] **Step 3: Implement `ChatRepository` and update database indexes in `app/db/mongo.py`**

In `app/db/mongo.py`:
Add index `await db.chats.create_index("chat_id", unique=True)` and `await db.games.create_index("messages.chat_id")`.

In `app/repositories/chats.py`:
Implement `ChatRepository` with `upsert_chat`, `list_active_chats`, and `set_active_status`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_chats_repo.py`
Expected: PASS.

---

### Task 2: Multi-Group Game Repository Support

**Files:**
- Modify: `app/repositories/games.py:18-68`
- Create: `tests/test_games_multigroup.py`

**Interfaces:**
- Consumes: `app.db.mongo.get_db`
- Produces: `GameRepository.add_linked_message(game_id: str, chat_id: int, message_id: int, chat_title: str) -> None`
- Produces: `GameRepository.remove_linked_message(game_id: str, chat_id: int, message_id: int | None = None) -> None`
- Updates: `GameRepository.create_game` to initialize `messages: []`
- Updates: `GameRepository.get_active_for_chat(chat_id: int)` to query `{"messages.chat_id": chat_id, "status": {"$in": ACTIVE_STATUSES}}`

- [ ] **Step 1: Write the failing test for multi-group game methods**

```python
# tests/test_games_multigroup.py
import pytest
from datetime import datetime, timezone
from mongomock_motor import AsyncMongoMockClient
from app.repositories.games import GameRepository

@pytest.mark.asyncio
async def test_linked_messages_and_lookup():
    client = AsyncMongoMockClient()
    db = client["test_db"]
    repo = GameRepository(db)

    game = await repo.create_game(
        chat_id=None,
        title="Футбол",
        start_at=datetime.now(timezone.utc),
        teams_count=3,
        players_per_team=6,
        price=200,
        duration_minutes=90,
        friends_open_after_hours=6,
        created_by=123,
    )
    game_id = str(game["_id"])
    assert game["messages"] == []

    await repo.add_linked_message(game_id, -1001, 50, "Group A")
    await repo.add_linked_message(game_id, -1002, 60, "Group B")

    found_a = await repo.get_active_for_chat(-1001)
    found_b = await repo.get_active_for_chat(-1002)
    assert found_a is not None and str(found_a["_id"]) == game_id
    assert found_b is not None and str(found_b["_id"]) == game_id

    await repo.remove_linked_message(game_id, -1001)
    updated = await repo.get(game_id)
    assert len(updated["messages"]) == 1
    assert updated["messages"][0]["chat_id"] == -1002
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_games_multigroup.py`
Expected: FAIL with `AttributeError` for `add_linked_message`.

- [ ] **Step 3: Implement multi-group methods in `GameRepository`**

1. Update `create_game()` to store `"messages": []`.
2. Implement `add_linked_message(game_id, chat_id, message_id, chat_title)` using `$push`.
3. Implement `remove_linked_message(game_id, chat_id, message_id=None)` using `$pull`.
4. Update `get_active_for_chat(chat_id)` and `get_manageable_for_chat(chat_id)` to filter on `{"messages.chat_id": chat_id}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_games_multigroup.py`
Expected: PASS.

---

### Task 3: Keyboards for Group Broadcasting and Admin Menus

**Files:**
- Modify: `app/bot/keyboards.py`
- Create: `tests/test_keyboards.py`

**Interfaces:**
- Produces: `broadcast_groups_keyboard(game_id: str, chats: list[dict], linked_chat_ids: set[int]) -> InlineKeyboardMarkup`
- Updates: `admin_game_keyboard` to include `[ 📢 Публикация в группах ]` button with callback `admin:<game_id>:broadcast_menu`

- [ ] **Step 1: Write test for broadcast keyboards and 64-byte limit constraint**

```python
# tests/test_keyboards.py
from app.bot.keyboards import broadcast_groups_keyboard, admin_game_keyboard

def test_broadcast_keyboard_callbacks_under_64_bytes():
    game_id = "64a8b79f2e3d4c5b6a7b8c9d"
    chats = [
        {"chat_id": -1001234567890, "title": "Основной состав"},
        {"chat_id": -1009876543210, "title": "Резервный состав"},
    ]
    linked_chat_ids = {-1001234567890}
    kb = broadcast_groups_keyboard(game_id, chats, linked_chat_ids)
    
    for row in kb.inline_keyboard:
        for btn in row:
            assert len(btn.callback_data.encode("utf-8")) <= 64

def test_admin_keyboard_includes_broadcast():
    game_id = "64a8b79f2e3d4c5b6a7b8c9d"
    kb = admin_game_keyboard(game_id, friends_allowed=False, status="registration_open")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"admin:{game_id}:broadcast_menu" in callbacks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_keyboards.py`
Expected: FAIL with `ImportError: cannot import name 'broadcast_groups_keyboard'`.

- [ ] **Step 3: Implement `broadcast_groups_keyboard` and update `admin_game_keyboard`**

In `app/bot/keyboards.py`:
- Implement `broadcast_groups_keyboard`:
  - Top row: `[ 📢 Опубликовать во всех ]` (callback `admin:{game_id}:pub_all`)
  - Rows for each chat: if in `linked_chat_ids`, button `✅ {chat_title}` (callback `admin:{game_id}:unpub:{chat_id}`); if not linked, button `➕ {chat_title}` (callback `admin:{game_id}:pub:{chat_id}`).
  - Bottom row: `[ ⚙️ Управление игрой ]` (callback `admin:{game_id}:settings`).
- In `admin_game_keyboard`:
  - Add button `[ 📢 Публикация в группах ]` (`admin:{game_id}:broadcast_menu`).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_keyboards.py`
Expected: PASS.

---

### Task 4: Bot Handlers for Group Discovery, DM Creation, and Publishing

**Files:**
- Modify: `app/bot/handlers.py`

**Interfaces:**
- Consumes: `ChatRepository`, `GameRepository`, `broadcast_groups_keyboard`, `admin_game_keyboard`
- Produces:
  - `@router.my_chat_member()` handler to auto-register/unregister bot groups.
  - Updated `@router.message(Command("new_game"))` allowing admins to run in DM.
  - Callback handlers:
    - `admin:<game_id>:broadcast_menu`
    - `admin:<game_id>:pub:<chat_id>`
    - `admin:<game_id>:unpub:<chat_id>`
    - `admin:<game_id>:pub_all`

- [ ] **Step 1: Update `/new_game` to allow creation in DM for admins**

Remove restriction `if not is_group_chat(message): ...` for admins. If executed in DM:
1. Create game with `messages: []`.
2. Fetch active chats via `ChatRepository.list_active_chats()`.
3. Send preview card to admin in DM with `broadcast_groups_keyboard`.

If executed in a group:
1. Also upsert that group in `ChatRepository`.
2. Create game and immediately post card in that group, saving `{chat_id, message_id}` to `game.messages`.

- [ ] **Step 2: Add `my_chat_member` event handler and group activity tracking**

Add handler:
```python
@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated):
    if event.chat.type in ("group", "supergroup"):
        db = get_db()
        chat_repo = ChatRepository(db)
        is_active = event.new_chat_member.status in ("member", "administrator")
        if is_active:
            await chat_repo.upsert_chat(event.chat.id, event.chat.title or "Группа", event.chat.type)
        else:
            await chat_repo.set_active_status(event.chat.id, False)
```

- [ ] **Step 3: Implement callbacks for publishing and unpublishing groups**

- `pub:<chat_id>`:
  1. Post game card to `chat_id` using `format_game_message()` and `game_keyboard()`.
  2. Call `game_repo.add_linked_message(game_id, chat_id, sent.message_id, chat_title)`.
  3. Refresh broadcast menu in admin DM.
- `unpub:<chat_id>`:
  1. Delete card from `chat_id`.
  2. Call `game_repo.remove_linked_message(game_id, chat_id)`.
  3. Refresh broadcast menu in admin DM.
- `pub_all`:
  Loop through all active chats not yet in `linked_chat_ids` and publish cards.

- [ ] **Step 4: Verify syntax and imports**

Run: `./.venv/bin/python -m py_compile app/bot/handlers.py`
Expected: Return 0 (no syntax errors).

---

### Task 5: Parallel Synchronization Engine in `update_game_message` & Scheduler

**Files:**
- Modify: `app/bot/handlers.py:59-77`
- Modify: `app/services/scheduler.py:19-28`

**Interfaces:**
- Consumes: `GameRepository`, `ParticipantRepository`, `PaymentRepository`
- Produces: `update_game_message(bot: Bot, game: dict) -> None` running `asyncio.gather` over all `game.messages` with exception handling.

- [ ] **Step 1: Refactor `update_game_message` to broadcast to all `game.messages`**

Implement helper:
```python
async def _update_single_message(bot, game_repo, chat_repo, game_id, chat_id, message_id, text, reply_markup):
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "not modified" in err_msg:
            return
        if "not found" in err_msg or "deleted" in err_msg or "can't be edited" in err_msg:
            await game_repo.remove_linked_message(game_id, chat_id, message_id)
    except TelegramForbiddenError:
        await game_repo.remove_linked_message(game_id, chat_id, message_id)
        await chat_repo.set_active_status(chat_id, False)
```
In `update_game_message`:
Gather tasks with `await asyncio.gather(*tasks, return_exceptions=True)`.

- [ ] **Step 2: Update `open_friends_job` in `app/services/scheduler.py`**

Replace the direct `bot.edit_message_text(...)` in `open_friends_job` with:
```python
await update_game_message(bot, game)
```
Now friend openings automatically broadcast across all linked chats.

- [ ] **Step 3: Verify syntax and imports**

Run: `./.venv/bin/python -m py_compile app/services/scheduler.py app/bot/handlers.py`
Expected: Return 0.

---

### Task 6: End-to-End Simulation Script and Documentation Update

**Files:**
- Create: `tests/e2e_multigroup_simulation.py`
- Modify: `README.md`
- Modify: `GEMINI.md`, `app/bot/GEMINI.md`, `app/repositories/GEMINI.md`

- [ ] **Step 1: Write and run end-to-end multi-group sync simulation test**

Simulate:
1. Registering 2 groups in `ChatRepository`.
2. Admin creating a game in DM.
3. Publishing the game to Group 1 and Group 2.
4. Player 1 joins in Group 1. Verify `update_game_message` triggers for both groups.
5. Player 2 joins in Group 2. Verify both cards show both players.
6. Format change by admin in DM. Verify both groups update with new slot limits.

- [ ] **Step 2: Run simulation test**

Run: `./.venv/bin/python tests/e2e_multigroup_simulation.py`
Expected: All assertions pass.

- [ ] **Step 3: Update documentation and directory prompts (`GEMINI.md`)**

Document the multi-group capability, the `chats` collection, and the publishing flow.
