"""留言板业务服务。

封装「主题+楼层」与「卡片化入库」的衔接：当 admin/maintainer/reviewer 标记某主题
为「已解决」时，把主题（标题+提问）与选定的答案楼层组装为消息列表，喂给
``GameKnowledgeAnalyzer.analyze_messages``，再用 ``ReviewQueueService.submit_cards``
进入审核队列。
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .gk_shims.logger_shim import get_logger

from .board_store import BoardStore

logger = get_logger("plugin.gk.board")


AnalyzerProvider = Callable[[], Any]
ReviewQueueProvider = Callable[[], Awaitable[Any]]
ConfigProvider = Callable[[], Dict[str, Any]]


class BoardService:
    """高层服务：CRUD + 入库联动。"""

    def __init__(
        self,
        *,
        store: BoardStore,
        analyzer_provider: AnalyzerProvider,
        review_queue_provider: ReviewQueueProvider,
        config_provider: ConfigProvider,
    ) -> None:
        self._store = store
        self._analyzer_provider = analyzer_provider
        self._review_queue_provider = review_queue_provider
        self._config_provider = config_provider

    @property
    def store(self) -> BoardStore:
        return self._store

    async def mark_resolved_and_ingest(
        self,
        thread_id: int,
        *,
        picked_post_ids: Optional[List[int]] = None,
        resolved_by_id: str = "",
        resolved_by_nickname: str = "",
    ) -> Dict[str, Any]:
        """将主题标记为已解决，并把选定的答案楼层送进审核队列。

        Args:
            thread_id: 主题 ID。
            picked_post_ids: 选定的答案楼层 ID 列表；为空则视为「所有非首楼楼层都是答案」。
            resolved_by_id: 操作者用户 ID（仅做审计记录）。
            resolved_by_nickname: 操作者昵称（用于卡片溯源 sender_name）。

        Returns:
            { "success": bool, "submitted": int, "card_hashes": [...], "ai_reviewed": int,
              "ai_rejected": int, "error": str }
        """

        thread = self._store.get_thread_with_posts(thread_id)
        if thread is None:
            return {"success": False, "error": "主题不存在", "submitted": 0, "card_hashes": []}
        if thread.get("status") == "closed":
            return {"success": False, "error": "主题已关闭", "submitted": 0, "card_hashes": []}

        posts: List[Dict[str, Any]] = list(thread.get("posts") or [])
        if not posts:
            return {"success": False, "error": "主题没有任何内容", "submitted": 0, "card_hashes": []}

        head_post = posts[0]
        reply_posts = posts[1:]
        if picked_post_ids:
            picked_set = {int(value) for value in picked_post_ids if value is not None}
            reply_posts = [post for post in reply_posts if int(post.get("id") or 0) in picked_set]

        if not reply_posts and not thread.get("status") in ("collecting", "forwarded"):
            # 允许在未选回答的情况下直接关闭（仅记入「已解决」状态、不产生卡片）
            self._store.mark_resolved(thread_id, resolved_by_id=resolved_by_id)
            return {
                "success": True,
                "submitted": 0,
                "card_hashes": [],
                "ai_reviewed": 0,
                "ai_rejected": 0,
                "error": "",
                "note": "已标记为已解决但未生成卡片（没有可选答案楼层）",
            }

        config = self._config_provider() or {}
        allowed_group_ids: List[str] = list(config.get("allowed_source_group_ids") or [])
        source_group_id = str((allowed_group_ids or [""])[0]).strip()
        source_platform = str(config.get("source_platform") or "qq").strip().lower()

        messages = self._build_messages_for_analyzer(
            head_post=head_post,
            reply_posts=reply_posts,
            thread=thread,
            source_group_id=source_group_id,
            source_platform=source_platform,
            resolved_by_nickname=resolved_by_nickname,
        )

        analyzer = self._analyzer_provider()
        if analyzer is None:
            return {"success": False, "error": "analyzer 未就绪", "submitted": 0, "card_hashes": []}
        review_queue = await self._review_queue_provider()
        if review_queue is None:
            return {"success": False, "error": "审核队列未就绪", "submitted": 0, "card_hashes": []}

        stream_id = f"board:{int(thread_id)}"
        try:
            analyzer_result = await analyzer.analyze_messages(messages, stream_id=stream_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"board {thread_id} analyzer 调用失败: {exc}", exc_info=True)
            return {"success": False, "error": f"analyzer 调用失败: {exc}", "submitted": 0, "card_hashes": []}

        cards = list(analyzer_result.get("cards") or [])
        if not cards:
            # 没提取出卡片也按已解决处理，避免反复重试
            self._store.mark_resolved(thread_id, resolved_by_id=resolved_by_id)
            self._store.close_thread(thread_id)
            return {
                "success": True,
                "submitted": 0,
                "card_hashes": [],
                "ai_reviewed": int(analyzer_result.get("ai_reviewed") or 0),
                "ai_rejected": int(analyzer_result.get("ai_rejected") or 0),
                "error": "",
                "note": "已标记为已解决但 analyzer 未提取出卡片",
            }

        # 给卡片注入溯源字段，保证 ReviewQueueService 白名单校验通过
        for card in cards:
            if not isinstance(card, dict):
                continue
            if source_group_id and not str(card.get("source_group_id") or "").strip():
                card["source_group_id"] = source_group_id
            if source_platform and not str(card.get("source_platform") or "").strip():
                card["source_platform"] = source_platform
            if source_platform and not str(card.get("platform") or "").strip():
                card["platform"] = source_platform

        submit_result = await review_queue.submit_cards(
            cards, game_id="", stream_id=stream_id,
        )
        submitted = int(submit_result.get("submitted") or 0)
        self._store.mark_resolved(thread_id, resolved_by_id=resolved_by_id)
        if submitted > 0:
            self._store.close_thread(thread_id)
        return {
            "success": bool(submit_result.get("success", True)),
            "submitted": submitted,
            "card_hashes": list(submit_result.get("card_hashes") or []),
            "ai_reviewed": int(analyzer_result.get("ai_reviewed") or 0),
            "ai_rejected": int(analyzer_result.get("ai_rejected") or 0),
            "error": str(submit_result.get("error") or ""),
        }

    def _build_messages_for_analyzer(
        self,
        *,
        head_post: Dict[str, Any],
        reply_posts: List[Dict[str, Any]],
        thread: Dict[str, Any],
        source_group_id: str,
        source_platform: str,
        resolved_by_nickname: str,
    ) -> List[Dict[str, Any]]:
        title = str(thread.get("title", "") or "").strip()
        head_nick = str(head_post.get("author_nickname", "") or thread.get("author_nickname", "") or "群友")
        first_content = str(head_post.get("content", "") or "").strip()
        merged_question = f"【提问】{title}\n{first_content}" if title else first_content
        timestamp = float(head_post.get("created_at") or thread.get("created_at") or time.time())
        messages: List[Dict[str, Any]] = [
            {
                "id": f"board:thread:{int(thread.get('id') or 0)}:head:{int(head_post.get('id') or 0)}",
                "content": merged_question,
                "sender_name": head_nick,
                "timestamp": timestamp,
                "source_platform": source_platform,
                "source_group_id": source_group_id,
                "source_group_name": "WebUI 留言板",
            }
        ]
        for post in reply_posts:
            content = str(post.get("content", "") or "").strip()
            if not content:
                continue
            sender = str(post.get("author_nickname", "") or resolved_by_nickname or "群友")
            messages.append(
                {
                    "id": f"board:thread:{int(thread.get('id') or 0)}:post:{int(post.get('id') or 0)}",
                    "content": content,
                    "sender_name": sender,
                    "timestamp": float(post.get("created_at") or time.time()),
                    "source_platform": source_platform,
                    "source_group_id": source_group_id,
                    "source_group_name": "WebUI 留言板",
                }
            )
        return messages
