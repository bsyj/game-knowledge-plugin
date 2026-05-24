"""Shim for src.common.logger - redirects to standard logging."""
import logging


def get_logger(name: str = "plugin.gk") -> logging.Logger:
    """Return a logger that works with MaiBot's IPC log forwarding.

    All loggers under plugin.* namespace are automatically forwarded to the host process.
    """
    # Ensure the logger name starts with plugin.gk so IPC forwarding works
    if not name.startswith("plugin."):
        name = f"plugin.gk.kernel.{name}"
    return logging.getLogger(name)
