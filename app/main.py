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
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
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
    if settings.is_default_jwt_secret and settings.bot_token and not settings.bot_token.startswith("test"):
        logger.warning(
            "CRITICAL SECURITY WARNING: Default JWT_SECRET is used! Please configure a secure JWT_SECRET in .env."
        )

    logger.info("Initializing MongoDB...")
    try:
        await init_mongo()
    except Exception as e:
        logger.warning(f"Mongo init skipped or failed in test/dev: {e}")

    bot = None
    polling_task = None
    scheduler = None
    dp = None

    if settings.bot_token and not settings.bot_token.startswith("test"):
        bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        set_bot(bot)
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(bot_router)

        scheduler = setup_scheduler(bot)
        # handle_signals=False allows Uvicorn to handle SIGINT/SIGTERM and trigger clean lifespan exit
        polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        logger.info("Bot polling and scheduler started.")

    try:
        yield
    except asyncio.CancelledError:
        logger.info("Lifespan received cancellation signal; initiating shutdown.")
    finally:
        logger.info("Shutting down...")
        if scheduler:
            try:
                scheduler.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"Error shutting down scheduler: {e}")
        if dp:
            try:
                await dp.stop_polling()
            except Exception as e:
                logger.warning(f"Error stopping bot polling: {e}")
        if polling_task:
            polling_task.cancel()
            try:
                await polling_task
            except (asyncio.CancelledError, Exception):
                pass
        if bot:
            try:
                await bot.session.close()
            except Exception as e:
                logger.warning(f"Error closing bot session: {e}")
        try:
            await close_mongo()
        except Exception as e:
            logger.warning(f"Error closing MongoDB: {e}")
        logger.info("Shutdown complete.")


app = FastAPI(
    title="Football Telegram Bot & Mini App API",
    description="REST API and Mini App backend for football matches management",
    lifespan=lifespan,
)

# CORS middleware for WebApp and local frontend dev
_settings = get_settings()
_cors_origins = [
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]
if _settings.webapp_url:
    _cors_origins.append(_settings.webapp_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    db_connected = False
    try:
        from app.db.mongo import get_db
        db = get_db()
        cmd_res = db.command("ping")
        if hasattr(cmd_res, "__await__"):
            await cmd_res
        db_connected = True
    except Exception:
        db_connected = False

    return {
        "status": "ok",
        "app": "football_bot",
        "database": "connected" if db_connected else "disconnected",
    }

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


def main() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
