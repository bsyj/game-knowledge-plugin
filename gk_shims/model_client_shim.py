"""Shim for src.llm_models.model_client.base_client."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EmbeddingRequest:
    texts: list = field(default_factory=list)
    model: str = ""


class DummyClientRegistry:
    """Registry stub."""

    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Model client registry not available in plugin mode")


client_registry = DummyClientRegistry()
