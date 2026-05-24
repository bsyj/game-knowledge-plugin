"""Shared pytest fixtures for game-knowledge-plugin test suite.

Provides mock dependencies and in-memory SQLite databases for isolated testing
of all plugin services without requiring the full MaiBot runtime.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# ── path setup ──────────────────────────────────────────────────────────
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


# ── Mock Store (bridges metadata_store SQLite to auth/board/announcement) ─

class MockMetadataStore:
    """Simulates kernel.core.storage.metadata_store.MetadataStore with
    only the surface needed by AuthService / BoardStore / AnnouncementStore.
    """

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_card_table()
        self._ensure_paragraph_table()

    def _ensure_card_table(self):
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_knowledge_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                category TEXT DEFAULT '',
                question TEXT DEFAULT '',
                answer TEXT DEFAULT '',
                steps TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                search_terms TEXT DEFAULT '[]',
                aliases TEXT DEFAULT '[]',
                game_id TEXT DEFAULT '',
                game_name TEXT DEFAULT '',
                version TEXT DEFAULT '',
                platform TEXT DEFAULT '',
                source_platform TEXT DEFAULT '',
                rlcraft_version TEXT DEFAULT '',
                answer_type TEXT DEFAULT 'other',
                valid_status TEXT DEFAULT 'active',
                confidence REAL DEFAULT 0,
                review_status TEXT DEFAULT 'pending',
                ai_review_status TEXT DEFAULT '',
                ai_review_reason TEXT DEFAULT '',
                ai_review_score REAL DEFAULT 0,
                ai_review_issues TEXT DEFAULT '[]',
                source_message_ids TEXT DEFAULT '[]',
                source_stream_id TEXT DEFAULT '',
                source_group_id TEXT DEFAULT '',
                source_group_name TEXT DEFAULT '',
                evidence TEXT DEFAULT '',
                card_hash TEXT NOT NULL UNIQUE,
                paragraph_hash TEXT DEFAULT '',
                revision_of_card_id INTEGER DEFAULT 0,
                created_by TEXT DEFAULT '',
                updated_by TEXT DEFAULT '',
                last_editor_id TEXT DEFAULT '',
                last_editor_name TEXT DEFAULT '',
                similar_cards_json TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def _ensure_paragraph_table(self):
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS paragraphs (
                paragraph_hash TEXT PRIMARY KEY,
                content TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                is_deleted INTEGER DEFAULT 0,
                source TEXT DEFAULT ''
            )
            """
        )
        self._conn.commit()

    def connect(self) -> None:
        pass

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── card methods used by RevisionService ─────────────────────────

    def get_knowledge_card_by_id(self, card_id: int) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM game_knowledge_cards WHERE id=?", (card_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_knowledge_card_by_hash(self, card_hash: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM game_knowledge_cards WHERE card_hash=?", (card_hash,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_knowledge_card_by_paragraph_hash(self, ph: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM game_knowledge_cards WHERE paragraph_hash=?",
            (ph,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "SELECT * FROM game_knowledge_cards WHERE card_hash=?",
                (ph,),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_paragraph(self, token: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM paragraphs WHERE paragraph_hash=?", (token,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_knowledge_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Minimal upsert for testing revision flows."""
        cursor = self._conn.cursor()
        now = time.time()
        data.setdefault("review_status", "pending")
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        data.setdefault("card_hash", data.get("card_hash") or f"hash_{now}")
        try:
            cursor.execute(
                "INSERT INTO game_knowledge_cards (title,answer,card_hash,review_status,revision_of_card_id,paragraph_hash,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (data.get("title", ""), data.get("answer", ""), data["card_hash"], data["review_status"], data.get("revision_of_card_id", 0), data.get("paragraph_hash", ""), data["created_at"], data["updated_at"]),
            )
            data["id"] = cursor.lastrowid
        except sqlite3.IntegrityError:
            cursor.execute("SELECT id FROM game_knowledge_cards WHERE card_hash=?", (data["card_hash"],))
            row = cursor.fetchone()
            data["id"] = row[0] if row else 0
            cursor.execute(
                "UPDATE game_knowledge_cards SET title=?,answer=?,updated_at=? WHERE id=?",
                (data.get("title", ""), data.get("answer", ""), now, data["id"]),
            )
        self._conn.commit()
        return {
            **data,
            "id": data.get("id", 0),
            "card_hash": data.get("card_hash", ""),
        }

    def update_knowledge_card_content(
        self, card_id: int, payload: Dict[str, Any],
        actor_id: str = "", actor_name: str = "",
        expected_updated_at: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        now = time.time()
        cursor.execute("SELECT * FROM game_knowledge_cards WHERE id=?", (card_id,))
        row = cursor.fetchone()
        if not row:
            return None
        current = dict(row)
        if current.get("review_status") == "approved":
            raise ValueError("不能原地编辑已通过的卡片")
        if expected_updated_at is not None and abs(current.get("updated_at", 0) - expected_updated_at) > 0.01:
            raise ValueError("卡片已被他人修改，请刷新后重试")
        title = payload.get("title", current.get("title", ""))
        answer = payload.get("answer", current.get("answer", ""))
        cursor.execute(
            "UPDATE game_knowledge_cards SET title=?,answer=?,last_editor_id=?,last_editor_name=?,updated_at=? WHERE id=?",
            (title, answer, actor_id, actor_name, now, card_id),
        )
        self._conn.commit()
        cursor.execute("SELECT * FROM game_knowledge_cards WHERE id=?", (card_id,))
        new_row = cursor.fetchone()
        return dict(new_row) if new_row else None

    def create_knowledge_card_revision(
        self, card_id: int, payload: Dict[str, Any],
        actor_id: str = "", actor_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Create a revision card for approved card."""
        base = self.get_knowledge_card_by_id(card_id)
        if not base:
            return None
        # Check for existing pending revision of this card
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id FROM game_knowledge_cards WHERE revision_of_card_id=? AND review_status IN ('pending','similar','needs_answer','conflict')",
            (card_id,),
        )
        existing = cursor.fetchone()
        if existing:
            now = time.time()
            cursor.execute(
                "UPDATE game_knowledge_cards SET title=?,answer=?,updated_at=? WHERE id=?",
                (payload.get("title", base.get("title", "")),
                 payload.get("answer", base.get("answer", "")),
                 now, existing[0]),
            )
            self._conn.commit()
            rev = self.get_knowledge_card_by_id(existing[0])
            if rev:
                rev["_revision_reused"] = True
            return rev
        now = time.time()
        rev_data = {
            "title": payload.get("title", base.get("title", "")),
            "answer": payload.get("answer", base.get("answer", "")),
            "card_hash": f"rev_{card_id}_{now}",
            "review_status": "pending",
            "revision_of_card_id": card_id,
            "ai_review_status": "manual_revision",
            "last_editor_id": actor_id,
            "last_editor_name": actor_name,
            "created_at": now,
            "updated_at": now,
        }
        return self.upsert_knowledge_card(rev_data)

    def record_knowledge_card_history(self, **kwargs: Any) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_knowledge_card_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                base_card_id INTEGER DEFAULT 0,
                action TEXT NOT NULL,
                actor_id TEXT DEFAULT '',
                actor_name TEXT DEFAULT '',
                before_json TEXT DEFAULT '{}',
                after_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            )
            """
        )
        import json
        cursor.execute(
            "INSERT INTO game_knowledge_card_history (card_id,base_card_id,action,actor_id,actor_name,before_json,after_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                kwargs.get("card_id", 0),
                kwargs.get("base_card_id", 0),
                kwargs.get("action", ""),
                kwargs.get("actor_id", ""),
                kwargs.get("actor_name", ""),
                json.dumps(kwargs.get("before", {})),
                json.dumps(kwargs.get("after", {})),
                time.time(),
            ),
        )
        self._conn.commit()

    def supersede_knowledge_card_revision(
        self, *, revision_card_id: int, base_card_id: int, reviewed_by: str = ""
    ) -> Dict[str, Any]:
        cursor = self._conn.cursor()
        now = time.time()
        cursor.execute(
            "UPDATE game_knowledge_cards SET review_status='superseded', updated_at=? WHERE id=?",
            (now, base_card_id),
        )
        cursor.execute(
            "UPDATE game_knowledge_cards SET review_status='approved', updated_at=? WHERE id=?",
            (now, revision_card_id),
        )
        self._conn.commit()
        return {"success": True}

    def merge_knowledge_card_into(
        self, *, source_card_id: int, target_card_id: int, actor_id: str = "", reason: str = ""
    ) -> Dict[str, Any]:
        if source_card_id == target_card_id:
            return {"success": False, "error": "不能合并相同卡片"}
        cursor = self._conn.cursor()
        now = time.time()
        cursor.execute(
            "UPDATE game_knowledge_cards SET review_status='superseded', revision_of_card_id=?, updated_at=? WHERE id=?",
            (target_card_id, now, source_card_id),
        )
        self._conn.commit()
        return {"success": True}


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create an isolated temporary SQLite database file."""
    with tempfile.TemporaryDirectory(prefix="gk_test_db_") as tmpdir:
        db_path = os.path.join(tmpdir, "metadata.db")
        yield db_path


@pytest.fixture
def mock_store(temp_db: str) -> Generator[MockMetadataStore, None, None]:
    """Create a MockMetadataStore backed by temp SQLite."""
    store = MockMetadataStore(temp_db)
    yield store
    store.close()


@pytest.fixture
def db_conn(mock_store: MockMetadataStore) -> Generator[sqlite3.Connection, None, None]:
    """Provide direct access to the underlying SQLite connection."""
    yield mock_store._conn


# ── Service fixtures ────────────────────────────────────────────────────


@pytest.fixture
def auth_service(mock_store: MockMetadataStore):
    """Create a GameKnowledgeAuthService with isolated store."""
    from auth_service import GameKnowledgeAuthService
    svc = GameKnowledgeAuthService(store=mock_store)
    return svc


@pytest.fixture
def board_store(mock_store: MockMetadataStore):
    """Create a BoardStore with isolated store."""
    from board_store import BoardStore
    store = BoardStore(store=mock_store)
    return store


@pytest.fixture
def announcement_store(mock_store: MockMetadataStore):
    """Create an AnnouncementStore with isolated store."""
    from announcement_store import AnnouncementStore
    store = AnnouncementStore(store=mock_store)
    return store


@pytest.fixture
def revision_service(mock_store: MockMetadataStore):
    """Create a RevisionService with isolated store."""
    from revision_service import GameKnowledgeRevisionService
    svc = GameKnowledgeRevisionService(store=mock_store)
    return svc


@pytest.fixture
def admin_user(auth_service):
    """Bootstrap an admin user and return user dict + token."""
    admin = auth_service.create_user(
        username="admin_test",
        password="Admin123456",
        display_name="Admin Test",
        group_ids=["admin"],
    )
    token = auth_service.issue_token(admin["id"])
    return {"user": admin, "token": token, "auth": auth_service}


@pytest.fixture
def viewer_user(auth_service):
    """Create a viewer user for permission tests."""
    viewer = auth_service.create_user(
        username="viewer_test",
        password="Viewer123456",
        display_name="Viewer Test",
        group_ids=["viewer"],
    )
    token = auth_service.issue_token(viewer["id"])
    return {"user": viewer, "token": token}


@pytest.fixture
def reviewer_user(auth_service):
    """Create a reviewer user for board resolution tests."""
    reviewer = auth_service.create_user(
        username="reviewer_test",
        password="Reviewer123456",
        display_name="Reviewer Test",
        group_ids=["reviewer"],
    )
    token = auth_service.issue_token(reviewer["id"])
    return {"user": reviewer, "token": token}
