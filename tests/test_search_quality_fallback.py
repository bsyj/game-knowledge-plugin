from __future__ import annotations

import sys
import types
from pathlib import Path


_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

sys.modules.setdefault("openai", types.ModuleType("openai"))
json_repair_stub = types.ModuleType("json_repair")
json_repair_stub.repair_json = lambda value, **_: value
sys.modules.setdefault("json_repair", json_repair_stub)

from kernel.core.runtime.sdk_memory_kernel import SDKMemoryKernel
from kernel.core.storage.metadata_store import MetadataStore


def _make_kernel_with_store(store: MetadataStore) -> SDKMemoryKernel:
    kernel = SDKMemoryKernel.__new__(SDKMemoryKernel)
    kernel.metadata_store = store
    return kernel


def test_approved_card_keyword_fallback_hits_exact_title(tmp_path):
    store = MetadataStore(data_dir=tmp_path, db_name="metadata.db")
    store.connect()
    try:
        card = store.upsert_knowledge_card(
            {
                "title": "星辉龙鳞护符合成材料",
                "category": "配方",
                "question": "星辉龙鳞护符怎么合成",
                "answer": "需要星辉龙鳞、金锭和符文核心。",
                "search_terms": ["星辉龙鳞", "护符合成"],
                "aliases": ["星辉护符"],
                "tags": ["SampleGame"],
                "confidence": 0.9,
                "review_status": "approved",
                "valid_status": "active",
                "card_hash": "star_dragon_scale_charm",
            }
        )
        kernel = _make_kernel_with_store(store)

        hits = kernel._approved_card_keyword_fallback(card["title"], limit=5)

        assert hits
        assert hits[0]["metadata"]["card_hash"] == "star_dragon_scale_charm"
        assert hits[0]["metadata"]["title"] == "星辉龙鳞护符合成材料"
        assert hits[0]["source"] == "approved_card_keyword"
    finally:
        store.close()


def test_approved_card_keyword_fallback_splits_natural_question(tmp_path):
    store = MetadataStore(data_dir=tmp_path, db_name="metadata.db")
    store.connect()
    try:
        store.upsert_knowledge_card(
            {
                "title": "海王锭获取方法",
                "category": "攻略",
                "question": "海王锭从哪里获取",
                "answer": "推荐打海洋恐怖地牢 boss，也可以用绿宝石在商店购买。",
                "search_terms": ["海王锭", "海洋恐怖地牢", "绿宝石商店"],
                "aliases": ["海王"],
                "tags": ["SampleGame"],
                "confidence": 0.9,
                "review_status": "approved",
                "valid_status": "active",
                "card_hash": "neptunium_ingot_source",
            }
        )
        store.upsert_knowledge_card(
            {
                "title": "普通铁锭合成",
                "category": "配方",
                "question": "铁锭怎么合成",
                "answer": "烧炼铁矿石即可获得铁锭。",
                "search_terms": ["铁锭"],
                "aliases": [],
                "tags": ["SampleGame"],
                "confidence": 0.9,
                "review_status": "approved",
                "valid_status": "active",
                "card_hash": "iron_ingot_recipe",
            }
        )
        kernel = _make_kernel_with_store(store)

        hits = kernel._approved_card_keyword_fallback("海王锭怎么获得", limit=5)

        assert hits
        assert hits[0]["metadata"]["card_hash"] == "neptunium_ingot_source"
        assert "海王锭获取方法" in hits[0]["content"]
    finally:
        store.close()


def test_broad_single_term_prefers_curated_card_fields(tmp_path):
    store = MetadataStore(data_dir=tmp_path, db_name="metadata.db")
    store.connect()
    try:
        store.upsert_knowledge_card(
            {
                "title": "终有一死建议点到几级",
                "category": "攻略",
                "question": "终有一死等级点到多少合适",
                "answer": "前期不用拉满，按资源情况逐步提升。",
                "search_terms": ["终有一死", "等级"],
                "aliases": [],
                "tags": ["SampleGame"],
                "confidence": 0.85,
                "review_status": "approved",
                "valid_status": "active",
                "card_hash": "undershirt_level_target",
            }
        )
        store.upsert_knowledge_card(
            {
                "title": "普通进度提醒",
                "category": "其他",
                "question": "前期怎么规划",
                "answer": "可以通过刷怪获取经验，提高等级后再补装备。",
                "search_terms": [],
                "aliases": [],
                "tags": ["SampleGame"],
                "confidence": 0.95,
                "review_status": "approved",
                "valid_status": "active",
                "card_hash": "answer_only_level_noise",
            }
        )
        kernel = _make_kernel_with_store(store)

        cards = store.search_knowledge_cards("等级", limit=5)
        hits = kernel._approved_card_keyword_fallback("等级", limit=5)

        assert cards[0]["card_hash"] == "undershirt_level_target"
        assert hits[0]["metadata"]["card_hash"] == "undershirt_level_target"
        assert hits[0]["score"] > hits[1]["score"]
    finally:
        store.close()
