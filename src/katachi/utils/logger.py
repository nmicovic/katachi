"""
Logging for Katachi.

Katachi logs through loguru but, like any library, doesn't touch the application's logging
setup on import: its messages are disabled until ``logger.enable("katachi")`` is called. The CLI
enables and configures them with :func:`set_log_level`.
"""

import contextlib
import sys

from loguru import logger

logger.disable("katachi")

_handler_id: int | None = None


def set_log_level(level: str) -> None:
    """Show log messages (Katachi's and plugins') at ``level`` and above on stderr; used by the CLI."""
    global _handler_id
    if _handler_id is None:
        # Replace loguru's default handler (id 0) if it is still installed; other handlers are kept
        with contextlib.suppress(ValueError):
            logger.remove(0)
    else:
        logger.remove(_handler_id)
    _handler_id = logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
    )
    logger.enable("katachi")


__all__ = ["logger", "set_log_level"]
