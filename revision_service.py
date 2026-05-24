"""Shared revision flow for GameKnowledge cards and search hits."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class GameKnowledgeRevisionService:
    """Apply the same revision semantics used by the WebUI editor."""

    def __init__(self, *, store: Any) -> None:
        self._store = store

    def revise_target(
        self,
        target: str,
        payload: Dict[str, Any],
        *,
        actor_id: str = "",
        actor_name: str = "",
    ) -> Dict[str, Any]:
        token = str(target or "").strip()
        if not token:
            return {"success": False, "error": "target 不能为空", "status": 400}

        card = self._store.get_knowledge_card_by_paragraph_hash(token)
        if card is not None:
            return self._revise_card(card, payload, actor_id=actor_id, actor_name=actor_name)

        paragraph = self._store.get_paragraph(token)
        if not paragraph or bool(paragraph.get("is_deleted", 0)):
            return {"success": False, "error": "未找到可编辑的检索结果", "status": 404}

        draft = self.build_card_from_search_hit(token, paragraph, payload)
        draft["created_by"] = str(actor_id or "")
        draft["updated_by"] = str(actor_id or "")
        draft["last_editor_id"] = str(actor_id or "")
        draft["last_editor_name"] = str(actor_name or "")
        revision = self._store.upsert_knowledge_card(draft)
        if revision and hasattr(self._store, "record_knowledge_card_history"):
            self._store.record_knowledge_card_history(
                card_id=int(revision.get("id", 0) or 0),
                base_card_id=0,
                action="create_from_search",
                actor_id=actor_id,
                actor_name=actor_name,
                before=paragraph,
                after=revision,
            )
        return {
            "success": True,
            "mode": "created_from_paragraph",
            "card": revision,
            "message": "已基于检索结果创建待审核修订卡片",
        }

    def revise_card_id(
        self,
        card_id: int,
        payload: Dict[str, Any],
        *,
        actor_id: str = "",
        actor_name: str = "",
        expected_updated_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        card = self._store.get_knowledge_card_by_id(card_id)
        if card is None:
            return {"success": False, "error": "卡片不存在", "status": 404}
        return self._revise_card(
            card, payload,
            actor_id=actor_id, actor_name=actor_name,
            expected_updated_at=expected_updated_at,
        )

    def _revise_card(
        self,
        card: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        actor_id: str = "",
        actor_name: str = "",
        expected_updated_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        card_id = int(card.get("id", 0) or 0)
        if str(card.get("review_status", "") or "").strip().lower() == "approved":
            revision = self._store.create_knowledge_card_revision(
                card_id,
                payload,
                actor_id=actor_id,
                actor_name=actor_name,
            )
            if not revision:
                return {"success": False, "error": "创建修订版失败", "status": 500}
            reused = bool(revision.pop("_revision_reused", False))
            return {
                "success": True,
                "mode": "revision_reused" if reused else "revision",
                "card": revision,
                "message": "已合并到现有待审核修订卡片" if reused else "已创建待审核修订卡片",
            }

        updated = self._store.update_knowledge_card_content(
            card_id,
            payload,
            actor_id=actor_id,
            actor_name=actor_name,
            expected_updated_at=expected_updated_at,
        )
        if not updated:
            return {"success": False, "error": "保存卡片失败", "status": 500}
        return {
            "success": True,
            "mode": "update",
            "card": updated,
            "message": "已更新未通过审核的卡片",
        }

    @staticmethod
    def build_card_from_search_hit(hit_hash: str, paragraph: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = paragraph.get("metadata") if isinstance(paragraph.get("metadata"), dict) else {}
        content = str(paragraph.get("content", "") or "")
        title = str(payload.get("title") or metadata.get("title") or "").strip()
        question = str(payload.get("question") or metadata.get("question") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        if not title:
            title = content.splitlines()[0].strip() if content.splitlines() else "检索结果修订"
        if not question:
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("q:") or stripped.startswith("Q："):
                    question = stripped.split(":", 1)[-1].strip() if ":" in stripped else stripped.split("：", 1)[-1].strip()
                    break
        if not answer:
            answer = content
        now = time.time()
        return {
            "title": title,
            "category": str(payload.get("category") or metadata.get("category") or "其他"),
            "question": question or title,
            "answer": answer,
            "steps": payload.get("steps") if isinstance(payload.get("steps"), list) else [],
            "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else ["game_knowledge"],
            "search_terms": payload.get("search_terms") if isinstance(payload.get("search_terms"), list) else metadata.get("search_terms", []),
            "aliases": payload.get("aliases") if isinstance(payload.get("aliases"), list) else metadata.get("aliases", []),
            "game_name": "",
            "game_id": str(payload.get("game_id") or metadata.get("game_id") or ""),
            "version": str(payload.get("version") or metadata.get("version") or ""),
            "platform": str(payload.get("platform") or metadata.get("platform") or ""),
            "source_platform": str(payload.get("source_platform") or metadata.get("source_platform") or metadata.get("platform") or ""),
            "rlcraft_version": str(payload.get("rlcraft_version") or metadata.get("rlcraft_version") or ""),
            "answer_type": str(payload.get("answer_type") or metadata.get("answer_type") or "other"),
            "valid_status": str(payload.get("valid_status") or metadata.get("valid_status") or "active"),
            "review_status": "pending",
            "source_stream_id": str(metadata.get("source_stream_id") or metadata.get("chat_id") or paragraph.get("source") or ""),
            "source_group_id": str(metadata.get("source_group_id") or ""),
            "source_group_name": str(metadata.get("source_group_name") or ""),
            "evidence": str(payload.get("evidence") or metadata.get("evidence") or f"由检索结果 {hit_hash} 人工修订生成"),
            "ai_review_status": "manual_revision",
            "ai_review_reason": f"由检索结果 {hit_hash} 人工修订生成",
            "ai_review_score": 1.0,
            "created_at": now,
            "updated_at": now,
        }
