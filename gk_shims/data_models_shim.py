"""Shim for src.common.data_models.llm_service_data_models."""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LLMServiceResult:
    success: bool = False
    response: str = ""
    reasoning: str = ""
    model: str = ""
    error: str = ""
    content: str = ""
