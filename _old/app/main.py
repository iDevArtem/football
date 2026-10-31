import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config.settings import get_settings
from app.db.mongo import init_mongo, close_mongo
from app.bot.handlers import router
from app.services.scheduler import setup_scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    await init_mongo()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = setup_scheduler(bot)
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await close_mongo()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
