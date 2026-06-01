"""游戏知识审核队列服务

职责：
- 接收分析器产出的知识卡片
- 存入 pending 状态的审核队列
- 审核通过后写入 game_knowledge 内核
- 提供 WebUI / 命令调用的审核接口
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gk_shims.logger_shim import get_logger

from ...core.storage.metadata_store import MetadataStore

if TYPE_CHECKING:
    from ...core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("GameKnowledge.ReviewQueue")


class ReviewQueueService:
    """审核队列服务

    遵循 SRP：只负责审核队列生命周期，不直接操作向量/图谱。
    写入核心库时调用 SDKMemoryKernel 的标准接口。
    """

    _review_write_lock = asyncio.Lock()
    _approve_ingest_semaphore = asyncio.Semaphore(3)

    def __init__(self, *, kernel: SDKMemoryKernel, allowed_source_group_ids: Optional[List[str]] = None) -> None:
        self._kernel = kernel
        self._allowed_source_group_ids = {
            str(item or "").strip()
            for item in (allowed_source_group_ids or [])
            if str(item or "").strip()
        }

    @property
    def metadata_store(self) -> Optional[MetadataStore]:
        return self._kernel.metadata_store


    async def submit_cards(
        self,
        cards: List[Dict[str, Any]],
        *,
        game_id: str = "",
        stream_id: str = "",
    ) -> Dict[str, Any]:
        """提交知识卡片到审核队列。

        Args:
            cards: 分析器产出的标准化卡片列表
            game_id: 游戏ID
            stream_id: 聊天流ID

        Returns:
            {"success": bool, "submitted": int, "card_hashes": [...]}
        """
        if not cards:
            return {"success": True, "submitted": 0, "card_hashes": []}

        store = self.metadata_store
        if store is None:
            return {"success": False, "submitted": 0, "card_hashes": [], "error": "metadata_store 未就绪"}

        submitted_hashes = []
        ai_review_counts = {"approved": 0, "rejected": 0, "similar": 0, "needs_answer": 0, "conflict": 0, "error": 0}
        errors: List[str] = []
        for card in cards:
            source_group_id = str(card.get("source_group_id", "") or "").strip()
            if self._allowed_source_group_ids and source_group_id not in self._allowed_source_group_ids:
                errors.append(f"跳过非白名单群卡片: group={source_group_id or '(empty)'} title={card.get('title', '')}")
                continue
            card_hash = self._compute_card_hash(card)
            ai_review_status = str(card.get("ai_review_status", "") or "").strip().lower()
            record = {
                "card_hash": card_hash,
                "title": card.get("title", ""),
                "category": card.get("category", ""),
                "question": card.get("question", ""),
                "answer": card.get("answer", ""),
                "steps": card.get("steps", []),
                "tags": card.get("tags", []),
                "search_terms": card.get("search_terms", []),
                "aliases": card.get("aliases", []),
                "game_name": "",
                "game_id": game_id,
                "platform": card.get("platform", "") or card.get("source_platform", ""),
                "source_platform": card.get("source_platform", "") or card.get("platform", ""),
                "rlcraft_version": card.get("rlcraft_version", ""),
                "answer_type": card.get("answer_type", "other"),
                "valid_status": card.get("valid_status", "active"),
                "confidence": card.get("confidence", 0.0),
                "review_status": self._normalize_review_status(card.get("review_status", "pending")),
                "ai_review_status": ai_review_status,
                "ai_review_reason": card.get("ai_review_reason", ""),
                "ai_review_score": card.get("ai_review_score", 0.0),
                "ai_review_issues": card.get("ai_review_issues", []),
                "source_message_ids": card.get("source_message_ids", []),
                "source_stream_id": stream_id or card.get("source_stream_id", ""),
                "source_group_id": card.get("source_group_id", ""),
                "source_group_name": card.get("source_group_name", ""),
                "evidence": card.get("evidence", ""),
            }
            try:
                if record["review_status"] == "pending" and str(record.get("valid_status", "")).strip().lower() == "conflict":
                    record["review_status"] = "conflict"
                    record["ai_review_status"] = record.get("ai_review_status") or "conflict_candidate"
                    record["ai_review_reason"] = record.get("ai_review_reason") or "检测到版本或答案冲突风险，请审核员确认"
                    ai_review_status = "conflict"
                if record["review_status"] == "pending" and hasattr(store, "find_similar_knowledge_cards"):
                    similar_cards = store.find_similar_knowledge_cards(record, limit=5, threshold=0.72)
                    if similar_cards:
                        record["review_status"] = "similar"
                        record["ai_review_status"] = record.get("ai_review_status") or "similar_candidate"
                        record["ai_review_reason"] = "检测到疑似相似卡片，请审核员对照后处理"
                        record["similar_cards"] = similar_cards
                        ai_review_status = "similar"
                store.upsert_knowledge_card(record)
                submitted_hashes.append(record["card_hash"])
                if ai_review_status in ai_review_counts:
                    ai_review_counts[ai_review_status] += 1
            except Exception as exc:
                logger.warning(f"写入审核队列失败: {exc}")
                errors.append(str(exc))

        if submitted_hashes and hasattr(store, "record_review_event"):
            try:
                store.record_review_event(
                    "auto_review",
                    "submitted",
                    count=len(submitted_hashes),
                    source_stream_id=stream_id,
                )
                for status, count in ai_review_counts.items():
                    if count > 0:
                        store.record_review_event(
                            "ai_review",
                            status,
                            count=count,
                            source_stream_id=stream_id,
                        )
            except Exception as exc:
                logger.warning(f"记录审核统计失败: {exc}")

        logger.info(f"审核队列提交: {len(submitted_hashes)}/{len(cards)} 张卡片")
        return {
            "success": bool(submitted_hashes),
            "partial": bool(submitted_hashes) and len(submitted_hashes) < len(cards),
            "submitted": len(submitted_hashes),
            "card_hashes": submitted_hashes,
            "errors": errors,
            "error": errors[0] if errors and not submitted_hashes else "",
        }

    async def approve_card(
        self,
        card_id: int,
        *,
        reviewed_by: str = "",
        auto_ingest: bool = True,
        allow_self_review: bool = False,
        wait_for_ingest: bool = True,
    ) -> Dict[str, Any]:
        """审核通过一张卡片，可选自动写入核心库。

        Args:
            card_id: 卡片自增ID
            reviewed_by: 审核人标识
            auto_ingest: 是否自动写入 game_knowledge 内核

        Returns:
            {"success": bool, "card_id": int, "ingested": bool, "paragraph_hash": ""}
        """
        store = self.metadata_store
        if store is None:
            return {"success": False, "card_id": card_id, "error": "metadata_store 未就绪"}

        async with self._review_write_lock:
            original = store.get_knowledge_card_by_id(card_id)
            if original is None:
                return {"success": False, "card_id": card_id, "error": "卡片不存在"}
            original_status = str(original.get("review_status", "") or "pending")
            if original_status == "processing":
                return {"success": False, "card_id": card_id, "error": "卡片正在处理中，请稍后刷新"}
            if original_status not in {"pending", "similar", "ai_rejected", "conflict", "needs_answer"}:
                return {"success": False, "card_id": card_id, "error": f"卡片当前状态为 {original_status}，不能重复审核"}
            if (
                not allow_self_review
                and reviewed_by
                and str(original.get("last_editor_id", "") or "").strip()
                and str(original.get("last_editor_id", "") or "").strip() == str(reviewed_by).strip()
            ):
                return {"success": False, "card_id": card_id, "error": "不能审核自己修改的卡片"}

            card = store.claim_knowledge_card_for_review(card_id, reviewed_by=reviewed_by)
            if card is None:
                return {"success": False, "card_id": card_id, "error": "卡片不存在"}
            if str(card.get("review_status", "") or "") != "processing":
                return {"success": False, "card_id": card_id, "error": "卡片已被其他审核操作占用，请刷新"}

        if not wait_for_ingest:
            asyncio.create_task(self._finish_approve_card_background(card_id, original, reviewed_by=reviewed_by, original_status=original_status, auto_ingest=auto_ingest))
            return {
                "success": True,
                "card_id": card_id,
                "queued": True,
                "status": "processing",
                "ingested": False,
                "paragraph_hash": "",
            }

        return await self._finish_approve_card(card_id, original, reviewed_by=reviewed_by, original_status=original_status, auto_ingest=auto_ingest)

    async def _finish_approve_card_background(
        self,
        card_id: int,
        original: Dict[str, Any],
        *,
        reviewed_by: str = "",
        original_status: str = "pending",
        auto_ingest: bool = True,
    ) -> None:
        result = await self._finish_approve_card(
            card_id,
            original,
            reviewed_by=reviewed_by,
            original_status=original_status,
            auto_ingest=auto_ingest,
        )
        if not result.get("success"):
            logger.warning(f"后台审核写入失败: id={card_id}, error={result.get('error', '未知错误')}")

    async def _finish_approve_card(
        self,
        card_id: int,
        original: Dict[str, Any],
        *,
        reviewed_by: str = "",
        original_status: str = "pending",
        auto_ingest: bool = True,
    ) -> Dict[str, Any]:
        store = self.metadata_store
        if store is None:
            return {"success": False, "card_id": card_id, "error": "metadata_store 未就绪"}
        ingested = False
        paragraph_hash = ""
        try:
            if auto_ingest:
                async with self._approve_ingest_semaphore:
                    ingest_result = await self._ingest_card_to_kernel(original)
                ingested = ingest_result.get("success", False)
                paragraph_hash = ingest_result.get("paragraph_hash", "")
                if not ingested:
                    store.update_knowledge_card_status(card_id, original_status, reviewed_by="")
                    return {
                        "success": False,
                        "card_id": card_id,
                        "ingested": False,
                        "paragraph_hash": "",
                        "error": ingest_result.get("error", "写入内核失败"),
                    }

            store.update_knowledge_card_status(card_id, "approved", reviewed_by=reviewed_by)
            if hasattr(store, "record_review_event"):
                try:
                    store.record_review_event("manual_review", "approved", count=1, source_stream_id=str(original.get("source_stream_id", "") or ""))
                except Exception as exc:
                    logger.warning(f"记录人工审核通过统计失败: {exc}")
            logger.info(f"卡片审核通过: id={card_id}, title={original.get('title', '')}")
            if auto_ingest and paragraph_hash:
                cursor = store._conn.cursor()
                cursor.execute(
                    "UPDATE game_knowledge_cards SET paragraph_hash=? WHERE id=?",
                    (paragraph_hash, card_id),
                )
                store._conn.commit()
                base_card_id = int(original.get("revision_of_card_id", 0) or 0)
                if base_card_id > 0 and hasattr(store, "supersede_knowledge_card_revision"):
                    store.supersede_knowledge_card_revision(
                        revision_card_id=card_id,
                        base_card_id=base_card_id,
                        reviewed_by=reviewed_by,
                    )

            return {
                "success": True,
                "card_id": card_id,
                "ingested": ingested,
                "paragraph_hash": paragraph_hash,
            }
        except Exception as exc:
            store.update_knowledge_card_status(card_id, original_status, reviewed_by="")
            logger.warning(f"审核通过失败，已回滚状态: id={card_id}, error={exc}")
            return {"success": False, "card_id": card_id, "ingested": False, "paragraph_hash": "", "error": str(exc)}

    async def question_card(
        self,
        card_id: int,
        *,
        reviewed_by: str = "",
        reviewer_name: str = "",
        reason: str = "",
        allow_self_review: bool = False,
    ) -> Dict[str, Any]:
        """把一张待审卡片置为 needs_answer（疑问），不写入核心库。

        仅允许从 {pending, similar, ai_rejected, conflict} 切换过来；needs_answer 自身、
        processing、approved、rejected、superseded 都不再走这条路径，避免把已入库的内容
        误降级。
        """
        store = self.metadata_store
        if store is None:
            return {"success": False, "card_id": card_id, "error": "metadata_store 未就绪"}

        reason_text = str(reason or "").strip()

        async with self._review_write_lock:
            original = store.get_knowledge_card_by_id(card_id)
            if original is None:
                return {"success": False, "card_id": card_id, "error": "卡片不存在"}
            original_status = str(original.get("review_status", "") or "pending")
            if original_status == "processing":
                return {"success": False, "card_id": card_id, "error": "卡片正在处理中，请稍后刷新"}
            if original_status == "approved":
                return {"success": False, "card_id": card_id, "error": "已入库卡片不能直接置为疑问，请先撤回入库"}
            if original_status not in {"pending", "similar", "ai_rejected", "conflict"}:
                return {"success": False, "card_id": card_id, "error": f"卡片当前状态为 {original_status}，不能置为疑问"}
            if (
                not allow_self_review
                and reviewed_by
                and str(original.get("last_editor_id", "") or "").strip()
                and str(original.get("last_editor_id", "") or "").strip() == str(reviewed_by).strip()
            ):
                return {"success": False, "card_id": card_id, "error": "不能审核自己修改的卡片"}

            try:
                ok = store.update_knowledge_card_status(card_id, "needs_answer", reviewed_by=reviewed_by)
                if not ok:
                    return {"success": False, "card_id": card_id, "error": "状态更新失败"}

                # 写入 ai_review 元数据 + 在 evidence 上拼一行人工标疑记录，
                # 让详情页的 questionReviewParts/questionOrigin 能识别来源和理由。
                try:
                    cursor = store._conn.cursor()
                    actor_label = reviewer_name or reviewed_by or "审核员"
                    timestamp_label = datetime.now().strftime("%Y-%m-%d %H:%M")
                    appended = [f"人工标疑: {actor_label} @ {timestamp_label}"]
                    if reason_text:
                        appended.append(f"疑问理由: {reason_text}")
                    existing_evidence = str(original.get("evidence", "") or "").rstrip()
                    new_evidence = "\n".join([existing_evidence] + appended) if existing_evidence else "\n".join(appended)
                    new_reason = reason_text or str(original.get("ai_review_reason", "") or "")
                    cursor.execute(
                        """
                        UPDATE game_knowledge_cards
                        SET ai_review_status='manual_review_question',
                            ai_review_reason=?,
                            evidence=?,
                            updated_at=?
                        WHERE id=?
                        """,
                        (new_reason, new_evidence, datetime.now().timestamp(), card_id),
                    )
                    store._conn.commit()
                except Exception as exc:
                    logger.warning(f"写入人工标疑元数据失败: id={card_id}, error={exc}")

                if hasattr(store, "record_review_event"):
                    try:
                        store.record_review_event(
                            "manual_review",
                            "needs_answer",
                            count=1,
                            source_stream_id=str(original.get("source_stream_id", "") or ""),
                        )
                    except Exception as exc:
                        logger.warning(f"记录人工标疑统计失败: {exc}")
                logger.info(f"卡片置为疑问: id={card_id}, from={original_status}, by={reviewed_by}")
                return {"success": True, "card_id": card_id, "from_status": original_status, "review_status": "needs_answer"}
            except Exception as exc:
                logger.warning(f"置疑问失败: id={card_id}, error={exc}")
                return {"success": False, "card_id": card_id, "error": str(exc)}

    async def reject_card(self, card_id: int, *, reviewed_by: str = "", allow_self_review: bool = False) -> Dict[str, Any]:
        """拒绝一张卡片（仅改状态，不写入核心库）。"""
        store = self.metadata_store
        if store is None:
            return {"success": False, "card_id": card_id, "error": "metadata_store 未就绪"}

        async with self._review_write_lock:
            original = store.get_knowledge_card_by_id(card_id)
            if original is None:
                return {"success": False, "card_id": card_id, "error": "卡片不存在"}
            original_status = str(original.get("review_status", "") or "pending")
            if original_status == "processing":
                return {"success": False, "card_id": card_id, "error": "卡片正在处理中，请稍后刷新"}
            if original_status not in {"pending", "similar", "needs_answer", "ai_rejected", "conflict"}:
                return {"success": False, "card_id": card_id, "error": f"卡片当前状态为 {original_status}，不能重复审核"}
            if (
                not allow_self_review
                and reviewed_by
                and str(original.get("last_editor_id", "") or "").strip()
                and str(original.get("last_editor_id", "") or "").strip() == str(reviewed_by).strip()
            ):
                return {"success": False, "card_id": card_id, "error": "不能审核自己修改的卡片"}

            card = store.claim_knowledge_card_for_review(card_id, reviewed_by=reviewed_by)
            if card is None:
                return {"success": False, "card_id": card_id, "error": "卡片不存在"}
            if str(card.get("review_status", "") or "") != "processing":
                return {"success": False, "card_id": card_id, "error": "卡片已被其他审核操作占用，请刷新"}

            try:
                ok = store.update_knowledge_card_status(card_id, "rejected", reviewed_by=reviewed_by)
                if ok:
                    if hasattr(store, "record_review_event"):
                        try:
                            store.record_review_event("manual_review", "rejected", count=1, source_stream_id=str(original.get("source_stream_id", "") or ""))
                        except Exception as exc:
                            logger.warning(f"记录人工审核拒绝统计失败: {exc}")
                    logger.info(f"卡片审核拒绝: id={card_id}")
                return {"success": ok, "card_id": card_id}
            except Exception as exc:
                store.update_knowledge_card_status(card_id, original_status, reviewed_by="")
                logger.warning(f"审核拒绝失败，已回滚状态: id={card_id}, error={exc}")
                return {"success": False, "card_id": card_id, "error": str(exc)}

    async def delete_card(self, card_id: int) -> Dict[str, Any]:
        """从审核队列中删除一张卡片。已通过卡片会同步软删除关联段落。"""
        store = self.metadata_store
        if store is None:
            return {"success": False, "card_id": card_id, "error": "metadata_store 未就绪"}
        try:
            ok = store.delete_knowledge_card(card_id)
            return {"success": ok, "card_id": card_id}
        except ValueError as exc:
            return {"success": False, "card_id": card_id, "error": str(exc)}

    def list_pending(
        self, *, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取待审核卡片列表。"""
        store = self.metadata_store
        if store is None:
            return []
        return store.list_knowledge_cards(status="pending", limit=limit, offset=offset)

    def list_approved(self, *, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取已审核通过卡片列表。"""
        store = self.metadata_store
        if store is None:
            return []
        return store.list_knowledge_cards(status="approved", limit=limit, offset=offset)

    def get_stats(self) -> Dict[str, int]:
        """获取审核队列统计。"""
        store = self.metadata_store
        if store is None:
            return {"pending": 0, "approved": 0, "rejected": 0, "total": 0}
        try:
            cursor = store._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='pending'")
            pending = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='similar'")
            similar = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='needs_answer'")
            needs_answer = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='processing'")
            processing = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='conflict'")
            conflict = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='approved'")
            approved = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='rejected'")
            rejected = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards WHERE review_status='ai_rejected'")
            ai_rejected = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM game_knowledge_cards")
            total = cursor.fetchone()[0]
            return {
                "pending": pending,
                "similar": similar,
                "needs_answer": needs_answer,
                "processing": processing,
                "conflict": conflict,
                "approved": approved,
                "rejected": rejected,
                "ai_rejected": ai_rejected,
                "total": total,
            }
        except Exception:
            return {"pending": 0, "similar": 0, "needs_answer": 0, "processing": 0, "conflict": 0, "approved": 0, "rejected": 0, "ai_rejected": 0, "total": 0}

    async def _ingest_card_to_kernel(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """将已审核卡片写入 game_knowledge 内核。"""
        text_parts = []
        title = str(card.get("title", "") or "").strip()
        question = str(card.get("question", "") or "").strip()
        answer = str(card.get("answer", "") or "").strip()
        header_parts = ["游戏知识"]
        header_map = [
            ("版本", card.get("rlcraft_version") or card.get("version", "")),
            ("类型", card.get("answer_type", "")),
            ("状态", card.get("valid_status", "active")),
            ("分类", card.get("category", "")),
        ]
        for label, value in header_map:
            text = str(value or "").strip()
            if text:
                header_parts.append(f"{label}: {text}")
        for label, field in (("关键词", "search_terms"), ("别名", "aliases")):
            values = card.get(field, [])
            if isinstance(values, list) and values:
                header_parts.append(f"{label}: " + " ".join(str(item).strip() for item in values if str(item).strip()))
        text_parts.append("\n".join(header_parts))
        if title:
            text_parts.append(title)
        if question:
            text_parts.append(f"Q: {question}")
        if answer:
            text_parts.append(f"A: {answer}")
        steps = card.get("steps", [])
        if steps:
            text_parts.append("\n步骤:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)))
        tags = card.get("tags", [])
        if isinstance(tags, list) and tags:
            text_parts.append("标签: " + " ".join(str(tag).strip() for tag in tags if str(tag).strip()))
        evidence = str(card.get("evidence", "") or "").strip()
        if evidence:
            text_parts.append(f"证据: {evidence}")
        text = "\n".join(text_parts).strip()
        if not text:
            return {"success": False, "error": "卡片内容为空"}

        external_id = f"gkb:{card.get('source_stream_id', '')}:{card.get('card_hash', '')}"
        metadata = {
            "domain": "game_knowledge",
            "game_id": card.get("game_id", ""),
            "category": card.get("category", ""),
            "question": card.get("question", ""),
            "review_status": "approved",
            "source_stream_id": card.get("source_stream_id", ""),
            "source_message_ids": card.get("source_message_ids", []),
            "source_group_id": card.get("source_group_id", ""),
            "source_group_name": card.get("source_group_name", ""),
            "search_terms": card.get("search_terms", []),
            "aliases": card.get("aliases", []),
            "rlcraft_version": card.get("rlcraft_version", ""),
            "answer_type": card.get("answer_type", "other"),
            "valid_status": card.get("valid_status", "active"),
            "source_platform": card.get("source_platform", "") or card.get("platform", ""),
            "evidence": card.get("evidence", ""),
            "version": card.get("version", ""),
            "platform": card.get("platform", ""),
        }
        tags = card.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        tags.append("game_knowledge")

        result = await self._kernel.ingest_text(
            external_id=external_id,
            source_type="game_knowledge",
            text=text,
            chat_id=card.get("source_stream_id", ""),
            tags=list(dict.fromkeys(tags)),
            metadata=metadata,
            entities=[],
            relations=[],
        )

        stored_ids = result.get("stored_ids", [])
        skipped_ids = result.get("skipped_ids", [])
        paragraph_hash = stored_ids[0] if stored_ids else (skipped_ids[0] if skipped_ids else "")
        if paragraph_hash:
            self._restore_ingested_paragraph_if_deleted(paragraph_hash)
        return {
            "success": bool(paragraph_hash),
            "paragraph_hash": paragraph_hash,
            "stored_ids": stored_ids,
        }

    def _restore_ingested_paragraph_if_deleted(self, paragraph_hash: str) -> None:
        """重复 external_id 入库时，如果旧 paragraph 是软删除状态，人工通过应恢复它。"""
        store = self.metadata_store
        if store is None:
            return
        token = str(paragraph_hash or "").strip()
        if not token:
            return
        try:
            paragraph = store.get_paragraph(token)
            if paragraph and bool(paragraph.get("is_deleted", 0)):
                store.restore_paragraph_by_hash(token)
                if hasattr(store, "fts_upsert_paragraph"):
                    store.fts_upsert_paragraph(token)
        except Exception as exc:
            logger.warning(f"恢复已通过卡片段落失败: paragraph_hash={token}, error={exc}")

    @staticmethod
    def _compute_card_hash(card: Dict[str, Any]) -> str:
        """计算卡片唯一哈希。"""
        from ..utils.hash import compute_hash

        seed = "|".join([
            str(card.get("title", "")),
            str(card.get("question", "")),
            str(card.get("answer", ""))[:80],
            str(card.get("source_stream_id", "")),
        ])
        return compute_hash(seed)

    @staticmethod
    def _normalize_review_status(status: Any) -> str:
        value = str(status or "").strip().lower()
        allowed = {"pending", "similar", "needs_answer", "processing", "approved", "rejected", "ai_rejected", "superseded", "conflict"}
        return value if value in allowed else "pending"
