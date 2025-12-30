"""
Order Book Module
Manages order book data and provides analysis utilities
"""

from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class OrderLevel:
    """Single order book level"""
    price: Decimal
    size: Decimal
    side: str  # "bid" or "ask"


@dataclass
class OrderBook:
    """Complete order book for a token"""
    token_id: str
    bids: List[OrderLevel] = field(default_factory=list)  # Sorted high to low
    asks: List[OrderLevel] = field(default_factory=list)  # Sorted low to high
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def best_bid(self) -> Optional[Decimal]:
        """Get best (highest) bid price"""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        """Get best (lowest) ask price"""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Get mid-market price"""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.best_bid or self.best_ask

    @property
    def spread(self) -> Optional[Decimal]:
        """Get bid-ask spread"""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_pct(self) -> Optional[Decimal]:
        """Get spread as percentage of mid price"""
        if self.spread and self.mid_price:
            return (self.spread / self.mid_price) * 100
        return None


class OrderBookManager:
    """
    Manages order books for multiple tokens

    Features:
    - Order book caching and updates
    - Spread analysis
    - Depth calculation
    - Slippage estimation
    """

    def __init__(self):
        self._books: Dict[str, OrderBook] = {}
        self._update_callbacks: List[callable] = []

    def update_book(self, token_id: str, raw_book: Dict) -> OrderBook:
        """
        Update order book from raw API data

        Args:
            token_id: Token identifier
            raw_book: Raw order book from API {"bids": [], "asks": []}

        Returns:
            Updated OrderBook
        """
        bids = []
        asks = []

        # Parse bids (sorted high to low)
        for level in raw_book.get("bids", []):
            bids.append(OrderLevel(
                price=Decimal(str(level.get("price", 0))),
                size=Decimal(str(level.get("size", 0))),
                side="bid"
            ))
        bids.sort(key=lambda x: x.price, reverse=True)

        # Parse asks (sorted low to high)
        for level in raw_book.get("asks", []):
            asks.append(OrderLevel(
                price=Decimal(str(level.get("price", 0))),
                size=Decimal(str(level.get("size", 0))),
                side="ask"
            ))
        asks.sort(key=lambda x: x.price)

        book = OrderBook(
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow()
        )

        self._books[token_id] = book

        # Notify callbacks
        for callback in self._update_callbacks:
            try:
                callback(book)
            except Exception as e:
                logger.error(f"Order book callback error: {e}")

        return book

    def get_book(self, token_id: str) -> Optional[OrderBook]:
        """Get cached order book"""
        return self._books.get(token_id)

    def add_update_callback(self, callback: callable):
        """Add callback for order book updates"""
        self._update_callbacks.append(callback)

    def calculate_bid_depth(
        self,
        token_id: str,
        price_range_pct: Decimal = Decimal("0.05")
    ) -> Decimal:
        """
        Calculate total bid depth within price range

        Args:
            token_id: Token identifier
            price_range_pct: Price range from best bid (e.g., 0.05 = 5%)

        Returns:
            Total bid size in range
        """
        book = self._books.get(token_id)
        if not book or not book.bids:
            return Decimal("0")

        best_bid = book.best_bid
        min_price = best_bid * (1 - price_range_pct)

        total = Decimal("0")
        for level in book.bids:
            if level.price >= min_price:
                total += level.size

        return total

    def calculate_ask_depth(
        self,
        token_id: str,
        price_range_pct: Decimal = Decimal("0.05")
    ) -> Decimal:
        """
        Calculate total ask depth within price range

        Args:
            token_id: Token identifier
            price_range_pct: Price range from best ask (e.g., 0.05 = 5%)

        Returns:
            Total ask size in range
        """
        book = self._books.get(token_id)
        if not book or not book.asks:
            return Decimal("0")

        best_ask = book.best_ask
        max_price = best_ask * (1 + price_range_pct)

        total = Decimal("0")
        for level in book.asks:
            if level.price <= max_price:
                total += level.size

        return total

    def estimate_buy_slippage(
        self,
        token_id: str,
        size: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        Estimate slippage for a buy order

        Args:
            token_id: Token identifier
            size: Order size in USDC

        Returns:
            Tuple of (average_price, slippage_pct)
        """
        book = self._books.get(token_id)
        if not book or not book.asks:
            return (Decimal("0"), Decimal("0"))

        remaining = size
        total_cost = Decimal("0")
        total_shares = Decimal("0")

        for level in book.asks:
            level_value = level.price * level.size

            if remaining <= level_value:
                shares = remaining / level.price
                total_cost += remaining
                total_shares += shares
                break
            else:
                total_cost += level_value
                total_shares += level.size
                remaining -= level_value

        if total_shares == 0:
            return (Decimal("0"), Decimal("0"))

        avg_price = total_cost / total_shares
        slippage = ((avg_price - book.best_ask) / book.best_ask) * 100 if book.best_ask else Decimal("0")

        return (avg_price, slippage)

    def estimate_sell_slippage(
        self,
        token_id: str,
        shares: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        Estimate slippage for a sell order

        Args:
            token_id: Token identifier
            shares: Number of shares to sell

        Returns:
            Tuple of (average_price, slippage_pct)
        """
        book = self._books.get(token_id)
        if not book or not book.bids:
            return (Decimal("0"), Decimal("0"))

        remaining = shares
        total_value = Decimal("0")
        total_shares = Decimal("0")

        for level in book.bids:
            if remaining <= level.size:
                total_value += remaining * level.price
                total_shares += remaining
                break
            else:
                total_value += level.size * level.price
                total_shares += level.size
                remaining -= level.size

        if total_shares == 0:
            return (Decimal("0"), Decimal("0"))

        avg_price = total_value / total_shares
        slippage = ((book.best_bid - avg_price) / book.best_bid) * 100 if book.best_bid else Decimal("0")

        return (avg_price, slippage)

    def is_liquid(
        self,
        token_id: str,
        min_depth: Decimal = Decimal("100")
    ) -> bool:
        """
        Check if market is liquid enough to trade

        Args:
            token_id: Token identifier
            min_depth: Minimum depth on each side

        Returns:
            True if market is liquid
        """
        bid_depth = self.calculate_bid_depth(token_id)
        ask_depth = self.calculate_ask_depth(token_id)

        return bid_depth >= min_depth and ask_depth >= min_depth

    def get_imbalance(self, token_id: str) -> Optional[Decimal]:
        """
        Calculate order book imbalance

        Args:
            token_id: Token identifier

        Returns:
            Imbalance ratio (-1 to 1, positive = more bids)
        """
        bid_depth = self.calculate_bid_depth(token_id)
        ask_depth = self.calculate_ask_depth(token_id)

        total = bid_depth + ask_depth
        if total == 0:
            return None

        return (bid_depth - ask_depth) / total


# Global order book manager
orderbook_manager = OrderBookManager()
