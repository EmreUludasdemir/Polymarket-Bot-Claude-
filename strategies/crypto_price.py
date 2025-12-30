"""
Crypto Price Market Strategy
Trade BTC/ETH 15-minute up/down prediction markets
Uses technical analysis for probability estimation
"""

from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from loguru import logger

from strategies.base_strategy import (
    BaseStrategy, TradingSignal, SignalType, SignalStrength
)
from data.price_feed import price_feed
from config.settings import settings


class CryptoPriceStrategy(BaseStrategy):
    """
    Crypto Price Prediction Strategy

    Target: BTC/ETH 15-minute or 1-hour up/down markets

    Logic:
    - Use RSI + momentum for direction prediction
    - Calculate probability estimate from technical indicators
    - Trade when our estimate differs from market price by >3%

    Resolution:
    - "Up" if end_price >= start_price
    - "Down" if end_price < start_price
    - Uses Chainlink oracles for settlement

    Technical Indicators Used:
    - RSI (Relative Strength Index): Momentum oscillator
    - Price Momentum: Rate of change
    - Trend Direction: Recent price movement

    $500 Capital Considerations:
    - Conservative 2% risk per trade ($10)
    - Quarter-Kelly sizing
    - Target 5+ edges per day
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_edge = settings.trading.min_edge_threshold  # 3%
        self.rsi_period = 14
        self.momentum_period = 10
        self.price_history: Dict[str, List[float]] = {}  # Symbol -> prices

        # Market identification keywords
        self.crypto_keywords = {
            "btc": ["bitcoin", "btc", "₿"],
            "eth": ["ethereum", "eth", "ether"]
        }
        self.direction_keywords = {
            "up": ["above", "over", "higher", "up", "rise", "increase"],
            "down": ["below", "under", "lower", "down", "fall", "decrease"]
        }

    def get_name(self) -> str:
        return "CryptoPrice"

    def calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """
        Calculate RSI from price series

        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss

        Args:
            prices: List of prices (oldest to newest)
            period: RSI period (default 14)

        Returns:
            RSI value 0-100, or None if insufficient data
        """
        if len(prices) < period + 1:
            return None

        # Calculate price changes
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        # Get recent changes
        recent_changes = changes[-(period):]

        # Separate gains and losses
        gains = [c if c > 0 else 0 for c in recent_changes]
        losses = [-c if c < 0 else 0 for c in recent_changes]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_momentum(self, prices: List[float], period: int = 10) -> Optional[float]:
        """
        Calculate momentum (rate of change)

        Momentum = ((Current - Past) / Past) * 100

        Args:
            prices: Price list
            period: Lookback period

        Returns:
            Momentum percentage, or None if insufficient data
        """
        if len(prices) < period + 1:
            return None

        current = prices[-1]
        previous = prices[-(period + 1)]

        if previous == 0:
            return None

        return ((current - previous) / previous) * 100

    def calculate_volatility(self, prices: List[float], period: int = 20) -> Optional[float]:
        """
        Calculate price volatility (standard deviation of returns)

        Args:
            prices: Price list
            period: Lookback period

        Returns:
            Volatility as percentage, or None
        """
        if len(prices) < period + 1:
            return None

        returns = []
        for i in range(1, min(period + 1, len(prices))):
            if prices[-(i+1)] != 0:
                ret = (prices[-i] - prices[-(i+1)]) / prices[-(i+1)]
                returns.append(ret)

        if not returns:
            return None

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        return (variance ** 0.5) * 100

    def estimate_probability(
        self,
        symbol: str,
        direction: str  # "up" or "down"
    ) -> Optional[Decimal]:
        """
        Estimate probability of price moving up or down

        Uses combination of:
        - RSI (momentum oscillator)
        - Price momentum
        - Recent trend direction
        - Volatility adjustment

        Args:
            symbol: "BTC" or "ETH"
            direction: "up" or "down"

        Returns:
            Probability estimate 0-1, or None if insufficient data
        """
        prices = self.price_history.get(symbol.upper(), [])

        if len(prices) < 20:  # Need at least 20 data points
            return None

        rsi = self.calculate_rsi(prices)
        momentum = self.calculate_momentum(prices)
        volatility = self.calculate_volatility(prices)

        if rsi is None or momentum is None:
            return None

        # Base probability 50%
        prob = 0.50

        # RSI adjustment (0-100 scale)
        # RSI < 30: Oversold -> likely to go up
        # RSI > 70: Overbought -> likely to go down
        if rsi < 30:
            prob += 0.12  # Strong bullish signal
        elif rsi < 40:
            prob += 0.06
        elif rsi > 70:
            prob -= 0.12  # Strong bearish signal
        elif rsi > 60:
            prob -= 0.06

        # Momentum adjustment
        # Positive momentum = bullish, negative = bearish
        if momentum > 2:
            prob += 0.10
        elif momentum > 0.5:
            prob += 0.05
        elif momentum < -2:
            prob -= 0.10
        elif momentum < -0.5:
            prob -= 0.05

        # Trend confirmation (last 3 prices)
        if len(prices) >= 3:
            recent = prices[-3:]
            if recent[-1] > recent[-2] > recent[-3]:
                prob += 0.03  # Uptrend
            elif recent[-1] < recent[-2] < recent[-3]:
                prob -= 0.03  # Downtrend

        # Volatility adjustment
        # High volatility = less certainty, move towards 50%
        if volatility and volatility > 3:
            adjustment = (prob - 0.50) * 0.2
            prob -= adjustment

        # Clamp to reasonable range
        prob = max(0.30, min(0.70, prob))

        # If we're predicting "down", invert the probability
        if direction.lower() == "down":
            prob = 1 - prob

        return Decimal(str(round(prob, 3)))

    def identify_market_type(self, question: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Identify cryptocurrency and direction from market question

        Args:
            question: Market question text

        Returns:
            Tuple of (symbol, direction) or (None, None)
        """
        question_lower = question.lower()

        # Identify symbol
        symbol = None
        for sym, keywords in self.crypto_keywords.items():
            if any(kw in question_lower for kw in keywords):
                symbol = sym.upper()
                break

        if not symbol:
            return None, None

        # Identify direction
        direction = None
        for dir_type, keywords in self.direction_keywords.items():
            if any(kw in question_lower for kw in keywords):
                direction = dir_type
                break

        return symbol, direction

    async def analyze(self, market_data: Dict) -> Optional[TradingSignal]:
        """
        Analyze crypto price market for trading opportunity

        Args:
            market_data: Should contain:
                - question: Market question (e.g., "Will BTC be above $100k?")
                - token_id or tokens: Token information
                - current_price: Market's current YES price (optional)

        Returns:
            TradingSignal if edge found
        """
        try:
            question = market_data.get("question", "")
            market_id = market_data.get("market_id", market_data.get("id", ""))

            # Identify market type
            symbol, direction = self.identify_market_type(question)

            if not symbol or not direction:
                return None

            # Get token ID
            token_id = market_data.get("token_id")
            if not token_id:
                tokens = market_data.get("tokens", [])
                for token in tokens:
                    if token.get("outcome", "").lower() == "yes":
                        token_id = token.get("token_id")
                        break

            if not token_id:
                return None

            # Get current market price
            market_price = market_data.get("current_price")
            if market_price is None:
                market_price = self.client.get_price(token_id)

            if market_price is None:
                return None

            market_price = Decimal(str(market_price))

            # Update price history from external feed
            await self._update_price_history(symbol)

            # Estimate our probability
            estimated_prob = self.estimate_probability(symbol, direction)

            if estimated_prob is None:
                logger.debug(f"Insufficient data for {symbol} probability estimation")
                return None

            # Calculate edge
            edge = estimated_prob - market_price

            if edge < self.min_edge:
                return None

            # Determine signal strength
            if edge >= Decimal("0.10"):
                strength = SignalStrength.VERY_STRONG
            elif edge >= Decimal("0.06"):
                strength = SignalStrength.STRONG
            elif edge >= Decimal("0.04"):
                strength = SignalStrength.MODERATE
            else:
                strength = SignalStrength.WEAK

            # Calculate confidence based on data quality
            prices = self.price_history.get(symbol, [])
            data_quality = min(len(prices) / 50, 1.0)  # More data = more confidence
            confidence = Decimal(str(min(abs(float(edge)) * 3 * data_quality, 0.9)))

            logger.info(
                f"Crypto signal: {symbol} {direction} | "
                f"Our prob: {estimated_prob:.0%}, Market: {market_price:.0%}, "
                f"Edge: {edge:.1%}"
            )

            return TradingSignal(
                signal_type=SignalType.BUY,
                token_id=token_id,
                market_id=market_id,
                price=market_price,
                estimated_prob=estimated_prob,
                confidence=confidence,
                strength=strength,
                reason=(
                    f"{symbol} {direction} prediction: "
                    f"our prob={estimated_prob:.0%}, market={market_price:.0%}, "
                    f"edge={edge:.1%}"
                ),
                metadata={
                    "symbol": symbol,
                    "direction": direction,
                    "edge": edge,
                    "rsi": self.calculate_rsi(self.price_history.get(symbol, [])),
                    "momentum": self.calculate_momentum(self.price_history.get(symbol, [])),
                    "volatility": self.calculate_volatility(self.price_history.get(symbol, [])),
                    "question": question[:100],
                    "strategy": "crypto_price_ta"
                }
            )

        except Exception as e:
            logger.error(f"Error analyzing crypto price market: {e}")
            return None

    async def execute(self, signal: TradingSignal) -> bool:
        """
        Execute crypto price prediction trade

        Args:
            signal: Trading signal with prediction details

        Returns:
            True if trade executed successfully
        """
        try:
            # Calculate position size using Kelly
            position = self.position_sizer.calculate_position_size(
                estimated_prob=signal.estimated_prob,
                market_price=signal.price
            )

            if position.recommended_size == 0:
                logger.warning(
                    f"Position size too small: edge={position.edge:.2%}, "
                    f"reason: {position.reason}"
                )
                return False

            # Apply risk adjustment
            adjusted_size = self.get_adjusted_size(position.recommended_size)

            if adjusted_size == 0:
                logger.warning("Trading restricted by risk manager")
                return False

            logger.info(
                f"Executing crypto trade: ${adjusted_size:.2f} on "
                f"{signal.metadata.get('symbol')} {signal.metadata.get('direction')}"
            )

            # Place order
            order = self.client.place_market_order(
                token_id=signal.token_id,
                side="BUY",
                amount=adjusted_size
            )

            if order:
                # Track position
                self.add_position(
                    market_id=signal.market_id,
                    token_id=signal.token_id,
                    side="BUY",
                    entry_price=signal.price,
                    size=adjusted_size,
                    metadata=signal.metadata
                )

                logger.info(
                    f"Trade executed successfully. "
                    f"Position: ${adjusted_size:.2f} @ {signal.price:.3f}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error executing crypto price trade: {e}")
            return False

    async def _update_price_history(self, symbol: str):
        """
        Update price history from external feed

        Args:
            symbol: "BTC" or "ETH"
        """
        try:
            # Get current price
            current_price = price_feed.get_current_price(symbol)

            if current_price:
                self.update_price(symbol, current_price)

            # Get recent history if we don't have enough
            if len(self.price_history.get(symbol, [])) < 20:
                recent_prices = price_feed.get_recent_prices(symbol, minutes=60)
                for p in recent_prices:
                    self.update_price(symbol, p)

        except Exception as e:
            logger.debug(f"Error updating price history for {symbol}: {e}")

    def update_price(self, symbol: str, price: float):
        """
        Update price history for a symbol

        Args:
            symbol: "BTC" or "ETH"
            price: Current price
        """
        symbol = symbol.upper()

        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(price)

        # Keep last 100 prices
        if len(self.price_history[symbol]) > 100:
            self.price_history[symbol] = self.price_history[symbol][-100:]

    def get_stats(self) -> Dict:
        """Get strategy statistics"""
        base_stats = super().get_stats()

        # Add price history info
        price_info = {}
        for symbol, prices in self.price_history.items():
            if prices:
                price_info[symbol] = {
                    "data_points": len(prices),
                    "current": prices[-1] if prices else None,
                    "rsi": self.calculate_rsi(prices),
                    "momentum": self.calculate_momentum(prices)
                }

        base_stats["price_data"] = price_info
        base_stats["min_edge"] = float(self.min_edge)

        return base_stats
