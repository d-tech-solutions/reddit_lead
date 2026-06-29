from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str
    MONITORED_SUBREDDITS: str = "startups,smallbusiness,entrepreneur,SaaS,forhire"
    POLL_INTERVAL_SECONDS: int = 300
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    MIN_NOTIFICATION_SCORE: int = 70



    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def subreddit_list(self) -> List[str]:
        return [s.strip() for s in self.MONITORED_SUBREDDITS.split(",") if s.strip()]

settings = Settings()
