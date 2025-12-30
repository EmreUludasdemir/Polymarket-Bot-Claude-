"""
Unit tests for Polymarket client
Tests API client functionality in paper trading mode
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch
from core.client import PolymarketClient, PolymarketClientError


class TestPolymarketClient:
    """Test cases for Polymarket client"""

    def setup_method(self):
        """Setup test fixtures"""
        # Create client in paper mode for testing
        with patch('core.client.settings') as mock_settings:
            mock_settings.operational.paper_trading = True
            self.client = PolymarketClient()
            self.client._paper_mode = True
            self.client._initialized = True

    def test_client_initialization(self):
        """Test client initializes correctly"""
        assert self.client.is_initialized is True
        assert self.client.is_paper_mode is True

    def test_get_mock_markets(self):
        """Test mock markets are returned in paper mode"""
        markets = self.client.get_markets(limit=10)
        assert len(markets) > 0
        assert "tokens" in markets[0]

    def test_get_mock_order_book(self):
        """Test mock order book is returned"""
        book = self.client.get_order_book("mock_token")
        assert "bids" in book
        assert "asks" in book
        assert len(book["bids"]) > 0
        assert len(book["asks"]) > 0

    def test_get_price_from_mock_book(self):
        """Test price calculation from mock order book"""
        price = self.client.get_price("mock_token")
        assert price is not None
        assert Decimal("0") < price < Decimal("1")

    def test_place_limit_order_paper_mode(self):
        """Test limit order in paper mode"""
        order = self.client.place_limit_order(
            token_id="mock_token",
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("10")
        )
        assert order is not None
        assert "order_id" in order
        assert order.get("paper_trade") is True

    def test_place_market_order_paper_mode(self):
        """Test market order in paper mode"""
        order = self.client.place_market_order(
            token_id="mock_token",
            side="BUY",
            amount=Decimal("10")
        )
        assert order is not None
        assert "order_id" in order
        assert order.get("status") == "FILLED"

    def test_cancel_order_paper_mode(self):
        """Test order cancellation in paper mode"""
        result = self.client.cancel_order("mock_order_id")
        assert result is True

    def test_cancel_all_orders_paper_mode(self):
        """Test cancel all orders in paper mode"""
        result = self.client.cancel_all_orders()
        assert result is True

    def test_get_open_orders_paper_mode(self):
        """Test get open orders returns empty in paper mode"""
        orders = self.client.get_open_orders()
        assert isinstance(orders, list)

    def test_invalid_price_rejected(self):
        """Test that invalid prices are rejected"""
        # Price too high
        order = self.client.place_limit_order(
            token_id="mock_token",
            side="BUY",
            price=Decimal("1.50"),  # Invalid: > 0.99
            size=Decimal("10")
        )
        assert order is None

        # Price too low
        order = self.client.place_limit_order(
            token_id="mock_token",
            side="BUY",
            price=Decimal("0.001"),  # Invalid: < 0.01
            size=Decimal("10")
        )
        assert order is None

    def test_invalid_size_rejected(self):
        """Test that invalid sizes are rejected"""
        order = self.client.place_limit_order(
            token_id="mock_token",
            side="BUY",
            price=Decimal("0.50"),
            size=Decimal("-10")  # Invalid: negative
        )
        assert order is None

    def test_get_spread(self):
        """Test spread calculation"""
        spread = self.client.get_spread("mock_token")
        assert spread is not None
        assert spread >= Decimal("0")

    def test_get_balances_paper_mode(self):
        """Test balance in paper mode"""
        with patch('core.client.settings') as mock_settings:
            mock_settings.trading.initial_capital = Decimal("500")
            balances = self.client.get_balances()
            assert "USDC" in balances


class TestPolymarketClientErrors:
    """Test error handling in Polymarket client"""

    def test_uninitialized_client_raises_error(self):
        """Test that operations on uninitialized client raise errors"""
        client = PolymarketClient()
        client._initialized = False
        client._paper_mode = False

        with pytest.raises(PolymarketClientError):
            client.get_markets()

    def test_client_error_exception(self):
        """Test PolymarketClientError exception"""
        error = PolymarketClientError("Test error")
        assert str(error) == "Test error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
