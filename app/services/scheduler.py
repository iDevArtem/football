from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db.mongo import get_db
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository
from app.bot.keyboards import game_keyboard
from app.services.render import format_game_message


async def open_friends_job(bot) -> None:
    db = get_db()
    game_repo = GameRepository(db)
    participant_repo = ParticipantRepository(db)
    games = await game_repo.games_to_open_friends()
    for game in games:
        participants = await participant_repo.list_by_game(str(game["_id"]))
        confirmed_count = len([p for p in participants if p["status"] == "confirmed"])
        if confirmed_count >= game["max_players"]:
            continue
        await game_repo.open_friends(str(game["_id"]))
        game = await game_repo.get(str(game["_id"]))
        from app.bot.handlers import update_game_message
        await update_game_message(bot, game)


def setup_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(open_friends_job, "interval", minutes=5, args=[bot], max_instances=1)
    scheduler.start()
    return scheduler
