import os
import pytest
from app.config.settings import get_settings

# Ensure testing environment variables are configured
os.environ.setdefault("BOT_TOKEN", "test_bot_token")


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Ensure get_settings cache is fresh if environment changes."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
