"""
Unit tests for trading strategies
Tests arbitrage and crypto price strategies
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from strategies.base_strategy import TradingSignal, SignalType, SignalStrength
from strategies.crypto_price import CryptoPriceStrategy


class TestTradingSignal:
    """Test TradingSignal dataclass"""

    def test_signal_creation(self):
        """Test signal creation"""
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            token_id="test_token",
            market_id="test_market",
            price=Decimal("0.50"),
            estimated_prob=Decimal("0.60"),
            confidence=Decimal("0.80"),
            reason="Test signal"
        )
        assert signal.signal_type == SignalType.BUY
        assert signal.edge == Decimal("0.10")

    def test_signal_edge_calculation(self):
        """Test edge calculation for buy signals"""
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            token_id="test",
            market_id="test",
            price=Decimal("0.45"),
            estimated_prob=Decimal("0.55"),
            confidence=Decimal("0.70"),
            reason="Test"
        )
        assert signal.edge == Decimal("0.10")

    def test_signal_actionable(self):
        """Test signal actionable check"""
        # Actionable signal (edge >= 3%)
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            token_id="test",
            market_id="test",
            price=Decimal("0.50"),
            estimated_prob=Decimal("0.55"),
            confidence=Decimal("0.70"),
            reason="Test"
        )
        assert signal.is_actionable(min_edge=Decimal("0.03")) is True

        # Non-actionable signal (edge < 3%)
        signal_small = TradingSignal(
            signal_type=SignalType.BUY,
            token_id="test",
            market_id="test",
            price=Decimal("0.50"),
            estimated_prob=Decimal("0.51"),
            confidence=Decimal("0.70"),
            reason="Test"
        )
        assert signal_small.is_actionable(min_edge=Decimal("0.03")) is False

    def test_signal_to_dict(self):
        """Test signal serialization"""
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            token_id="test",
            market_id="test",
            price=Decimal("0.50"),
            estimated_prob=Decimal("0.60"),
            confidence=Decimal("0.80"),
            reason="Test"
        )
        d = signal.to_dict()
        assert d["signal_type"] == "buy"
        assert d["edge"] == "0.10"


class TestCryptoPriceStrategy:
    """Test crypto price strategy"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_client = Mock()
        self.mock_client.get_price.return_value = Decimal("0.50")
        self.mock_risk_manager = Mock()
        self.mock_risk_manager.can_open_new_position.return_value = True
        self.mock_risk_manager.get_size_multiplier.return_value = Decimal("1.0")
        self.mock_position_sizer = Mock()

        self.strategy = CryptoPriceStrategy(
            client=self.mock_client,
            risk_manager=self.mock_risk_manager,
            position_sizer=self.mock_position_sizer
        )

    def test_strategy_name(self):
        """Test strategy name"""
        assert self.strategy.get_name() == "CryptoPrice"

    def test_rsi_calculation(self):
        """Test RSI calculation"""
        # Create price series with upward movement
        prices = [100 + i for i in range(20)]
        rsi = self.strategy.calculate_rsi(prices)
        assert rsi is not None
        assert rsi > 50  # Should be bullish

    def test_rsi_insufficient_data(self):
        """Test RSI with insufficient data"""
        prices = [100, 101, 102]
        rsi = self.strategy.calculate_rsi(prices)
        assert rsi is None

    def test_momentum_calculation(self):
        """Test momentum calculation"""
        prices = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120]
        momentum = self.strategy.calculate_momentum(prices)
        assert momentum is not None
        assert momentum > 0  # Positive momentum

    def test_momentum_insufficient_data(self):
        """Test momentum with insufficient data"""
        prices = [100, 101]
        momentum = self.strategy.calculate_momentum(prices, period=10)
        assert momentum is None

    def test_identify_market_type_btc_up(self):
        """Test market type identification - BTC up"""
        question = "Will Bitcoin be above $100,000 by January 1?"
        symbol, direction = self.strategy.identify_market_type(question)
        assert symbol == "BTC"
        assert direction == "up"

    def test_identify_market_type_eth_down(self):
        """Test market type identification - ETH down"""
        question = "Will Ethereum price fall below $3,000?"
        symbol, direction = self.strategy.identify_market_type(question)
        assert symbol == "ETH"
        assert direction == "down"

    def test_identify_market_type_unknown(self):
        """Test market type identification - unknown"""
        question = "Will it rain tomorrow?"
        symbol, direction = self.strategy.identify_market_type(question)
        assert symbol is None or direction is None

    def test_probability_estimation(self):
        """Test probability estimation with price history"""
        # Add price history
        for i in range(30):
            self.strategy.update_price("BTC", 50000 + i * 100)

        prob = self.strategy.estimate_probability("BTC", "up")
        assert prob is not None
        assert Decimal("0.30") <= prob <= Decimal("0.70")

    def test_probability_estimation_insufficient_data(self):
        """Test probability estimation with insufficient data"""
        self.strategy.price_history["BTC"] = [50000, 50100]
        prob = self.strategy.estimate_probability("BTC", "up")
        assert prob is None

    def test_update_price_history(self):
        """Test price history management"""
        for i in range(150):
            self.strategy.update_price("BTC", 50000 + i)

        # Should keep only last 100
        assert len(self.strategy.price_history["BTC"]) == 100

    def test_get_stats(self):
        """Test statistics retrieval"""
        stats = self.strategy.get_stats()
        assert "name" in stats
        assert stats["name"] == "CryptoPrice"
        assert "signals_generated" in stats


class TestSignalStrength:
    """Test SignalStrength enum"""

    def test_strength_values(self):
        """Test signal strength values"""
        assert SignalStrength.WEAK.value == 1
        assert SignalStrength.MODERATE.value == 2
        assert SignalStrength.STRONG.value == 3
        assert SignalStrength.VERY_STRONG.value == 4


class TestSignalType:
    """Test SignalType enum"""

    def test_signal_types(self):
        """Test signal type values"""
        assert SignalType.BUY.value == "buy"
        assert SignalType.SELL.value == "sell"
        assert SignalType.HOLD.value == "hold"
        assert SignalType.CLOSE.value == "close"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
