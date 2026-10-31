from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from bson import ObjectId

from app.config.settings import get_settings, Settings
from app.db.mongo import get_db
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository
from app.repositories.payments import PaymentRepository
from app.api.dependencies import get_current_user, get_optional_user
from app.api.sync import trigger_sync
from app.services.render import dynamic_format_text, status_text

# For patching in tests
from app.bot.handlers import update_game_message

router = APIRouter(tags=["games"])


class UserProxy:
    def __init__(self, telegram_id: int, first_name: str, username: str | None = None):
        self.id = telegram_id
        self.first_name = first_name
        self.username = username
        self.full_name = first_name


class FriendRequest(BaseModel):
    friend_name: str


class PaymentStatusRequest(BaseModel):
    participant_id: Optional[str] = None
    status: str  # "paid" or "not_played"


def serialize_game(game: dict, confirmed_count: int, reserve_count: int = 0) -> dict:
    g_id = str(game["_id"])
    return {
        "id": g_id,
        "title": game.get("title", "⚽ Футбол 5х5"),
        "start_at": game.get("start_at"),
        "status": game.get("status", "registration_open"),
        "status_label": status_text(game.get("status", "registration_open")),
        "max_players": game.get("max_players", 15),
        "confirmed_count": confirmed_count,
        "reserve_count": reserve_count,
        "format_description": dynamic_format_text(confirmed_count, game.get("max_players", 15)),
        "friends_allowed": bool(game.get("friends_allowed", False)),
        "friends_allowed_after": game.get("friends_allowed_after"),
        "duration_minutes": game.get("duration_minutes", 90),
        "hourly_rate": game.get("hourly_rate", 600),
        "price": game.get("price", 0),
        "total_cost": game.get("total_cost"),
        "cancel_reason": game.get("cancel_reason"),
        "linked_chats": [
            {"chat_id": m.get("chat_id"), "title": m.get("chat_title", "Чат")}
            for m in game.get("messages", [])
        ],
    }


def serialize_participant(p: dict, payment: dict | None = None) -> dict:
    return {
        "id": str(p["_id"]),
        "telegram_id": p.get("telegram_id"),
        "display_name": p.get("display_name", ""),
        "type": p.get("type", "player"),
        "status": p.get("status", "confirmed"),
        "position": p.get("position", 0),
        "added_by_telegram_id": p.get("added_by_telegram_id"),
        "payment_status": payment.get("status", "unpaid") if payment else "unpaid",
        "payment_amount": payment.get("amount") if payment else None,
        "confirmed_by_user": payment.get("confirmed_by_user", False) if payment else False,
        "confirmed_by_admin": payment.get("confirmed_by_admin", False) if payment else False,
    }


@router.get("")
async def list_games():
    db = get_db()
    game_repo = GameRepository(db)
    part_repo = ParticipantRepository(db)

    games = await game_repo.list_active_games()
    result = []
    for g in games:
        g_id = str(g["_id"])
        confirmed = await part_repo.count_confirmed(g_id)
        parts = await part_repo.list_by_game(g_id)
        reserve = sum(1 for p in parts if p.get("status") == "reserve")
        result.append(serialize_game(g, confirmed, reserve))
    return result


@router.get("/{game_id}")
async def get_game_detail(
    game_id: str,
    settings: Settings = Depends(get_settings),
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    db = get_db()
    game_repo = GameRepository(db)
    part_repo = ParticipantRepository(db)
    pay_repo = PaymentRepository(db)

    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    participants = await part_repo.list_by_game(game_id)
    payments = await pay_repo.list_by_game(game_id) if game.get("status") == "payment_collection" else []
    pay_map = {str(p["participant_id"]): p for p in payments}

    confirmed_count = sum(1 for p in participants if p.get("status") == "confirmed")
    reserve_count = sum(1 for p in participants if p.get("status") == "reserve")

    serialized = serialize_game(game, confirmed_count, reserve_count)
    serialized["participants"] = [
        serialize_participant(p, pay_map.get(str(p["_id"])))
        for p in participants
    ]
    serialized["payment_details"] = {
        "card_number": settings.card_number,
        "recipient": settings.card_recipient,
    }
    return serialized


@router.post("/{game_id}/join")
async def join_game(
    game_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    db = get_db()
    game_repo = GameRepository(db)
    part_repo = ParticipantRepository(db)

    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.get("status") in {"cancelled", "closed"}:
        raise HTTPException(status_code=400, detail="Game is closed or cancelled")

    tg_user = UserProxy(
        telegram_id=user["telegram_id"],
        first_name=user.get("first_name", ""),
        username=user.get("username"),
    )

    participant = await part_repo.join_player(game, tg_user)
    trigger_sync(game_id)

    return {
        "status": participant["status"],
        "position": participant.get("position"),
        "display_name": participant.get("display_name"),
    }


@router.post("/{game_id}/leave")
async def leave_game(
    game_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    db = get_db()
    game_repo = GameRepository(db)
    part_repo = ParticipantRepository(db)

    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    tg_user = UserProxy(
        telegram_id=user["telegram_id"],
        first_name=user.get("first_name", ""),
        username=user.get("username"),
    )

    await part_repo.decline_player(game_id, tg_user)
    trigger_sync(game_id)

    return {"status": "declined"}


@router.post("/{game_id}/friends")
async def add_friend(
    game_id: str,
    req: FriendRequest,
    user: dict = Depends(get_current_user),
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    if not req.friend_name.strip():
        raise HTTPException(status_code=400, detail="Friend name cannot be empty")

    db = get_db()
    game_repo = GameRepository(db)
    part_repo = ParticipantRepository(db)

    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if not game.get("friends_allowed"):
        raise HTTPException(status_code=400, detail="Friends registration is not allowed yet")

    # Friends limit: max 3 per user
    count = await part_repo.count_friends_by_user(game_id, user["telegram_id"])
    if count >= 3:
        raise HTTPException(status_code=400, detail="Maximum 3 friends allowed per participant")

    friend = await part_repo.add_friend(game, user["telegram_id"], req.friend_name)
    trigger_sync(game_id)

    return serialize_participant(friend)


@router.delete("/{game_id}/friends/{participant_id}")
async def remove_friend(
    game_id: str,
    participant_id: str,
    user: dict = Depends(get_current_user),
):
    try:
        ObjectId(game_id)
        ObjectId(participant_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    db = get_db()
    part_repo = ParticipantRepository(db)

    success = await part_repo.cancel_friend(game_id, participant_id, user["telegram_id"])
    if not success:
        raise HTTPException(status_code=404, detail="Friend participant not found or not owned by user")

    trigger_sync(game_id)
    return {"status": "removed"}


@router.post("/{game_id}/payment/status")
async def update_payment_status(
    game_id: str,
    req: PaymentStatusRequest,
    user: dict = Depends(get_current_user),
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    db = get_db()
    pay_repo = PaymentRepository(db)

    if req.status not in {"paid", "not_played"}:
        raise HTTPException(status_code=400, detail="Invalid status: must be 'paid' or 'not_played'")

    # If participant_id specified (for friend or specific participant)
    if req.participant_id:
        success = await pay_repo.mark_by_participant_id(
            game_id=game_id,
            participant_id=req.participant_id,
            status=req.status,
            actor_telegram_id=user["telegram_id"],
            is_admin=user.get("role") == "admin",
        )
        if not success:
            raise HTTPException(status_code=403, detail="Not authorized or participant not found")
    else:
        # Mark for user himself
        if req.status == "paid":
            await pay_repo.mark_paid_by_user(game_id, user["telegram_id"])
        else:
            await pay_repo.mark_not_played_by_user(game_id, user["telegram_id"])

    trigger_sync(game_id)
    return {"status": req.status}
