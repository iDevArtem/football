from datetime import datetime, timezone


class ChatRepository:
    def __init__(self, db):
        self.db = db

    async def upsert_chat(self, chat_id: int, title: str, chat_type: str) -> dict:
        now = datetime.now(timezone.utc)
        doc = {
            "chat_id": chat_id,
            "title": title,
            "type": chat_type,
            "is_active": True,
            "updated_at": now,
        }
        await self.db.chats.update_one(
            {"chat_id": chat_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return doc

    async def list_active_chats(self) -> list[dict]:
        cursor = self.db.chats.find({"is_active": True}).sort("title", 1)
        return [doc async for doc in cursor]

    async def set_active_status(self, chat_id: int, is_active: bool) -> None:
        await self.db.chats.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "is_active": is_active,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
