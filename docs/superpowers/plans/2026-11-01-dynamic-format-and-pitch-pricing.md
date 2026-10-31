# Dynamic Format, Pitch Rental Cost-Splitting & Clean Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify game creation to `/new_game YYYY-MM-DD HH:MM`, add dynamic game format descriptions (up to 15 players), remove friends text from game card messages, and implement dynamic pitch rental cost-splitting (1.5h vs 2h) at payment collection.

**Architecture:** 
- `render.py` dynamically calculates game format text (5x5, with subs, 3 teams, full squad) based on confirmed player count, removes friends text, and displays pitch rent / per-player cost.
- `/new_game` accepts simplified `date` and `time` arguments with defaults: `max_players = 15`, `hourly_rate = 600`, `duration_minutes = 90`, `friends_open_after_hours = 6`.
- Payment collection flow prompts admin in DM to pick duration (`1.5 часа (900 грн)` vs `2.0 часа (1200 грн)`), automatically splits pitch rental across confirmed players (`ceil(total / count)`), and updates all group cards.

**Tech Stack:** Python 3.12, aiogram 3.13, PyMongo 4.10, unittest.

## Global Constraints
- `callback_data` must strictly stay under 64 bytes.
- All dynamic strings must be escaped with `html.escape()`.
- Backward compatibility for full `/new_game` arguments (8 args) preserved alongside the new 2-arg syntax.
- All MongoDB dates in UTC.

## Review Focus
1. Correct rounding of per-player cost (ceil to avoid under-collecting rent).
2. Clean card formatting without any friends text when friends are closed or open.
3. Division by zero safety if payment collection starts with 0 confirmed players.
4. Correct dynamic format labels for 0-9, 10, 11-12, 13-14, 15, and 16+ players.

---

### Task 1: Update Card Rendering in `render.py`

**Files:**
- Modify: `app/services/render.py`
- Test: `tests/test_render_dynamic.py`

**Interfaces:**
- Produces: `format_game_message(game: dict, participants: list[dict], payments: list[dict] | None = None) -> str`
- Requirements:
  - Remove all lines mentioning friends status (`👥 Друзья: ...` and footer text).
  - Dynamic format text based on `len(confirmed)`:
    - 0-9: `⏳ Сбор состава (нужно от 10 чел для 5х5)`
    - 10: `⚽ 2 команды 5х5`
    - 11-12: `⚽ 2 команды 5х5 (+{count - 10} на замену)`
    - 13-14: `⚽ 3 команды ({count} чел, с ротацией/заменами)`
    - 15: `🔥 3 команды 5х5 (15 чел — полный сбор!)`
    - 16+: `🔥 3 команды 5х5 (основа 15, резерв {count - 15})`
  - In `payment_collection`: display `Аренда поля: {total} грн ({duration} ч) — по {price} грн с игрока`.

- [ ] **Step 1: Write the failing test for dynamic rendering and no friends text**

```python
# tests/test_render_dynamic.py
import unittest
from datetime import datetime, timezone
from bson import ObjectId
from app.services.render import format_game_message

class TestRenderDynamic(unittest.TestCase):
    def test_dynamic_format_and_no_friends_text(self):
        game = {
            "_id": ObjectId(),
            "title": "Футбол",
            "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            "duration_minutes": 90,
            "hourly_rate": 600,
            "price": 75,
            "max_players": 15,
            "status": "registration_open",
            "friends_allowed": False,
        }
        
        # 0 players
        text_0 = format_game_message(game, [])
        self.assertNotIn("Друзья", text_0)
        self.assertIn("Сбор состава (нужно от 10 чел для 5х5)", text_0)

        # 10 players
        p10 = [{"status": "confirmed", "type": "player", "display_name": f"P{i}"} for i in range(10)]
        text_10 = format_game_message(game, p10)
        self.assertIn("2 команды 5х5", text_10)
        self.assertNotIn("Друзья", text_10)

        # 12 players
        p12 = [{"status": "confirmed", "type": "player", "display_name": f"P{i}"} for i in range(12)]
        text_12 = format_game_message(game, p12)
        self.assertIn("2 команды 5х5 (+2 на замену)", text_12)

        # 15 players
        p15 = [{"status": "confirmed", "type": "player", "display_name": f"P{i}"} for i in range(15)]
        text_15 = format_game_message(game, p15)
        self.assertIn("3 команды 5х5 (15 чел — полный сбор!)", text_15)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m unittest tests/test_render_dynamic.py`
Expected: FAIL.

- [ ] **Step 3: Implement dynamic format and remove friends text in `app/services/render.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m unittest tests/test_render_dynamic.py`
Expected: PASS.

---

### Task 2: Simplified `/new_game YYYY-MM-DD HH:MM` and Repository Defaults

**Files:**
- Modify: `app/repositories/games.py`
- Modify: `app/bot/handlers.py`
- Test: `tests/test_new_game_short.py`

**Interfaces:**
- `/new_game 2026-11-06 19:00` (2 parts after command) creates game with:
  - `max_players = 15`
  - `teams_count = 3`, `players_per_team = 5`
  - `hourly_rate = 600`
  - `duration_minutes = 90`
  - `friends_open_after_hours = 6`
  - `price = 0` (computed upon payment collection)

- [ ] **Step 1: Write test for short creation syntax and repository defaults**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement short `/new_game` handling and repository defaults**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 3: Interactive Duration Selection and Cost-Splitting at Payment Collection

**Files:**
- Modify: `app/bot/keyboards.py` (add `payment_duration_keyboard(game_id, hourly_rate)`)
- Modify: `app/bot/handlers.py` (handle duration choice `admin:{game_id}:pay_dur:{minutes}`)

**Interfaces:**
- Callback: `admin:{game_id}:confirm_payments` sends duration choice keyboard:
  `[ ⏱ 1.5 часа (900 грн) ]  [ ⏱ 2.0 часа (1200 грн) ]`
- Callback: `admin:{game_id}:pay_dur:{minutes}`:
  - `minutes = int(...)` (90 or 120)
  - `total_cost = int((minutes / 60) * hourly_rate)`
  - `confirmed_count = len(confirmed)`
  - `per_player = math.ceil(total_cost / confirmed_count) if confirmed_count > 0 else 0`
  - Updates game: `price = per_player`, `total_cost = total_cost`, `duration_minutes = minutes`, `status = "payment_collection"`
  - Calls `pay_repo.ensure_for_game(game_id, per_player)`
  - Calls `update_game_message(bot, game)`

- [ ] **Step 1: Write test for payment duration keyboard and cost calculation**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement duration selection in keyboards and handlers**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 4: Full Suite & End-to-End Verification

- [ ] **Step 1: Run all tests in test suite**
- [ ] **Step 2: Update documentation and directory prompts (`GEMINI.md`, `README.md`)**
