"""
Async Polymarket CLOB Client
Rate-limit aware, production-grade client for CLOB and Gamma APIs
"""

import asyncio
import aiohttp
from decimal import Decimal
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType, ApiCreds
from py_clob_client.order_builder.constants import BUY, SELL

from config.settings import settings
from utils.rate_limiter import get_rate_limiter, MultiEndpointRateLimiter


@dataclass
class MarketInfo:
    """Complete market information from Gamma API"""
    condition_id: str
    question_id: str
    question: str
    description: str
    market_slug: str
    end_date: Optional[datetime]
    tokens: List[Dict[str, Any]]
    yes_token_id: str
    no_token_id: str
    active: bool
    closed: bool
    liquidity: Decimal
    volume_24h: Decimal
    # Rewards info
    rewards_min_size: Optional[Decimal] = None
    rewards_max_spread: Optional[Decimal] = None
    rewards_daily_rate: Optional[Decimal] = None


@dataclass
class OrderBookLevel:
    """Single orderbook level"""
    price: Decimal
    size: Decimal


@dataclass
class OrderBook:
    """Complete orderbook snapshot"""
    token_id: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.best_bid or self.best_ask

    @property
    def spread(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_bps(self) -> Optional[Decimal]:
        """Spread in basis points"""
        if self.spread and self.mid_price and self.mid_price > 0:
            return (self.spread / self.mid_price) * Decimal("10000")
        return None


class AsyncClobClient:
    """
    Async Polymarket CLOB Client with rate limiting

    Features:
    - Rate-limit aware with exponential backoff
    - Gamma API integration for market discovery
    - Async-first design
    - Comprehensive error handling
    """

    def __init__(self, paper_mode: bool = False):
        """
        Initialize async CLOB client

        Args:
            paper_mode: Enable paper trading (no real orders)
        """
        self.paper_mode = paper_mode or settings.operational.paper_trading
        self.rate_limiter = get_rate_limiter()

        self._clob_client: Optional[ClobClient] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False

        # Caches
        self._market_cache: Dict[str, MarketInfo] = {}
        self._orderbook_cache: Dict[str, OrderBook] = {}

    async def initialize(self) -> bool:
        """
        Initialize the client

        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True

        try:
            # Create aiohttp session
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)

            if not self.paper_mode:
                # Validate settings
                if not settings.wallet.private_key:
                    raise ValueError("PRIVATE_KEY not configured")
                if not settings.wallet.proxy_wallet_address:
                    raise ValueError("PROXY_WALLET_ADDRESS not configured")

                # Create sync CLOB client for order signing
                self._clob_client = ClobClient(
                    host=settings.api.clob_api_url,
                    key=settings.wallet.private_key,
                    chain_id=settings.api.chain_id,
                    signature_type=settings.wallet.signature_type,
                    funder=settings.wallet.proxy_wallet_address
                )

                # Derive API credentials
                api_creds = self._clob_client.create_or_derive_api_creds()
                self._clob_client.set_api_creds(api_creds)

            self._initialized = True
            logger.info(
                f"AsyncClobClient initialized "
                f"({'PAPER MODE' if self.paper_mode else 'LIVE'})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize AsyncClobClient: {e}")
            return False

    async def close(self) -> None:
        """Close the client and cleanup resources"""
        if self._session:
            await self._session.close()
            self._session = None
        self._initialized = False
        logger.info("AsyncClobClient closed")

    async def _request(
        self,
        method: str,
        url: str,
        endpoint_type: str = "api",
        **kwargs
    ) -> Dict:
        """
        Make rate-limited HTTP request

        Args:
            method: HTTP method
            url: Request URL
            endpoint_type: Rate limiter endpoint type
            **kwargs: Additional request arguments

        Returns:
            Response JSON
        """
        if not self._session:
            raise RuntimeError("Client not initialized")

        # Rate limit
        await self.rate_limiter.acquire(endpoint_type)

        try:
            async with self._session.request(method, url, **kwargs) as response:
                if response.status == 429:
                    await self.rate_limiter.on_rate_limit_error(endpoint_type)
                    raise Exception("Rate limited")

                response.raise_for_status()
                await self.rate_limiter.on_success(endpoint_type)
                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {e}")
            raise

    # =========================================================================
    # GAMMA API - Market Discovery
    # =========================================================================

    async def get_markets(
        self,
        limit: int = 100,
        active: bool = True,
        closed: bool = False
    ) -> List[MarketInfo]:
        """
        Fetch markets from Gamma API

        Args:
            limit: Maximum markets to fetch
            active: Only active markets
            closed: Include closed markets

        Returns:
            List of MarketInfo objects
        """
        url = f"{settings.api.gamma_api_url}/markets"
        params = {
            "limit": limit,
            "active": str(active).lower(),
            "closed": str(closed).lower()
        }

        try:
            data = await self._request("GET", url, "gamma", params=params)

            markets = []
            for item in data:
                market = self._parse_market(item)
                if market:
                    markets.append(market)
                    self._market_cache[market.condition_id] = market

            logger.debug(f"Fetched {len(markets)} markets from Gamma API")
            return markets

        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    async def get_market(self, condition_id: str) -> Optional[MarketInfo]:
        """
        Get specific market by condition ID

        Args:
            condition_id: Market condition ID

        Returns:
            MarketInfo or None
        """
        # Check cache first
        if condition_id in self._market_cache:
            return self._market_cache[condition_id]

        url = f"{settings.api.gamma_api_url}/markets/{condition_id}"

        try:
            data = await self._request("GET", url, "gamma")
            market = self._parse_market(data)
            if market:
                self._market_cache[condition_id] = market
            return market

        except Exception as e:
            logger.error(f"Failed to fetch market {condition_id}: {e}")
            return None

    def _parse_market(self, data: Dict) -> Optional[MarketInfo]:
        """Parse raw market data into MarketInfo"""
        try:
            tokens = data.get("tokens", [])
            yes_token_id = ""
            no_token_id = ""

            for token in tokens:
                outcome = token.get("outcome", "").lower()
                if outcome == "yes":
                    yes_token_id = token.get("token_id", "")
                elif outcome == "no":
                    no_token_id = token.get("token_id", "")

            if not yes_token_id or not no_token_id:
                return None

            # Parse end date
            end_date = None
            end_str = data.get("end_date_iso") or data.get("endDate")
            if end_str:
                try:
                    end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Parse rewards info if present
            rewards = data.get("rewards", {}) or {}

            return MarketInfo(
                condition_id=data.get("condition_id", ""),
                question_id=data.get("question_id", ""),
                question=data.get("question", ""),
                description=data.get("description", ""),
                market_slug=data.get("market_slug", ""),
                end_date=end_date,
                tokens=tokens,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                active=data.get("active", False),
                closed=data.get("closed", False),
                liquidity=Decimal(str(data.get("liquidity", 0))),
                volume_24h=Decimal(str(data.get("volume24hr", 0))),
                rewards_min_size=Decimal(str(rewards.get("min_size", 0))) if rewards.get("min_size") else None,
                rewards_max_spread=Decimal(str(rewards.get("max_spread", 0))) if rewards.get("max_spread") else None,
                rewards_daily_rate=Decimal(str(rewards.get("rates", [{}])[0].get("rewards_daily_rate", 0))) if rewards.get("rates") else None
            )

        except Exception as e:
            logger.debug(f"Failed to parse market: {e}")
            return None

    # =========================================================================
    # CLOB API - Orderbook
    # =========================================================================

    async def get_orderbook(self, token_id: str) -> OrderBook:
        """
        Get orderbook for a token

        Args:
            token_id: Token ID

        Returns:
            OrderBook object
        """
        url = f"{settings.api.clob_api_url}/book"
        params = {"token_id": token_id}

        try:
            data = await self._request("GET", url, "api", params=params)

            bids = [
                OrderBookLevel(
                    price=Decimal(str(level.get("price", 0))),
                    size=Decimal(str(level.get("size", 0)))
                )
                for level in data.get("bids", [])
            ]
            bids.sort(key=lambda x: x.price, reverse=True)

            asks = [
                OrderBookLevel(
                    price=Decimal(str(level.get("price", 0))),
                    size=Decimal(str(level.get("size", 0)))
                )
                for level in data.get("asks", [])
            ]
            asks.sort(key=lambda x: x.price)

            orderbook = OrderBook(
                token_id=token_id,
                bids=bids,
                asks=asks,
                timestamp=datetime.utcnow()
            )

            self._orderbook_cache[token_id] = orderbook
            return orderbook

        except Exception as e:
            logger.error(f"Failed to fetch orderbook for {token_id}: {e}")
            return OrderBook(token_id=token_id)

    async def get_orderbooks(self, token_ids: List[str]) -> Dict[str, OrderBook]:
        """
        Get orderbooks for multiple tokens concurrently

        Args:
            token_ids: List of token IDs

        Returns:
            Dict mapping token_id to OrderBook
        """
        tasks = [self.get_orderbook(tid) for tid in token_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        orderbooks = {}
        for tid, result in zip(token_ids, results):
            if isinstance(result, OrderBook):
                orderbooks[tid] = result
            else:
                logger.error(f"Failed to get orderbook for {tid}: {result}")
                orderbooks[tid] = OrderBook(token_id=tid)

        return orderbooks

    # =========================================================================
    # CLOB API - Orders
    # =========================================================================

    async def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        order_type: str = "GTC"
    ) -> Optional[Dict]:
        """
        Place a limit order

        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            price: Limit price (0.01 to 0.99)
            size: Number of shares
            order_type: GTC, GTD, or FOK

        Returns:
            Order response or None
        """
        # Validate inputs
        if not (Decimal("0.01") <= price <= Decimal("0.99")):
            logger.error(f"Invalid price {price}: must be between 0.01 and 0.99")
            return None

        if size <= 0:
            logger.error(f"Invalid size {size}: must be positive")
            return None

        if self.paper_mode:
            return self._mock_order(token_id, side, price, size, "LIMIT")

        await self.rate_limiter.acquire("orders")

        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=float(price),
                size=float(size),
                side=BUY if side.upper() == "BUY" else SELL
            )

            signed_order = self._clob_client.create_order(order_args)

            type_map = {
                "GTC": OrderType.GTC,
                "GTD": OrderType.GTD,
                "FOK": OrderType.FOK
            }

            response = self._clob_client.post_order(
                signed_order,
                type_map.get(order_type, OrderType.GTC)
            )

            await self.rate_limiter.on_success("orders")
            logger.info(f"Limit order placed: {side} {size} @ {price}")
            return response

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "429" in error_str:
                await self.rate_limiter.on_rate_limit_error("orders")
            logger.error(f"Failed to place limit order: {e}")
            return None

    async def place_fok_order(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal
    ) -> Optional[Dict]:
        """
        Place a Fill-or-Kill order

        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            price: Limit price
            size: Number of shares

        Returns:
            Order response or None (rejected if not fully fillable)
        """
        return await self.place_limit_order(token_id, side, price, size, "FOK")

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful
        """
        if self.paper_mode:
            logger.info(f"[PAPER] Order cancelled: {order_id}")
            return True

        await self.rate_limiter.acquire("orders")

        try:
            self._clob_client.cancel(order_id)
            await self.rate_limiter.on_success("orders")
            logger.info(f"Order cancelled: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_orders(self, order_ids: List[str]) -> Dict[str, bool]:
        """
        Cancel multiple orders concurrently

        Args:
            order_ids: List of order IDs to cancel

        Returns:
            Dict mapping order_id to success status
        """
        tasks = [self.cancel_order(oid) for oid in order_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            oid: isinstance(result, bool) and result
            for oid, result in zip(order_ids, results)
        }

    async def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders

        Returns:
            True if successful
        """
        if self.paper_mode:
            logger.info("[PAPER] All orders cancelled")
            return True

        await self.rate_limiter.acquire("orders")

        try:
            self._clob_client.cancel_all()
            await self.rate_limiter.on_success("orders")
            logger.info("All orders cancelled")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    async def get_open_orders(self, market: Optional[str] = None) -> List[Dict]:
        """
        Get open orders

        Args:
            market: Optional market filter

        Returns:
            List of open orders
        """
        if self.paper_mode:
            return []

        await self.rate_limiter.acquire("api")

        try:
            if market:
                orders = self._clob_client.get_orders(market=market)
            else:
                orders = self._clob_client.get_orders()

            await self.rate_limiter.on_success("api")
            return orders or []

        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_price(self, token_id: str) -> Optional[Decimal]:
        """Get cached mid-price for a token"""
        book = self._orderbook_cache.get(token_id)
        return book.mid_price if book else None

    def calculate_worst_case_fill(
        self,
        orderbook: OrderBook,
        side: str,
        size: Decimal
    ) -> Tuple[Optional[Decimal], Decimal]:
        """
        Calculate worst-case fill price for a given size

        Args:
            orderbook: Current orderbook
            side: "BUY" or "SELL"
            size: Order size in USDC

        Returns:
            Tuple of (worst_price, fillable_size)
        """
        levels = orderbook.asks if side.upper() == "BUY" else orderbook.bids
        if not levels:
            return None, Decimal("0")

        remaining = size
        total_filled = Decimal("0")
        worst_price = None

        for level in levels:
            level_value = level.price * level.size
            if remaining <= level_value:
                worst_price = level.price
                total_filled += remaining / level.price
                break
            else:
                worst_price = level.price
                total_filled += level.size
                remaining -= level_value

        return worst_price, total_filled

    def _mock_order(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        order_type: str
    ) -> Dict:
        """Generate mock order response for paper trading"""
        import uuid
        order_id = str(uuid.uuid4())[:8]
        logger.info(
            f"[PAPER] {order_type} order: {side} {size} @ {price} "
            f"(ID: {order_id})"
        )
        return {
            "order_id": order_id,
            "token_id": token_id,
            "side": side,
            "price": str(price),
            "size": str(size),
            "status": "LIVE",
            "paper_trade": True
        }

    @property
    def is_initialized(self) -> bool:
        return self._initialized


# Global client instance
_async_clob_client: Optional[AsyncClobClient] = None


async def get_async_clob_client() -> AsyncClobClient:
    """Get or create global async CLOB client"""
    global _async_clob_client
    if _async_clob_client is None:
        _async_clob_client = AsyncClobClient()
        await _async_clob_client.initialize()
    return _async_clob_client
