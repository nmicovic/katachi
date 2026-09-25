import sys

from loguru import logger

_handler_id: int | None = None


def set_log_level(level: str) -> None:
    """(Re)configure the stderr log handler with the given level."""
    global _handler_id
    if _handler_id is not None:
        logger.remove(_handler_id)
    _handler_id = logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=None,
        level=level,
    )


logger.remove()  # Remove default handler
set_log_level("WARNING")

__all__ = ["logger", "set_log_level"]
