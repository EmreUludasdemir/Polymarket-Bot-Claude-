"""
Position Sizing Module
Implements Kelly Criterion and risk-based position sizing for $500 capital
"""

from decimal import Decimal, ROUND_DOWN
from typing import Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from config.settings import settings


@dataclass
class PositionSize:
    """Position sizing result"""
    recommended_size: Decimal      # Recommended USDC amount
    kelly_fraction: Decimal        # Kelly percentage
    edge: Decimal                  # Calculated edge
    max_allowed: Decimal           # Maximum allowed by risk limits
    capped: bool                   # Whether size was capped
    shares: Decimal = Decimal("0") # Estimated shares at current price
    reason: str = ""               # Explanation of sizing decision


class PositionSizer:
    """
    Position sizing calculator using Kelly Criterion

    For $500 capital:
    - Uses Quarter-Kelly (0.25) by default for safety
    - Caps individual trades at 5% of capital ($25)
    - Minimum trade size: $1 (to avoid dust)

    Kelly Criterion Formula:
        f* = (bp - q) / b

    Where:
        f* = fraction of bankroll to bet
        b = odds received on the bet (payout - 1)
        p = probability of winning
        q = probability of losing (1 - p)

    For binary markets with price p:
        Edge = estimated_prob - market_price
        Kelly = edge / (1 - market_price)
    """

    def __init__(
        self,
        capital: Decimal,
        kelly_fraction: Decimal = Decimal("0.25"),
        max_position_pct: Decimal = Decimal("0.05"),
        min_trade_size: Decimal = Decimal("1.0")
    ):
        """
        Initialize position sizer

        Args:
            capital: Available trading capital in USDC
            kelly_fraction: Fraction of Kelly to use (0.25 = quarter Kelly)
            max_position_pct: Maximum position as fraction of capital
            min_trade_size: Minimum trade size in USDC
        """
        self.capital = capital
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct
        self.min_trade_size = min_trade_size

        logger.info(
            f"PositionSizer initialized: capital=${capital}, "
            f"kelly_fraction={kelly_fraction}, max_position={max_position_pct*100}%"
        )

    def update_capital(self, new_capital: Decimal):
        """Update available capital"""
        self.capital = new_capital
        logger.debug(f"Capital updated to ${new_capital}")

    def calculate_kelly(
        self,
        estimated_prob: Decimal,
        market_price: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate Kelly criterion bet fraction

        Args:
            estimated_prob: Your estimated probability of YES winning (0-1)
            market_price: Current market price for YES (0-1)

        Returns:
            Tuple of (kelly_fraction, edge)
        """
        # Validate inputs
        if not (0 < estimated_prob < 1):
            logger.warning(f"Invalid estimated_prob: {estimated_prob}")
            return Decimal("0"), Decimal("0")

        if not (0 < market_price < 1):
            logger.warning(f"Invalid market_price: {market_price}")
            return Decimal("0"), Decimal("0")

        # No edge if our estimate equals or is less than market price
        if estimated_prob <= market_price:
            return Decimal("0"), Decimal("0")

        # Edge = our_prob - market_prob
        edge = estimated_prob - market_price

        # Full Kelly = edge / (1 - market_price)
        # This represents the optimal fraction of bankroll to bet
        # when buying at market_price for payout of 1
        full_kelly = edge / (Decimal("1") - market_price)

        # Apply Kelly fraction (quarter-Kelly for safety)
        # Quarter-Kelly reduces variance by 75% while only reducing
        # expected growth by 50%
        fractional_kelly = full_kelly * self.kelly_fraction

        return fractional_kelly, edge

    def calculate_position_size(
        self,
        estimated_prob: Decimal,
        market_price: Decimal
    ) -> PositionSize:
        """
        Calculate recommended position size in USDC

        Args:
            estimated_prob: Your probability estimate (0-1)
            market_price: Current YES price (0-1)

        Returns:
            PositionSize dataclass with details
        """
        kelly_frac, edge = self.calculate_kelly(estimated_prob, market_price)

        # Calculate raw position size
        raw_size = self.capital * kelly_frac

        # Calculate maximum allowed size (5% of capital)
        max_allowed = self.capital * self.max_position_pct

        # Apply caps and determine final size
        capped = False
        reason = ""

        if kelly_frac <= 0:
            recommended = Decimal("0")
            reason = "No positive edge detected"
        elif raw_size > max_allowed:
            recommended = max_allowed
            capped = True
            reason = f"Capped at {self.max_position_pct*100}% of capital"
        elif raw_size < self.min_trade_size:
            recommended = Decimal("0")
            reason = f"Size ${raw_size:.2f} below minimum ${self.min_trade_size}"
        else:
            recommended = raw_size
            reason = f"Kelly sizing: {kelly_frac*100:.1f}% of capital"

        # Round down to 2 decimal places
        recommended = recommended.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        # Calculate estimated shares
        shares = Decimal("0")
        if market_price > 0 and recommended > 0:
            shares = (recommended / market_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        return PositionSize(
            recommended_size=recommended,
            kelly_fraction=kelly_frac,
            edge=edge,
            max_allowed=max_allowed,
            capped=capped,
            shares=shares,
            reason=reason
        )

    def calculate_arbitrage_size(
        self,
        yes_price: Decimal,
        no_price: Decimal
    ) -> PositionSize:
        """
        Calculate position size for YES+NO arbitrage

        When YES + NO < 1.0, we can buy both for guaranteed profit.
        For arbitrage, we can use more capital since risk is minimal.

        Args:
            yes_price: Current YES price
            no_price: Current NO price

        Returns:
            PositionSize for arbitrage opportunity
        """
        total_cost = yes_price + no_price

        if total_cost >= Decimal("1.0"):
            # No arbitrage opportunity
            return PositionSize(
                recommended_size=Decimal("0"),
                kelly_fraction=Decimal("0"),
                edge=Decimal("0"),
                max_allowed=Decimal("0"),
                capped=False,
                reason="No arbitrage opportunity (YES + NO >= 1.0)"
            )

        # Edge is the guaranteed profit percentage
        edge = Decimal("1.0") - total_cost

        # For arbitrage, we can use up to 50% of capital
        # Risk is minimal since profit is guaranteed
        max_arb_allocation = self.capital * Decimal("0.5")

        # Size based on edge magnitude
        if edge >= Decimal("0.02"):  # 2%+ edge - larger position
            recommended = max_arb_allocation
            reason = f"Strong arbitrage: {edge*100:.2f}% guaranteed"
        elif edge >= Decimal("0.01"):  # 1-2% edge
            recommended = max_arb_allocation * Decimal("0.5")
            reason = f"Medium arbitrage: {edge*100:.2f}% guaranteed"
        else:  # 0.5-1% edge - small position (may not cover gas)
            recommended = self.capital * edge * Decimal("5")
            reason = f"Small arbitrage: {edge*100:.2f}% (watch gas costs)"

        # Apply cap
        capped = recommended >= max_arb_allocation
        recommended = min(recommended, max_arb_allocation)

        # Round down
        recommended = recommended.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        return PositionSize(
            recommended_size=recommended,
            kelly_fraction=edge,  # Using edge as fraction for arb
            edge=edge,
            max_allowed=max_arb_allocation,
            capped=capped,
            reason=reason
        )

    def calculate_fixed_size(
        self,
        market_price: Decimal
    ) -> PositionSize:
        """
        Calculate position using fixed trade unit (simpler approach)

        Uses TRADE_UNIT from settings instead of Kelly

        Args:
            market_price: Current market price

        Returns:
            PositionSize with fixed amount
        """
        trade_unit = settings.trading.trade_unit
        max_allowed = self.capital * self.max_position_pct

        if trade_unit > max_allowed:
            recommended = max_allowed
            capped = True
        else:
            recommended = trade_unit
            capped = False

        shares = Decimal("0")
        if market_price > 0:
            shares = (recommended / market_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        return PositionSize(
            recommended_size=recommended,
            kelly_fraction=Decimal("0"),  # Not using Kelly
            edge=Decimal("0"),
            max_allowed=max_allowed,
            capped=capped,
            shares=shares,
            reason=f"Fixed unit: ${trade_unit}"
        )

    def validate_position(
        self,
        size: Decimal,
        current_exposure: Decimal = Decimal("0")
    ) -> Tuple[bool, str]:
        """
        Validate if position size is acceptable

        Args:
            size: Proposed position size
            current_exposure: Current total exposure

        Returns:
            Tuple of (is_valid, reason)
        """
        if size <= 0:
            return False, "Position size must be positive"

        if size < self.min_trade_size:
            return False, f"Below minimum trade size (${self.min_trade_size})"

        max_size = self.capital * self.max_position_pct
        if size > max_size:
            return False, f"Exceeds max position size (${max_size})"

        # Check total exposure (existing + new)
        max_total_exposure = self.capital * Decimal("0.3")  # 30% max total exposure
        if current_exposure + size > max_total_exposure:
            return False, f"Total exposure would exceed 30% of capital"

        return True, "Position size valid"


def get_position_sizer() -> PositionSizer:
    """Get configured position sizer for current capital"""
    return PositionSizer(
        capital=settings.trading.initial_capital,
        kelly_fraction=settings.trading.kelly_fraction,
        max_position_pct=Decimal("0.05"),  # 5% max = $25 for $500
        min_trade_size=Decimal("1.0")
    )


# Convenience functions
def calculate_kelly_size(
    estimated_prob: Decimal,
    market_price: Decimal,
    capital: Decimal = None
) -> PositionSize:
    """
    Quick Kelly calculation

    Args:
        estimated_prob: Your probability estimate
        market_price: Current market price
        capital: Override capital (uses settings if None)

    Returns:
        PositionSize
    """
    cap = capital or settings.trading.initial_capital
    sizer = PositionSizer(cap)
    return sizer.calculate_position_size(estimated_prob, market_price)
