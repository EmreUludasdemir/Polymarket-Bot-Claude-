"""
Risk Management Module
Implements stop-loss, drawdown limits, and trading circuit breakers
"""

from decimal import Decimal
from datetime import datetime, date
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from config.settings import settings


class RiskAction(Enum):
    """Actions the risk manager can mandate"""
    CONTINUE = "continue"           # Normal trading
    REDUCE_SIZE = "reduce_size"     # Reduce position sizes by 50%
    STOP_NEW_TRADES = "stop_new"    # No new trades, manage existing
    HALT_ALL = "halt_all"           # Emergency stop all trading


@dataclass
class TradeRecord:
    """Record of a single trade for tracking"""
    trade_id: str
    timestamp: datetime
    market_id: str
    side: str
    entry_price: Decimal
    exit_price: Optional[Decimal] = None
    size: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    is_open: bool = True
    strategy: str = ""


@dataclass
class RiskStatus:
    """Current risk status summary"""
    action: RiskAction
    daily_pnl: Decimal
    total_pnl: Decimal
    current_drawdown: Decimal
    peak_balance: Decimal
    current_balance: Decimal
    open_positions: int
    consecutive_losses: int
    message: str
    can_trade: bool = True
    size_multiplier: Decimal = Decimal("1.0")


class RiskManager:
    """
    Comprehensive risk management for Polymarket trading

    Features:
    - Daily loss limits (5% = $25 for $500 capital)
    - Maximum drawdown protection (20% = $100)
    - Consecutive loss circuit breaker
    - Position-level stop-loss tracking
    - Real-time PnL monitoring

    $500 Capital Risk Parameters:
    - Max daily loss: $25 (5%)
    - Max drawdown: $100 (20%)
    - Max consecutive losses: 3
    - Position stop-loss: 10%

    Usage:
        risk_manager = RiskManager(initial_capital=500)

        # Check before trading
        if risk_manager.can_open_new_position():
            # Execute trade
            pass

        # Record trade result
        risk_manager.record_trade_result(...)

        # Get current status
        status = risk_manager.check_risk_status()
    """

    def __init__(
        self,
        initial_capital: Decimal,
        max_daily_loss_pct: Decimal = Decimal("0.05"),
        max_drawdown_pct: Decimal = Decimal("0.20"),
        max_consecutive_losses: int = 3,
        stop_loss_pct: Decimal = Decimal("0.10")
    ):
        """
        Initialize risk manager

        Args:
            initial_capital: Starting capital in USDC
            max_daily_loss_pct: Maximum daily loss as fraction
            max_drawdown_pct: Maximum drawdown from peak as fraction
            max_consecutive_losses: Max consecutive losses before reducing size
            stop_loss_pct: Default stop-loss percentage per position
        """
        self.initial_capital = initial_capital
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.default_stop_loss_pct = stop_loss_pct

        # Tracking variables
        self.current_balance = initial_capital
        self.peak_balance = initial_capital
        self.daily_pnl = Decimal("0")
        self.total_pnl = Decimal("0")
        self.last_reset_date = date.today()
        self.consecutive_losses = 0
        self.trades: List[TradeRecord] = []
        self.is_halted = False

        # Statistics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

        logger.info(
            f"RiskManager initialized: capital=${initial_capital}, "
            f"max_daily_loss={max_daily_loss_pct*100}%, "
            f"max_drawdown={max_drawdown_pct*100}%"
        )

    def _reset_daily_if_needed(self):
        """Reset daily counters if new day"""
        today = date.today()
        if today > self.last_reset_date:
            logger.info(
                f"New trading day - resetting daily counters. "
                f"Previous day PnL: ${self.daily_pnl:.2f}"
            )
            self.daily_pnl = Decimal("0")
            self.last_reset_date = today

            # Reset consecutive losses on new day (fresh start)
            if self.consecutive_losses > 0:
                logger.info(
                    f"Resetting consecutive losses counter from "
                    f"{self.consecutive_losses} to 0"
                )
                self.consecutive_losses = 0

    def record_trade_result(
        self,
        trade_id: str,
        market_id: str,
        side: str,
        entry_price: Decimal,
        exit_price: Decimal,
        size: Decimal,
        strategy: str = ""
    ) -> RiskAction:
        """
        Record a completed trade and update risk metrics

        Args:
            trade_id: Unique trade identifier
            market_id: Market identifier
            side: "BUY" or "SELL"
            entry_price: Entry price
            exit_price: Exit price
            size: Position size in USDC
            strategy: Strategy name

        Returns:
            RiskAction indicating what bot should do next
        """
        self._reset_daily_if_needed()

        # Calculate PnL
        if side.upper() == "BUY":
            # Bought YES: profit if exit > entry
            pnl = (exit_price - entry_price) * size / entry_price
        else:
            # Sold YES: profit if exit < entry
            pnl = (entry_price - exit_price) * size / entry_price

        # Update balances
        self.current_balance += pnl
        self.daily_pnl += pnl
        self.total_pnl += pnl

        # Update peak balance
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

        # Update trade statistics
        self.total_trades += 1
        is_winner = pnl >= 0

        if is_winner:
            self.winning_trades += 1
            self.consecutive_losses = 0
            logger.info(f"WIN: ${pnl:.2f} | Balance: ${self.current_balance:.2f}")
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            logger.warning(
                f"LOSS: ${pnl:.2f} | Balance: ${self.current_balance:.2f} | "
                f"Consecutive losses: {self.consecutive_losses}"
            )

        # Record trade
        self.trades.append(TradeRecord(
            trade_id=trade_id,
            timestamp=datetime.now(),
            market_id=market_id,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            is_open=False,
            strategy=strategy
        ))

        return self.check_risk_status().action

    def check_risk_status(self) -> RiskStatus:
        """
        Check current risk status and determine required action

        Returns:
            RiskStatus with current metrics and recommended action
        """
        self._reset_daily_if_needed()

        # Calculate limits
        daily_loss_limit = self.initial_capital * self.max_daily_loss_pct
        max_drawdown_amount = self.initial_capital * self.max_drawdown_pct

        # Calculate current drawdown
        if self.peak_balance > 0:
            current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
        else:
            current_drawdown = Decimal("0")

        # Determine action
        action = RiskAction.CONTINUE
        message = "Trading normally"
        can_trade = True
        size_multiplier = Decimal("1.0")

        # Check halt conditions (most severe first)
        if self.is_halted:
            action = RiskAction.HALT_ALL
            message = "Trading halted - manual reset required"
            can_trade = False
            size_multiplier = Decimal("0")

        elif self.current_balance <= self.initial_capital * (1 - self.max_drawdown_pct):
            action = RiskAction.HALT_ALL
            message = f"Maximum drawdown ({self.max_drawdown_pct*100:.0f}%) reached - HALTING"
            self.is_halted = True
            can_trade = False
            size_multiplier = Decimal("0")
            logger.critical(message)

        elif abs(self.daily_pnl) >= daily_loss_limit and self.daily_pnl < 0:
            action = RiskAction.STOP_NEW_TRADES
            message = f"Daily loss limit (${daily_loss_limit:.2f}) reached - stopping new trades"
            can_trade = False
            size_multiplier = Decimal("0")
            logger.warning(message)

        elif self.consecutive_losses >= self.max_consecutive_losses:
            action = RiskAction.REDUCE_SIZE
            message = f"{self.consecutive_losses} consecutive losses - reducing position sizes by 50%"
            can_trade = True
            size_multiplier = Decimal("0.5")
            logger.warning(message)

        elif current_drawdown >= Decimal("0.10"):  # 10% drawdown warning
            action = RiskAction.REDUCE_SIZE
            message = f"Drawdown at {current_drawdown*100:.1f}% - reducing position sizes by 50%"
            can_trade = True
            size_multiplier = Decimal("0.5")
            logger.warning(message)

        return RiskStatus(
            action=action,
            daily_pnl=self.daily_pnl,
            total_pnl=self.total_pnl,
            current_drawdown=current_drawdown,
            peak_balance=self.peak_balance,
            current_balance=self.current_balance,
            open_positions=len([t for t in self.trades if t.is_open]),
            consecutive_losses=self.consecutive_losses,
            message=message,
            can_trade=can_trade,
            size_multiplier=size_multiplier
        )

    def should_close_position(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        side: str,
        stop_loss_pct: Decimal = None
    ) -> bool:
        """
        Check if position should be closed due to stop-loss

        Args:
            entry_price: Original entry price
            current_price: Current market price
            side: "BUY" or "SELL"
            stop_loss_pct: Stop-loss percentage (uses default if None)

        Returns:
            True if stop-loss triggered
        """
        if stop_loss_pct is None:
            stop_loss_pct = self.default_stop_loss_pct

        if side.upper() == "BUY":
            # Long position: close if price dropped too much
            if entry_price > 0:
                loss_pct = (entry_price - current_price) / entry_price
            else:
                loss_pct = Decimal("0")
        else:
            # Short position: close if price rose too much
            if entry_price > 0:
                loss_pct = (current_price - entry_price) / entry_price
            else:
                loss_pct = Decimal("0")

        if loss_pct >= stop_loss_pct:
            logger.warning(
                f"Stop-loss triggered: {loss_pct*100:.1f}% loss "
                f"(threshold: {stop_loss_pct*100:.1f}%)"
            )
            return True

        return False

    def can_open_new_position(self) -> bool:
        """Check if new positions are allowed"""
        status = self.check_risk_status()
        return status.can_trade

    def get_size_multiplier(self) -> Decimal:
        """Get position size multiplier based on risk status"""
        status = self.check_risk_status()
        return status.size_multiplier

    def get_max_position_size(self) -> Decimal:
        """Get maximum allowed position size"""
        base_max = self.current_balance * Decimal("0.05")  # 5% of current balance
        multiplier = self.get_size_multiplier()
        return base_max * multiplier

    def register_open_position(
        self,
        trade_id: str,
        market_id: str,
        side: str,
        entry_price: Decimal,
        size: Decimal,
        strategy: str = ""
    ):
        """Register a new open position for tracking"""
        self.trades.append(TradeRecord(
            trade_id=trade_id,
            timestamp=datetime.now(),
            market_id=market_id,
            side=side,
            entry_price=entry_price,
            size=size,
            is_open=True,
            strategy=strategy
        ))
        logger.debug(f"Position registered: {trade_id}")

    def get_statistics(self) -> Dict:
        """Get trading statistics"""
        win_rate = (
            self.winning_trades / self.total_trades
            if self.total_trades > 0 else 0
        )

        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": float(win_rate),
            "total_pnl": float(self.total_pnl),
            "daily_pnl": float(self.daily_pnl),
            "current_balance": float(self.current_balance),
            "peak_balance": float(self.peak_balance),
            "current_drawdown": float(
                (self.peak_balance - self.current_balance) / self.peak_balance
                if self.peak_balance > 0 else 0
            ),
            "consecutive_losses": self.consecutive_losses,
            "is_halted": self.is_halted
        }

    def reset(self, force: bool = False):
        """
        Manual reset (use with caution)

        Args:
            force: If True, also reset halt status
        """
        logger.warning("Risk manager reset requested")

        if force:
            self.is_halted = False
            logger.warning("Halt status forcefully cleared")

        self.consecutive_losses = 0
        # Don't reset PnL or balance - those are real

    def emergency_halt(self, reason: str = "Manual halt"):
        """Emergency halt all trading"""
        self.is_halted = True
        logger.critical(f"EMERGENCY HALT: {reason}")

    def __str__(self) -> str:
        """String representation of current status"""
        status = self.check_risk_status()
        return (
            f"RiskManager Status:\n"
            f"  Balance: ${status.current_balance:.2f}\n"
            f"  Daily PnL: ${status.daily_pnl:.2f}\n"
            f"  Total PnL: ${status.total_pnl:.2f}\n"
            f"  Drawdown: {status.current_drawdown*100:.1f}%\n"
            f"  Action: {status.action.value}\n"
            f"  Message: {status.message}"
        )


def get_risk_manager() -> RiskManager:
    """Get configured risk manager"""
    return RiskManager(
        initial_capital=settings.trading.initial_capital,
        max_daily_loss_pct=settings.trading.max_daily_loss,
        max_drawdown_pct=settings.trading.max_drawdown
    )
