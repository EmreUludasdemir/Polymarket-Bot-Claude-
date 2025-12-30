"""
YES+NO Arbitrage Strategy
Risk-free profit when YES + NO prices sum to less than $1.00
"""

from decimal import Decimal
from typing import Optional, Dict, List
from datetime import datetime
from loguru import logger

from strategies.base_strategy import (
    BaseStrategy, TradingSignal, SignalType, SignalStrength
)
from config.settings import settings


class ArbitrageStrategy(BaseStrategy):
    """
    Binary Complement Arbitrage Strategy

    Logic:
    - When YES_price + NO_price < 1.00, buy both
    - Guaranteed profit = 1.00 - (YES + NO)
    - Low risk, low return (typically 0.5-2%)

    Example:
        YES price = 0.45
        NO price = 0.53
        Total cost = 0.98
        Guaranteed profit = $0.02 per $1 invested (2%)

    $500 Capital Considerations:
    - Use up to 50% of capital per opportunity (low risk)
    - Minimum edge: 0.5% to cover gas costs
    - Expected daily return: $5-10 if opportunities exist

    Risks:
    - Gas costs may eat into small spreads
    - Execution risk (prices may move)
    - Liquidity risk (large orders may move prices)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_spread = settings.trading.arb_min_spread  # 0.5%
        self.opportunities_found = 0
        self.opportunities_executed = 0
        self.total_expected_profit = Decimal("0")

    def get_name(self) -> str:
        return "Arbitrage"

    async def analyze(self, market_data: Dict) -> Optional[TradingSignal]:
        """
        Analyze market for arbitrage opportunity

        Args:
            market_data: Should contain:
                - yes_token_id: Token ID for YES outcome
                - no_token_id: Token ID for NO outcome
                - market_id: Market identifier
                - question: Market question (optional)

        Returns:
            TradingSignal if arbitrage opportunity exists
        """
        try:
            # Extract token IDs
            yes_token_id = market_data.get("yes_token_id")
            no_token_id = market_data.get("no_token_id")
            market_id = market_data.get("market_id", market_data.get("id"))
            question = market_data.get("question", "Unknown market")

            # Try to extract from tokens array if not provided directly
            if not yes_token_id or not no_token_id:
                tokens = market_data.get("tokens", [])
                for token in tokens:
                    outcome = token.get("outcome", "").lower()
                    if outcome == "yes":
                        yes_token_id = token.get("token_id")
                    elif outcome == "no":
                        no_token_id = token.get("token_id")

            if not yes_token_id or not no_token_id:
                return None

            # Get current prices
            yes_price = self.client.get_price(yes_token_id)
            no_price = self.client.get_price(no_token_id)

            if yes_price is None or no_price is None:
                return None

            # Check for arbitrage opportunity
            total_cost = yes_price + no_price
            edge = Decimal("1.0") - total_cost

            if edge < self.min_spread:
                return None

            self.opportunities_found += 1

            # Determine signal strength based on edge
            if edge >= Decimal("0.03"):
                strength = SignalStrength.VERY_STRONG
            elif edge >= Decimal("0.02"):
                strength = SignalStrength.STRONG
            elif edge >= Decimal("0.01"):
                strength = SignalStrength.MODERATE
            else:
                strength = SignalStrength.WEAK

            logger.info(
                f"Arbitrage opportunity in {market_id}: "
                f"YES={yes_price:.3f}, NO={no_price:.3f}, "
                f"Edge={edge*100:.2f}%"
            )

            return TradingSignal(
                signal_type=SignalType.BUY,  # Buy both YES and NO
                token_id=f"{yes_token_id},{no_token_id}",  # Combined tokens
                market_id=market_id,
                price=total_cost,
                estimated_prob=Decimal("1.0"),  # Guaranteed outcome
                confidence=Decimal("1.0"),  # 100% confidence
                strength=strength,
                reason=f"YES+NO arbitrage: {edge*100:.2f}% guaranteed profit",
                metadata={
                    "yes_token_id": yes_token_id,
                    "no_token_id": no_token_id,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "edge": edge,
                    "question": question[:100],
                    "strategy": "binary_arbitrage"
                }
            )

        except Exception as e:
            logger.error(f"Error analyzing arbitrage opportunity: {e}")
            return None

    async def execute(self, signal: TradingSignal) -> bool:
        """
        Execute arbitrage trade - buy both YES and NO

        Args:
            signal: Signal containing both token IDs

        Returns:
            True if both orders executed successfully
        """
        if not signal.metadata:
            logger.error("Signal missing metadata for arbitrage execution")
            return False

        try:
            yes_token_id = signal.metadata["yes_token_id"]
            no_token_id = signal.metadata["no_token_id"]
            yes_price = signal.metadata["yes_price"]
            no_price = signal.metadata["no_price"]
            edge = signal.metadata["edge"]

            # Calculate position size
            position = self.position_sizer.calculate_arbitrage_size(yes_price, no_price)

            if position.recommended_size == 0:
                logger.warning("Position size too small for arbitrage")
                return False

            # Adjust for risk status
            adjusted_size = self.get_adjusted_size(position.recommended_size)

            if adjusted_size == 0:
                logger.warning("Trading restricted by risk manager")
                return False

            # Calculate allocation for each side
            # For arbitrage, we buy equal dollar amounts of YES and NO
            half_size = adjusted_size / 2

            # Calculate shares
            yes_shares = half_size / yes_price
            no_shares = half_size / no_price

            logger.info(
                f"Executing arbitrage: ${adjusted_size:.2f} total "
                f"(${half_size:.2f} each side), edge: {edge*100:.2f}%"
            )

            # Execute both orders
            yes_order = self.client.place_market_order(
                token_id=yes_token_id,
                side="BUY",
                amount=half_size
            )

            no_order = self.client.place_market_order(
                token_id=no_token_id,
                side="BUY",
                amount=half_size
            )

            if yes_order and no_order:
                self.opportunities_executed += 1
                expected_profit = adjusted_size * edge
                self.total_expected_profit += expected_profit

                # Track as a combined position
                self.add_position(
                    market_id=signal.market_id,
                    token_id=signal.token_id,
                    side="ARBITRAGE",
                    entry_price=signal.price,
                    size=adjusted_size,
                    metadata={
                        "yes_token_id": yes_token_id,
                        "no_token_id": no_token_id,
                        "expected_profit": expected_profit,
                        "yes_order_id": yes_order.get("order_id"),
                        "no_order_id": no_order.get("order_id")
                    }
                )

                logger.info(
                    f"Arbitrage executed! "
                    f"Expected profit: ${expected_profit:.4f}"
                )
                return True

            else:
                # Handle partial fill
                if yes_order and not no_order:
                    logger.error("NO order failed - attempting to cancel YES order")
                    if yes_order.get("order_id"):
                        self.client.cancel_order(yes_order["order_id"])
                elif no_order and not yes_order:
                    logger.error("YES order failed - attempting to cancel NO order")
                    if no_order.get("order_id"):
                        self.client.cancel_order(no_order["order_id"])

                logger.error("Failed to execute arbitrage - partial or no fill")
                return False

        except Exception as e:
            logger.error(f"Error executing arbitrage: {e}")
            return False

    def scan_markets_for_arbitrage(
        self,
        markets: List[Dict]
    ) -> List[Dict]:
        """
        Scan multiple markets for arbitrage opportunities

        Args:
            markets: List of market data dictionaries

        Returns:
            List of markets with arbitrage opportunities
        """
        opportunities = []

        for market in markets:
            try:
                # Extract token info
                tokens = market.get("tokens", [])
                yes_token = None
                no_token = None

                for token in tokens:
                    outcome = token.get("outcome", "").lower()
                    if outcome == "yes":
                        yes_token = token
                    elif outcome == "no":
                        no_token = token

                if not yes_token or not no_token:
                    continue

                yes_price = Decimal(str(yes_token.get("price", 0)))
                no_price = Decimal(str(no_token.get("price", 0)))

                if yes_price <= 0 or no_price <= 0:
                    continue

                total_cost = yes_price + no_price
                edge = Decimal("1.0") - total_cost

                if edge >= self.min_spread:
                    opportunities.append({
                        "market_id": market.get("id"),
                        "question": market.get("question", ""),
                        "yes_token_id": yes_token.get("token_id"),
                        "no_token_id": no_token.get("token_id"),
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "edge": edge,
                        "edge_pct": float(edge * 100)
                    })

            except Exception as e:
                logger.debug(f"Error scanning market: {e}")
                continue

        # Sort by edge (highest first)
        opportunities.sort(key=lambda x: x["edge"], reverse=True)

        if opportunities:
            logger.info(
                f"Found {len(opportunities)} arbitrage opportunities, "
                f"best edge: {opportunities[0]['edge_pct']:.2f}%"
            )

        return opportunities

    def get_stats(self) -> Dict:
        """Get strategy statistics"""
        base_stats = super().get_stats()
        base_stats.update({
            "opportunities_found": self.opportunities_found,
            "opportunities_executed": self.opportunities_executed,
            "execution_rate": (
                self.opportunities_executed / self.opportunities_found
                if self.opportunities_found > 0 else 0
            ),
            "total_expected_profit": float(self.total_expected_profit),
            "min_spread": float(self.min_spread)
        })
        return base_stats

    def estimate_gas_breakeven(
        self,
        gas_cost_usdc: Decimal = Decimal("0.01")
    ) -> Decimal:
        """
        Calculate minimum spread needed to break even after gas

        Args:
            gas_cost_usdc: Estimated gas cost in USDC

        Returns:
            Minimum spread as decimal
        """
        # With typical trade size of $50 per side ($100 total)
        # Gas of $0.01 requires 0.01% edge to break even
        typical_size = Decimal("100")
        return gas_cost_usdc / typical_size
