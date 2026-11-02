# Project Audit Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve critical race conditions, API-to-roster sync bugs, CORS security flaw, unhandled sync errors, hardcoded bot username, and repository hygiene issues discovered during the audit.

**Architecture:** 
1. Use atomic MongoDB operations (`$inc` on `games.last_position`) for queue position assignments and add partial unique indexes for participants.
2. Ensure REST API (`admin.py`) triggers `normalize_roster` upon `max_players` changes, matching bot behavior.
3. Fix CORS configuration and expose `/api/health` in FastAPI.
4. Provide dynamic bot username to the frontend and rebuild static assets.
5. Clean repository artifacts (`_old/`, `.DS_Store`).

**Tech Stack:** Python 3.12, aiogram 3.13, FastAPI, PyMongo, Pydantic, Vite/React, pytest.

---

## Global Constraints

- Preserve all existing tests and ensure all 34+ tests pass.
- Maintain backward compatibility with existing MongoDB documents (e.g. games that do not yet have `last_position`).
- Comply with Telegram 64-byte `callback_data` limit.
- Keep Python code formatted cleanly and free of unawaited coroutine warnings.

---

### Task 1: Atomic Queue Position & Partial Unique Index

**Files:**
- Modify: `app/db/mongo.py`
- Modify: `app/repositories/games.py`
- Modify: `app/repositories/participants.py`
- Test: `tests/test_roster_atomic.py`

- [x] **Step 1: Write failing unit test for atomic position counter and unique participant constraint**
- [x] **Step 2: Run test to confirm it fails**
- [x] **Step 3: Implement atomic position logic in repositories and mongo indexes**
- [x] **Step 4: Run tests and verify they pass**

---

### Task 2: Fix Roster Normalization on API `edit_game` & Code Cleanup

**Files:**
- Modify: `app/api/routers/admin.py`
- Modify: `app/api/routers/games.py`
- Test: `tests/test_api_games.py`

- [x] **Step 1: Write unit test in `tests/test_api_games.py` for `edit_game(max_players)`**
- [x] **Step 2: Run test to confirm it fails**
- [x] **Step 3: Update `admin.py` and `games.py`**
- [x] **Step 4: Run tests to verify pass**

---

### Task 3: Background Sync Logging, Flood Control & Health Endpoint

**Files:**
- Modify: `app/api/sync.py`
- Modify: `app/bot/handlers.py`
- Modify: `app/main.py`
- Test: `tests/test_sync_and_health.py`

- [x] **Step 1: Write tests for health endpoint and sync error logging**
- [x] **Step 2: Implement `/api/health`, fix CORS, handle retry after, and add logging**
- [x] **Step 3: Run tests and verify they pass**

---

### Task 4: Frontend Dynamic Bot Username & Rebuild

**Files:**
- Modify: `app/config/settings.py`
- Modify: `app/api/routers/auth.py`
- Modify: `frontend/src/pages/CabinetPage.tsx`
- Modify: `frontend/src/pages/PublicSchedule.tsx`
- Modify: `app/services/render.py`
- Test: `tests/test_render_dynamic.py`

- [x] **Step 1: Expose bot username from backend configuration**
- [x] **Step 2: Update frontend to use dynamic bot username and rebuild**
- [x] **Step 3: Verify frontend build and tests**

---

### Task 5: Repository Hygiene & Git Cleanup

**Files:**
- Remove from git: `_old/`
- Remove from git: `.DS_Store`, `app/.DS_Store`
- Update: `.gitignore`

- [x] **Step 1: Untrack `.DS_Store` and delete `_old` directory**
- [x] **Step 2: Run complete test suite and verify everything passes**
