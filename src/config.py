from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Mongo
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    mongodb_db_name: str = Field(default="lowkey_ecom", env="MONGODB_DB_NAME")

    # Auth
    admin_email: str = Field(default="admin@chokmoki.com", env="ADMIN_EMAIL")
    admin_password: str = Field(default="admin123", env="ADMIN_PASSWORD")
    jwt_secret: str = Field(default="chokmoki-jwt-secret-change-me", env="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, env="JWT_EXPIRATION_HOURS")

    # Infra
    redis_url: str = Field(..., env="REDIS_URL")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # Razorpay
    razorpay_key_id: str = Field(..., env="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(..., env="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: Optional[str] = Field(default=None, env="RAZORPAY_WEBHOOK_SECRET")

    # Telegram
    telegram_enabled: bool = Field(default=False, env="TELEGRAM_ENABLED")
    telegram_bot_token: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, env="TELEGRAM_CHAT_ID")
    telegram_message_max_chars: int = Field(default=3800, env="TELEGRAM_MESSAGE_MAX_CHARS")
    telegram_redis_key: str = Field(default="telegram:orders:pending", env="TELEGRAM_REDIS_KEY")
    telegram_product_base_url: str = Field(default="https://lowkey-ui.vercel.app/product", env="TELEGRAM_PRODUCT_BASE_URL")

    # R2 / S3
    r2_account_id: str = Field(default="", env="R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", env="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", env="R2_SECRET_ACCESS_KEY")
    r2_bucket: str = Field(default="chokmoki", env="R2_BUCKET")
    r2_key_prefix: str = Field(default="", env="R2_KEY_PREFIX")
    r2_public_base_url: str = Field(default="", env="R2_PUBLIC_BASE_URL")

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    rate_limit_normal_get: int = Field(default=40, env="RATE_LIMIT_NORMAL_GET")
    rate_limit_normal_post: int = Field(default=40, env="RATE_LIMIT_NORMAL_POST")
    rate_limit_normal_time: str = Field(default="3m", env="RATE_LIMIT_NORMAL_TIME")
    rate_limit_order_max: int = Field(default=5, env="RATE_LIMIT_ORDER_MAX")
    rate_limit_order_time: str = Field(default="24h", env="RATE_LIMIT_ORDER_TIME")


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True
    )

settings = Settings()
