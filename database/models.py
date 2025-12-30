"""
Database Models for Trade Logging and Analysis
Uses SQLite for simplicity with $500 budget
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Boolean, Text, Index, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import Optional
from pathlib import Path

from config.settings import settings

Base = declarative_base()


class Trade(Base):
    """
    Trade record for performance analysis

    Stores all trade information including entry, exit,
    strategy used, and outcome for analysis.
    """
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Trade identification
    trade_id = Column(String(100), unique=True, nullable=False, index=True)
    market_id = Column(String(100), nullable=False, index=True)
    token_id = Column(String(100), nullable=False)

    # Trade details
    strategy = Column(String(50), nullable=False, index=True)  # arbitrage, crypto_price, etc.
    side = Column(String(10), nullable=False)  # BUY, SELL
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT

    # Pricing
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    size = Column(Float, nullable=False)  # USDC amount

    # Probability estimates (for analysis)
    estimated_prob = Column(Float, nullable=True)
    market_prob = Column(Float, nullable=True)
    edge = Column(Float, nullable=True)

    # Outcome
    pnl = Column(Float, default=0.0)
    pnl_pct = Column(Float, default=0.0)  # PnL as percentage
    is_winner = Column(Boolean, nullable=True)
    status = Column(String(20), default="OPEN", index=True)  # OPEN, CLOSED, CANCELLED

    # Metadata
    reason = Column(Text, nullable=True)  # Why trade was taken
    metadata_json = Column(Text, nullable=True)  # Additional data as JSON
    market_question = Column(Text, nullable=True)  # Market question text

    # Timestamps
    entry_time = Column(DateTime, default=datetime.utcnow, index=True)
    exit_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for common queries
    __table_args__ = (
        Index('idx_trade_strategy_status', 'strategy', 'status'),
        Index('idx_trade_entry_time', 'entry_time'),
    )


class DailyStats(Base):
    """
    Daily performance statistics

    Aggregated daily metrics for performance tracking
    and analysis.
    """
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD

    # Trade metrics
    trades_count = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)

    # PnL metrics
    total_pnl = Column(Float, default=0.0)
    gross_profit = Column(Float, default=0.0)
    gross_loss = Column(Float, default=0.0)

    # Capital tracking
    start_balance = Column(Float, nullable=False)
    end_balance = Column(Float, nullable=False)
    peak_balance = Column(Float, nullable=False)

    # Risk metrics
    max_drawdown = Column(Float, default=0.0)
    max_drawdown_pct = Column(Float, default=0.0)
    largest_win = Column(Float, default=0.0)
    largest_loss = Column(Float, default=0.0)
    average_win = Column(Float, default=0.0)
    average_loss = Column(Float, default=0.0)

    # Strategy breakdown
    arbitrage_trades = Column(Integer, default=0)
    crypto_trades = Column(Integer, default=0)
    arbitrage_pnl = Column(Float, default=0.0)
    crypto_pnl = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)


class MarketSnapshot(Base):
    """
    Price snapshots for analysis

    Historical price data for backtesting and
    market analysis.
    """
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)

    market_id = Column(String(100), nullable=False, index=True)
    token_id = Column(String(100), nullable=False)

    # Prices
    yes_price = Column(Float, nullable=True)
    no_price = Column(Float, nullable=True)
    mid_price = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)

    # Order book depth
    bid_depth = Column(Float, nullable=True)
    ask_depth = Column(Float, nullable=True)

    # Volume
    volume_24h = Column(Float, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_snapshot_market_time', 'market_id', 'timestamp'),
    )


class Position(Base):
    """
    Active position tracking

    Real-time position management with stop-loss
    and take-profit levels.
    """
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    market_id = Column(String(100), nullable=False, index=True)
    token_id = Column(String(100), nullable=False)
    trade_id = Column(String(100), nullable=True)

    # Position details
    side = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    size = Column(Float, nullable=False)
    shares = Column(Float, nullable=True)

    # PnL
    unrealized_pnl = Column(Float, default=0.0)
    unrealized_pnl_pct = Column(Float, default=0.0)

    # Risk levels
    stop_loss_price = Column(Float, nullable=True)
    take_profit_price = Column(Float, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, index=True)
    strategy = Column(String(50), nullable=True)

    # Timestamps
    entry_time = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_position_active', 'is_active', 'strategy'),
    )


class Signal(Base):
    """
    Trading signals log

    Historical log of all signals generated
    for strategy analysis and improvement.
    """
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)

    market_id = Column(String(100), nullable=False, index=True)
    token_id = Column(String(100), nullable=False)

    # Signal details
    strategy = Column(String(50), nullable=False, index=True)
    signal_type = Column(String(20), nullable=False)  # BUY, SELL, HOLD
    strength = Column(Integer, default=2)  # 1-4 scale

    # Analysis
    estimated_prob = Column(Float, nullable=True)
    market_price = Column(Float, nullable=True)
    edge = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)

    # Outcome
    was_executed = Column(Boolean, default=False)
    was_profitable = Column(Boolean, nullable=True)
    reason = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_signal_strategy_time', 'strategy', 'timestamp'),
    )


class ErrorLog(Base):
    """
    Error logging for debugging

    Track errors for system reliability
    improvement.
    """
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Error details
    error_type = Column(String(100), nullable=False, index=True)
    message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)

    # Context
    module = Column(String(100), nullable=True)
    function = Column(String(100), nullable=True)
    market_id = Column(String(100), nullable=True)

    # Severity
    severity = Column(String(20), default="ERROR")  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


# Database initialization functions
def init_database(db_path: str = None) -> "Engine":
    """
    Initialize SQLite database

    Args:
        db_path: Path to database file (uses settings if None)

    Returns:
        SQLAlchemy engine
    """
    path = db_path or settings.operational.database_path

    # Ensure directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{path}",
        echo=False,  # Set to True for SQL debugging
        connect_args={"check_same_thread": False}  # For SQLite
    )

    # Create all tables
    Base.metadata.create_all(engine)

    return engine


def get_session(engine=None):
    """
    Get database session

    Args:
        engine: SQLAlchemy engine (creates new if None)

    Returns:
        Session instance
    """
    if engine is None:
        engine = init_database()

    Session = sessionmaker(bind=engine)
    return Session()


def get_sessionmaker(engine=None):
    """
    Get session factory

    Args:
        engine: SQLAlchemy engine

    Returns:
        Sessionmaker class
    """
    if engine is None:
        engine = init_database()

    return sessionmaker(bind=engine)


# Convenience function for quick queries
class DatabaseManager:
    """
    Simple database manager for common operations
    """

    def __init__(self, db_path: str = None):
        self.engine = init_database(db_path)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self):
        """Get a new session"""
        return self.SessionLocal()

    def close(self):
        """Close engine connections"""
        self.engine.dispose()
