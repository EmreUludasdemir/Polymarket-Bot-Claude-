"""
Pytest configuration and fixtures
"""

import pytest
import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import Mock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def mock_settings():
    """Mock settings fixture"""
    with patch('config.settings.settings') as mock:
        mock.trading.initial_capital = Decimal("500")
        mock.trading.risk_per_trade = Decimal("0.02")
        mock.trading.max_daily_loss = Decimal("0.05")
        mock.trading.max_drawdown = Decimal("0.20")
        mock.trading.min_edge_threshold = Decimal("0.03")
        mock.trading.trade_unit = Decimal("3.0")
        mock.trading.kelly_fraction = Decimal("0.25")
        mock.trading.arb_min_spread = Decimal("0.005")
        mock.operational.paper_trading = True
        mock.operational.log_level = "DEBUG"
        mock.operational.database_path = ":memory:"
        yield mock


@pytest.fixture
def mock_client():
    """Mock Polymarket client fixture"""
    client = Mock()
    client.is_initialized = True
    client.is_paper_mode = True
    client.get_price.return_value = Decimal("0.50")
    client.get_order_book.return_value = {
        "bids": [{"price": "0.48", "size": "100"}],
        "asks": [{"price": "0.52", "size": "100"}]
    }
    client.place_market_order.return_value = {"order_id": "test123", "status": "FILLED"}
    client.place_limit_order.return_value = {"order_id": "test123", "status": "OPEN"}
    return client


@pytest.fixture
def mock_risk_manager():
    """Mock risk manager fixture"""
    from risk.risk_manager import RiskManager, RiskAction, RiskStatus

    manager = Mock(spec=RiskManager)
    manager.can_open_new_position.return_value = True
    manager.get_size_multiplier.return_value = Decimal("1.0")
    manager.check_risk_status.return_value = RiskStatus(
        action=RiskAction.CONTINUE,
        daily_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        current_drawdown=Decimal("0"),
        peak_balance=Decimal("500"),
        current_balance=Decimal("500"),
        open_positions=0,
        consecutive_losses=0,
        message="Trading normally",
        can_trade=True,
        size_multiplier=Decimal("1.0")
    )
    return manager


@pytest.fixture
def mock_position_sizer():
    """Mock position sizer fixture"""
    from risk.position_sizing import PositionSizer, PositionSize

    sizer = Mock(spec=PositionSizer)
    sizer.calculate_position_size.return_value = PositionSize(
        recommended_size=Decimal("10"),
        kelly_fraction=Decimal("0.05"),
        edge=Decimal("0.05"),
        max_allowed=Decimal("25"),
        capped=False,
        shares=Decimal("20"),
        reason="Test position"
    )
    sizer.calculate_arbitrage_size.return_value = PositionSize(
        recommended_size=Decimal("50"),
        kelly_fraction=Decimal("0.02"),
        edge=Decimal("0.02"),
        max_allowed=Decimal("250"),
        capped=False,
        reason="Arbitrage"
    )
    return sizer


@pytest.fixture
def sample_market_data():
    """Sample market data fixture"""
    return {
        "id": "test_market_1",
        "market_id": "test_market_1",
        "condition_id": "condition_123",
        "question": "Will Bitcoin be above $100,000 by January 1, 2025?",
        "tokens": [
            {"token_id": "yes_token_123", "outcome": "Yes", "price": 0.45},
            {"token_id": "no_token_123", "outcome": "No", "price": 0.53}
        ],
        "volume24hr": 50000,
        "liquidity": 10000,
        "active": True
    }


@pytest.fixture
def sample_arbitrage_market():
    """Sample arbitrage opportunity market"""
    return {
        "id": "arb_market_1",
        "market_id": "arb_market_1",
        "question": "Test arbitrage market",
        "yes_token_id": "yes_arb_123",
        "no_token_id": "no_arb_123",
        "tokens": [
            {"token_id": "yes_arb_123", "outcome": "Yes", "price": 0.48},
            {"token_id": "no_arb_123", "outcome": "No", "price": 0.50}
        ]
    }
