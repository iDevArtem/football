from pymongo import AsyncMongoClient
from app.config.settings import get_settings

_client: AsyncMongoClient | None = None
_db = None


async def init_mongo():
    global _client, _db
    settings = get_settings()
    _client = AsyncMongoClient(
        settings.mongo_url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    try:
        default_db = _client.get_default_database()
        if default_db is not None and default_db.name not in ("admin", "local", "config"):
            _db = default_db
        else:
            _db = _client[settings.mongo_db_name]
    except Exception:
        _db = _client[settings.mongo_db_name]
    await create_indexes(_db)
    return _db


def get_db():
    if _db is None:
        raise RuntimeError("MongoDB is not initialized")
    return _db


async def close_mongo() -> None:
    global _client, _db
    if _client is not None:
        await _client.close()
    _client = None
    _db = None


async def create_indexes(db) -> None:
    await db.users.create_index("telegram_id", unique=True)
    await db.chats.create_index("chat_id", unique=True)
    await db.games.create_index([("messages.chat_id", 1), ("status", 1)])
    await db.games.create_index("start_at")
    await db.participants.create_index(
        [("game_id", 1), ("telegram_id", 1)],
        unique=True,
        partialFilterExpression={"type": "player", "telegram_id": {"$type": "number"}},
    )
    await db.participants.create_index([("game_id", 1), ("position", 1)])
    await db.participants.create_index([("game_id", 1), ("added_by_telegram_id", 1), ("type", 1)])
    await db.payments.create_index([("game_id", 1), ("participant_id", 1)], unique=True)
