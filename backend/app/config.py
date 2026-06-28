from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str
    MONITORED_SUBREDDITS: str = "startups,smallbusiness,entrepreneur,SaaS,forhire"
    POLL_INTERVAL_SECONDS: int = 300
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "meta-llama/llama-3-8b-instruct:free"


    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def subreddit_list(self) -> List[str]:
        return [s.strip() for s in self.MONITORED_SUBREDDITS.split(",") if s.strip()]

settings = Settings()
