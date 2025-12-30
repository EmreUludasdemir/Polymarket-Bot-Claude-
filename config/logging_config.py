"""
Logging Configuration
Centralized logging setup using Loguru
"""

import sys
from pathlib import Path
from loguru import logger

from config.constants import LOG_FORMAT, LOG_ROTATION, LOG_RETENTION


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    console_output: bool = True
) -> None:
    """
    Configure application logging

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        console_output: Whether to output to console
    """
    # Remove default handler
    logger.remove()

    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Console handler
    if console_output:
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
                   "<level>{message}</level>",
            level=log_level,
            colorize=True
        )

    # Main log file
    logger.add(
        log_path / "polymarket_bot_{time:YYYY-MM-DD}.log",
        format=LOG_FORMAT,
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        level="DEBUG",
        compression="zip"
    )

    # Error log file
    logger.add(
        log_path / "errors_{time:YYYY-MM-DD}.log",
        format=LOG_FORMAT,
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        level="ERROR",
        compression="zip"
    )

    # Trade log file (for audit trail)
    logger.add(
        log_path / "trades_{time:YYYY-MM-DD}.log",
        format=LOG_FORMAT,
        rotation=LOG_ROTATION,
        retention="90 days",  # Keep trades longer
        level="INFO",
        filter=lambda record: "trade" in record["extra"].get("type", ""),
        compression="zip"
    )

    logger.info(f"Logging configured: level={log_level}, dir={log_dir}")


def get_trade_logger():
    """Get a logger instance for trade logging"""
    return logger.bind(type="trade")


def get_strategy_logger(strategy_name: str):
    """Get a logger instance for specific strategy"""
    return logger.bind(strategy=strategy_name)
