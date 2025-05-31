import sys

from loguru import logger

logger.remove()  # Remove default handler

logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<bold><level>{message}</level></bold>",
    colorize=True,
    level="INFO",
)
