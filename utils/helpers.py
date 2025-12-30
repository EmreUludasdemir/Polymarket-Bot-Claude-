"""
Utility Helper Functions
Common utilities used throughout the bot
"""

from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone
import hashlib
import json


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """
    Safely convert value to Decimal

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Decimal value
    """
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def round_price(price: Decimal, tick_size: Decimal = Decimal("0.01")) -> Decimal:
    """
    Round price to valid tick size

    Args:
        price: Price to round
        tick_size: Minimum price increment

    Returns:
        Rounded price
    """
    return (price / tick_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * tick_size


def round_size(size: Decimal, min_size: Decimal = Decimal("0.01")) -> Decimal:
    """
    Round size to valid minimum

    Args:
        size: Size to round
        min_size: Minimum size increment

    Returns:
        Rounded size
    """
    return (size / min_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * min_size


def calculate_pnl(
    entry_price: Decimal,
    exit_price: Decimal,
    size: Decimal,
    side: str
) -> Decimal:
    """
    Calculate profit/loss for a trade

    Args:
        entry_price: Entry price
        exit_price: Exit price
        size: Position size in USDC
        side: "BUY" or "SELL"

    Returns:
        PnL in USDC
    """
    if side.upper() == "BUY":
        # Long: profit if exit > entry
        return (exit_price - entry_price) * size / entry_price
    else:
        # Short: profit if exit < entry
        return (entry_price - exit_price) * size / entry_price


def calculate_roi(pnl: Decimal, investment: Decimal) -> Decimal:
    """
    Calculate return on investment

    Args:
        pnl: Profit/loss amount
        investment: Original investment

    Returns:
        ROI as decimal (0.10 = 10%)
    """
    if investment == 0:
        return Decimal("0")
    return pnl / investment


def format_usd(amount: Decimal) -> str:
    """Format amount as USD string"""
    return f"${amount:,.2f}"


def format_pct(value: Decimal) -> str:
    """Format value as percentage string"""
    return f"{value * 100:.2f}%"


def generate_trade_id() -> str:
    """Generate unique trade ID"""
    import uuid
    return str(uuid.uuid4())[:8]


def generate_order_hash(order_data: Dict) -> str:
    """
    Generate deterministic hash for order

    Args:
        order_data: Order dictionary

    Returns:
        Hash string
    """
    order_str = json.dumps(order_data, sort_keys=True)
    return hashlib.sha256(order_str.encode()).hexdigest()[:16]


def utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


def timestamp_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    """
    Parse ISO datetime string

    Args:
        iso_str: ISO format datetime string

    Returns:
        datetime or None
    """
    if not iso_str:
        return None
    try:
        # Handle various ISO formats
        iso_str = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return None


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Split list into chunks

    Args:
        lst: List to split
        chunk_size: Maximum chunk size

    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def safe_divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """
    Safely divide with zero check

    Args:
        numerator: Top number
        denominator: Bottom number

    Returns:
        Division result or 0
    """
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def clamp(value: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    """
    Clamp value to range

    Args:
        value: Value to clamp
        min_val: Minimum
        max_val: Maximum

    Returns:
        Clamped value
    """
    return max(min_val, min(value, max_val))


def is_valid_token_id(token_id: str) -> bool:
    """
    Validate token ID format

    Args:
        token_id: Token ID string

    Returns:
        True if valid
    """
    if not token_id or not isinstance(token_id, str):
        return False
    # Token IDs are typically long numeric strings
    return len(token_id) > 10 and token_id.isdigit()


def sanitize_log_message(message: str, max_length: int = 500) -> str:
    """
    Sanitize message for logging

    Args:
        message: Message to sanitize
        max_length: Maximum length

    Returns:
        Sanitized message
    """
    # Remove potential secrets
    sanitized = message
    sensitive_patterns = ["private_key", "secret", "password", "api_key"]
    for pattern in sensitive_patterns:
        if pattern.lower() in sanitized.lower():
            sanitized = "[REDACTED]"
            break

    # Truncate if needed
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized
