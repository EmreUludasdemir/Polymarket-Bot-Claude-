"""
Unit tests for position sizing module
Tests Kelly criterion and risk-based position sizing
"""

import pytest
from decimal import Decimal
from risk.position_sizing import PositionSizer, PositionSize


class TestPositionSizer:
    """Test cases for Kelly criterion position sizing"""

    def setup_method(self):
        """Setup test fixtures"""
        self.sizer = PositionSizer(
            capital=Decimal("500"),
            kelly_fraction=Decimal("0.25"),
            max_position_pct=Decimal("0.05"),
            min_trade_size=Decimal("1.0")
        )

    def test_no_edge_returns_zero(self):
        """If estimated prob <= market price, no trade"""
        result = self.sizer.calculate_position_size(
            estimated_prob=Decimal("0.50"),
            market_price=Decimal("0.55")
        )
        assert result.recommended_size == Decimal("0")
        assert result.edge <= Decimal("0")

    def test_positive_edge_returns_position(self):
        """With positive edge, should return position size"""
        result = self.sizer.calculate_position_size(
            estimated_prob=Decimal("0.60"),
            market_price=Decimal("0.50")
        )
        assert result.recommended_size > Decimal("0")
        assert result.edge == Decimal("0.10")

    def test_position_capped_at_max(self):
        """Large edge should still be capped at 5%"""
        result = self.sizer.calculate_position_size(
            estimated_prob=Decimal("0.90"),
            market_price=Decimal("0.10")
        )
        # Max 5% of $500 = $25
        assert result.recommended_size <= Decimal("25.00")
        assert result.capped is True

    def test_kelly_calculation(self):
        """Test Kelly criterion formula"""
        kelly_frac, edge = self.sizer.calculate_kelly(
            estimated_prob=Decimal("0.60"),
            market_price=Decimal("0.50")
        )
        # Edge = 0.60 - 0.50 = 0.10
        assert edge == Decimal("0.10")
        # Full Kelly = 0.10 / 0.50 = 0.20
        # Quarter Kelly = 0.20 * 0.25 = 0.05
        assert abs(kelly_frac - Decimal("0.05")) < Decimal("0.001")

    def test_minimum_trade_size(self):
        """Small positions below minimum should be zero"""
        sizer = PositionSizer(
            capital=Decimal("100"),
            kelly_fraction=Decimal("0.01"),  # Very small fraction
            max_position_pct=Decimal("0.05"),
            min_trade_size=Decimal("5.0")
        )
        result = sizer.calculate_position_size(
            estimated_prob=Decimal("0.52"),
            market_price=Decimal("0.50")
        )
        # Very small edge with small kelly should result in < $5
        assert result.recommended_size == Decimal("0")

    def test_arbitrage_sizing(self):
        """Arbitrage should use larger position"""
        result = self.sizer.calculate_arbitrage_size(
            yes_price=Decimal("0.48"),
            no_price=Decimal("0.50")
        )
        # Edge = 1.0 - 0.98 = 0.02 (2%)
        assert result.edge == Decimal("0.02")
        assert result.recommended_size > Decimal("0")

    def test_no_arbitrage_when_sum_exceeds_one(self):
        """No arbitrage when YES + NO >= 1.0"""
        result = self.sizer.calculate_arbitrage_size(
            yes_price=Decimal("0.55"),
            no_price=Decimal("0.50")
        )
        assert result.recommended_size == Decimal("0")
        assert result.edge <= Decimal("0")

    def test_arbitrage_no_opportunity_at_fair_value(self):
        """No arbitrage at exactly 1.0"""
        result = self.sizer.calculate_arbitrage_size(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.50")
        )
        assert result.recommended_size == Decimal("0")

    def test_capital_update(self):
        """Test capital can be updated"""
        self.sizer.update_capital(Decimal("1000"))
        result = self.sizer.calculate_position_size(
            estimated_prob=Decimal("0.60"),
            market_price=Decimal("0.50")
        )
        # Max should now be 5% of $1000 = $50
        assert result.max_allowed == Decimal("50")

    def test_position_validation(self):
        """Test position validation logic"""
        # Valid position
        is_valid, reason = self.sizer.validate_position(
            size=Decimal("10"),
            current_exposure=Decimal("50")
        )
        assert is_valid is True

        # Too small
        is_valid, reason = self.sizer.validate_position(
            size=Decimal("0.50"),
            current_exposure=Decimal("0")
        )
        assert is_valid is False
        assert "minimum" in reason.lower()

    def test_edge_calculation_at_extremes(self):
        """Test edge calculation at price extremes"""
        # Very low market price
        result = self.sizer.calculate_position_size(
            estimated_prob=Decimal("0.10"),
            market_price=Decimal("0.05")
        )
        assert result.edge == Decimal("0.05")

        # Very high market price
        result = self.sizer.calculate_position_size(
            estimated_prob=Decimal("0.95"),
            market_price=Decimal("0.90")
        )
        assert result.edge == Decimal("0.05")


class TestPositionSizeDataclass:
    """Test PositionSize dataclass"""

    def test_position_size_creation(self):
        """Test PositionSize creation"""
        pos = PositionSize(
            recommended_size=Decimal("10"),
            kelly_fraction=Decimal("0.05"),
            edge=Decimal("0.10"),
            max_allowed=Decimal("25"),
            capped=False
        )
        assert pos.recommended_size == Decimal("10")
        assert pos.capped is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
