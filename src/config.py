from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os


class Settings(BaseSettings):
    # Mongo
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    mongodb_db_name: str = Field(default="lowkey_ecom", env="MONGODB_DB_NAME")

    # Auth
    clerk_secret_key: Optional[str] = Field(default=None, env="CLERK_SECRET_KEY")
    admin_key: str = Field(default="", env="ADMIN_KEYS")

    # Infra
    redis_url: str = Field(..., env="REDIS_URL")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # Razorpay
    razorpay_key_id: str = Field(..., env="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(..., env="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: Optional[str] = Field(default=None, env="RAZORPAY_WEBHOOK_SECRET")


    @field_validator("admin_key", mode="before")
    @classmethod
    def validate_admin_key(cls, v):
        if v is None or v == "":
            return os.getenv("ADMIN_KEYS", "")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True
    )

settings = Settings()
