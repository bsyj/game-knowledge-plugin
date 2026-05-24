"""Shim for src.config - plugin-local config stubs.

The kernel modules were originally written against MaiBot's internal
``src.config.config.config_manager``. As a plugin we cannot reach into the host,
so this shim returns a minimal ``ModelConfig`` view. The kernel's embedding
adapter catches the resulting "no embedding model configured" errors and falls
back to the configured ``embedding.dimension`` default — actual embeddings are
provided through the plugin SDK via ``ctx.llm`` elsewhere in the codebase.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ModelInfo:
    name: str = ""
    api_provider: str = ""
    model_identifier: str = ""
    provider: str = ""
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class APIProvider:
    name: str = ""
    client_type: str = "openai"
    base_url: str = ""
    api_key: str = ""
    models: list = field(default_factory=list)


@dataclass
class TaskConfig:
    model_list: List[str] = field(default_factory=list)
    max_tokens: int = 4000
    temperature: float = 0.7
    slow_threshold: float = 300.0


@dataclass
class ModelTaskConfig:
    replyer: TaskConfig = field(default_factory=TaskConfig)
    planner: TaskConfig = field(default_factory=TaskConfig)
    memory: TaskConfig = field(default_factory=TaskConfig)
    utils: TaskConfig = field(default_factory=TaskConfig)
    embedding: TaskConfig = field(default_factory=TaskConfig)


@dataclass
class ModelConfig:
    models: List[ModelInfo] = field(default_factory=list)
    api_providers: List[APIProvider] = field(default_factory=list)
    model_task_config: ModelTaskConfig = field(default_factory=ModelTaskConfig)
    models_dict: Dict[str, Any] = field(default_factory=dict)


class GlobalConfigProxy:
    """Plugin-mode placeholder for the host's config manager.

    Returns empty config objects so the kernel's adapters can run their
    configured fallback paths instead of crashing on missing host config.
    """

    def __init__(self) -> None:
        self._model_config = ModelConfig()
        self._global_config: Any = None

    def get_model_config(self) -> ModelConfig:
        return self._model_config

    def get_global_config(self) -> Any:
        return self._global_config

    def load_model_config(self) -> ModelConfig:
        return self._model_config

    def load_global_config(self) -> Any:
        return self._global_config


global_config = GlobalConfigProxy()
config_manager = GlobalConfigProxy()
