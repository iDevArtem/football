from datetime import datetime, timezone
from app.config.settings import get_settings


class SettingsRepository:
    def __init__(self, db):
        self.db = db

    async def get_default_payment_details(self) -> dict:
        doc = await self.db.settings.find_one({"_id": "default_payment_details"})
        if doc and doc.get("card_number"):
            return {
                "card_number": doc.get("card_number", ""),
                "recipient": doc.get("recipient", ""),
            }
        settings = get_settings()
        return {
            "card_number": settings.card_number,
            "recipient": settings.card_recipient,
        }

    async def set_default_payment_details(self, card_number: str, recipient: str) -> None:
        await self.db.settings.update_one(
            {"_id": "default_payment_details"},
            {
                "$set": {
                    "card_number": card_number.strip(),
                    "recipient": recipient.strip(),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
