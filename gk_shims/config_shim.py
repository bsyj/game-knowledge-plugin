"""Shim for src.config - plugin-local config stubs."""
from __future__ import annotations
from typing import Any, Optional
from dataclasses import dataclass, field


class GlobalConfigProxy:
    """Proxy that returns itself for attribute access."""
    pass


global_config = GlobalConfigProxy()
config_manager = GlobalConfigProxy()


# Stub model types
@dataclass
class ModelInfo:
    name: str = ""
    provider: str = ""


@dataclass
class APIProvider:
    name: str = ""
    client_type: str = ""
    base_url: str = ""
    api_key: str = ""
    models: list = field(default_factory=list)


@dataclass
class TaskConfig:
    model_list: list = field(default_factory=list)
    max_tokens: int = 4000
    temperature: float = 0.7
    slow_threshold: float = 300.0
