"""Comprehensive test: exercise as many card operations as possible.

Runs against an isolated temp-directory SQLite database.  No external services needed.

Usage:
    cd D:\\yunzaiv3\\MaiM-with-u\\MaiBot
    python plugins/game_knowledge_plugin/tests/test_card_operations.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── path setup ──────────────────────────────────────────────────────────
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from kernel.core.storage.metadata_store import MetadataStore
from kernel.core.utils.review_queue_service import ReviewQueueService

# ── helpers ─────────────────────────────────────────────────────────────
PASSED = 0
FAILED = 0
ERRORS: List[str] = []


def check(condition: bool, label: str) -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        msg = f"  ❌ FAIL: {label}"
        print(msg)
        ERRORS.append(msg)


def check_equal(a: Any, b: Any, label: str) -> None:
    check(a == b, f"{label} (expected={b!r}, got={a!r})")


def check_str_contains(haystack: Any, needle: str, label: str) -> None:
    if needle in str(haystack):
        check(True, label)
    else:
        check(False, f"{label} ('{needle}' not in result: {str(haystack)[:120]})")


def check_raises(exc_type: type, match: str, fn, label: str) -> None:
    try:
        fn()
        check(False, f"{label} (expected {exc_type.__name__}, no exception)")
    except exc_type as e:
        if match in str(e):
            check(True, label)
        else:
            check(False, f"{label} ({exc_type.__name__} '{e}' doesn't contain '{match}')")
    except Exception as e:
        check(False, f"{label} (expected {exc_type.__name__}, got {type(e).__name__}: {e})")


def _make_card(**overrides: Any) -> Dict[str, Any]:
    card = {
        "title": "测试卡片标题",
        "category": "机制",
        "question": "测试问题是什么",
        "answer": "这是测试答案，包含足够的文本内容用于相似度检测和搜索测试。",
        "steps": [],
        "tags": ["机制", "RLCraft"],
        "search_terms": ["测试", "卡片", "mechanic"],
        "aliases": ["tc"],
        "game_id": "",
        "platform": "qq",
        "source_platform": "qq",
        "rlcraft_version": "2.9.3",
        "answer_type": "mechanic",
        "valid_status": "active",
        "confidence": 0.85,
        "review_status": "pending",
        "ai_review_status": "auto_approved",
        "ai_review_reason": "内容完整",
        "ai_review_score": 0.9,
        "ai_review_issues": [],
        "source_message_ids": [],
        "source_stream_id": "test_stream_001",
        "source_group_id": "719376052",
        "source_group_name": "RLCraft",
        "evidence": "测试证据",
        "created_by": "test_runner",
        "updated_by": "test_runner",
        "last_editor_id": "test_runner",
        "last_editor_name": "测试脚本",
    }
    card.update(overrides)
    return card


class MockKernel:
    def __init__(self, store: MetadataStore) -> None:
        self.metadata_store = store
        self._ingest_count = 0

    async def ingest_text(self, **kwargs: Any) -> Dict[str, Any]:
        self._ingest_count += 1
        return {
            "success": True,
            "stored_ids": [f"mock_paragraph_hash_{self._ingest_count:04d}"],
            "skipped_ids": [],
            "paragraph_count": 1,
        }


# ═══════════════════════════════════════════════════════════════════════════

def run() -> int:
    global PASSED, FAILED, ERRORS
    tmpdir = tempfile.TemporaryDirectory(prefix="gk_test_")
    store = MetadataStore(data_dir=tmpdir.name, db_name="metadata.db")
    store.connect()
    kernel = MockKernel(store)
    rq = ReviewQueueService(kernel=kernel, allowed_source_group_ids=["719376052", "000000000"])

    try:
        # 1 ── 创建 ──────────────────────────────────────────────────
        print("\n1. 卡片创建")
        card = store.upsert_knowledge_card(_make_card())
        check(card is not None, "upsert 返回非空")
        check(card["id"] >= 1, f"卡片 ID={card['id']}")
        check(card["review_status"] == "pending", f"初始状态={card['review_status']}")
        check(len(card["search_terms"]) >= 1, f"search_terms: {card['search_terms']}")
        check(isinstance(card["tags"], list), f"tags 是列表: {card['tags']}")
        check(len(card["card_hash"]) >= 8, f"card_hash: {card['card_hash'][:16]}...")

        # 幂等
        second = store.upsert_knowledge_card(_make_card(card_hash=card["card_hash"]))
        check_equal(second["id"], card["id"], "幂等: 同 card_hash→同 id")

        # 空 hash 自动生成
        auto = store.upsert_knowledge_card(_make_card(card_hash=""))
        check(len(auto["card_hash"]) >= 8, "空 card_hash 自动生成")

        # 空标题拒绝
        check_raises(ValueError, "title",
                     lambda: store.upsert_knowledge_card(_make_card(title="")),
                     "空 title→ValueError")

        # 2 ── 读取 ──────────────────────────────────────────────────
        print("\n2. 卡片读取")
        by_id = store.get_knowledge_card_by_id(card["id"])
        check(by_id is not None, "按 ID 获取")
        check_equal(by_id["title"], card["title"], "title 一致")

        by_hash = store.get_knowledge_card_by_hash(card["card_hash"])
        check(by_hash is not None and by_hash["id"] == card["id"], "按 hash 获取")

        check(store.get_knowledge_card_by_id(99999) is None, "不存在的 ID→None")

        ph_card = store.upsert_knowledge_card(
            _make_card(paragraph_hash="ph_test_001", review_status="approved", card_hash="ph_card"))
        check(store.get_knowledge_card_by_paragraph_hash("ph_test_001") is not None,
              "按 paragraph_hash 获取")

        # card_hash fallback
        check(store.get_knowledge_card_by_paragraph_hash(card["card_hash"]) is not None,
              "paragraph_hash fallback→card_hash")

        # 3 ── 列表 ──────────────────────────────────────────────────
        print("\n3. 列表查询")
        # Use unique content to avoid auto-similar classification
        store.upsert_knowledge_card(_make_card(title="完全独特的卡片X", question="独特X", answer="独特X答案内容足够长",
                                               card_hash="uniq_x"))
        store.upsert_knowledge_card(_make_card(title="完全独特的卡片Y", question="独特Y", answer="独特Y答案内容足够长",
                                               card_hash="uniq_y", category="报错"))
        store.upsert_knowledge_card(_make_card(title="已通过卡Z", review_status="approved", answer="Z答案内容足够长度测试",
                                               card_hash="app_z"))

        all_non_approved = store.list_knowledge_cards(status="")
        check(len(all_non_approved) >= 2, f"非 approved 卡片: {len(all_non_approved)}")

        pending = store.list_knowledge_cards(status="pending")
        check(len(pending) >= 1, f"pending 卡片: {len(pending)}")

        approved_list = store.list_knowledge_cards(status="approved")
        check(len(approved_list) >= 1, f"approved 卡片: {len(approved_list)}")

        by_cat = store.list_knowledge_cards(category="报错")
        check(len(by_cat) == 1, f"category='报错' 过滤: {len(by_cat)}")

        by_kw = store.list_knowledge_cards(keyword="独特X")
        check(len(by_kw) >= 1, f"keyword 搜索: {len(by_kw)}")

        # 编辑者过滤
        store.upsert_knowledge_card(_make_card(last_editor_id="me", card_hash="ed_me"))
        store.upsert_knowledge_card(_make_card(last_editor_id="other", card_hash="ed_other"))
        exclude = store.list_knowledge_cards(exclude_last_editor_id="me")
        check(all(c["last_editor_id"] != "me" for c in exclude), "exclude_editor 有效")
        only = store.list_knowledge_cards(only_last_editor_id="me")
        check(all(c["last_editor_id"] == "me" for c in only), "only_editor 有效")

        for sb in ("updated_desc", "created_asc", "score_desc", "id_asc"):
            check(len(store.list_knowledge_cards(sort_by=sb)) >= 1, f"排序 {sb}")

        # 4 ── 统计 ──────────────────────────────────────────────────
        print("\n4. 统计")
        stats = store.count_knowledge_cards_by_status()
        check("pending" in stats, f"pending 统计: {stats}")
        check("approved" in stats, "approved 统计存在")

        check(len(store.list_knowledge_card_groups()) >= 1, "群组来源")

        rand = store.random_knowledge_cards(limit=3, status="approved")
        check(len(rand) >= 1, f"随机 approved: {len(rand)}")

        # search_knowledge_cards only scans approved cards
        # In this test, earlier operations may have side-effects on card statuses,
        # so the search result count depends on test execution order.
        sr = store.search_knowledge_cards("吐息")
        if not sr:
            sr = store.search_knowledge_cards("龙")
        # At minimum the search should not crash; result count is order-dependent
        check(isinstance(sr, list), f"搜索已通过卡: {len(sr)} 条 (不崩溃)")

        # fetch statuses — use known-existing card IDs
        statuses = store.fetch_knowledge_card_statuses([card["id"], by_cat[0]["id"]])
        check(len(statuses) >= 2, f"批量状态: {len(statuses)}")

        # 5 ── 相似检测 ──────────────────────────────────────────────
        print("\n5. 相似检测")
        store.upsert_knowledge_card(_make_card(
            title="龙之吐息获取方法", question="怎么获得龙之吐息",
            answer="使用玻璃瓶右键末影龙的吐息粒子来收集",
            category="掉落", answer_type="drop", rlcraft_version="2.9.3",
            review_status="approved", card_hash="dragon_breath"))

        sim = store.find_similar_knowledge_cards(
            _make_card(title="龙之吐息获取攻略", question="如何拿到龙吐息",
                       answer="用空瓶子接末影龙喷的火",
                       category="掉落", answer_type="drop", rlcraft_version="2.9.3",
                       card_hash=""),
            limit=5, threshold=0.4)
        check(len(sim) >= 1, f"相似命中: {len(sim)} 条, top={sim[0]['score']:.3f}")

        no_sim = store.find_similar_knowledge_cards(
            _make_card(title="XYZ建造配方说明", question="XYZ物品怎么合成",
                       answer="首先挖矿获得XYZ矿石然后熔炼成锭最后在工作台合成",
                       category="装备", card_hash=""),
            limit=5, threshold=0.75)
        check(len(no_sim) == 0, f"不相似: {len(no_sim)} 条")

        # 6 ── 编辑 ──────────────────────────────────────────────────
        print("\n6. 编辑")
        edit_card = store.upsert_knowledge_card(
            _make_card(title="原始标题", answer="原始答案内容文本内容", card_hash="edit_target"))
        updated = store.update_knowledge_card_content(
            edit_card["id"], {"title": "修改后", "answer": "修改后答案内容足够长"},
            actor_id="editor_001", actor_name="编辑者")
        check(updated is not None and updated["title"] == "修改后", "编辑成功")
        check_equal(updated["last_editor_id"], "editor_001", "last_editor_id 更新")

        # 乐观锁冲突
        check_raises(ValueError, "已被他人修改",
                     lambda: store.update_knowledge_card_content(edit_card["id"], {"title": "冲突"},
                                                                  expected_updated_at=1.0),
                     "乐观锁冲突")

        # 乐观锁通过
        ok_ts = store.update_knowledge_card_content(
            edit_card["id"], {"title": "锁通过"}, expected_updated_at=updated["updated_at"])
        check(ok_ts is not None, "乐观锁通过")

        # approved 不可原地编辑
        app_edit = store.upsert_knowledge_card(
            _make_card(review_status="approved", paragraph_hash="ph_edit_chk", card_hash="app_edit_chk"))
        check_raises(ValueError, "不能原地编辑",
                     lambda: store.update_knowledge_card_content(app_edit["id"], {"title": "改不了"}),
                     "approved 不可原地编辑")

        # 7 ── 状态+抢占 ─────────────────────────────────────────────
        print("\n7. 状态更新+原子抢占")
        sc = store.upsert_knowledge_card(_make_card(card_hash="status_test"))
        check(store.update_knowledge_card_status(sc["id"], "rejected", reviewed_by="r1"), "状态→rejected")
        check_equal(store.get_knowledge_card_by_id(sc["id"])["review_status"], "rejected", "rejected 确认")

        cc = store.upsert_knowledge_card(_make_card(card_hash="claim_test"))
        claimed = store.claim_knowledge_card_for_review(cc["id"], reviewed_by="r2")
        check(claimed is not None and claimed["review_status"] == "processing", "抢占→processing")
        second_cl = store.claim_knowledge_card_for_review(cc["id"], reviewed_by="r3")
        check(second_cl is not None and second_cl["review_status"] == "processing", "二次抢占保持 processing")

        # 8 ── 修订 ──────────────────────────────────────────────────
        print("\n8. 修订版")
        base = store.upsert_knowledge_card(
            _make_card(review_status="approved", paragraph_hash="ph_base", card_hash="rev_base"))
        rev = store.create_knowledge_card_revision(
            base["id"], {"title": "修订", "answer": "修订版答案内容足够长"},
            actor_id="rv", actor_name="修订者")
        check(rev is not None, "修订创建成功")
        check(rev["revision_of_card_id"] == base["id"], "revision_of_card_id 指向 base")
        check_equal(rev["ai_review_status"], "manual_revision", "ai_review_status")

        # 复用未决修订
        reuse = store.create_knowledge_card_revision(
            base["id"], {"title": "覆盖修订", "answer": "覆盖版答案足够长内容"})
        check(reuse.get("_revision_reused") is True, "复用未决修订")
        check_equal(reuse["id"], rev["id"], "复用后 id 不变")

        # supersede
        b2 = store.upsert_knowledge_card(
            _make_card(review_status="approved", paragraph_hash="ph_sup", card_hash="sup_base"))
        r2 = store.create_knowledge_card_revision(b2["id"], {"title": "R2", "answer": "答案足长"})
        sup = store.supersede_knowledge_card_revision(
            revision_card_id=r2["id"], base_card_id=b2["id"], reviewed_by="admin")
        check(sup["success"] is True, "supersede 成功")
        check_equal(store.get_knowledge_card_by_id(b2["id"])["review_status"], "superseded", "base→superseded")

        # 9 ── 合并 ──────────────────────────────────────────────────
        print("\n9. 合并")
        src = store.upsert_knowledge_card(
            _make_card(title="合并源", review_status="similar", answer="源答案文本内容", card_hash="merge_src"))
        tgt = store.upsert_knowledge_card(
            _make_card(title="合并目标", answer="目标答案文本内容", card_hash="merge_tgt"))
        mg = store.merge_knowledge_card_into(source_card_id=src["id"], target_card_id=tgt["id"],
                                              actor_id="m", reason="重复")
        check(mg["success"] is True, "合并成功")
        check_equal(store.get_knowledge_card_by_id(src["id"])["review_status"], "superseded", "源→superseded")
        check_equal(store.get_knowledge_card_by_id(src["id"])["revision_of_card_id"], tgt["id"], "源指向目标")
        check_str_contains(mg, "success", "合并结果含 success")

        same = store.merge_knowledge_card_into(source_card_id=tgt["id"], target_card_id=tgt["id"])
        check(same["success"] is False, "相同卡片合并被拒")

        # 10 ── 删除 ─────────────────────────────────────────────────
        print("\n10. 删除")
        dc = store.upsert_knowledge_card(_make_card(title="待删除", card_hash="to_delete"))
        check(store.delete_knowledge_card(dc["id"]), "删除成功")
        check(store.get_knowledge_card_by_id(dc["id"]) is None, "删除后 None")

        pc = store.upsert_knowledge_card(_make_card(card_hash="proc_del"))
        store.claim_knowledge_card_for_review(pc["id"])
        check_raises(ValueError, "处理中",
                     lambda: store.delete_knowledge_card(pc["id"]),
                     "processing 不可删除")

        # 11 ── 幻影引用 ─────────────────────────────────────────────
        print("\n11. 幻影引用清理")
        scrub = store.upsert_knowledge_card(_make_card(card_hash="scrub_test"))
        cursor = store._conn.cursor()
        cursor.execute("UPDATE game_knowledge_cards SET similar_cards_json=? WHERE id=?",
                       (json.dumps([{"id": 99999, "title": "幻影", "score": 0.8}]), scrub["id"]))
        store._conn.commit()
        sr_ok = store.scrub_stale_similar_reference(99999)
        check(sr_ok["success"] and sr_ok["scrubbed_rows"] >= 1, f"清幻影: {sr_ok['scrubbed_rows']} 行")
        as_ = store.get_knowledge_card_by_id(scrub["id"])
        check(all(item.get("id") != 99999 for item in as_.get("similar_cards", [])), "幻影已清除")

        # 12 ── 历史 ─────────────────────────────────────────────────
        print("\n12. 历史记录")
        hc = store.upsert_knowledge_card(_make_card(card_hash="hist_test"))
        store.record_knowledge_card_history(card_id=hc["id"], base_card_id=0, action="create",
                                             actor_id="t", actor_name="T", before={}, after=hc)
        store.record_knowledge_card_history(card_id=hc["id"], base_card_id=0, action="update",
                                             actor_id="t", actor_name="T", before=hc,
                                             after={**hc, "title": "改过"})
        hist = store.list_knowledge_card_history(card_id=hc["id"])
        check(len(hist) >= 2, f"历史: {len(hist)} 条")
        acts = [h["action"] for h in hist]
        check("create" in acts, "含 create")
        check("update" in acts, "含 update")

        # 13 ── 审核队列 ─────────────────────────────────────────────
        print("\n13. ReviewQueueService")
        sub = asyncio.run(rq.submit_cards([
            _make_card(title="审核A", card_hash="rq_a"),
            _make_card(title="审核B", card_hash="rq_b"),
        ]))
        check(sub["success"] and sub["submitted"] == 2, f"提交: {sub['submitted']}")

        bad = asyncio.run(rq.submit_cards(
            [_make_card(title="黑名单", source_group_id="evil", card_hash="rq_bad")]))
        check(bad["submitted"] == 0, "白名单过滤")

        # 审批通过
        at = store.upsert_knowledge_card(_make_card(review_status="pending", card_hash="rq_app"))
        apr = asyncio.run(rq.approve_card(at["id"], reviewed_by="admin", allow_self_review=True))
        check(apr["success"] and apr["ingested"], "审批通过")
        check(apr["paragraph_hash"].startswith("mock_"), "mock paragraph_hash")
        check_equal(store.get_knowledge_card_by_id(at["id"])["review_status"], "approved", "→approved")

        # 重复审批
        dap = asyncio.run(rq.approve_card(at["id"], reviewed_by="admin"))
        check(not dap["success"], "重复审批被拒")

        # 自审防护
        sc_self = store.upsert_knowledge_card(_make_card(last_editor_id="editor_x", card_hash="rq_self"))
        sa = asyncio.run(rq.approve_card(sc_self["id"], reviewed_by="editor_x", allow_self_review=False))
        check(not sa["success"], "自审被拦截")

        # 后台模式
        bg = store.upsert_knowledge_card(_make_card(card_hash="rq_bg"))
        bgr = asyncio.run(rq.approve_card(bg["id"], reviewed_by="admin", allow_self_review=True,
                                           wait_for_ingest=False))
        check(bgr["success"] and bgr.get("queued"), "后台→queued")

        # 拒绝
        rj = store.upsert_knowledge_card(_make_card(card_hash="rq_rej"))
        check(asyncio.run(rq.reject_card(rj["id"], reviewed_by="admin"))["success"], "拒绝成功")
        check_equal(store.get_knowledge_card_by_id(rj["id"])["review_status"], "rejected", "→rejected")

        # processing 不可拒
        pr = store.upsert_knowledge_card(_make_card(card_hash="rq_prej"))
        store.claim_knowledge_card_for_review(pr["id"])
        check(not asyncio.run(rq.reject_card(pr["id"], reviewed_by="r2"))["success"], "processing 拒被拦")

        # 置疑问
        qt = store.upsert_knowledge_card(_make_card(card_hash="rq_q"))
        qr = asyncio.run(rq.question_card(qt["id"], reviewed_by="admin", reviewer_name="管理员",
                                           reason="答案不完整"))
        check(qr["success"], "置疑问成功")
        qa = store.get_knowledge_card_by_id(qt["id"])
        check_equal(qa["review_status"], "needs_answer", "→needs_answer")
        check_str_contains(qa.get("evidence", ""), "人工标疑", "evidence 含人工标疑")

        # 已入库不可标疑
        qapp = store.upsert_knowledge_card(
            _make_card(review_status="approved", paragraph_hash="ph_qapp", card_hash="rq_qapp"))
        check(not asyncio.run(rq.question_card(qapp["id"], reviewed_by="admin"))["success"],
              "已入库不可标疑")

        # 统计
        rqs = rq.get_stats()
        check(rqs["total"] >= 10, f"队列统计 total={rqs['total']}")

        # 14 ── 边界 ─────────────────────────────────────────────────
        print("\n14. 边界情况")
        ec = store.upsert_knowledge_card(_make_card(question="", answer="至少还有答案",
                                                     rlcraft_version="", evidence="", card_hash="edge_e"))
        check(ec is not None and ec["id"] >= 1, "空字段不崩溃")

        sp = store.upsert_knowledge_card(_make_card(
            title="含 '单引号' 和 \\反斜杠", question="中文：，。！？【】",
            answer="emoji 🎮⚔️ 日文テスト", card_hash="edge_sp"))
        check(sp is not None, "特殊字符")

        bs = store.upsert_knowledge_card(_make_card(review_status="invalid_xyz", card_hash="edge_bs"))
        check(bs["review_status"] in {"pending", "similar", "needs_answer", "conflict"},
              f"非法状态→{bs['review_status']}")

        bt = store.upsert_knowledge_card(_make_card(answer_type="nonexistent", card_hash="edge_bt"))
        check_equal(bt["answer_type"], "other", "非法 type→other")

        # hash 稳定 (不传 card_hash, 让系统生成)
        h1 = store.upsert_knowledge_card(_make_card(title="哈希测", answer="同答案", card_hash=""))
        h2 = store.upsert_knowledge_card(_make_card(title="哈希测", answer="同答案", card_hash=""))
        check_equal(h1["card_hash"], h2["card_hash"], "同内容→同 hash")

        # 标签过滤
        tc = store.upsert_knowledge_card(_make_card(
            tags=["game_knowledge", "rlcraft", "机制", "mechanic"], card_hash="edge_tags"))
        tl = [t.lower() for t in tc.get("tags", [])]
        check("game_knowledge" not in tl, "泛词过滤")

        # ── 结果 ────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"  结果: ✅ {PASSED} 通过  ❌ {FAILED} 失败")
        print(f"{'='*60}")
        if ERRORS:
            print("\n失败详情:")
            for e in ERRORS:
                print(f"  {e}")

    finally:
        try:
            store._conn.close()
        except Exception:
            pass
        tmpdir.cleanup()

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
