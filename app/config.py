from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str
    railway_token: str
    github_token: Optional[str] = None
    poll_interval_seconds: int = 60

    class Config:
        env_file = ".env"


settings = Settings()
