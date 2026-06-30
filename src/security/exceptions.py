class AuthorizationError(Exception):
    """Raised when a caller lacks permission for an operation."""


class MFACodeRequired(Exception):
    """Raised when password is valid but MFA code is missing."""


class AccountLockedError(Exception):
    """Raised when login is blocked due to too many failed attempts."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(f"Account locked for {self.retry_after_seconds} seconds")
