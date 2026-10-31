import math
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, List
from bson import ObjectId

from app.db.mongo import get_db
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository
from app.repositories.payments import PaymentRepository
from app.repositories.chats import ChatRepository
from app.api.dependencies import require_admin
from app.api.sync import trigger_sync
from app.bot.bot_instance import get_bot

# For patching in tests
from app.bot.handlers import update_game_message

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


class CreateGameRequest(BaseModel):
    title: str = "⚽ Футбол 5х5"
    start_at: datetime
    max_players: int = 15
    hourly_rate: int = 600
    duration_minutes: int = 90
    friends_open_after_hours: int = 6


class EditGameRequest(BaseModel):
    title: Optional[str] = None
    start_at: Optional[datetime] = None
    max_players: Optional[int] = None
    hourly_rate: Optional[int] = None
    duration_minutes: Optional[int] = None
    friends_open_after_hours: Optional[int] = None


class CancelGameRequest(BaseModel):
    reason: Optional[str] = "Игра отменена организатором"


class ToggleFriendsRequest(BaseModel):
    allowed: bool


class StartPaymentRequest(BaseModel):
    duration_minutes: int = 90


class ParticipantStatusRequest(BaseModel):
    status: Optional[str] = None  # "confirmed", "reserve", "removed"
    payment_status: Optional[str] = None  # "paid", "not_played", "pending"


class PublishGameRequest(BaseModel):
    chat_ids: List[int]


@router.post("/games")
async def create_game(
    req: CreateGameRequest,
    admin_user: dict = Depends(require_admin),
):
    db = get_db()
    game_repo = GameRepository(db)

    teams_count = 3
    players_per_team = 5
    if req.max_players != 15:
        teams_count = max(2, req.max_players // 5)
        players_per_team = req.max_players // teams_count

    game = await game_repo.create_game(
        title=req.title,
        start_at=req.start_at,
        created_by=admin_user["telegram_id"],
        teams_count=teams_count,
        players_per_team=players_per_team,
        max_players=req.max_players,
        duration_minutes=req.duration_minutes,
        friends_open_after_hours=req.friends_open_after_hours,
        hourly_rate=req.hourly_rate,
    )
    return {"id": str(game["_id"]), "status": "created"}


@router.patch("/games/{game_id}")
async def edit_game(
    game_id: str,
    req: EditGameRequest,
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    update_fields = {}
    if req.title is not None:
        update_fields["title"] = req.title
    if req.start_at is not None:
        update_fields["start_at"] = req.start_at
    if req.hourly_rate is not None:
        update_fields["hourly_rate"] = req.hourly_rate
    if req.duration_minutes is not None:
        update_fields["duration_minutes"] = req.duration_minutes
    if req.friends_open_after_hours is not None:
        update_fields["friends_open_after_hours"] = req.friends_open_after_hours
    if req.max_players is not None:
        update_fields["max_players"] = req.max_players

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc)
        await db.games.update_one({"_id": ObjectId(game_id)}, {"$set": update_fields})
        trigger_sync(game_id)

    return {"status": "updated"}


@router.post("/games/{game_id}/cancel")
async def cancel_game(
    game_id: str,
    req: CancelGameRequest,
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    await game_repo.cancel_game(game_id, reason=req.reason)
    trigger_sync(game_id)

    return {"status": "cancelled"}


@router.post("/games/{game_id}/friends/toggle")
async def toggle_friends(
    game_id: str,
    req: ToggleFriendsRequest,
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    db = get_db()
    game_repo = GameRepository(db)
    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if req.allowed:
        await game_repo.open_friends(game_id)
    else:
        await game_repo.close_friends(game_id)

    trigger_sync(game_id)
    return {"friends_allowed": req.allowed}


@router.post("/games/{game_id}/payment/start")
async def start_payment(
    game_id: str,
    req: StartPaymentRequest,
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

    minutes = req.duration_minutes
    hourly_rate = game.get("hourly_rate", 600)
    total_cost = int((minutes / 60) * hourly_rate)

    confirmed_count = await part_repo.count_confirmed(game_id)
    per_player = math.ceil(total_cost / confirmed_count) if confirmed_count > 0 else 0

    await db.games.update_one(
        {"_id": ObjectId(game_id)},
        {"$set": {
            "status": "payment_collection",
            "duration_minutes": minutes,
            "total_cost": total_cost,
            "price": per_player,
            "updated_at": datetime.now(timezone.utc),
        }}
    )
    await pay_repo.ensure_for_game(game_id, per_player)
    trigger_sync(game_id)

    return {
        "status": "payment_collection",
        "duration_minutes": minutes,
        "total_cost": total_cost,
        "price_per_player": per_player,
        "confirmed_count": confirmed_count,
    }


@router.patch("/games/{game_id}/participants/{participant_id}")
async def update_participant_status(
    game_id: str,
    participant_id: str,
    req: ParticipantStatusRequest,
    admin_user: dict = Depends(require_admin),
):
    try:
        ObjectId(game_id)
        ObjectId(participant_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    db = get_db()
    part_repo = ParticipantRepository(db)
    pay_repo = PaymentRepository(db)

    part = await part_repo.get(participant_id)
    if not part or str(part.get("game_id")) != game_id:
        raise HTTPException(status_code=404, detail="Participant not found")

    if req.status:
        if req.status not in {"confirmed", "reserve", "removed"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        await db.participants.update_one(
            {"_id": ObjectId(participant_id)},
            {"$set": {"status": req.status, "updated_at": datetime.now(timezone.utc)}}
        )
        game = await db.games.find_one({"_id": ObjectId(game_id)})
        if game:
            await part_repo.normalize_roster(game_id, game.get("max_players", 15))

    if req.payment_status:
        await pay_repo.mark_by_participant_id(
            game_id=game_id,
            participant_id=participant_id,
            status=req.payment_status,
            actor_telegram_id=admin_user["telegram_id"],
            is_admin=True,
        )

    trigger_sync(game_id)
    return {"status": "updated"}


@router.get("/chats")
async def list_chats():
    db = get_db()
    chat_repo = ChatRepository(db)
    chats = await chat_repo.list_active_chats()
    return [
        {"chat_id": c["chat_id"], "title": c["title"], "type": c.get("type", "group")}
        for c in chats
    ]


@router.post("/games/{game_id}/publish")
async def publish_game(
    game_id: str,
    req: PublishGameRequest,
):
    try:
        ObjectId(game_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid game_id")

    bot = get_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Telegram bot is not connected")

    db = get_db()
    game_repo = GameRepository(db)
    chat_repo = ChatRepository(db)
    game = await game_repo.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    from app.services.render import format_game_message
    from app.bot.keyboards import game_keyboard
    from app.repositories.participants import ParticipantRepository
    from app.repositories.payments import PaymentRepository

    participants = await ParticipantRepository(db).list_by_game(game_id)
    payments = await PaymentRepository(db).list_by_game(game_id) if game.get("status") == "payment_collection" else []

    text = format_game_message(game, participants, payments)
    keyboard = game_keyboard(game_id, game.get("friends_allowed", False), game.get("status"))

    for chat_id in req.chat_ids:
        try:
            sent = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
            chat_doc = await db.chats.find_one({"chat_id": chat_id})
            chat_title = chat_doc.get("title", f"Чат {chat_id}") if chat_doc else f"Чат {chat_id}"
            await game_repo.add_linked_message(game_id, chat_id, sent.message_id, chat_title)
        except Exception:
            pass

    return {"status": "published"}
