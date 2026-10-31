from datetime import datetime, timezone
from bson import ObjectId


class ParticipantRepository:
    def __init__(self, db):
        self.db = db

    async def list_by_game(self, game_id: str) -> list[dict]:
        cursor = self.db.participants.find({
            "game_id": ObjectId(game_id),
            "status": {"$ne": "removed"},
        }).sort("position", 1)
        return [doc async for doc in cursor]

    async def count_confirmed(self, game_id: str) -> int:
        return await self.db.participants.count_documents({"game_id": ObjectId(game_id), "status": "confirmed"})

    async def count_friends_by_user(self, game_id: str, telegram_id: int) -> int:
        return await self.db.participants.count_documents({
            "game_id": ObjectId(game_id),
            "type": "friend",
            "added_by_telegram_id": telegram_id,
            "status": {"$in": ["confirmed", "reserve"]},
        })

    async def list_friends_by_user(self, game_id: str, telegram_id: int) -> list[dict]:
        cursor = self.db.participants.find({
            "game_id": ObjectId(game_id),
            "type": "friend",
            "added_by_telegram_id": telegram_id,
            "status": {"$in": ["confirmed", "reserve"]},
        }).sort("position", 1)
        return [doc async for doc in cursor]

    async def next_position(self, game_id: str) -> int:
        last = await self.db.participants.find_one({"game_id": ObjectId(game_id)}, sort=[("position", -1)])
        return int(last["position"]) + 1 if last else 1

    async def join_player(self, game: dict, tg_user) -> dict:
        game_id = str(game["_id"])
        current = await self.count_confirmed(game_id)
        status = "confirmed" if current < game["max_players"] else "reserve"
        now = datetime.now(timezone.utc)
        display_name = tg_user.full_name or tg_user.username or str(tg_user.id)
        query = {"game_id": game["_id"], "telegram_id": tg_user.id, "type": "player"}
        existing = await self.db.participants.find_one(query)

        # Нельзя одновременно писать одно поле через $set и $setOnInsert.
        # Поэтому insert/update разделены явно.
        if existing:
            update_doc = {
                "status": status,
                "display_name": display_name,
                "added_by_telegram_id": None,
                "updated_at": now,
            }
            # Если игрок раньше отказался/был удален и снова нажал «Буду»,
            # ставим его в конец очереди. Повторный клик уже записанного игрока
            # позицию не меняет.
            if existing.get("status") not in ("confirmed", "reserve"):
                update_doc["position"] = await self.next_position(game_id)
            await self.db.participants.update_one(query, {"$set": update_doc})
        else:
            doc = {
                "game_id": game["_id"],
                "telegram_id": tg_user.id,
                "type": "player",
                "status": status,
                "added_by_telegram_id": None,
                "display_name": display_name,
                "position": await self.next_position(game_id),
                "created_at": now,
                "updated_at": now,
            }
            await self.db.participants.insert_one(doc)

        await self.normalize_roster(game_id, game["max_players"])
        return await self.db.participants.find_one(query)

    async def decline_player(self, game_id: str, tg_user) -> None:
        now = datetime.now(timezone.utc)
        await self.db.participants.update_one(
            {"game_id": ObjectId(game_id), "telegram_id": tg_user.id, "type": "player"},
            {"$set": {"status": "declined", "updated_at": now}},
            upsert=False,
        )
        game = await self.db.games.find_one({"_id": ObjectId(game_id)})
        if game:
            await self.normalize_roster(game_id, game["max_players"])

    async def add_friend(self, game: dict, added_by_telegram_id: int, friend_name: str) -> dict:
        game_id = str(game["_id"])
        current = await self.count_confirmed(game_id)
        status = "confirmed" if current < game["max_players"] else "reserve"
        now = datetime.now(timezone.utc)
        doc = {
            "game_id": game["_id"],
            "telegram_id": None,
            "type": "friend",
            "status": status,
            "added_by_telegram_id": added_by_telegram_id,
            "display_name": friend_name.strip(),
            "position": await self.next_position(game_id),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.participants.insert_one(doc)
        doc["_id"] = result.inserted_id
        await self.normalize_roster(game_id, game["max_players"])
        return await self.db.participants.find_one({"_id": result.inserted_id})

    async def cancel_friend(self, game_id: str, friend_id: str, added_by_telegram_id: int) -> bool:
        result = await self.db.participants.update_one(
            {
                "_id": ObjectId(friend_id),
                "game_id": ObjectId(game_id),
                "type": "friend",
                "added_by_telegram_id": added_by_telegram_id,
                "status": {"$in": ["confirmed", "reserve"]},
            },
            {"$set": {"status": "removed", "updated_at": datetime.now(timezone.utc)}},
        )
        if result.modified_count:
            game = await self.db.games.find_one({"_id": ObjectId(game_id)})
            if game:
                await self.normalize_roster(game_id, game["max_players"])
            return True
        return False

    async def normalize_roster(self, game_id: str, max_players: int) -> None:
        """Первые max_players активных участников становятся confirmed, остальные reserve."""
        cursor = self.db.participants.find({
            "game_id": ObjectId(game_id),
            "status": {"$in": ["confirmed", "reserve"]},
        }).sort("position", 1)
        active = [doc async for doc in cursor]
        now = datetime.now(timezone.utc)
        for index, participant in enumerate(active):
            new_status = "confirmed" if index < max_players else "reserve"
            if participant.get("status") != new_status:
                await self.db.participants.update_one(
                    {"_id": participant["_id"]},
                    {"$set": {"status": new_status, "updated_at": now}},
                )

    async def promote_from_reserve(self, game_id: str) -> dict | None:
        game = await self.db.games.find_one({"_id": ObjectId(game_id)})
        if not game:
            return None
        await self.normalize_roster(game_id, game["max_players"])
        return await self.db.participants.find_one({"game_id": ObjectId(game_id), "status": "confirmed"}, sort=[("position", -1)])
