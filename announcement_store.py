"""GameKnowledge 插件 WebUI 公告存储。

公告由管理员发布，普通登录用户可在 plugin webui 顶部 Banner 与列表页中阅读；
设计为可删不可改（CLAUDE 对齐项），独立挂在 plugin 自己的 metadata_store SQLite。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class AnnouncementStore:
    """公告持久化层。

    复用 plugin 的 ``metadata_store`` 连接，所有表名以 ``gk_announcement_`` 为前缀，
    避免与主程序或 ``game_knowledge_*`` 表冲突。
    """

    SEVERITY_VALUES = ("info", "warning", "critical")
    STATUS_VALUES = ("draft", "published")

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
            CREATE TABLE IF NOT EXISTS gk_announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                pinned INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'published',
                starts_at REAL,
                ends_at REAL,
                author_id TEXT NOT NULL DEFAULT '',
                author_nickname TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_gk_announcements_status ON gk_announcements(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_gk_announcements_pinned ON gk_announcements(pinned)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_gk_announcements_created ON gk_announcements(created_at)"
        )
        self._conn.commit()

    @classmethod
    def normalize_severity(cls, value: Any) -> str:
        normalized = str(value or "info").strip().lower()
        return normalized if normalized in cls.SEVERITY_VALUES else "info"

    @classmethod
    def normalize_status(cls, value: Any) -> str:
        normalized = str(value or "published").strip().lower()
        return normalized if normalized in cls.STATUS_VALUES else "published"

    def create(
        self,
        *,
        title: str,
        content: str,
        severity: str,
        pinned: bool,
        status: str,
        starts_at: Optional[float],
        ends_at: Optional[float],
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
        if len(clean_content) > 20000:
            raise ValueError("正文最多 20000 个字符")
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO gk_announcements (
                title, content, severity, pinned, status,
                starts_at, ends_at, author_id, author_nickname,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_title,
                clean_content,
                self.normalize_severity(severity),
                1 if pinned else 0,
                self.normalize_status(status),
                float(starts_at) if starts_at is not None else None,
                float(ends_at) if ends_at is not None else None,
                str(author_id or ""),
                str(author_nickname or "")[:64],
                now,
                now,
            ),
        )
        self._conn.commit()
        record_id = int(cursor.lastrowid or 0)
        record = self.get(record_id)
        assert record is not None
        return record

    def get(self, announcement_id: int) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM gk_announcements WHERE id=?", (int(announcement_id),))
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def delete(self, announcement_id: int) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM gk_announcements WHERE id=?", (int(announcement_id),))
        self._conn.commit()
        return cursor.rowcount > 0

    def list(
        self,
        *,
        status: str = "",
        include_inactive: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        clean_status = str(status or "").strip().lower()
        conditions: List[str] = []
        params: List[Any] = []
        if clean_status in self.STATUS_VALUES:
            conditions.append("status=?")
            params.append(clean_status)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM gk_announcements{where}", params)
        total = int(cursor.fetchone()[0] or 0)
        safe_limit = max(1, min(200, int(limit or 50)))
        safe_offset = max(0, int(offset or 0))
        cursor.execute(
            f"""
            SELECT * FROM gk_announcements
            {where}
            ORDER BY pinned DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        )
        rows = [self._row_to_dict(row) for row in cursor.fetchall()]
        if not include_inactive:
            rows = [row for row in rows if self._is_currently_active(row)]
        return {"items": rows, "total": total}

    def list_active(self, *, limit: int = 5) -> List[Dict[str, Any]]:
        """供 Banner 拉取的活跃公告。"""

        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM gk_announcements
            WHERE status='published'
            ORDER BY pinned DESC, created_at DESC
            """
        )
        rows = [self._row_to_dict(row) for row in cursor.fetchall()]
        active = [row for row in rows if self._is_currently_active(row)]
        safe_limit = max(1, min(20, int(limit or 5)))
        return active[:safe_limit]

    @staticmethod
    def _is_currently_active(record: Dict[str, Any]) -> bool:
        if record.get("status") != "published":
            return False
        now = time.time()
        starts_at = record.get("starts_at")
        ends_at = record.get("ends_at")
        if starts_at is not None and now < float(starts_at):
            return False
        if ends_at is not None and now > float(ends_at):
            return False
        return True

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        data = dict(row)
        return {
            "id": int(data.get("id") or 0),
            "title": str(data.get("title", "") or ""),
            "content": str(data.get("content", "") or ""),
            "severity": str(data.get("severity", "info") or "info"),
            "pinned": bool(data.get("pinned")),
            "status": str(data.get("status", "published") or "published"),
            "starts_at": (float(data["starts_at"]) if data.get("starts_at") is not None else None),
            "ends_at": (float(data["ends_at"]) if data.get("ends_at") is not None else None),
            "author_id": str(data.get("author_id", "") or ""),
            "author_nickname": str(data.get("author_nickname", "") or ""),
            "created_at": float(data.get("created_at") or 0),
            "updated_at": float(data.get("updated_at") or 0),
        }
