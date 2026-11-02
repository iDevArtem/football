from datetime import datetime, timezone
from app.services.render import status_text, format_game_message


def test_render_game_started_status():
    assert status_text("game_started") == "игра началась ⚽"
    game = {
        "title": "Матч пятницы",
        "start_at": datetime.now(timezone.utc),
        "duration_minutes": 90,
        "hourly_rate": 600,
        "max_players": 15,
        "status": "game_started",
    }
    msg = format_game_message(game, [])
    assert "игра началась ⚽" in msg
    assert "Матч начался" in msg or "Игра началась" in msg
    assert "Запись и отмены заблокированы" in msg or "Запись и отмены закрыты" in msg


def test_render_payment_collection_with_card():
    game = {
        "title": "Матч пятницы",
        "start_at": datetime.now(timezone.utc),
        "duration_minutes": 90,
        "hourly_rate": 600,
        "max_players": 15,
        "price": 100,
        "total_cost": 900,
        "status": "payment_collection",
        "payment_details": {
            "card_number": "4441 1111 2222 3333",
            "recipient": "Иван И."
        }
    }
    msg = format_game_message(game, [], [])
    assert "<code>4441 1111 2222 3333</code>" in msg
    assert "Иван И." in msg


import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from app.services.scheduler import check_and_start_due_games_job

@pytest.mark.asyncio
async def test_scheduler_auto_starts_due_games():
    db = MagicMock()
    mock_game = {
        "_id": ObjectId("6724123456789abcdef01234"),
        "title": "Автостарт матч",
        "status": "registration_open",
        "messages": [],
    }
    with patch("app.services.scheduler.get_db", return_value=db), \
         patch("app.services.scheduler.GameRepository") as mock_game_repo_cls, \
         patch("app.bot.handlers.update_game_message", new_callable=AsyncMock) as mock_update_msg:
        repo_instance = MagicMock()
        repo_instance.games_to_auto_start = AsyncMock(return_value=[mock_game])
        repo_instance.set_status = AsyncMock(return_value=True)
        repo_instance.get = AsyncMock(return_value={**mock_game, "status": "game_started"})
        mock_game_repo_cls.return_value = repo_instance

        bot = MagicMock()
        await check_and_start_due_games_job(bot)

        repo_instance.set_status.assert_called_once_with(str(mock_game["_id"]), "game_started")
        mock_update_msg.assert_called_once()

