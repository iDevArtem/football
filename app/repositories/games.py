from datetime import datetime, timezone, timedelta
from bson import ObjectId


ACTIVE_STATUSES = [
    "registration_open",
    "registration_closed",
    "friends_allowed",
    "full",
    "game_started",
    "payment_collection",
]


class GameRepository:
    def __init__(self, db):
        self.db = db

    async def create_game(self, *, title: str, start_at: datetime, created_by: int,
                          teams_count: int = 3, players_per_team: int = 5,
                          price: int = 0, duration_minutes: int = 90,
                          friends_open_after_hours: int = 6,
                          hourly_rate: int = 600, max_players: int | None = None,
                          chat_id: int | None = None,
                          location: dict | None = None) -> dict:
        calculated_max = max_players if max_players is not None else (teams_count * players_per_team)
        now = datetime.now(timezone.utc)
        friends_after = now + timedelta(hours=friends_open_after_hours)
        doc = {
            "chat_id": chat_id,
            "message_id": None,
            "messages": [],
            "title": title,
            "start_at": start_at,
            "location": location,
            "teams_count": teams_count,
            "players_per_team": players_per_team,
            "max_players": calculated_max,
            "hourly_rate": hourly_rate,
            "price": price,
            "total_cost": None,
            "duration_minutes": duration_minutes,
            "friends_open_after_hours": friends_open_after_hours,
            "last_position": 0,
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

    async def add_linked_message(self, game_id: str, chat_id: int, message_id: int, chat_title: str, venue_message_id: int | None = None) -> None:
        now = datetime.now(timezone.utc)
        msg_entry = {
            "chat_id": chat_id,
            "message_id": message_id,
            "chat_title": chat_title,
            "added_at": now,
        }
        if venue_message_id is not None:
            msg_entry["venue_message_id"] = venue_message_id

        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {
                "$push": {
                    "messages": msg_entry
                },
                "$set": {"updated_at": now},
            }
        )

    async def update_location(self, game_id: str, location: dict | None) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"location": location, "updated_at": datetime.now(timezone.utc)}}
        )

    async def remove_linked_message(self, game_id: str, chat_id: int, message_id: int | None = None) -> None:
        pull_filter = {"chat_id": chat_id}
        if message_id is not None:
            pull_filter["message_id"] = message_id
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {
                "$pull": {"messages": pull_filter},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            }
        )

    async def set_message_id(self, game_id: str, message_id: int) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"message_id": message_id, "updated_at": datetime.now(timezone.utc)}}
        )

    async def get(self, game_id: str) -> dict | None:
        return await self.db.games.find_one({"_id": ObjectId(game_id)})

    async def get_active_for_chat(self, chat_id: int) -> dict | None:
        return await self.db.games.find_one(
            {"messages.chat_id": chat_id, "status": {"$in": ACTIVE_STATUSES}},
            sort=[("created_at", -1)],
        )

    async def get_manageable_for_chat(self, chat_id: int) -> dict | None:
        return await self.db.games.find_one(
            {"messages.chat_id": chat_id, "status": {"$in": ACTIVE_STATUSES + ["cancelled", "finished"]}},
            sort=[("created_at", -1)],
        )

    async def get_latest_manageable(self) -> dict | None:
        return await self.db.games.find_one(
            {"status": {"$in": ACTIVE_STATUSES + ["cancelled", "finished"]}},
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

    async def set_status(self, game_id: str, status: str) -> bool:
        res = await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}},
        )
        return bool(res.matched_count > 0)

    async def set_payment_details(self, game_id: str, card_number: str, recipient: str) -> bool:
        res = await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "payment_details": {
                    "card_number": card_number.strip(),
                    "recipient": recipient.strip(),
                },
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return bool(res.matched_count > 0)

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

    async def finish_game(
        self,
        game_id: str,
        finish_note: str | None = None,
        media_items: list[dict] | None = None,
        media_type: str | None = None,
        media_file_id: str | None = None,
    ) -> None:
        update_data = {
            "status": "finished",
            "updated_at": datetime.now(timezone.utc),
        }
        if finish_note is not None:
            update_data["finish_note"] = finish_note
        if media_items is not None:
            update_data["media_items"] = media_items
        elif media_type and media_file_id:
            update_data["media_items"] = [{"type": media_type, "file_id": media_file_id}]
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": update_data},
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
                "finish_note": None,
                "media_type": None,
                "media_file_id": None,
                "closed_at": None,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def restore_game(self, game_id: str) -> None:
        await self.open_registration(game_id)

    async def update_start_at(self, game_id: str, start_at: datetime) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "start_at": start_at,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def update_price(self, game_id: str, price: int) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"price": price, "updated_at": datetime.now(timezone.utc)}},
        )

    async def update_duration(self, game_id: str, duration_minutes: int) -> None:
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"duration_minutes": duration_minutes, "updated_at": datetime.now(timezone.utc)}},
        )

    async def update_friends_open_after_hours(self, game_id: str, hours: int) -> None:
        game = await self.get(game_id)
        if not game:
            return
        created_at = game.get("created_at") or datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        friends_after = created_at + timedelta(hours=hours)
        await self.db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {
                "friends_open_after_hours": hours,
                "friends_allowed_after": friends_after,
                "updated_at": datetime.now(timezone.utc),
            }},
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

    get_by_id = get

    async def list_active_games(self) -> list[dict]:
        cursor = self.db.games.find(
            {"status": {"$in": ACTIVE_STATUSES}}
        ).sort("start_at", -1)
        return [doc async for doc in cursor]

    async def games_to_open_friends(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        cursor = self.db.games.find({
            "friends_allowed": False,
            "status": "registration_open",
            "friends_allowed_after": {"$lte": now},
        })
        return [doc async for doc in cursor]

    async def games_to_auto_start(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        cursor = self.db.games.find({
            "status": {"$in": ["registration_open", "friends_allowed", "full", "registration_closed"]},
            "start_at": {"$lte": now},
        })
        return [doc async for doc in cursor]
