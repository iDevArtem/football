from datetime import datetime, timezone


class UserRepository:
    def __init__(self, db):
        self.db = db

    async def upsert_from_telegram(self, tg_user, is_admin: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        doc = {
            "telegram_id": tg_user.id,
            "username": tg_user.username,
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name,
            "role": "admin" if is_admin else "player",
            "is_active": True,
            "updated_at": now,
        }
        await self.db.users.update_one(
            {"telegram_id": tg_user.id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return await self.db.users.find_one({"telegram_id": tg_user.id})
