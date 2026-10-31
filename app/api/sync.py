import asyncio
from app.bot.bot_instance import get_bot
from app.db.mongo import get_db
from app.repositories.games import GameRepository


async def sync_game_message(game_id: str) -> None:
    bot = get_bot()
    if not bot:
        return
    try:
        from app.bot.handlers import update_game_message
        db = get_db()
        game = await GameRepository(db).get(game_id)
        if game:
            await update_game_message(bot, game)
    except Exception:
        pass


def trigger_sync(game_id: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(sync_game_message(game_id))
    except RuntimeError:
        pass
