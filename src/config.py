from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os


class Settings(BaseSettings):
    # Mongo
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    mongodb_db_name: str = Field(default="lowkey_ecom", env="MONGODB_DB_NAME")

    # Auth
    clerk_secret_key: Optional[str] = Field(default=None, env="CLERK_SECRET_KEY")
    admin_key: str = Field(..., env="ADMIN_KEYS")

    # Infra
    redis_url: str = Field(..., env="REDIS_URL")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True
    )

settings = Settings()
