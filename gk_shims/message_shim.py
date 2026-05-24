"""Shim for src.services.message_service - delegates to ctx.message capability.

Kernel modules that use `message_api` will call these module-level functions.
The plugin's on_load() should call `set_message_context(ctx)` to enable the bridge.
"""
from __future__ import annotations
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from maibot_sdk.context import PluginContext

_plugin_ctx: Optional["PluginContext"] = None


def set_message_context(ctx: "PluginContext") -> None:
    """Set the plugin context for message API delegation."""
    global _plugin_ctx
    _plugin_ctx = ctx


async def get_messages_by_time_in_chat(chat_id: str, start_time: Any, end_time: Any, limit: int = 100) -> list:
    """Get messages by time range in a specific chat."""
    global _plugin_ctx
    if _plugin_ctx is None:
        return []
    try:
        return await _plugin_ctx.message.get_by_time_in_chat(chat_id, str(start_time), str(end_time)) or []
    except Exception:
        return []


async def build_readable_messages(messages: list, **kwargs: Any) -> str:
    """Build readable text from message list."""
    global _plugin_ctx
    if _plugin_ctx is None:
        return ""
    try:
        return await _plugin_ctx.message.build_readable(messages, **kwargs) or ""
    except Exception:
        return ""


def get_recent_messages(*args: Any, **kwargs: Any) -> list:
    """Stub."""
    return []
