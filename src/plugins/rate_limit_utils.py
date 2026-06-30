import re


def parse_time_to_seconds(time_str: str) -> int:
    """Parse time string (e.g., '3m', '24h', '30s') to seconds."""
    if not time_str:
        return 60

    time_str = time_str.strip().lower()
    match = re.match(r"^(\d+)([smhd])$", time_str)
    if not match:
        raise ValueError(
            f"Invalid time format: {time_str}. Use format like '3m', '24h', '30s'"
        )

    value, unit = match.groups()
    value = int(value)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]
