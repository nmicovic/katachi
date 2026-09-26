"""
Logging for Katachi.

Katachi logs through loguru but, like any library, doesn't touch the application's logging
setup on import: its messages are disabled until ``logger.enable("katachi")`` is called. The CLI
enables and configures them with :func:`set_log_level`.
"""

import sys

from loguru import logger

logger.disable("katachi")

_handler_id: int | None = None


def set_log_level(level: str) -> None:
    """Show Katachi's log messages at ``level`` and above on stderr (used by the CLI)."""
    global _handler_id
    if _handler_id is None:
        # The CLI owns the process: replace loguru's default handler
        logger.remove()
    else:
        logger.remove(_handler_id)
    _handler_id = logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        filter="katachi",
    )
    logger.enable("katachi")


__all__ = ["logger", "set_log_level"]
