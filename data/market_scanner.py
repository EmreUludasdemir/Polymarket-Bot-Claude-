"""
Market Scanner Module
Scans and filters Polymarket markets for trading opportunities
"""

from typing import Optional, Dict, List, Any
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
import requests
from loguru import logger

from config.constants import (
    GAMMA_API_HOST,
    CRYPTO_MARKET_KEYWORDS,
    ESPORTS_MARKET_KEYWORDS
)


@dataclass
class MarketInfo:
    """Structured market information"""
    market_id: str
    condition_id: str
    question: str
    description: str
    yes_token_id: str
    no_token_id: str
    yes_price: Optional[Decimal]
    no_price: Optional[Decimal]
    volume_24h: Decimal
    liquidity: Decimal
    end_date: Optional[datetime]
    is_active: bool
    category: str
    tags: List[str]


class MarketScanner:
    """
    Scans Polymarket for trading opportunities

    Features:
    - Filter by category (crypto, esports, politics)
    - Filter by liquidity and volume
    - Identify arbitrage opportunities
    - Track market resolution times
    """

    def __init__(self, gamma_api_url: str = GAMMA_API_HOST):
        self.gamma_api_url = gamma_api_url
        self._cache: Dict[str, MarketInfo] = {}
        self._last_scan: Optional[datetime] = None

    def fetch_all_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = True
    ) -> List[Dict]:
        """
        Fetch markets from Gamma API

        Args:
            limit: Maximum markets to fetch
            offset: Pagination offset
            active_only: Only fetch active markets

        Returns:
            List of market dictionaries
        """
        try:
            url = f"{self.gamma_api_url}/markets"
            params = {
                "limit": limit,
                "offset": offset,
                "active": active_only
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            markets = response.json()
            logger.debug(f"Fetched {len(markets)} markets from Gamma API")
            return markets

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    def get_market_details(self, market_id: str) -> Optional[Dict]:
        """
        Get detailed information for a specific market

        Args:
            market_id: Market identifier

        Returns:
            Market details or None
        """
        try:
            url = f"{self.gamma_api_url}/markets/{market_id}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch market {market_id}: {e}")
            return None

    def parse_market(self, raw_market: Dict) -> Optional[MarketInfo]:
        """
        Parse raw market data into MarketInfo

        Args:
            raw_market: Raw market dictionary from API

        Returns:
            MarketInfo or None if parsing fails
        """
        try:
            # Extract token IDs from outcomes/tokens
            tokens = raw_market.get("tokens", [])
            yes_token = None
            no_token = None

            for token in tokens:
                outcome = token.get("outcome", "").lower()
                if outcome == "yes":
                    yes_token = token
                elif outcome == "no":
                    no_token = token

            if not yes_token or not no_token:
                return None

            # Parse end date
            end_date = None
            end_str = raw_market.get("endDate") or raw_market.get("end_date_iso")
            if end_str:
                try:
                    end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            return MarketInfo(
                market_id=raw_market.get("id", ""),
                condition_id=raw_market.get("conditionId", ""),
                question=raw_market.get("question", ""),
                description=raw_market.get("description", ""),
                yes_token_id=yes_token.get("token_id", ""),
                no_token_id=no_token.get("token_id", ""),
                yes_price=Decimal(str(yes_token.get("price", 0))) if yes_token.get("price") else None,
                no_price=Decimal(str(no_token.get("price", 0))) if no_token.get("price") else None,
                volume_24h=Decimal(str(raw_market.get("volume24hr", 0))),
                liquidity=Decimal(str(raw_market.get("liquidity", 0))),
                end_date=end_date,
                is_active=raw_market.get("active", False),
                category=raw_market.get("category", ""),
                tags=raw_market.get("tags", [])
            )

        except Exception as e:
            logger.error(f"Failed to parse market: {e}")
            return None

    def filter_crypto_markets(self, markets: List[MarketInfo]) -> List[MarketInfo]:
        """
        Filter for crypto-related markets

        Args:
            markets: List of MarketInfo objects

        Returns:
            Crypto markets only
        """
        crypto_markets = []

        for market in markets:
            question_lower = market.question.lower()
            desc_lower = market.description.lower()

            # Check for crypto keywords
            for keyword in CRYPTO_MARKET_KEYWORDS:
                if keyword in question_lower or keyword in desc_lower:
                    crypto_markets.append(market)
                    break

        logger.info(f"Found {len(crypto_markets)} crypto markets")
        return crypto_markets

    def filter_esports_markets(self, markets: List[MarketInfo]) -> List[MarketInfo]:
        """
        Filter for esports-related markets

        Args:
            markets: List of MarketInfo objects

        Returns:
            Esports markets only
        """
        esports_markets = []

        for market in markets:
            question_lower = market.question.lower()

            for keyword in ESPORTS_MARKET_KEYWORDS:
                if keyword in question_lower:
                    esports_markets.append(market)
                    break

        logger.info(f"Found {len(esports_markets)} esports markets")
        return esports_markets

    def filter_by_liquidity(
        self,
        markets: List[MarketInfo],
        min_liquidity: Decimal = Decimal("1000")
    ) -> List[MarketInfo]:
        """
        Filter markets by minimum liquidity

        Args:
            markets: List of markets
            min_liquidity: Minimum liquidity in USDC

        Returns:
            Markets meeting liquidity threshold
        """
        filtered = [m for m in markets if m.liquidity >= min_liquidity]
        logger.debug(f"Filtered to {len(filtered)} markets with liquidity >= ${min_liquidity}")
        return filtered

    def filter_expiring_soon(
        self,
        markets: List[MarketInfo],
        max_hours: int = 24
    ) -> List[MarketInfo]:
        """
        Filter for markets expiring within specified hours

        Args:
            markets: List of markets
            max_hours: Maximum hours until expiration

        Returns:
            Markets expiring soon
        """
        cutoff = datetime.utcnow() + timedelta(hours=max_hours)
        expiring = []

        for market in markets:
            if market.end_date and market.end_date <= cutoff:
                expiring.append(market)

        logger.debug(f"Found {len(expiring)} markets expiring within {max_hours} hours")
        return expiring

    def find_arbitrage_opportunities(
        self,
        markets: List[MarketInfo],
        min_edge: Decimal = Decimal("0.005")
    ) -> List[MarketInfo]:
        """
        Find markets with YES+NO arbitrage opportunities

        Args:
            markets: List of markets
            min_edge: Minimum edge required (default 0.5%)

        Returns:
            Markets with arbitrage opportunities
        """
        opportunities = []

        for market in markets:
            if market.yes_price is None or market.no_price is None:
                continue

            total_cost = market.yes_price + market.no_price
            edge = Decimal("1.0") - total_cost

            if edge >= min_edge:
                opportunities.append(market)
                logger.info(
                    f"Arbitrage opportunity: {market.question[:50]}... "
                    f"Edge: {edge*100:.2f}%"
                )

        return opportunities

    def scan(
        self,
        category: Optional[str] = None,
        min_liquidity: Decimal = Decimal("500"),
        include_arbitrage: bool = True
    ) -> Dict[str, List[MarketInfo]]:
        """
        Comprehensive market scan

        Args:
            category: Filter by category (crypto, esports, or None for all)
            min_liquidity: Minimum liquidity requirement
            include_arbitrage: Whether to scan for arbitrage

        Returns:
            Dictionary with categorized market lists
        """
        self._last_scan = datetime.utcnow()

        # Fetch all markets
        raw_markets = self.fetch_all_markets(limit=200)
        markets = []

        for raw in raw_markets:
            parsed = self.parse_market(raw)
            if parsed and parsed.is_active:
                markets.append(parsed)
                self._cache[parsed.market_id] = parsed

        # Apply liquidity filter
        markets = self.filter_by_liquidity(markets, min_liquidity)

        results = {
            "all": markets,
            "crypto": self.filter_crypto_markets(markets),
            "esports": self.filter_esports_markets(markets),
            "expiring_24h": self.filter_expiring_soon(markets, 24),
        }

        if include_arbitrage:
            results["arbitrage"] = self.find_arbitrage_opportunities(markets)

        logger.info(
            f"Scan complete: {len(markets)} markets, "
            f"{len(results['crypto'])} crypto, "
            f"{len(results.get('arbitrage', []))} arbitrage opportunities"
        )

        return results
