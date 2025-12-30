"""
Polymarket CLOB API Client Wrapper
Handles authentication, order signing, and API communication
"""

import os
from decimal import Decimal
from typing import Optional, Dict, List, Any
from loguru import logger
import requests

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from config.settings import settings
from utils.retry import api_retry, RetryError


class PolymarketClientError(Exception):
    """Custom exception for Polymarket client errors"""
    pass


class PolymarketClient:
    """
    Production-ready Polymarket CLOB API client

    Features:
    - Automatic API credential derivation
    - Order creation and signing
    - Market and limit order support
    - Error handling with retry logic
    - Paper trading mode support

    Usage:
        client = PolymarketClient()
        client.initialize()

        # Place order
        client.place_limit_order(token_id, "BUY", 0.45, 10)
    """

    def __init__(self):
        self._client: Optional[ClobClient] = None
        self._initialized = False
        self._paper_mode = settings.operational.paper_trading

    def initialize(self) -> bool:
        """
        Initialize the CLOB client with wallet credentials

        Returns:
            bool: True if initialization successful

        Raises:
            PolymarketClientError: If initialization fails
        """
        if self._paper_mode:
            logger.info("Initializing in PAPER TRADING mode - no real orders")
            self._initialized = True
            return True

        try:
            # Validate settings
            if not settings.wallet.private_key:
                raise PolymarketClientError("PRIVATE_KEY not configured")

            if not settings.wallet.proxy_wallet_address:
                raise PolymarketClientError("PROXY_WALLET_ADDRESS not configured")

            # Create CLOB client
            self._client = ClobClient(
                host=settings.api.clob_api_url,
                key=settings.wallet.private_key,
                chain_id=settings.api.chain_id,
                signature_type=settings.wallet.signature_type,
                funder=settings.wallet.proxy_wallet_address
            )

            # Derive or create API credentials
            api_creds = self._client.create_or_derive_api_creds()
            self._client.set_api_creds(api_creds)

            self._initialized = True
            logger.info("Polymarket client initialized successfully")
            logger.info(f"Wallet: {settings.wallet.proxy_wallet_address[:10]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Polymarket client: {e}")
            raise PolymarketClientError(f"Initialization failed: {e}")

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_paper_mode(self) -> bool:
        return self._paper_mode

    def _ensure_initialized(self):
        """Ensure client is initialized before operations"""
        if not self._initialized:
            raise PolymarketClientError("Client not initialized. Call initialize() first.")

    @api_retry
    def get_markets(self, limit: int = 100, next_cursor: str = None) -> List[Dict]:
        """
        Fetch available markets from CLOB API

        Args:
            limit: Maximum number of markets to fetch
            next_cursor: Pagination cursor

        Returns:
            List of market dictionaries
        """
        self._ensure_initialized()

        if self._paper_mode:
            return self._get_mock_markets()

        try:
            response = self._client.get_markets(next_cursor=next_cursor)

            if isinstance(response, dict):
                markets = response.get("data", [])
            else:
                markets = response if response else []

            logger.debug(f"Fetched {len(markets)} markets")
            return markets[:limit] if markets else []

        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    @api_retry
    def get_market(self, condition_id: str) -> Optional[Dict]:
        """
        Get specific market by condition ID

        Args:
            condition_id: Market condition ID

        Returns:
            Market dictionary or None
        """
        self._ensure_initialized()

        if self._paper_mode:
            return {"condition_id": condition_id, "question": "Mock market"}

        try:
            return self._client.get_market(condition_id)
        except Exception as e:
            logger.error(f"Failed to get market {condition_id}: {e}")
            return None

    @api_retry
    def get_order_book(self, token_id: str) -> Dict:
        """
        Get order book for a specific token

        Args:
            token_id: The token ID to query

        Returns:
            Order book with bids and asks
        """
        self._ensure_initialized()

        if self._paper_mode:
            return self._get_mock_order_book()

        try:
            book = self._client.get_order_book(token_id)
            return book if book else {"bids": [], "asks": []}
        except Exception as e:
            logger.error(f"Failed to get order book for {token_id}: {e}")
            return {"bids": [], "asks": []}

    def get_price(self, token_id: str) -> Optional[Decimal]:
        """
        Get current mid-price for a token

        Args:
            token_id: The token ID

        Returns:
            Mid-price as Decimal, or None if unavailable
        """
        try:
            book = self.get_order_book(token_id)

            if not book.get("bids") or not book.get("asks"):
                return None

            best_bid = Decimal(str(book["bids"][0]["price"]))
            best_ask = Decimal(str(book["asks"][0]["price"]))

            return (best_bid + best_ask) / 2

        except Exception as e:
            logger.error(f"Failed to get price for {token_id}: {e}")
            return None

    def get_spread(self, token_id: str) -> Optional[Decimal]:
        """
        Get bid-ask spread for a token

        Args:
            token_id: The token ID

        Returns:
            Spread as Decimal, or None
        """
        try:
            book = self.get_order_book(token_id)

            if not book.get("bids") or not book.get("asks"):
                return None

            best_bid = Decimal(str(book["bids"][0]["price"]))
            best_ask = Decimal(str(book["asks"][0]["price"]))

            return best_ask - best_bid

        except Exception as e:
            logger.error(f"Failed to get spread for {token_id}: {e}")
            return None

    def place_limit_order(
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
            Order response or None on failure
        """
        self._ensure_initialized()

        # Validate inputs
        if not (Decimal("0.01") <= price <= Decimal("0.99")):
            logger.error(f"Invalid price {price}: must be between 0.01 and 0.99")
            return None

        if size <= 0:
            logger.error(f"Invalid size {size}: must be positive")
            return None

        if self._paper_mode:
            return self._mock_order(token_id, side, price, size, "LIMIT")

        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=float(price),
                size=float(size),
                side=BUY if side.upper() == "BUY" else SELL
            )

            signed_order = self._client.create_order(order_args)

            # Map order type string to enum
            type_map = {
                "GTC": OrderType.GTC,
                "GTD": OrderType.GTD,
                "FOK": OrderType.FOK
            }

            response = self._client.post_order(
                signed_order,
                type_map.get(order_type, OrderType.GTC)
            )

            logger.info(f"Limit order placed: {side} {size} @ {price}")
            return response

        except Exception as e:
            logger.error(f"Failed to place limit order: {e}")
            return None

    def place_market_order(
        self,
        token_id: str,
        side: str,
        amount: Decimal
    ) -> Optional[Dict]:
        """
        Place a market order (FOK)

        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            amount: USDC amount for BUY, shares for SELL

        Returns:
            Order response or None on failure
        """
        self._ensure_initialized()

        if amount <= 0:
            logger.error(f"Invalid amount {amount}: must be positive")
            return None

        if self._paper_mode:
            # Estimate price for paper trade
            price = self.get_price(token_id) or Decimal("0.50")
            return self._mock_order(token_id, side, price, amount, "MARKET")

        try:
            market_order = MarketOrderArgs(
                token_id=token_id,
                amount=float(amount),
                side=BUY if side.upper() == "BUY" else SELL
            )

            signed_order = self._client.create_market_order(market_order)
            response = self._client.post_order(signed_order, OrderType.FOK)

            logger.info(f"Market order executed: {side} ${amount}")
            return response

        except Exception as e:
            logger.error(f"Failed to place market order: {e}")
            return None

    @api_retry
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order

        Args:
            order_id: The order ID to cancel

        Returns:
            True if cancellation successful
        """
        self._ensure_initialized()

        if self._paper_mode:
            logger.info(f"[PAPER] Order cancelled: {order_id}")
            return True

        try:
            self._client.cancel(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders

        Returns:
            True if successful
        """
        self._ensure_initialized()

        if self._paper_mode:
            logger.info("[PAPER] All orders cancelled")
            return True

        try:
            self._client.cancel_all()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    @api_retry
    def get_open_orders(self) -> List[Dict]:
        """
        Get all open orders

        Returns:
            List of open order dictionaries
        """
        self._ensure_initialized()

        if self._paper_mode:
            return []

        try:
            orders = self._client.get_orders()
            return orders if orders else []
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    @api_retry
    def get_trades(self, limit: int = 100) -> List[Dict]:
        """
        Get trade history

        Args:
            limit: Maximum trades to fetch

        Returns:
            List of trade dictionaries
        """
        self._ensure_initialized()

        if self._paper_mode:
            return []

        try:
            trades = self._client.get_trades()
            return trades[:limit] if trades else []
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def get_balances(self) -> Dict[str, Decimal]:
        """
        Get wallet balances

        Returns:
            Dictionary with token balances
        """
        self._ensure_initialized()

        if self._paper_mode:
            return {"USDC": settings.trading.initial_capital}

        try:
            # This requires custom implementation or Web3
            # Placeholder for balance fetching logic
            return {"USDC": Decimal("0")}
        except Exception as e:
            logger.error(f"Failed to get balances: {e}")
            return {}

    # Mock methods for paper trading
    def _get_mock_markets(self) -> List[Dict]:
        """Generate mock markets for paper trading"""
        return [
            {
                "id": "mock_btc_up",
                "condition_id": "mock_condition_1",
                "question": "Will BTC be above $100,000 on Jan 1?",
                "tokens": [
                    {"token_id": "mock_yes_1", "outcome": "Yes", "price": 0.45},
                    {"token_id": "mock_no_1", "outcome": "No", "price": 0.55}
                ]
            },
            {
                "id": "mock_eth_up",
                "condition_id": "mock_condition_2",
                "question": "Will ETH be above $5,000 on Jan 1?",
                "tokens": [
                    {"token_id": "mock_yes_2", "outcome": "Yes", "price": 0.35},
                    {"token_id": "mock_no_2", "outcome": "No", "price": 0.65}
                ]
            }
        ]

    def _get_mock_order_book(self) -> Dict:
        """Generate mock order book for paper trading"""
        return {
            "bids": [
                {"price": "0.48", "size": "100"},
                {"price": "0.47", "size": "200"},
                {"price": "0.46", "size": "300"}
            ],
            "asks": [
                {"price": "0.52", "size": "100"},
                {"price": "0.53", "size": "200"},
                {"price": "0.54", "size": "300"}
            ]
        }

    def _mock_order(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        order_type: str
    ) -> Dict:
        """Generate mock order response"""
        import uuid
        order_id = str(uuid.uuid4())[:8]
        logger.info(f"[PAPER] {order_type} order: {side} {size} @ {price} (ID: {order_id})")
        return {
            "order_id": order_id,
            "token_id": token_id,
            "side": side,
            "price": str(price),
            "size": str(size),
            "status": "FILLED" if order_type == "MARKET" else "OPEN",
            "paper_trade": True
        }


# Global client instance
polymarket_client = PolymarketClient()
