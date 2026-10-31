from datetime import datetime, timezone
from bson import ObjectId


ACTIVE_STATUSES = [
    "registration_open",
    "registration_closed",
    "friends_allowed",
    "full",
    "payment_collection",
]


class GameRepository:
    def __init__(self, db):
        self.db = db

    async def create_game(self, *, chat_id: int, title: str, start_at: datetime, teams_count: int,
                          players_per_team: int, price: int, created_by: int) -> dict:
        max_players = teams_count * players_per_team
        friends_after = start_at.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        doc = {
            "chat_id": chat_id,
            "message_id": None,
            "title": title,
            "start_at": start_at,
            "teams_count": teams_count,
            "players_per_team": players_per_team,
            "max_players": max_players,
            "price": price,
            "status": "registration_open",
            "friends_allowed": False,
            "friends_allowed_after": friends_after,
            "created_by": created_by,
            "cancel_reason": None,
            "closed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.games.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def set_message_id(self, game_id: str, message_id: int) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"message_id": message_id, "updated_at": datetime.now(timezone.utc)}}
        )

    async def get(self, game_id: str) -> dict | None:
        return await self.db.games.find_one({"_id": ObjectId(game_id)})

    async def get_active_for_chat(self, chat_id: int) -> dict | None:
        return await self.db.games.find_one(
            {"chat_id": chat_id, "status": {"$in": ACTIVE_STATUSES}},
            sort=[("created_at", -1)],
        )

    async def get_manageable_for_chat(self, chat_id: int) -> dict | None:
        return await self.db.games.find_one(
            {"chat_id": chat_id, "status": {"$in": ACTIVE_STATUSES + ["cancelled"]}},
            sort=[("created_at", -1)],
        )

    async def open_friends(self, game_id: str) -> None:
        # Manual opening means friends can be added immediately, not only after friends_allowed_after.
        now = datetime.now(timezone.utc)
        await self.db.games.update_one(
            {"_id": ObjectId(game_id), "status": {"$nin": ["cancelled", "payment_collection", "closed"]}},
            {"$set": {
                "friends_allowed": True,
                "friends_allowed_after": now,
                "status": "friends_allowed",
                "updated_at": now,
            }},
        )

    async def close_friends(self, game_id: str) -> None:
        game = await self.get(game_id)
        if not game or game.get("status") in {"cancelled", "payment_collection", "closed"}:
            return
        now = datetime.now(timezone.utc)
        status = "registration_open" if game.get("status") == "friends_allowed" else game.get("status", "registration_open")
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "friends_allowed": False,
                "status": status,
                "updated_at": now,
            }},
        )

    async def set_status(self, game_id: str, status: str) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}},
        )

    async def cancel_game(self, game_id: str, reason: str | None = None) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "status": "cancelled",
                "cancel_reason": reason or "без причины",
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def close_registration(self, game_id: str) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id), "status": {"$nin": ["cancelled", "payment_collection"]}},
            {"$set": {
                "status": "registration_closed",
                "closed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def open_registration(self, game_id: str) -> None:
        game = await self.get(game_id)
        if not game or game.get("status") in {"payment_collection", "closed"}:
            return
        status = "friends_allowed" if game.get("friends_allowed") else "registration_open"
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "status": status,
                "cancel_reason": None,
                "closed_at": None,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def restore_game(self, game_id: str) -> None:
        await self.open_registration(game_id)

    async def update_start_at(self, game_id: str, start_at: datetime) -> None:
        friends_after = start_at.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "start_at": start_at,
                "friends_allowed_after": friends_after,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def update_price(self, game_id: str, price: int) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"price": price, "updated_at": datetime.now(timezone.utc)}},
        )

    async def update_format(self, game_id: str, *, teams_count: int | None = None, players_per_team: int | None = None) -> dict | None:
        game = await self.get(game_id)
        if not game:
            return None
        new_teams_count = teams_count if teams_count is not None else game["teams_count"]
        new_players_per_team = players_per_team if players_per_team is not None else game["players_per_team"]
        max_players = new_teams_count * new_players_per_team
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "teams_count": new_teams_count,
                "players_per_team": new_players_per_team,
                "max_players": max_players,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return await self.get(game_id)

    async def games_to_open_friends(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        cursor = self.db.games.find({
            "friends_allowed": False,
            "status": "registration_open",
            "friends_allowed_after": {"$lte": now},
        })
        return [doc async for doc in cursor]
