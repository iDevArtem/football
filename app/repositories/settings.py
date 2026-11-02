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

    async def get_default_location(self) -> dict | None:
        res = self.db.settings.find_one({"_id": "default_location"})
        if hasattr(res, "__await__"):
            doc = await res
        elif isinstance(res, dict):
            doc = res
        else:
            doc = None

        if doc and isinstance(doc, dict) and doc.get("latitude") is not None and doc.get("longitude") is not None:
            return {
                "title": doc.get("title", ""),
                "address": doc.get("address", ""),
                "latitude": float(doc["latitude"]),
                "longitude": float(doc["longitude"]),
            }
        return None

    async def set_default_location(self, *, title: str, address: str, latitude: float, longitude: float) -> None:
        await self.db.settings.update_one(
            {"_id": "default_location"},
            {
                "$set": {
                    "title": title.strip(),
                    "address": address.strip(),
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
