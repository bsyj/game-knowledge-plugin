"""Shim for src.services.llm_service - LLM client interface for plugin use.

Provides the same module-level API surface as src.services.llm_service,
but delegates actual LLM calls through the plugin's ctx.llm capability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LLMServiceRequest:
    """Matches src.services.llm_service.LLMServiceRequest."""
    prompt: str = ""
    model: str = ""
    max_tokens: int = 4000
    temperature: float = 0.7
    request_type: str = ""


@dataclass
class LLMGenerationOptions:
    """Matches src.services.llm_service.LLMGenerationOptions."""
    temperature: float = 0.7
    max_tokens: int = 4000
    model: str = ""


@dataclass
class LLMServiceResult:
    """Matches src.common.data_models.llm_service_data_models.LLMServiceResult."""
    success: bool = False
    response: str = ""
    reasoning: str = ""
    model: str = ""
    error: str = ""
    content: str = ""

    @classmethod
    def from_response_result(cls, completion: Dict[str, Any]) -> "LLMServiceResult":
        return cls(
            success=True,
            response=str(completion.get("response", "") or ""),
            reasoning=str(completion.get("reasoning", "") or ""),
            model=str(completion.get("model", "") or ""),
            content=str(completion.get("response", "") or ""),
        )

    @classmethod
    def from_error(cls, error_message: str, error: Any = None) -> "LLMServiceResult":
        return cls(success=False, error=error_message)


class LLMServiceClient:
    """LLM client that wraps the plugin's ctx.llm capability.

    During plugin on_load(), set the context via set_context().
    """

    def __init__(self, task_name: str = "utils", *, plugin_ctx: Any = None, request_type: str = ""):
        self._task_name = task_name
        self._plugin_ctx = plugin_ctx
        self._request_type = request_type

    def set_context(self, ctx: Any) -> None:
        self._plugin_ctx = ctx

    async def generate_response(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        if self._plugin_ctx is None:
            return {"success": False, "error": "LLM context not initialized"}
        try:
            result = await self._plugin_ctx.llm.generate(
                prompt=prompt,
                **{k: v for k, v in kwargs.items() if k in ("model", "temperature", "max_tokens")},
            )
            return result if isinstance(result, dict) else {"success": True, "response": str(result)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# Module-level API (matching src.services.llm_service interface)

def get_available_models() -> Dict[str, Any]:
    """Return available LLM models (stub)."""
    return {}


async def generate(request: LLMServiceRequest, options: LLMGenerationOptions) -> LLMServiceResult:
    """Module-level generate function (stub - use LLMServiceClient instead)."""
    return LLMServiceResult.from_error("generate() not configured in plugin mode. Use LLMServiceClient instead.")


# Re-export for backward compatibility with kernel code
LLMResponse = LLMServiceResult  # alias
