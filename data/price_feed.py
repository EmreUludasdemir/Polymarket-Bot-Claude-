"""
Price Feed Module
Fetches real-time and historical price data for crypto assets
Used by crypto price prediction strategy
"""

from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
import requests
from loguru import logger


@dataclass
class PricePoint:
    """Single price data point"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class PriceSummary:
    """Price summary with indicators"""
    symbol: str
    current_price: float
    change_1h: float
    change_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    last_update: datetime


class PriceFeed:
    """
    Fetches cryptocurrency price data from public APIs

    Supports:
    - Real-time prices (BTC, ETH)
    - Historical OHLCV data
    - Price change calculations

    Uses CoinGecko API (free tier, no API key required)
    """

    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self._price_cache: Dict[str, PriceSummary] = {}
        self._history_cache: Dict[str, List[PricePoint]] = {}

        # CoinGecko coin IDs
        self.coin_ids = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "MATIC": "matic-network",
            "SOL": "solana"
        }

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol

        Args:
            symbol: Cryptocurrency symbol (BTC, ETH)

        Returns:
            Current USD price or None
        """
        try:
            coin_id = self.coin_ids.get(symbol.upper())
            if not coin_id:
                logger.warning(f"Unknown symbol: {symbol}")
                return None

            url = f"{self.base_url}/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true"
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            price = data.get(coin_id, {}).get("usd")

            if price:
                logger.debug(f"{symbol} current price: ${price}")
                return float(price)

            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return None

    def get_price_summary(self, symbol: str) -> Optional[PriceSummary]:
        """
        Get comprehensive price summary

        Args:
            symbol: Cryptocurrency symbol

        Returns:
            PriceSummary or None
        """
        try:
            coin_id = self.coin_ids.get(symbol.upper())
            if not coin_id:
                return None

            url = f"{self.base_url}/coins/{coin_id}"
            params = {
                "localization": "false",
                "tickers": "false",
                "community_data": "false",
                "developer_data": "false"
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            market_data = data.get("market_data", {})

            summary = PriceSummary(
                symbol=symbol.upper(),
                current_price=market_data.get("current_price", {}).get("usd", 0),
                change_1h=market_data.get("price_change_percentage_1h_in_currency", {}).get("usd", 0),
                change_24h=market_data.get("price_change_percentage_24h", 0),
                high_24h=market_data.get("high_24h", {}).get("usd", 0),
                low_24h=market_data.get("low_24h", {}).get("usd", 0),
                volume_24h=market_data.get("total_volume", {}).get("usd", 0),
                last_update=datetime.utcnow()
            )

            self._price_cache[symbol.upper()] = summary
            return summary

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch price summary for {symbol}: {e}")
            return None

    def get_historical_prices(
        self,
        symbol: str,
        days: int = 1,
        interval: str = "hourly"
    ) -> List[PricePoint]:
        """
        Get historical OHLCV data

        Args:
            symbol: Cryptocurrency symbol
            days: Number of days of history
            interval: Data interval (minutely for <1 day, hourly for 1-90 days)

        Returns:
            List of PricePoint objects
        """
        try:
            coin_id = self.coin_ids.get(symbol.upper())
            if not coin_id:
                return []

            # For short periods, use OHLC endpoint
            url = f"{self.base_url}/coins/{coin_id}/ohlc"
            params = {
                "vs_currency": "usd",
                "days": days
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            prices = []

            for point in data:
                timestamp, open_p, high, low, close = point
                prices.append(PricePoint(
                    timestamp=datetime.fromtimestamp(timestamp / 1000),
                    open=open_p,
                    high=high,
                    low=low,
                    close=close,
                    volume=0  # OHLC endpoint doesn't include volume
                ))

            self._history_cache[symbol.upper()] = prices
            logger.debug(f"Fetched {len(prices)} historical prices for {symbol}")
            return prices

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch history for {symbol}: {e}")
            return []

    def get_recent_prices(
        self,
        symbol: str,
        minutes: int = 60
    ) -> List[float]:
        """
        Get recent close prices for technical analysis

        Args:
            symbol: Cryptocurrency symbol
            minutes: How many minutes of data

        Returns:
            List of close prices (oldest to newest)
        """
        # Fetch hourly data and interpolate if needed
        history = self.get_historical_prices(symbol, days=1)

        if not history:
            return []

        # Get close prices
        close_prices = [p.close for p in history]

        # Return last N points (each point is roughly 30 min for 1-day data)
        points_needed = max(1, minutes // 30)
        return close_prices[-points_needed:]

    def get_price_momentum(self, symbol: str) -> Tuple[float, float]:
        """
        Calculate price momentum indicators

        Args:
            symbol: Cryptocurrency symbol

        Returns:
            Tuple of (short_term_change, long_term_change) in percentage
        """
        prices = self.get_recent_prices(symbol, minutes=120)

        if len(prices) < 2:
            return (0.0, 0.0)

        current = prices[-1]

        # Short-term: last 30 minutes
        short_ago = prices[-2] if len(prices) >= 2 else current
        short_change = ((current - short_ago) / short_ago) * 100 if short_ago else 0

        # Long-term: last 2 hours
        long_ago = prices[0]
        long_change = ((current - long_ago) / long_ago) * 100 if long_ago else 0

        return (short_change, long_change)

    def is_trending_up(self, symbol: str, threshold: float = 0.5) -> bool:
        """
        Check if price is trending up

        Args:
            symbol: Cryptocurrency symbol
            threshold: Minimum percentage change to consider trending

        Returns:
            True if trending up
        """
        short, long = self.get_price_momentum(symbol)
        return short > threshold and long > 0

    def is_trending_down(self, symbol: str, threshold: float = 0.5) -> bool:
        """
        Check if price is trending down

        Args:
            symbol: Cryptocurrency symbol
            threshold: Minimum percentage change to consider trending

        Returns:
            True if trending down
        """
        short, long = self.get_price_momentum(symbol)
        return short < -threshold and long < 0


# Global price feed instance
price_feed = PriceFeed()
