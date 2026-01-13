from src.config import settings


def validate_admin_key(admin_key: str) -> bool:
    print("key recv: ", admin_key)
    print("key expected: ", settings.admin_key)
    if not admin_key:
        return False
    return admin_key == settings.admin_key
