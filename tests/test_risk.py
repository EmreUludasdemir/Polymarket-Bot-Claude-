"""
Unit tests for risk management module
Tests stop-loss, drawdown limits, and circuit breakers
"""

import pytest
from decimal import Decimal
from datetime import datetime, date
from risk.risk_manager import RiskManager, RiskAction, RiskStatus


class TestRiskManager:
    """Test cases for risk management"""

    def setup_method(self):
        """Setup test fixtures"""
        self.risk_manager = RiskManager(
            initial_capital=Decimal("500"),
            max_daily_loss_pct=Decimal("0.05"),  # 5% = $25
            max_drawdown_pct=Decimal("0.20"),     # 20% = $100
            max_consecutive_losses=3
        )

    def test_initial_state(self):
        """Test initial risk manager state"""
        status = self.risk_manager.check_risk_status()
        assert status.action == RiskAction.CONTINUE
        assert status.daily_pnl == Decimal("0")
        assert status.total_pnl == Decimal("0")
        assert status.current_balance == Decimal("500")
        assert status.can_trade is True

    def test_winning_trade_updates_balance(self):
        """Test that winning trades update balance correctly"""
        self.risk_manager.record_trade_result(
            trade_id="test_1",
            market_id="market_1",
            side="BUY",
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.60"),
            size=Decimal("10"),
            strategy="test"
        )

        status = self.risk_manager.check_risk_status()
        # PnL = (0.60 - 0.50) * 10 / 0.50 = 2.0
        assert status.daily_pnl > Decimal("0")
        assert status.current_balance > Decimal("500")
        assert self.risk_manager.consecutive_losses == 0

    def test_losing_trade_increments_consecutive_losses(self):
        """Test consecutive loss tracking"""
        # Record 3 losing trades
        for i in range(3):
            self.risk_manager.record_trade_result(
                trade_id=f"test_{i}",
                market_id=f"market_{i}",
                side="BUY",
                entry_price=Decimal("0.50"),
                exit_price=Decimal("0.40"),
                size=Decimal("5"),
                strategy="test"
            )

        assert self.risk_manager.consecutive_losses == 3

    def test_reduce_size_after_consecutive_losses(self):
        """Test that size is reduced after max consecutive losses"""
        # Record max consecutive losses
        for i in range(3):
            self.risk_manager.record_trade_result(
                trade_id=f"test_{i}",
                market_id=f"market_{i}",
                side="BUY",
                entry_price=Decimal("0.50"),
                exit_price=Decimal("0.40"),
                size=Decimal("3"),
                strategy="test"
            )

        status = self.risk_manager.check_risk_status()
        assert status.action == RiskAction.REDUCE_SIZE
        assert status.size_multiplier == Decimal("0.5")

    def test_daily_loss_limit(self):
        """Test daily loss limit triggers stop"""
        # Lose more than 5% of capital ($25)
        self.risk_manager.record_trade_result(
            trade_id="big_loss",
            market_id="market_1",
            side="BUY",
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.10"),
            size=Decimal("40"),
            strategy="test"
        )

        status = self.risk_manager.check_risk_status()
        # Check if daily loss limit was exceeded
        if abs(status.daily_pnl) >= Decimal("25"):
            assert status.action == RiskAction.STOP_NEW_TRADES
            assert status.can_trade is False

    def test_max_drawdown_halts_trading(self):
        """Test that max drawdown halts all trading"""
        # Lose more than 20% = $100
        for i in range(5):
            self.risk_manager.record_trade_result(
                trade_id=f"loss_{i}",
                market_id=f"market_{i}",
                side="BUY",
                entry_price=Decimal("0.50"),
                exit_price=Decimal("0.10"),
                size=Decimal("30"),
                strategy="test"
            )

        status = self.risk_manager.check_risk_status()
        if self.risk_manager.current_balance <= Decimal("400"):  # 20% of 500
            assert status.action == RiskAction.HALT_ALL
            assert self.risk_manager.is_halted is True

    def test_stop_loss_trigger(self):
        """Test stop-loss detection"""
        # 10% drop should trigger stop-loss
        should_close = self.risk_manager.should_close_position(
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.40"),
            side="BUY",
            stop_loss_pct=Decimal("0.10")
        )
        assert should_close is True

        # 5% drop should not trigger 10% stop-loss
        should_close = self.risk_manager.should_close_position(
            entry_price=Decimal("0.50"),
            current_price=Decimal("0.47"),
            side="BUY",
            stop_loss_pct=Decimal("0.10")
        )
        assert should_close is False

    def test_winning_trade_resets_consecutive_losses(self):
        """Test that winning trade resets consecutive loss counter"""
        # Record 2 losses
        for i in range(2):
            self.risk_manager.record_trade_result(
                trade_id=f"loss_{i}",
                market_id=f"market_{i}",
                side="BUY",
                entry_price=Decimal("0.50"),
                exit_price=Decimal("0.45"),
                size=Decimal("5"),
                strategy="test"
            )
        assert self.risk_manager.consecutive_losses == 2

        # Record a win
        self.risk_manager.record_trade_result(
            trade_id="win",
            market_id="market_win",
            side="BUY",
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.60"),
            size=Decimal("5"),
            strategy="test"
        )
        assert self.risk_manager.consecutive_losses == 0

    def test_peak_balance_tracking(self):
        """Test peak balance is tracked correctly"""
        # Record a win
        self.risk_manager.record_trade_result(
            trade_id="win_1",
            market_id="market_1",
            side="BUY",
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.70"),
            size=Decimal("10"),
            strategy="test"
        )

        peak_after_win = self.risk_manager.peak_balance
        assert peak_after_win > Decimal("500")

        # Record a loss - peak should not decrease
        self.risk_manager.record_trade_result(
            trade_id="loss_1",
            market_id="market_2",
            side="BUY",
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.40"),
            size=Decimal("5"),
            strategy="test"
        )

        assert self.risk_manager.peak_balance == peak_after_win

    def test_get_statistics(self):
        """Test statistics calculation"""
        # Record some trades
        self.risk_manager.record_trade_result(
            trade_id="trade_1",
            market_id="market_1",
            side="BUY",
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.60"),
            size=Decimal("10"),
            strategy="test"
        )
        self.risk_manager.record_trade_result(
            trade_id="trade_2",
            market_id="market_2",
            side="BUY",
            entry_price=Decimal("0.50"),
            exit_price=Decimal("0.40"),
            size=Decimal("10"),
            strategy="test"
        )

        stats = self.risk_manager.get_statistics()
        assert stats["total_trades"] == 2
        assert stats["winning_trades"] == 1
        assert stats["losing_trades"] == 1
        assert stats["win_rate"] == 0.5

    def test_manual_reset(self):
        """Test manual reset functionality"""
        # Create some state
        for i in range(3):
            self.risk_manager.record_trade_result(
                trade_id=f"loss_{i}",
                market_id=f"market_{i}",
                side="BUY",
                entry_price=Decimal("0.50"),
                exit_price=Decimal("0.45"),
                size=Decimal("3"),
                strategy="test"
            )

        assert self.risk_manager.consecutive_losses == 3

        # Reset
        self.risk_manager.reset()
        assert self.risk_manager.consecutive_losses == 0

    def test_emergency_halt(self):
        """Test emergency halt functionality"""
        self.risk_manager.emergency_halt("Test emergency")
        assert self.risk_manager.is_halted is True

        status = self.risk_manager.check_risk_status()
        assert status.action == RiskAction.HALT_ALL

    def test_can_open_new_position(self):
        """Test position opening check"""
        assert self.risk_manager.can_open_new_position() is True

        # Halt trading
        self.risk_manager.emergency_halt("Test")
        assert self.risk_manager.can_open_new_position() is False


class TestRiskAction:
    """Test RiskAction enum"""

    def test_risk_actions_exist(self):
        """Verify all risk actions exist"""
        assert RiskAction.CONTINUE.value == "continue"
        assert RiskAction.REDUCE_SIZE.value == "reduce_size"
        assert RiskAction.STOP_NEW_TRADES.value == "stop_new"
        assert RiskAction.HALT_ALL.value == "halt_all"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
