from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from kernel.core.embedding.api_adapter import EmbeddingAPIAdapter  # noqa: E402


class _FakeLLMProxy:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def embed(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(dict(kwargs))
        return {"success": True, "embedding": [1.0, 2.0, 3.0]}


class _FakePluginContext:
    def __init__(self) -> None:
        self.llm = _FakeLLMProxy()


@pytest.mark.asyncio
async def test_embedding_adapter_uses_sdk_embedding_capability() -> None:
    plugin_ctx = _FakePluginContext()
    adapter = EmbeddingAPIAdapter(default_dimension=3, plugin_ctx=plugin_ctx)

    embedding = await adapter._get_embedding_direct("测试文本")

    assert embedding == [1.0, 2.0, 3.0]
    assert plugin_ctx.llm.calls == [{"text": "测试文本", "task_name": "embedding"}]
