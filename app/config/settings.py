from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = ""
    bot_username: str = "mini_football_robot"
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db_name: str = "football_bot"
    default_timezone: str = "Europe/Kyiv"
    admin_telegram_ids: str = ""
    webapp_url: str = "https://football.idev.wtf"
    jwt_secret: str = "change-me-secret-key-32-chars-minimum-length!"
    card_number: str = ""
    card_recipient: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def admin_ids(self) -> set[int]:
        result: set[int] = set()
        for raw in self.admin_telegram_ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                result.add(int(raw))
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()
