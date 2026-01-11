from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    mongodb_uri: str = Field(
        default="mongodb+srv://sourav:@test-cluster.hfj3cs6.mongodb.net/?appName=test-cluster",
        env="MONGODB_URI"
    )
    mongodb_db_name: str = Field(default="lowkey_ecom", env="MONGODB_DB_NAME")
    clerk_secret_key: Optional[str] = Field(None, env="CLERK_SECRET_KEY")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

