"""Production-like smoke tests for auto analysis and review ingestion.

These tests exercise the plugin entry path used in production:
message hook -> auto analysis -> review queue -> approve -> kernel ingest.
External LLM and MaiBot runtime dependencies are replaced with deterministic fakes.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
import types
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, List

import pytest

from config import GameKnowledgePluginConfig
from kernel.core.storage.metadata_store import MetadataStore
from kernel.core.utils.review_queue_service import ReviewQueueService


_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE_NAME = "game_knowledge_plugin_smoke"
if _PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(_PACKAGE_NAME)
    package.__path__ = [str(_PLUGIN_ROOT)]
    sys.modules[_PACKAGE_NAME] = package

_PLUGIN_SPEC = importlib.util.spec_from_file_location(
    f"{_PACKAGE_NAME}.plugin",
    _PLUGIN_ROOT / "plugin.py",
)
assert _PLUGIN_SPEC is not None and _PLUGIN_SPEC.loader is not None
_PLUGIN_MODULE = importlib.util.module_from_spec(_PLUGIN_SPEC)
sys.modules[f"{_PACKAGE_NAME}.plugin"] = _PLUGIN_MODULE
_PLUGIN_SPEC.loader.exec_module(_PLUGIN_MODULE)
GameKnowledgePlugin = _PLUGIN_MODULE.GameKnowledgePlugin


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def analyze_messages(self, messages: List[Dict[str, Any]], *, stream_id: str = "") -> Dict[str, Any]:
        self.calls.append({"messages": messages, "stream_id": stream_id})
        joined = " ".join(str(message.get("content", "")) for message in messages)
        return {
            "cards": [
                {
                    "title": "烟花火箭飞行测试",
                    "category": "机制",
                    "question": "烟花火箭怎么用于鞘翅飞行？",
                    "answer": f"装备鞘翅后在空中使用烟花火箭可以加速飞行。上下文：{joined}",
                    "steps": ["装备鞘翅", "起跳滑翔", "使用烟花火箭"],
                    "tags": ["鞘翅", "烟花"],
                    "search_terms": ["烟花火箭", "鞘翅飞行"],
                    "aliases": ["烟花"],
                    "source_platform": "qq",
                    "source_group_id": "100000001",
                    "source_group_name": "测试游戏群",
                    "confidence": 0.92,
                    "review_status": "pending",
                    "ai_review_status": "approved",
                    "ai_review_reason": "测试用例中的高质量知识",
                    "ai_review_score": 0.95,
                    "valid_status": "active",
                    "answer_type": "guide",
                }
            ]
        }


class FakeKernel:
    def __init__(self, store: Any) -> None:
        self.metadata_store = store
        self.ingested_payloads: List[Dict[str, Any]] = []
        self._ingest_count = 0

    async def ingest_text(self, **kwargs: Any) -> Dict[str, Any]:
        self._ingest_count += 1
        paragraph_hash = f"prod_smoke_paragraph_{self._ingest_count:04d}"
        self.ingested_payloads.append({**kwargs, "paragraph_hash": paragraph_hash})
        return {
            "success": True,
            "stored_ids": [paragraph_hash],
            "skipped_ids": [],
            "paragraph_count": 1,
        }


def _message(index: int, content: str) -> Dict[str, Any]:
    return {
        "message_id": f"msg_{index}",
        "processed_plain_text": content,
        "platform": "qq",
        "user_id": f"user_{index}",
        "timestamp": time.time() + index,
        "message_info": {
            "user_info": {
                "user_id": f"user_{index}",
                "user_nickname": f"玩家{index}",
            },
            "group_info": {
                "group_id": "100000001",
                "group_name": "测试游戏群",
            },
        },
    }


def _configure_plugin(plugin: GameKnowledgePlugin, config: GameKnowledgePluginConfig) -> None:
    plugin.set_plugin_config(config.model_dump(mode="json"))


@pytest.fixture
def production_store() -> Generator[MetadataStore, None, None]:
    with tempfile.TemporaryDirectory(prefix="gk_prod_smoke_") as tmpdir:
        store = MetadataStore(data_dir=tmpdir, db_name="metadata.db")
        store.connect()
        try:
            yield store
        finally:
            store.close()


@pytest.mark.asyncio
async def test_auto_analysis_submit_and_approve_ingests_to_kernel(production_store) -> None:
    plugin = GameKnowledgePlugin()
    config = GameKnowledgePluginConfig()
    config.web.enabled = False
    config.collector.allowed_source_group_ids = ["100000001"]
    config.collector.auto_analyze_threshold = 3
    config.collector.context_length = 10
    config.collector.min_message_length = 2
    _configure_plugin(plugin, config)

    analyzer = FakeAnalyzer()
    kernel = FakeKernel(production_store)
    plugin._kernel = kernel
    plugin._analyzer = analyzer
    plugin._review_queue = ReviewQueueService(
        kernel=kernel,
        allowed_source_group_ids=list(plugin.config.collector.allowed_source_group_ids),
    )

    await plugin.on_message("chat.receive.after_process", _message(1, "鞘翅怎么飞得更远？"))
    await plugin.on_message("chat.receive.after_process", _message(2, "用烟花火箭能加速。"))
    await plugin.on_message("chat.receive.after_process", _message(3, "注意不要用爆炸伤害太高的烟花。"))

    for _ in range(30):
        if not plugin._auto_analyze_tasks:
            break
        await asyncio.sleep(0.05)

    assert len(analyzer.calls) == 1
    assert analyzer.calls[0]["stream_id"]
    assert plugin._message_buffer.get(analyzer.calls[0]["stream_id"], []) == []

    pending_cards = production_store.list_knowledge_cards(status="pending")
    assert len(pending_cards) == 1
    card = pending_cards[0]
    assert card["title"] == "烟花火箭飞行测试"
    assert card["source_group_id"] == "100000001"

    approve_result = await plugin._review_queue.approve_card(
        int(card["id"]),
        reviewed_by="prod_smoke_reviewer",
        allow_self_review=True,
    )

    assert approve_result["success"] is True
    assert approve_result["ingested"] is True
    assert approve_result["paragraph_hash"].startswith("prod_smoke_paragraph_")
    assert len(kernel.ingested_payloads) == 1
    assert "烟花火箭怎么用于鞘翅飞行" in kernel.ingested_payloads[0]["text"]

    approved = production_store.get_knowledge_card_by_id(int(card["id"]))
    assert approved is not None
    assert approved["review_status"] == "approved"
    assert approved["paragraph_hash"] == approve_result["paragraph_hash"]


@pytest.mark.asyncio
async def test_auto_analysis_restores_buffer_when_analyzer_returns_no_cards(production_store) -> None:
    plugin = GameKnowledgePlugin()
    config = GameKnowledgePluginConfig()
    config.collector.allowed_source_group_ids = ["100000001"]
    config.collector.auto_analyze_threshold = 2
    config.collector.min_message_length = 2
    _configure_plugin(plugin, config)

    class EmptyAnalyzer:
        async def analyze_messages(self, messages: List[Dict[str, Any]], *, stream_id: str = "") -> Dict[str, Any]:
            return {"cards": []}

    kernel = FakeKernel(production_store)
    plugin._kernel = kernel
    plugin._analyzer = EmptyAnalyzer()
    plugin._review_queue = ReviewQueueService(
        kernel=kernel,
        allowed_source_group_ids=list(plugin.config.collector.allowed_source_group_ids),
    )

    await plugin.on_message("chat.receive.after_process", _message(1, "这是一条闲聊"))
    await plugin.on_message("chat.receive.after_process", _message(2, "没有可入库知识"))

    for _ in range(30):
        if not plugin._auto_analyze_tasks:
            break
        await asyncio.sleep(0.05)

    assert sum(len(messages) for messages in plugin._message_buffer.values()) == 2
    assert production_store.list_knowledge_cards(status="pending") == []
    assert kernel.ingested_payloads == []
