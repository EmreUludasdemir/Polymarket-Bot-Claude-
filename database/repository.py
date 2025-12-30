"""
Database Repository
Data access layer for trade and market data
"""

from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine, desc, func
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from loguru import logger

from config.settings import settings


class Repository:
    """
    Data access layer for SQLite database

    Provides CRUD operations for:
    - Trades
    - Positions
    - Daily statistics
    - Market snapshots
    """

    def __init__(self, db_path: str = None):
        """
        Initialize repository

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path or settings.operational.database_path
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.SessionLocal = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        """Get database session context manager"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()

    # Trade operations
    def create_trade(
        self,
        trade_id: str,
        market_id: str,
        token_id: str,
        strategy: str,
        side: str,
        order_type: str,
        entry_price: float,
        size: float,
        reason: str = None,
        metadata: Dict = None
    ) -> bool:
        """
        Record a new trade

        Returns:
            True if successful
        """
        # Import here to avoid circular imports
        from database.models import Trade
        import json

        try:
            with self.get_session() as session:
                trade = Trade(
                    trade_id=trade_id,
                    market_id=market_id,
                    token_id=token_id,
                    strategy=strategy,
                    side=side,
                    order_type=order_type,
                    entry_price=entry_price,
                    size=size,
                    reason=reason,
                    metadata_json=json.dumps(metadata) if metadata else None,
                    status="OPEN"
                )
                session.add(trade)
                logger.info(f"Trade created: {trade_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to create trade: {e}")
            return False

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        pnl: float,
        is_winner: bool
    ) -> bool:
        """
        Close an open trade

        Returns:
            True if successful
        """
        from database.models import Trade

        try:
            with self.get_session() as session:
                trade = session.query(Trade).filter(
                    Trade.trade_id == trade_id
                ).first()

                if not trade:
                    logger.warning(f"Trade not found: {trade_id}")
                    return False

                trade.exit_price = exit_price
                trade.exit_time = datetime.utcnow()
                trade.pnl = pnl
                trade.is_winner = is_winner
                trade.status = "CLOSED"

                logger.info(f"Trade closed: {trade_id}, PnL: ${pnl:.2f}")
                return True

        except Exception as e:
            logger.error(f"Failed to close trade: {e}")
            return False

    def get_open_trades(self, strategy: str = None) -> List[Dict]:
        """Get all open trades"""
        from database.models import Trade

        try:
            with self.get_session() as session:
                query = session.query(Trade).filter(Trade.status == "OPEN")

                if strategy:
                    query = query.filter(Trade.strategy == strategy)

                trades = query.all()
                return [self._trade_to_dict(t) for t in trades]

        except Exception as e:
            logger.error(f"Failed to get open trades: {e}")
            return []

    def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """Get recent trades"""
        from database.models import Trade

        try:
            with self.get_session() as session:
                trades = session.query(Trade).order_by(
                    desc(Trade.entry_time)
                ).limit(limit).all()

                return [self._trade_to_dict(t) for t in trades]

        except Exception as e:
            logger.error(f"Failed to get recent trades: {e}")
            return []

    def _trade_to_dict(self, trade) -> Dict:
        """Convert Trade model to dictionary"""
        import json
        return {
            "trade_id": trade.trade_id,
            "market_id": trade.market_id,
            "token_id": trade.token_id,
            "strategy": trade.strategy,
            "side": trade.side,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "size": trade.size,
            "pnl": trade.pnl,
            "is_winner": trade.is_winner,
            "status": trade.status,
            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
            "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
            "metadata": json.loads(trade.metadata_json) if trade.metadata_json else None
        }

    # Position operations
    def update_position(
        self,
        market_id: str,
        token_id: str,
        side: str,
        entry_price: float,
        size: float,
        current_price: float = None
    ) -> bool:
        """Create or update position"""
        from database.models import Position

        try:
            with self.get_session() as session:
                position = session.query(Position).filter(
                    Position.market_id == market_id,
                    Position.is_active == True
                ).first()

                if position:
                    position.current_price = current_price or position.current_price
                    position.unrealized_pnl = self._calc_unrealized_pnl(
                        position.entry_price,
                        current_price or position.current_price,
                        position.size,
                        position.side
                    )
                    position.updated_at = datetime.utcnow()
                else:
                    position = Position(
                        market_id=market_id,
                        token_id=token_id,
                        side=side,
                        entry_price=entry_price,
                        current_price=current_price or entry_price,
                        size=size,
                        is_active=True
                    )
                    session.add(position)

                return True

        except Exception as e:
            logger.error(f"Failed to update position: {e}")
            return False

    def close_position(self, market_id: str) -> bool:
        """Mark position as closed"""
        from database.models import Position

        try:
            with self.get_session() as session:
                position = session.query(Position).filter(
                    Position.market_id == market_id,
                    Position.is_active == True
                ).first()

                if position:
                    position.is_active = False
                    position.updated_at = datetime.utcnow()
                    return True

                return False

        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return False

    def get_active_positions(self) -> List[Dict]:
        """Get all active positions"""
        from database.models import Position

        try:
            with self.get_session() as session:
                positions = session.query(Position).filter(
                    Position.is_active == True
                ).all()

                return [{
                    "market_id": p.market_id,
                    "token_id": p.token_id,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "size": p.size,
                    "unrealized_pnl": p.unrealized_pnl,
                    "entry_time": p.entry_time.isoformat() if p.entry_time else None
                } for p in positions]

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def _calc_unrealized_pnl(
        self,
        entry: float,
        current: float,
        size: float,
        side: str
    ) -> float:
        """Calculate unrealized PnL"""
        if side.upper() == "BUY":
            return (current - entry) * size / entry
        else:
            return (entry - current) * size / entry

    # Daily stats operations
    def update_daily_stats(
        self,
        pnl: float,
        is_win: bool,
        start_balance: float,
        end_balance: float,
        peak_balance: float
    ) -> bool:
        """Update or create daily statistics"""
        from database.models import DailyStats

        today = date.today().isoformat()

        try:
            with self.get_session() as session:
                stats = session.query(DailyStats).filter(
                    DailyStats.date == today
                ).first()

                if stats:
                    stats.trades_count += 1
                    stats.total_pnl += pnl
                    if is_win:
                        stats.wins += 1
                        stats.largest_win = max(stats.largest_win, pnl)
                    else:
                        stats.losses += 1
                        stats.largest_loss = min(stats.largest_loss, pnl)
                    stats.end_balance = end_balance
                    stats.peak_balance = max(stats.peak_balance, peak_balance)
                    stats.max_drawdown = max(
                        stats.max_drawdown,
                        (stats.peak_balance - end_balance) / stats.peak_balance
                    )
                else:
                    stats = DailyStats(
                        date=today,
                        trades_count=1,
                        wins=1 if is_win else 0,
                        losses=0 if is_win else 1,
                        total_pnl=pnl,
                        start_balance=start_balance,
                        end_balance=end_balance,
                        peak_balance=peak_balance,
                        largest_win=pnl if is_win else 0,
                        largest_loss=pnl if not is_win else 0
                    )
                    session.add(stats)

                return True

        except Exception as e:
            logger.error(f"Failed to update daily stats: {e}")
            return False

    def get_daily_stats(self, days: int = 7) -> List[Dict]:
        """Get recent daily statistics"""
        from database.models import DailyStats

        try:
            with self.get_session() as session:
                stats = session.query(DailyStats).order_by(
                    desc(DailyStats.date)
                ).limit(days).all()

                return [{
                    "date": s.date,
                    "trades": s.trades_count,
                    "wins": s.wins,
                    "losses": s.losses,
                    "win_rate": s.wins / s.trades_count if s.trades_count else 0,
                    "pnl": s.total_pnl,
                    "start_balance": s.start_balance,
                    "end_balance": s.end_balance,
                    "max_drawdown": s.max_drawdown
                } for s in stats]

        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return []

    # Metrics
    def get_performance_metrics(self) -> Dict:
        """Calculate overall performance metrics"""
        from database.models import Trade

        try:
            with self.get_session() as session:
                trades = session.query(Trade).filter(
                    Trade.status == "CLOSED"
                ).all()

                if not trades:
                    return {
                        "total_trades": 0,
                        "win_rate": 0,
                        "total_pnl": 0,
                        "avg_win": 0,
                        "avg_loss": 0,
                        "profit_factor": 0
                    }

                wins = [t for t in trades if t.is_winner]
                losses = [t for t in trades if not t.is_winner]

                total_wins = sum(t.pnl for t in wins) if wins else 0
                total_losses = abs(sum(t.pnl for t in losses)) if losses else 0

                return {
                    "total_trades": len(trades),
                    "wins": len(wins),
                    "losses": len(losses),
                    "win_rate": len(wins) / len(trades) if trades else 0,
                    "total_pnl": sum(t.pnl for t in trades),
                    "avg_win": total_wins / len(wins) if wins else 0,
                    "avg_loss": total_losses / len(losses) if losses else 0,
                    "profit_factor": total_wins / total_losses if total_losses else float('inf')
                }

        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return {}


# Global repository instance
repository = Repository()
