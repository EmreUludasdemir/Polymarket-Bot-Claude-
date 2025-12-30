"""
Polymarket Bot Configuration Management
Pydantic-based settings with environment variable support
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional
from decimal import Decimal
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


class WalletSettings(BaseSettings):
    """Wallet and authentication configuration"""

    private_key: str = Field(
        default="",
        description="Ethereum private key for signing transactions"
    )
    proxy_wallet_address: str = Field(
        default="",
        description="Polymarket proxy wallet address from profile"
    )
    signature_type: int = Field(
        default=1,
        ge=0,
        le=2,
        description="Signature type: 0=EOA, 1=Magic/Email, 2=Proxy"
    )

    @field_validator("private_key")
    @classmethod
    def validate_private_key(cls, v: str) -> str:
        """Ensure private key has correct format"""
        if v and not v.startswith("0x"):
            v = "0x" + v
        return v

    class Config:
        env_prefix = ""
        case_sensitive = False


class APISettings(BaseSettings):
    """Polymarket API endpoints"""

    clob_api_url: str = Field(
        default="https://clob.polymarket.com",
        description="CLOB API endpoint"
    )
    gamma_api_url: str = Field(
        default="https://gamma-api.polymarket.com",
        description="Gamma API for market data"
    )
    ws_url: str = Field(
        default="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        description="WebSocket endpoint"
    )
    polygon_rpc_url: str = Field(
        default="https://polygon-rpc.com",
        description="Polygon RPC endpoint"
    )
    chain_id: int = Field(
        default=137,
        description="Polygon chain ID (137 = mainnet)"
    )

    class Config:
        env_prefix = ""
        case_sensitive = False


class TradingSettings(BaseSettings):
    """Trading parameters and risk limits"""

    initial_capital: Decimal = Field(
        default=Decimal("500"),
        description="Starting capital in USDC"
    )
    risk_per_trade: Decimal = Field(
        default=Decimal("0.02"),
        ge=Decimal("0.001"),
        le=Decimal("0.10"),
        description="Risk percentage per trade (0.02 = 2%)"
    )
    max_daily_loss: Decimal = Field(
        default=Decimal("0.05"),
        ge=Decimal("0.01"),
        le=Decimal("0.20"),
        description="Maximum daily loss before stopping (0.05 = 5%)"
    )
    max_drawdown: Decimal = Field(
        default=Decimal("0.20"),
        ge=Decimal("0.05"),
        le=Decimal("0.50"),
        description="Maximum drawdown from peak (0.20 = 20%)"
    )
    min_edge_threshold: Decimal = Field(
        default=Decimal("0.03"),
        ge=Decimal("0.01"),
        le=Decimal("0.20"),
        description="Minimum edge to enter trade (0.03 = 3%)"
    )
    trade_unit: Decimal = Field(
        default=Decimal("3.0"),
        ge=Decimal("1.0"),
        le=Decimal("100.0"),
        description="Fixed trade size in USDC"
    )
    kelly_fraction: Decimal = Field(
        default=Decimal("0.25"),
        ge=Decimal("0.1"),
        le=Decimal("1.0"),
        description="Kelly criterion fraction (0.25 = quarter Kelly)"
    )
    arb_min_spread: Decimal = Field(
        default=Decimal("0.005"),
        ge=Decimal("0.001"),
        le=Decimal("0.05"),
        description="Minimum arbitrage spread (0.005 = 0.5%)"
    )

    class Config:
        env_prefix = ""
        case_sensitive = False


class MarketMakingSettings(BaseSettings):
    """Market making strategy parameters"""

    enabled: bool = Field(
        default=True,
        description="Enable market making strategy"
    )
    quote_size: Decimal = Field(
        default=Decimal("5.0"),
        ge=Decimal("1.0"),
        le=Decimal("100.0"),
        description="Default quote size in USDC per side"
    )
    max_spread: Decimal = Field(
        default=Decimal("0.04"),
        ge=Decimal("0.01"),
        le=Decimal("0.10"),
        description="Maximum spread to quote (4% default)"
    )
    min_spread: Decimal = Field(
        default=Decimal("0.01"),
        ge=Decimal("0.005"),
        le=Decimal("0.05"),
        description="Minimum spread to maintain profitability"
    )
    max_position_per_market: Decimal = Field(
        default=Decimal("25.0"),
        ge=Decimal("5.0"),
        le=Decimal("100.0"),
        description="Maximum position size per market (USDC)"
    )
    inventory_skew_factor: Decimal = Field(
        default=Decimal("0.5"),
        ge=Decimal("0.0"),
        le=Decimal("1.0"),
        description="How much to skew quotes based on inventory"
    )
    volatility_cooldown_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Seconds to pause after volatility spike"
    )
    max_markets: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum markets to make simultaneously"
    )
    quote_refresh_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=60.0,
        description="How often to refresh quotes"
    )

    class Config:
        env_prefix = "MM_"
        case_sensitive = False


class RewardsSettings(BaseSettings):
    """Liquidity rewards configuration"""

    enabled: bool = Field(
        default=True,
        description="Enable rewards-aware market making"
    )
    min_reward_rate: Decimal = Field(
        default=Decimal("0.0"),
        description="Minimum reward rate to participate"
    )
    prefer_reward_markets: bool = Field(
        default=True,
        description="Prioritize reward-eligible markets"
    )
    max_incentive_spread_buffer: Decimal = Field(
        default=Decimal("0.005"),
        description="Quote inside max_incentive_spread by this buffer"
    )

    class Config:
        env_prefix = "REWARDS_"
        case_sensitive = False


class RateLimitSettings(BaseSettings):
    """API rate limiting configuration"""

    max_orders_per_second: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum orders per second"
    )
    max_requests_per_second: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Maximum API requests per second"
    )
    burst_limit: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Burst limit for rate limiter"
    )
    backoff_base_seconds: float = Field(
        default=1.0,
        ge=0.5,
        le=5.0,
        description="Base backoff time for rate limit errors"
    )
    backoff_max_seconds: float = Field(
        default=60.0,
        ge=10.0,
        le=300.0,
        description="Maximum backoff time"
    )

    class Config:
        env_prefix = "RATE_"
        case_sensitive = False


class OperationalSettings(BaseSettings):
    """Operational parameters"""

    poll_interval: int = Field(
        default=2,
        ge=1,
        le=60,
        description="REST API polling interval in seconds"
    )
    use_websocket: bool = Field(
        default=True,
        description="Enable WebSocket for real-time data"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    database_path: str = Field(
        default="./data/trading.db",
        description="SQLite database path"
    )
    paper_trading: bool = Field(
        default=False,
        description="Enable paper trading mode (no real orders)"
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure valid log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v

    class Config:
        env_prefix = ""
        case_sensitive = False


class NotificationSettings(BaseSettings):
    """Notification configuration (optional)"""

    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token from @BotFather"
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat ID"
    )
    discord_webhook_url: str = Field(
        default="",
        description="Discord webhook URL"
    )

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_webhook_url)

    class Config:
        env_prefix = ""
        case_sensitive = False


class Settings:
    """
    Combined settings container

    Usage:
        from config.settings import settings

        print(settings.trading.initial_capital)
        print(settings.wallet.private_key)
        print(settings.market_making.quote_size)
    """

    def __init__(self):
        self.wallet = WalletSettings()
        self.api = APISettings()
        self.trading = TradingSettings()
        self.market_making = MarketMakingSettings()
        self.rewards = RewardsSettings()
        self.rate_limit = RateLimitSettings()
        self.operational = OperationalSettings()
        self.notifications = NotificationSettings()

    @property
    def max_position_size(self) -> Decimal:
        """Maximum position size based on capital (5%)"""
        return self.trading.initial_capital * Decimal("0.05")

    @property
    def daily_loss_limit(self) -> Decimal:
        """Absolute daily loss limit in USDC"""
        return self.trading.initial_capital * self.trading.max_daily_loss

    @property
    def max_drawdown_amount(self) -> Decimal:
        """Maximum drawdown amount in USDC"""
        return self.trading.initial_capital * self.trading.max_drawdown

    @property
    def is_configured(self) -> bool:
        """Check if essential settings are configured"""
        return bool(
            self.wallet.private_key
            and self.wallet.proxy_wallet_address
        )

    def validate(self) -> bool:
        """
        Validate all settings

        Returns:
            True if all settings are valid

        Raises:
            ValueError: If settings are invalid
        """
        if not self.wallet.private_key:
            raise ValueError("PRIVATE_KEY is required")

        if not self.wallet.proxy_wallet_address:
            raise ValueError("PROXY_WALLET_ADDRESS is required")

        if self.trading.initial_capital <= 0:
            raise ValueError("INITIAL_CAPITAL must be positive")

        if self.trading.trade_unit > self.max_position_size:
            raise ValueError(
                f"TRADE_UNIT ({self.trading.trade_unit}) exceeds "
                f"max position size ({self.max_position_size})"
            )

        return True

    def to_dict(self) -> dict:
        """Export settings as dictionary (excluding secrets)"""
        return {
            "trading": {
                "initial_capital": str(self.trading.initial_capital),
                "risk_per_trade": str(self.trading.risk_per_trade),
                "max_daily_loss": str(self.trading.max_daily_loss),
                "max_drawdown": str(self.trading.max_drawdown),
                "kelly_fraction": str(self.trading.kelly_fraction),
            },
            "operational": {
                "poll_interval": self.operational.poll_interval,
                "use_websocket": self.operational.use_websocket,
                "log_level": self.operational.log_level,
                "paper_trading": self.operational.paper_trading,
            },
            "notifications": {
                "telegram_enabled": self.notifications.telegram_enabled,
                "discord_enabled": self.notifications.discord_enabled,
            }
        }


# Global settings instance
settings = Settings()
