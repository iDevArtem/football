import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import lifespan, app


@pytest.mark.asyncio
async def test_lifespan_empty_bot_token_shutdown():
    """Verify that lifespan shuts down cleanly without UnboundLocalError when bot_token is empty."""
    with patch("app.main.get_settings") as mock_settings, \
         patch("app.main.init_mongo", new=AsyncMock()), \
         patch("app.main.close_mongo", new=AsyncMock()):
        settings_instance = MagicMock()
        settings_instance.bot_token = ""
        mock_settings.return_value = settings_instance

        # Entering and exiting lifespan should succeed with no UnboundLocalError for 'dp'
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_lifespan_cancellation_suppressed():
    """Verify that CancelledError during lifespan is gracefully caught and cleaned up."""
    with patch("app.main.get_settings") as mock_settings, \
         patch("app.main.init_mongo", new=AsyncMock()), \
         patch("app.main.close_mongo", new=AsyncMock()):
        settings_instance = MagicMock()
        settings_instance.bot_token = ""
        mock_settings.return_value = settings_instance

        # Simulate task cancellation inside lifespan context
        try:
            async with lifespan(app):
                raise asyncio.CancelledError()
        except asyncio.CancelledError:
            pytest.fail("lifespan should catch and suppress CancelledError during shutdown")


@pytest.mark.asyncio
async def test_lifespan_normal_shutdown_with_bot():
    """Verify that lifespan properly shuts down bot, dp, scheduler, and mongo."""
    mock_scheduler = MagicMock()
    mock_dp = MagicMock()
    mock_dp.start_polling = AsyncMock()
    mock_dp.stop_polling = AsyncMock()
    mock_bot = MagicMock()
    mock_bot.session.close = AsyncMock()

    mock_polling_task = asyncio.create_task(asyncio.sleep(10))

    with patch("app.main.get_settings") as mock_settings, \
         patch("app.main.init_mongo", new=AsyncMock()), \
         patch("app.main.close_mongo", new=AsyncMock()) as mock_close_mongo, \
         patch("app.main.Bot", return_value=mock_bot), \
         patch("app.main.Dispatcher", return_value=mock_dp), \
         patch("app.main.setup_scheduler", return_value=mock_scheduler), \
         patch("asyncio.create_task", return_value=mock_polling_task):
        
        settings_instance = MagicMock()
        settings_instance.bot_token = "123456:valid_token"
        mock_settings.return_value = settings_instance

        async with lifespan(app):
            pass

        mock_scheduler.shutdown.assert_called_once_with(wait=False)
        mock_dp.stop_polling.assert_awaited_once()
        mock_close_mongo.assert_awaited_once()
