import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from aiogram.exceptions import TelegramRetryAfter

from app.main import app
from app.api.sync import sync_game_message
from app.bot.handlers import _update_single_message


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["app"] == "football_bot"


@pytest.mark.asyncio
async def test_sync_game_message_logs_exception():
    with patch("app.api.sync.get_bot") as mock_get_bot, \
         patch("app.api.sync.get_db") as mock_get_db, \
         patch("app.api.sync.GameRepository") as mock_game_cls, \
         patch("app.bot.handlers.update_game_message", side_effect=Exception("Telegram connection lost")), \
         patch("app.api.sync.logger") as mock_logger:
        bot = MagicMock()
        mock_get_bot.return_value = bot
        mock_get_db.return_value = MagicMock()
        game_repo = MagicMock()
        game_repo.get = AsyncMock(return_value={"_id": "test_game"})
        mock_game_cls.return_value = game_repo

        await sync_game_message("test_game")
        mock_logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_update_single_message_handles_retry_after():
    bot = MagicMock()
    bot.edit_message_text = AsyncMock(side_effect=TelegramRetryAfter(method=MagicMock(), message="Flood limit", retry_after=5))
    game_repo = MagicMock()
    chat_repo = MagicMock()

    with patch("app.bot.handlers.logger") as mock_logger:
        # Should not raise exception
        await _update_single_message(
            bot=bot,
            game_repo=game_repo,
            chat_repo=chat_repo,
            game_id="game123",
            chat_id=-1001,
            message_id=42,
            text="text",
            reply_markup=None,
        )
        mock_logger.warning.assert_called()
