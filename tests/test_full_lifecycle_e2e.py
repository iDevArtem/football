import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.auth import create_access_token
from app.config.settings import get_settings
from app.services.render import format_game_message


@pytest.fixture
def app():
    from app.api.routers.games import router as games_router
    from app.api.routers.admin import router as admin_router
    from app.api.routers.auth import router as auth_router

    application = FastAPI()
    application.include_router(auth_router, prefix="/api/auth")
    application.include_router(games_router, prefix="/api/games")
    application.include_router(admin_router, prefix="/api/admin")
    return application


@pytest.fixture
def admin_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "999", "telegram_id": 999, "first_name": "Admin", "role": "admin"},
        secret=secret,
    )


@pytest.fixture
def player_a_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "111", "telegram_id": 111, "first_name": "PlayerA", "role": "player"},
        secret=secret,
    )


@pytest.fixture
def player_b_token():
    secret = get_settings().jwt_secret
    return create_access_token(
        {"sub": "222", "telegram_id": 222, "first_name": "PlayerB", "role": "player"},
        secret=secret,
    )


@pytest.mark.asyncio
async def test_full_lifecycle_e2e(app, admin_token, player_a_token, player_b_token):
    game_id = "6724123456789abcdef01234"
    friend_id = ObjectId("6724123456789abcdef08888")
    guest_id = ObjectId("6724123456789abcdef09999")

    # In-memory simulated storage for this game
    game_state = {
        "_id": ObjectId(game_id),
        "title": "Пятничный матч",
        "start_at": datetime.now(timezone.utc),
        "status": "registration_open",
        "hourly_rate": 600,
        "duration_minutes": 90,
        "max_players": 15,
        "friends_allowed": True,
        "price": 0,
        "total_cost": None,
        "messages": [],
        "payment_details": None,
    }

    participants_state = [
        {"_id": ObjectId("6724123456789abcdef01111"), "telegram_id": 111, "display_name": "PlayerA", "type": "player", "status": "confirmed", "position": 1, "added_by_telegram_id": None},
        {"_id": ObjectId("6724123456789abcdef02222"), "telegram_id": 222, "display_name": "PlayerB", "type": "player", "status": "confirmed", "position": 2, "added_by_telegram_id": None},
        {"_id": friend_id, "telegram_id": None, "display_name": "FriendC", "type": "friend", "status": "confirmed", "position": 3, "added_by_telegram_id": 111},
    ]

    payments_state = {}

    db = MagicMock()

    async def mock_game_get(gid):
        if str(gid) == game_id:
            return game_state
        return None

    async def mock_game_set_status(gid, st):
        game_state["status"] = st
        return True

    async def mock_game_update_one(query, update, **kwargs):
        if "$set" in update:
            game_state.update(update["$set"])
        return MagicMock(matched_count=1)

    db.games.update_one = AsyncMock(side_effect=mock_game_update_one)

    with patch("app.api.routers.admin.get_db", return_value=db), \
         patch("app.api.routers.games.get_db", return_value=db), \
         patch("app.api.routers.admin.GameRepository") as mock_admin_game_repo, \
         patch("app.api.routers.games.GameRepository") as mock_games_game_repo, \
         patch("app.api.routers.admin.ParticipantRepository") as mock_admin_part_repo, \
         patch("app.api.routers.games.ParticipantRepository") as mock_games_part_repo, \
         patch("app.api.routers.admin.PaymentRepository") as mock_admin_pay_repo, \
         patch("app.api.routers.games.PaymentRepository") as mock_games_pay_repo, \
         patch("app.api.routers.admin.SettingsRepository") as mock_admin_settings_repo, \
         patch("app.api.routers.games.SettingsRepository") as mock_games_settings_repo, \
         patch("app.api.routers.admin.update_game_message", new_callable=AsyncMock), \
         patch("app.api.routers.games.update_game_message", new_callable=AsyncMock):

        # Setup GameRepository mock
        game_repo = MagicMock()
        game_repo.get = AsyncMock(side_effect=mock_game_get)
        game_repo.get_by_id = AsyncMock(side_effect=mock_game_get)
        game_repo.set_status = AsyncMock(side_effect=mock_game_set_status)
        mock_admin_game_repo.return_value = game_repo
        mock_games_game_repo.return_value = game_repo

        # Setup ParticipantRepository mock
        part_repo = MagicMock()
        part_repo.get = AsyncMock(side_effect=lambda pid: next((x for x in participants_state if str(x["_id"]) == str(pid)), None))
        part_repo.count_confirmed = AsyncMock(side_effect=lambda gid: len([p for p in participants_state if p["status"] == "confirmed"]))
        part_repo.list_by_game = AsyncMock(return_value=participants_state)

        async def mock_add_guest(game, display_name, added_by_telegram_id, status="confirmed"):
            guest_doc = {
                "_id": guest_id,
                "game_id": ObjectId(game_id),
                "telegram_id": None,
                "display_name": display_name,
                "type": "guest",
                "status": status,
                "position": 4,
                "added_by_telegram_id": added_by_telegram_id,
            }
            participants_state.append(guest_doc)
            return guest_doc

        part_repo.add_guest = AsyncMock(side_effect=mock_add_guest)
        mock_admin_part_repo.return_value = part_repo
        mock_games_part_repo.return_value = part_repo

        # Setup PaymentRepository mock
        pay_repo = MagicMock()
        async def mock_ensure(gid, amount):
            for p in participants_state:
                if p["status"] == "confirmed":
                    payments_state[str(p["_id"])] = {"participant_id": p["_id"], "amount": amount, "status": "pending"}
        pay_repo.ensure_for_game = AsyncMock(side_effect=mock_ensure)

        async def mock_mark_by_participant(game_id, participant_id, status, actor_telegram_id, is_admin=False):
            # Find participant
            p = next((x for x in participants_state if str(x["_id"]) == str(participant_id)), None)
            if not p:
                return False
            if p["type"] == "friend" and not is_admin:
                if p.get("added_by_telegram_id") != actor_telegram_id:
                    return False
            elif p["type"] == "player" and not is_admin:
                if p.get("telegram_id") != actor_telegram_id:
                    return False
            elif p["type"] == "guest" and not is_admin:
                return False

            if str(participant_id) in payments_state:
                payments_state[str(participant_id)]["status"] = status
            else:
                payments_state[str(participant_id)] = {"participant_id": ObjectId(participant_id), "status": status}
            return True

        pay_repo.mark_by_participant_id = AsyncMock(side_effect=mock_mark_by_participant)
        pay_repo.list_by_game = AsyncMock(side_effect=lambda gid: list(payments_state.values()))
        mock_admin_pay_repo.return_value = pay_repo
        mock_games_pay_repo.return_value = pay_repo

        # Setup SettingsRepository mock
        settings_repo = MagicMock()
        settings_repo.get_default_payment_details = AsyncMock(return_value={"card_number": "4441 0000 1111 2222", "recipient": "Олег О."})
        settings_repo.set_default_payment_details = AsyncMock()
        mock_admin_settings_repo.return_value = settings_repo
        mock_games_settings_repo.return_value = settings_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Start game via Admin endpoint -> game_started
            res_start = await client.post(
                f"/api/admin/games/{game_id}/start",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res_start.status_code == 200
            assert game_state["status"] == "game_started"

            # 2. Regular player tries to join during game_started -> 400
            res_join = await client.post(
                f"/api/games/{game_id}/join",
                headers={"Authorization": f"Bearer {player_a_token}"},
            )
            assert res_join.status_code == 400

            # 3. Regular player tries to leave during game_started -> 400
            res_leave = await client.post(
                f"/api/games/{game_id}/leave",
                headers={"Authorization": f"Bearer {player_a_token}"},
            )
            assert res_leave.status_code == 400

            # 4. Admin adds unregistered walk-in guest D
            res_guest = await client.post(
                f"/api/admin/games/{game_id}/participants/guest",
                json={"display_name": "GuestD"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res_guest.status_code == 200
            assert res_guest.json()["type"] == "guest"
            assert len([p for p in participants_state if p["status"] == "confirmed"]) == 4

            # 5. Admin starts payment collection for 90 minutes with custom card
            res_pay = await client.post(
                f"/api/admin/games/{game_id}/payment/start",
                json={
                    "duration_minutes": 90,
                    "card_number": "4441 0000 1111 2222",
                    "card_recipient": "Олег О.",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res_pay.status_code == 200
            assert game_state["status"] == "payment_collection"
            # 90 min at 600 грн/час = 900 грн / 4 игрока = 225 грн/чел
            assert game_state["total_cost"] == 900
            assert game_state["price"] == 225
            assert game_state["payment_details"]["card_number"] == "4441 0000 1111 2222"

            # 6. Player A pays for Friend C -> OK
            res_friend_pay = await client.post(
                f"/api/games/{game_id}/payment/status",
                json={"participant_id": str(friend_id), "status": "paid"},
                headers={"Authorization": f"Bearer {player_a_token}"},
            )
            assert res_friend_pay.status_code == 200
            assert payments_state[str(friend_id)]["status"] == "paid"

            # 7. Player B tries to pay/mark Player A's Friend C -> 403 Forbidden
            res_bad_pay = await client.post(
                f"/api/games/{game_id}/payment/status",
                json={"participant_id": str(friend_id), "status": "not_played"},
                headers={"Authorization": f"Bearer {player_b_token}"},
            )
            assert res_bad_pay.status_code == 403

            # 8. Admin marks Guest D as paid
            res_guest_pay = await client.patch(
                f"/api/admin/games/{game_id}/participants/{str(guest_id)}",
                json={"payment_status": "paid"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert res_guest_pay.status_code == 200

            # 9. Telegram render check: contains monospaced card number and card recipient
            render_text = format_game_message(game_state, participants_state, list(payments_state.values()))
            assert "<code>4441 0000 1111 2222</code>" in render_text
            assert "Олег О." in render_text
            assert "225 грн" in render_text
