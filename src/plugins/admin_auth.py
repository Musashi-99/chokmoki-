from src.config import settings


def validate_admin_key(admin_key: str) -> bool:
    if not admin_key:
        return False
    return admin_key == settings.admin_key
