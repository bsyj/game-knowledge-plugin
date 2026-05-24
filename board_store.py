"""GameKnowledge 插件留言板存储层。

留言板支持登录用户发起提问主题、其他用户楼层回复并引用某楼。当主题被标记
为「已解决」时由上层 board_service 调用 GameKnowledgeAnalyzer 生成知识卡片，
进入现有审核队列。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class BoardStore:
    """留言板持久化层。

    依赖 ``metadata_store._conn`` 提供的 SQLite 连接，使用 ``gk_board_*`` 表名前缀。
    """

    THREAD_STATUSES = ("open", "forwarded", "collecting", "resolved", "closed")
    POST_SOURCES = ("web", "qq")

    def __init__(self, *, store: Any) -> None:
        self._store = store
        self._conn = getattr(store, "_conn", None)
        if self._conn is None:
            raise RuntimeError("metadata_store 未连接")
        self.ensure_tables()

    def ensure_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gk_board_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author_id TEXT NOT NULL DEFAULT '',
                author_nickname TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                source_group_id TEXT,
                forwarded_at REAL,
                forwarded_message_id TEXT,
                forward_target_group_id TEXT,
                collected_until REAL,
                collected_message_count INTEGER NOT NULL DEFAULT 0,
                resolved_at REAL,
                resolved_by_id TEXT,
                last_reply_at REAL,
                reply_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gk_board_threads_status ON gk_board_threads(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gk_board_threads_created ON gk_board_threads(created_at)")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gk_board_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                author_id TEXT NOT NULL DEFAULT '',
                author_nickname TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                reply_to_post_id INTEGER,
                source TEXT NOT NULL DEFAULT 'web',
                source_user_id TEXT,
                source_message_id TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_gk_board_posts_thread ON gk_board_posts(thread_id, created_at)"
        )
        self._conn.commit()

    # ==================== Thread ====================

    def create_thread(
        self,
        *,
        title: str,
        content: str,
        author_id: str,
        author_nickname: str,
    ) -> Dict[str, Any]:
        clean_title = str(title or "").strip()
        if not clean_title:
            raise ValueError("标题不能为空")
        if len(clean_title) > 200:
            raise ValueError("标题最多 200 个字符")
        clean_content = str(content or "").strip()
        if not clean_content:
            raise ValueError("正文不能为空")
        if len(clean_content) > 8000:
            raise ValueError("正文最多 8000 个字符")
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO gk_board_threads (
                title, author_id, author_nickname, status,
                last_reply_at, reply_count, created_at, updated_at
            ) VALUES (?, ?, ?, 'open', ?, 0, ?, ?)
            """,
            (
                clean_title,
                str(author_id or ""),
                str(author_nickname or "")[:64],
                now,
                now,
                now,
            ),
        )
        thread_id = int(cursor.lastrowid or 0)
        cursor.execute(
            """
            INSERT INTO gk_board_posts (
                thread_id, author_id, author_nickname, content,
                reply_to_post_id, source, created_at
            ) VALUES (?, ?, ?, ?, NULL, 'web', ?)
            """,
            (
                thread_id,
                str(author_id or ""),
                str(author_nickname or "")[:64],
                clean_content,
                now,
            ),
        )
        self._conn.commit()
        thread = self.get_thread(thread_id)
        assert thread is not None
        return thread

    def get_thread(self, thread_id: int) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM gk_board_threads WHERE id=?", (int(thread_id),))
        row = cursor.fetchone()
        return self._thread_to_dict(row) if row else None

    def get_thread_with_posts(self, thread_id: int) -> Optional[Dict[str, Any]]:
        thread = self.get_thread(thread_id)
        if thread is None:
            return None
        thread["posts"] = self.list_posts(thread_id)
        return thread

    def delete_thread(self, thread_id: int) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM gk_board_posts WHERE thread_id=?", (int(thread_id),))
        cursor.execute("DELETE FROM gk_board_threads WHERE id=?", (int(thread_id),))
        self._conn.commit()
        return cursor.rowcount > 0

    def list_threads(
        self,
        *,
        status: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        cursor = self._conn.cursor()
        conditions: List[str] = []
        params: List[Any] = []
        clean_status = str(status or "").strip().lower()
        if clean_status in self.THREAD_STATUSES:
            conditions.append("status=?")
            params.append(clean_status)
        elif clean_status == "active":
            conditions.append("status IN ('open', 'forwarded', 'collecting')")
        elif clean_status == "done":
            conditions.append("status IN ('resolved', 'closed')")
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor.execute(f"SELECT COUNT(*) FROM gk_board_threads{where}", params)
        total = int(cursor.fetchone()[0] or 0)
        safe_limit = max(1, min(100, int(limit or 20)))
        safe_offset = max(0, int(offset or 0))
        cursor.execute(
            f"""
            SELECT * FROM gk_board_threads
            {where}
            ORDER BY (status IN ('open','forwarded','collecting')) DESC,
                     COALESCE(last_reply_at, created_at) DESC
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        )
        items = [self._thread_to_dict(row) for row in cursor.fetchall()]
        return {"items": items, "total": total}

    def mark_forwarded(
        self,
        thread_id: int,
        *,
        forwarded_message_id: str,
        forward_target_group_id: str,
        collected_until: float,
    ) -> None:
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE gk_board_threads
            SET status='collecting',
                forwarded_at=?,
                forwarded_message_id=?,
                forward_target_group_id=?,
                collected_until=?,
                updated_at=?
            WHERE id=? AND status IN ('open', 'forwarded')
            """,
            (
                now,
                str(forwarded_message_id or ""),
                str(forward_target_group_id or ""),
                float(collected_until),
                now,
                int(thread_id),
            ),
        )
        self._conn.commit()

    def mark_resolved(self, thread_id: int, *, resolved_by_id: str = "") -> None:
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE gk_board_threads
            SET status='resolved', resolved_at=?, resolved_by_id=?, updated_at=?
            WHERE id=?
            """,
            (now, str(resolved_by_id or ""), now, int(thread_id)),
        )
        self._conn.commit()

    def close_thread(self, thread_id: int) -> None:
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE gk_board_threads SET status='closed', updated_at=? WHERE id=?",
            (now, int(thread_id)),
        )
        self._conn.commit()

    def list_open_overdue(self, *, threshold_seconds: float) -> List[Dict[str, Any]]:
        """返回创建超过阈值且仍处于 open 且 reply_count==0 的主题。"""

        cutoff = time.time() - float(threshold_seconds)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM gk_board_threads
            WHERE status='open' AND reply_count=0 AND created_at <= ?
            ORDER BY created_at ASC
            """,
            (cutoff,),
        )
        return [self._thread_to_dict(row) for row in cursor.fetchall()]

    def list_collecting_in_group(self, group_id: str) -> List[Dict[str, Any]]:
        clean = str(group_id or "").strip()
        if not clean:
            return []
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM gk_board_threads
            WHERE status='collecting' AND forward_target_group_id=?
            """,
            (clean,),
        )
        return [self._thread_to_dict(row) for row in cursor.fetchall()]

    def list_collecting_expired(self) -> List[Dict[str, Any]]:
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM gk_board_threads
            WHERE status='collecting' AND collected_until IS NOT NULL AND collected_until <= ?
            """,
            (now,),
        )
        return [self._thread_to_dict(row) for row in cursor.fetchall()]

    # ==================== Post ====================

    def add_post(
        self,
        thread_id: int,
        *,
        content: str,
        author_id: str,
        author_nickname: str,
        reply_to_post_id: Optional[int] = None,
        source: str = "web",
        source_user_id: str = "",
        source_message_id: str = "",
    ) -> Dict[str, Any]:
        clean_content = str(content or "").strip()
        if not clean_content:
            raise ValueError("回复内容不能为空")
        if len(clean_content) > 8000:
            raise ValueError("回复最多 8000 个字符")
        normalized_source = source if source in self.POST_SOURCES else "web"
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id FROM gk_board_threads WHERE id=?",
            (int(thread_id),),
        )
        if cursor.fetchone() is None:
            raise ValueError("主题不存在")
        now = time.time()
        reply_target: Optional[int] = None
        if reply_to_post_id is not None:
            cursor.execute(
                "SELECT id FROM gk_board_posts WHERE id=? AND thread_id=?",
                (int(reply_to_post_id), int(thread_id)),
            )
            if cursor.fetchone() is not None:
                reply_target = int(reply_to_post_id)
        cursor.execute(
            """
            INSERT INTO gk_board_posts (
                thread_id, author_id, author_nickname, content,
                reply_to_post_id, source, source_user_id, source_message_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(thread_id),
                str(author_id or ""),
                str(author_nickname or "")[:64],
                clean_content,
                reply_target,
                normalized_source,
                str(source_user_id or ""),
                str(source_message_id or ""),
                now,
            ),
        )
        post_id = int(cursor.lastrowid or 0)
        cursor.execute(
            """
            UPDATE gk_board_threads
            SET last_reply_at=?, reply_count=reply_count + 1, updated_at=?
            WHERE id=?
            """,
            (now, now, int(thread_id)),
        )
        self._conn.commit()
        return self._post_row(post_id) or {}

    def append_collected_qq_post(
        self,
        thread_id: int,
        *,
        content: str,
        source_user_id: str,
        source_message_id: str,
        author_nickname: str = "",
    ) -> int:
        """收集 QQ 群里转发后的群消息作为「候选答案」楼层。

        Returns:
            int: 该 thread 上当前已累计的 collecting 楼层数（含本次插入）。
        """
        clean_content = str(content or "").strip()
        if not clean_content:
            return 0
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO gk_board_posts (
                thread_id, author_id, author_nickname, content,
                reply_to_post_id, source, source_user_id, source_message_id, created_at
            ) VALUES (?, '', ?, ?, NULL, 'qq', ?, ?, ?)
            """,
            (
                int(thread_id),
                str(author_nickname or "")[:64],
                clean_content,
                str(source_user_id or ""),
                str(source_message_id or ""),
                now,
            ),
        )
        cursor.execute(
            """
            UPDATE gk_board_threads
            SET collected_message_count=collected_message_count + 1,
                last_reply_at=?,
                updated_at=?
            WHERE id=?
            """,
            (now, now, int(thread_id)),
        )
        self._conn.commit()
        cursor.execute(
            "SELECT collected_message_count FROM gk_board_threads WHERE id=?",
            (int(thread_id),),
        )
        row = cursor.fetchone()
        return int(row[0] or 0) if row else 0

    def list_posts(self, thread_id: int) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM gk_board_posts
            WHERE thread_id=?
            ORDER BY created_at ASC, id ASC
            """,
            (int(thread_id),),
        )
        return [self._post_to_dict(row) for row in cursor.fetchall()]

    def get_post(self, post_id: int) -> Optional[Dict[str, Any]]:
        return self._post_row(post_id)

    def delete_post(self, post_id: int) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT thread_id FROM gk_board_posts WHERE id=?", (int(post_id),))
        row = cursor.fetchone()
        if row is None:
            return False
        thread_id = int(dict(row).get("thread_id") or 0)
        cursor.execute("DELETE FROM gk_board_posts WHERE id=?", (int(post_id),))
        # 同步 reply_count（不允许变成负数）
        cursor.execute(
            """
            UPDATE gk_board_threads
            SET reply_count = CASE
                    WHEN reply_count > 0 THEN reply_count - 1
                    ELSE 0
                END,
                updated_at=?
            WHERE id=?
            """,
            (time.time(), thread_id),
        )
        self._conn.commit()
        return True

    def _post_row(self, post_id: int) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM gk_board_posts WHERE id=?", (int(post_id),))
        row = cursor.fetchone()
        return self._post_to_dict(row) if row else None

    # ==================== 序列化 ====================

    @staticmethod
    def _thread_to_dict(row: Any) -> Dict[str, Any]:
        data = dict(row)
        return {
            "id": int(data.get("id") or 0),
            "title": str(data.get("title", "") or ""),
            "author_id": str(data.get("author_id", "") or ""),
            "author_nickname": str(data.get("author_nickname", "") or ""),
            "status": str(data.get("status", "open") or "open"),
            "source_group_id": (str(data["source_group_id"]) if data.get("source_group_id") else None),
            "forwarded_at": (float(data["forwarded_at"]) if data.get("forwarded_at") is not None else None),
            "forwarded_message_id": (str(data["forwarded_message_id"]) if data.get("forwarded_message_id") else None),
            "forward_target_group_id": (str(data["forward_target_group_id"]) if data.get("forward_target_group_id") else None),
            "collected_until": (float(data["collected_until"]) if data.get("collected_until") is not None else None),
            "collected_message_count": int(data.get("collected_message_count") or 0),
            "resolved_at": (float(data["resolved_at"]) if data.get("resolved_at") is not None else None),
            "resolved_by_id": (str(data["resolved_by_id"]) if data.get("resolved_by_id") else None),
            "last_reply_at": (float(data["last_reply_at"]) if data.get("last_reply_at") is not None else None),
            "reply_count": int(data.get("reply_count") or 0),
            "created_at": float(data.get("created_at") or 0),
            "updated_at": float(data.get("updated_at") or 0),
        }

    @staticmethod
    def _post_to_dict(row: Any) -> Dict[str, Any]:
        data = dict(row)
        return {
            "id": int(data.get("id") or 0),
            "thread_id": int(data.get("thread_id") or 0),
            "author_id": str(data.get("author_id", "") or ""),
            "author_nickname": str(data.get("author_nickname", "") or ""),
            "content": str(data.get("content", "") or ""),
            "reply_to_post_id": (int(data["reply_to_post_id"]) if data.get("reply_to_post_id") is not None else None),
            "source": str(data.get("source", "web") or "web"),
            "source_user_id": str(data.get("source_user_id", "") or ""),
            "source_message_id": str(data.get("source_message_id", "") or ""),
            "created_at": float(data.get("created_at") or 0),
        }
