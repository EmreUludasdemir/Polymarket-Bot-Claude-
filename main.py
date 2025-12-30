"""
Polymarket Trading Bot - Main Entry Point
Production-ready automated trading system for $500 capital

Usage:
    python main.py              # Normal operation
    python main.py --paper      # Paper trading mode
    python main.py --debug      # Debug mode with verbose logging
"""

import asyncio
import signal
import sys
import argparse
from decimal import Decimal
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
from loguru import logger

from config.settings import settings
from config.logging_config import setup_logging
from core.client import polymarket_client, PolymarketClientError
from risk.risk_manager import get_risk_manager, RiskAction
from risk.position_sizing import get_position_sizer
from strategies.arbitrage import ArbitrageStrategy
from strategies.crypto_price import CryptoPriceStrategy
from data.market_scanner import MarketScanner
from database.models import init_database


class PolymarketBot:
    """
    Main trading bot orchestrator

    Manages multiple strategies and coordinates:
    - Market scanning
    - Signal generation
    - Trade execution
    - Risk management
    - Performance logging

    Features:
    - Multi-strategy support
    - Real-time risk monitoring
    - Automatic position sizing
    - Database logging
    - Graceful shutdown
    """

    def __init__(self, paper_mode: bool = False, debug: bool = False):
        """
        Initialize the trading bot

        Args:
            paper_mode: Enable paper trading (no real orders)
            debug: Enable debug logging
        """
        self.paper_mode = paper_mode or settings.operational.paper_trading
        self.debug = debug or settings.operational.debug
        self.is_running = False
        self.strategies = []
        self.risk_manager = None
        self.position_sizer = None
        self.market_scanner = None
        self.cycle_count = 0
        self.start_time = None

        # Configure logging
        self._setup_logging()

    def _setup_logging(self):
        """Configure loguru logging"""
        log_level = "DEBUG" if self.debug else settings.operational.log_level
        setup_logging(log_level=log_level)

    def initialize(self) -> bool:
        """
        Initialize all bot components

        Returns:
            True if initialization successful
        """
        logger.info("=" * 60)
        logger.info("POLYMARKET TRADING BOT INITIALIZING")
        logger.info("=" * 60)
        logger.info(f"Mode: {'PAPER TRADING' if self.paper_mode else 'LIVE TRADING'}")
        logger.info(f"Capital: ${settings.trading.initial_capital}")
        logger.info(f"Risk per trade: {settings.trading.risk_per_trade * 100}%")
        logger.info(f"Max daily loss: {settings.trading.max_daily_loss * 100}%")
        logger.info(f"Max drawdown: {settings.trading.max_drawdown * 100}%")
        logger.info("=" * 60)

        # Validate settings
        if not self.paper_mode:
            try:
                settings.validate()
            except ValueError as e:
                logger.error(f"Configuration error: {e}")
                return False

        # Initialize database
        try:
            init_database()
            logger.info("Database initialized")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False

        # Initialize risk management
        self.risk_manager = get_risk_manager()
        self.position_sizer = get_position_sizer()
        logger.info("Risk management initialized")

        # Initialize Polymarket client
        try:
            if not polymarket_client.initialize():
                logger.error("Failed to initialize Polymarket client")
                return False
        except PolymarketClientError as e:
            logger.error(f"Polymarket client error: {e}")
            return False

        # Initialize market scanner
        self.market_scanner = MarketScanner()
        logger.info("Market scanner initialized")

        # Initialize strategies
        self._init_strategies()

        logger.info(f"Initialized {len(self.strategies)} strategies")
        logger.info("Bot initialization complete!")

        return True

    def _init_strategies(self):
        """Initialize trading strategies"""

        # 1. Arbitrage Strategy (primary - low risk)
        arbitrage = ArbitrageStrategy(
            client=polymarket_client,
            risk_manager=self.risk_manager,
            position_sizer=self.position_sizer
        )
        self.strategies.append(arbitrage)
        logger.info(f"Loaded strategy: {arbitrage.get_name()}")

        # 2. Crypto Price Strategy
        crypto_price = CryptoPriceStrategy(
            client=polymarket_client,
            risk_manager=self.risk_manager,
            position_sizer=self.position_sizer
        )
        self.strategies.append(crypto_price)
        logger.info(f"Loaded strategy: {crypto_price.get_name()}")

        # Start all strategies
        for strategy in self.strategies:
            strategy.start()

    async def fetch_markets(self) -> Dict[str, List[Dict]]:
        """
        Fetch and categorize markets

        Returns:
            Dictionary with categorized market lists
        """
        try:
            # Use market scanner for comprehensive scan
            markets = self.market_scanner.scan(
                min_liquidity=Decimal("500"),
                include_arbitrage=True
            )

            logger.debug(
                f"Markets: {len(markets.get('all', []))} total, "
                f"{len(markets.get('crypto', []))} crypto, "
                f"{len(markets.get('arbitrage', []))} arbitrage opportunities"
            )

            return markets

        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return {"all": [], "crypto": [], "arbitrage": []}

    async def run_trading_cycle(self):
        """Execute one full trading cycle"""
        self.cycle_count += 1

        # Check risk status first
        risk_status = self.risk_manager.check_risk_status()

        if risk_status.action == RiskAction.HALT_ALL:
            logger.critical(f"Trading HALTED: {risk_status.message}")
            return

        if risk_status.action == RiskAction.STOP_NEW_TRADES:
            logger.warning(f"New trades stopped: {risk_status.message}")
            # Still check existing positions
            await self._check_positions()
            return

        # Fetch markets
        markets = await self.fetch_markets()

        if not markets.get("all"):
            logger.debug("No markets available")
            return

        # Run Arbitrage strategy on arbitrage opportunities
        arb_markets = markets.get("arbitrage", [])
        if arb_markets and self.strategies:
            arb_strategy = next(
                (s for s in self.strategies if s.get_name() == "Arbitrage"),
                None
            )
            if arb_strategy:
                # Convert MarketInfo to dict for strategy
                arb_dicts = [
                    {
                        "market_id": m.market_id if hasattr(m, 'market_id') else m.get("market_id"),
                        "yes_token_id": m.yes_token_id if hasattr(m, 'yes_token_id') else m.get("yes_token_id"),
                        "no_token_id": m.no_token_id if hasattr(m, 'no_token_id') else m.get("no_token_id"),
                        "question": m.question if hasattr(m, 'question') else m.get("question", ""),
                    }
                    for m in arb_markets
                ]
                await arb_strategy.run_cycle(arb_dicts)

        # Run Crypto strategy on crypto markets
        crypto_markets = markets.get("crypto", [])
        if crypto_markets and self.strategies:
            crypto_strategy = next(
                (s for s in self.strategies if s.get_name() == "CryptoPrice"),
                None
            )
            if crypto_strategy:
                crypto_dicts = [
                    {
                        "market_id": m.market_id if hasattr(m, 'market_id') else m.get("market_id"),
                        "question": m.question if hasattr(m, 'question') else m.get("question", ""),
                        "tokens": [
                            {"token_id": m.yes_token_id if hasattr(m, 'yes_token_id') else "", "outcome": "Yes"},
                            {"token_id": m.no_token_id if hasattr(m, 'no_token_id') else "", "outcome": "No"},
                        ] if hasattr(m, 'yes_token_id') else m.get("tokens", []),
                    }
                    for m in crypto_markets
                ]
                await crypto_strategy.run_cycle(crypto_dicts)

        # Check existing positions for stop-losses
        await self._check_positions()

        # Log status periodically
        if self.cycle_count % 30 == 0:  # Every ~minute at 2s intervals
            self._log_status()

    async def _check_positions(self):
        """Check all positions for stop-loss triggers"""
        for strategy in self.strategies:
            triggered = strategy.check_stop_losses()
            for market_id in triggered:
                # Get current price and close position
                position = strategy.active_positions.get(market_id)
                if position and position.current_price:
                    strategy.close_position(market_id, position.current_price)
                    logger.warning(f"Stop-loss closed position in {market_id}")

    def _log_status(self):
        """Log current bot status"""
        risk_status = self.risk_manager.check_risk_status()
        runtime = datetime.now() - self.start_time if self.start_time else None

        logger.info(
            f"\n{'='*50}\n"
            f"BOT STATUS (Cycle #{self.cycle_count})\n"
            f"{'='*50}\n"
            f"Runtime: {runtime}\n"
            f"Balance: ${risk_status.current_balance:.2f}\n"
            f"Daily PnL: ${risk_status.daily_pnl:.2f}\n"
            f"Total PnL: ${risk_status.total_pnl:.2f}\n"
            f"Drawdown: {risk_status.current_drawdown*100:.1f}%\n"
            f"Risk Status: {risk_status.action.value}\n"
            f"{'='*50}"
        )

        for strategy in self.strategies:
            strategy.log_status()

    async def main_loop(self):
        """Main trading loop"""
        logger.info("Starting main trading loop...")
        self.start_time = datetime.now()

        while self.is_running:
            try:
                cycle_start = datetime.now()

                await self.run_trading_cycle()

                # Wait for next cycle
                elapsed = (datetime.now() - cycle_start).total_seconds()
                sleep_time = max(0, settings.operational.poll_interval - elapsed)

                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                logger.info("Main loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()
                await asyncio.sleep(settings.operational.poll_interval)

    def start(self):
        """Start the trading bot"""
        self.is_running = True
        logger.info("Bot started")

        # Run the main loop
        try:
            asyncio.run(self.main_loop())
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the trading bot gracefully"""
        logger.info("Stopping bot...")
        self.is_running = False

        # Stop all strategies
        for strategy in self.strategies:
            strategy.stop()

        # Cancel all open orders
        if not self.paper_mode:
            try:
                polymarket_client.cancel_all_orders()
            except Exception as e:
                logger.error(f"Error cancelling orders: {e}")

        # Log final stats
        self._log_final_stats()

        logger.info("Bot stopped")

    def _log_final_stats(self):
        """Log final trading statistics"""
        risk_status = self.risk_manager.check_risk_status()
        stats = self.risk_manager.get_statistics()
        runtime = datetime.now() - self.start_time if self.start_time else None

        logger.info("=" * 60)
        logger.info("FINAL TRADING STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Runtime: {runtime}")
        logger.info(f"Starting Balance: ${settings.trading.initial_capital}")
        logger.info(f"Final Balance: ${risk_status.current_balance:.2f}")
        logger.info(f"Total PnL: ${risk_status.total_pnl:.2f}")
        logger.info(f"Peak Balance: ${risk_status.peak_balance:.2f}")
        logger.info(f"Max Drawdown: {risk_status.current_drawdown*100:.1f}%")
        logger.info(f"Total Trades: {stats['total_trades']}")
        logger.info(f"Win Rate: {stats['win_rate']*100:.1f}%")

        for strategy in self.strategies:
            strat_stats = strategy.get_stats()
            logger.info(f"\n{strategy.get_name()} Strategy:")
            for key, value in strat_stats.items():
                if key != "name":
                    logger.info(f"  {key}: {value}")

        logger.info("=" * 60)


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    sys.exit(0)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Polymarket Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py              # Normal operation
    python main.py --paper      # Paper trading mode (no real orders)
    python main.py --debug      # Debug mode with verbose logging
    python main.py --paper --debug  # Paper trading with debug
        """
    )

    parser.add_argument(
        "--paper",
        action="store_true",
        help="Enable paper trading mode (no real orders)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to custom config file"
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    # Parse arguments
    args = parse_args()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and initialize bot
    bot = PolymarketBot(
        paper_mode=args.paper,
        debug=args.debug
    )

    if not bot.initialize():
        logger.error("Bot initialization failed")
        sys.exit(1)

    # Start trading
    try:
        bot.start()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
