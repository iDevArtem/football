from datetime import datetime, timezone
from bson import ObjectId


class PaymentRepository:
    def __init__(self, db):
        self.db = db

    async def ensure_for_game(self, game_id: str, amount: int, excluded_participant_ids: set[str] | list[str] | None = None) -> None:
        excluded = set(str(pid) for pid in (excluded_participant_ids or []))
        cursor = self.db.participants.find({"game_id": ObjectId(game_id), "status": "confirmed"})
        now = datetime.now(timezone.utc)
        async for participant in cursor:
            pid = participant["_id"]
            is_excluded = str(pid) in excluded
            existing = await self.db.payments.find_one({"game_id": ObjectId(game_id), "participant_id": pid})
            if is_excluded:
                await self.db.payments.update_one(
                    {"game_id": ObjectId(game_id), "participant_id": pid},
                    {
                        "$set": {
                            "amount": 0,
                            "status": "not_played",
                            "confirmed_by_admin": True,
                            "updated_at": now,
                        },
                        "$setOnInsert": {
                            "game_id": ObjectId(game_id),
                            "participant_id": pid,
                            "confirmed_by_user": False,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
            else:
                set_fields = {
                    "amount": amount,
                    "updated_at": now,
                }
                if not existing or existing.get("status") != "paid":
                    set_fields["status"] = "pending"
                    set_fields["confirmed_by_admin"] = False
                await self.db.payments.update_one(
                    {"game_id": ObjectId(game_id), "participant_id": pid},
                    {
                        "$set": set_fields,
                        "$setOnInsert": {
                            "game_id": ObjectId(game_id),
                            "participant_id": pid,
                            "confirmed_by_user": False,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )

    async def mark_paid_by_user(self, game_id: str, telegram_id: int) -> bool:
        participant = await self.db.participants.find_one({
            "game_id": ObjectId(game_id),
            "telegram_id": telegram_id,
            "type": "player",
            "status": "confirmed",
        })
        if not participant:
            return False
        result = await self.db.payments.update_one(
            {"game_id": ObjectId(game_id), "participant_id": participant["_id"]},
            {"$set": {
                "status": "paid",
                "confirmed_by_user": True,
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )
        # matched_count важнее modified_count: если игрок уже был paid, документ не изменится,
        # но это все равно валидное нажатие кнопки.
        return result.matched_count > 0


    async def mark_not_played_by_user(self, game_id: str, telegram_id: int) -> bool:
        participant = await self.db.participants.find_one({
            "game_id": ObjectId(game_id),
            "telegram_id": telegram_id,
            "type": "player",
            "status": "confirmed",
        })
        if not participant:
            return False
        result = await self.db.payments.update_one(
            {"game_id": ObjectId(game_id), "participant_id": participant["_id"]},
            {"$set": {
                "status": "not_played",
                "confirmed_by_user": True,
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )
        return result.matched_count > 0


    async def mark_by_participant_id(self, game_id: str, participant_id: str, status: str, actor_telegram_id: int, is_admin: bool = False) -> bool:
        if status not in {"paid", "not_played", "pending"}:
            return False
        participant = await self.db.participants.find_one({
            "_id": ObjectId(participant_id),
            "game_id": ObjectId(game_id),
            "status": "confirmed",
        })
        if not participant:
            return False
        if participant.get("type") == "friend" and not is_admin:
            if participant.get("added_by_telegram_id") != actor_telegram_id:
                return False
        elif participant.get("type") == "player" and not is_admin:
            if participant.get("telegram_id") != actor_telegram_id:
                return False
        result = await self.db.payments.update_one(
            {"game_id": ObjectId(game_id), "participant_id": participant["_id"]},
            {"$set": {
                "status": status,
                "confirmed_by_user": not is_admin,
                "confirmed_by_admin": is_admin,
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=False,
        )
        return result.matched_count > 0

    async def list_by_game(self, game_id: str) -> list[dict]:
        pipeline = [
            {"$match": {"game_id": ObjectId(game_id)}},
            {"$lookup": {"from": "participants", "localField": "participant_id", "foreignField": "_id", "as": "participant"}},
            {"$unwind": "$participant"},
            {"$sort": {"participant.position": 1}},
        ]
        cursor = await self.db.payments.aggregate(pipeline)
        return [doc async for doc in cursor]
