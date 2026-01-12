from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional

password_db = ""
class Settings(BaseSettings):
    mongodb_uri: str = Field(
        default=f"mongodb+srv://sourav:{password_db}@test-cluster.hfj3cs6.mongodb.net/?appName=test-cluster",
        env="MONGODB_URI"
    )
    mongodb_db_name: str = Field(default="lowkey_ecom", env="MONGODB_DB_NAME")
    clerk_secret_key: Optional[str] = Field(None, env="CLERK_SECRET_KEY")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    admin_keys: list[str] = Field(default=["abcd", "1234", "pqrst"], env="ADMIN_KEYS")
    redis_url: str = Field(default="redis://default:@redis-11487.crce182.ap-south-1-1.ec2.cloud.redislabs.com:11487", env="REDIS_URL")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

