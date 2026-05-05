"""
utils/logger.py — Centralised loguru logger for the agent.
"""
import sys
from pathlib import Path
from loguru import logger

# Remove default handler and add a clean one
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="DEBUG",
    colorize=True,
)

# Also log to file
_log_dir = Path(__file__).parent.parent / "output"
_log_dir.mkdir(parents=True, exist_ok=True)
logger.add(
    str(_log_dir / "agent.log"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="INFO",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
)

__all__ = ["logger"]
