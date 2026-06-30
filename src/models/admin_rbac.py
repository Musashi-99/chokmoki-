from enum import Enum


class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"


class AdminPermission(str, Enum):
    ACCESS = "admin:access"
    ORDERS_READ = "orders:read"
    ORDERS_WRITE = "orders:write"
    PRODUCTS_READ = "products:read"
    PRODUCTS_WRITE = "products:write"
    CONTENT_WRITE = "content:write"
    MEDIA_UPLOAD = "media:upload"
    SETTINGS_WRITE = "settings:write"
    INBOX_READ = "inbox:read"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS: dict[str, set[str]] = {
    AdminRole.SUPER_ADMIN.value: {"*"},
}


def permissions_for_role(role: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, set()))


def role_has_permission(role: str, permission: str) -> bool:
    perms = permissions_for_role(role)
    return "*" in perms or permission in perms
