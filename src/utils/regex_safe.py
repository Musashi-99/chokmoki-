import re


def escape_mongo_regex(value: str) -> str:
    """Escape user input for safe use inside MongoDB $regex queries."""
    if not value:
        return value
    return re.escape(value)
