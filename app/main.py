import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config.settings import get_settings
from app.db.mongo import init_mongo, close_mongo
from app.bot.handlers import router as bot_router
from app.bot.bot_instance import set_bot
from app.services.scheduler import setup_scheduler

from app.api.routers.auth import router as auth_router
from app.api.routers.games import router as games_router
from app.api.routers.admin import router as admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Initializing MongoDB...")
    try:
        await init_mongo()
    except Exception as e:
        logger.warning(f"Mongo init skipped or failed in test/dev: {e}")

    bot = None
    polling_task = None
    scheduler = None

    if settings.bot_token and settings.bot_token != "test_token":
        bot = Bot(token=settings.bot_token)
        set_bot(bot)
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(bot_router)

        scheduler = setup_scheduler(bot)
        # handle_signals=False allows Uvicorn to handle SIGINT/SIGTERM and trigger clean lifespan exit
        polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        logger.info("Bot polling and scheduler started.")

    yield

    logger.info("Shutting down...")
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
    if dp:
        try:
            await dp.stop_polling()
        except Exception:
            pass
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except (asyncio.CancelledError, Exception):
            pass
    if bot:
        await bot.session.close()
    await close_mongo()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Football Telegram Bot & Mini App API",
    description="REST API and Mini App backend for football matches management",
    lifespan=lifespan,
)

# CORS middleware for local frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(auth_router, prefix="/api/auth")
app.include_router(games_router, prefix="/api/games")
app.include_router(admin_router, prefix="/api/admin")

# Static files & SPA fallback
STATIC_DIR = Path(__file__).resolve().parent / "static"

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(request: Request, full_path: str):
    # Don't hijack /api routes with HTML
    if full_path.startswith("api/"):
        return HTMLResponse(status_code=404, content="API endpoint not found")

    resolved_static = STATIC_DIR.resolve()
    target_file = (STATIC_DIR / full_path).resolve()
    if full_path and target_file.is_file() and target_file.is_relative_to(resolved_static):
        return FileResponse(target_file)

    index_html = STATIC_DIR / "index.html"
    if index_html.is_file():
        return FileResponse(index_html)

    return HTMLResponse("<html><body><h1>Football Mini App</h1></body></html>")


async def main() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    asyncio.run(main())
