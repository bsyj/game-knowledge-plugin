"""Test database schema creation and integrity.

Validates that all services' ensure_tables() create correct schemas
and that FK/UNIQUE constraints work as expected.
"""

from __future__ import annotations

import pytest
import sqlite3
import time
from unittest.mock import MagicMock


class TestAuthSchema:
    """Validate GameKnowledgeAuthService.ensure_tables() schema."""

    def test_auth_tables_created(self, auth_service, db_conn):
        """All auth tables should exist after service init."""
        tables = [
            "game_knowledge_auth_settings",
            "game_knowledge_users",
            "game_knowledge_user_groups",
            "game_knowledge_user_group_members",
            "game_knowledge_auth_audit",
            "game_knowledge_registration_captchas",
        ]
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row["name"] for row in cursor.fetchall()}
        for t in tables:
            assert t in existing, f"Table {t} should exist"

    def test_default_user_groups_seeded(self, auth_service):
        """Five default groups should be seeded on init."""
        groups = auth_service.list_groups()
        group_ids = {g["id"] for g in groups}
        expected = {"admin", "maintainer", "reviewer", "editor", "viewer"}
        assert group_ids == expected, f"Expected {expected}, got {group_ids}"

    def test_token_secret_auto_generated(self, auth_service, db_conn):
        """Token secret should be auto-generated on first init."""
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT value FROM game_knowledge_auth_settings WHERE key='token_secret'"
        )
        row = cursor.fetchone()
        assert row is not None, "token_secret should be set"
        assert len(row["value"]) == 64  # token_hex(32) = 64 hex chars

    def test_default_settings_inserted(self, auth_service, db_conn):
        """Default settings should be present."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT key, value FROM game_knowledge_auth_settings")
        settings = {row["key"]: row["value"] for row in cursor.fetchall()}
        assert settings["allow_registration"] == "true"
        assert settings["default_registration_group"] == "viewer"

    def test_username_unique_constraint(self, auth_service):
        """Duplicate username should raise IntegrityError."""
        auth_service.create_user(username="dup_user", password="Dup12345678")
        with pytest.raises(sqlite3.IntegrityError):
            auth_service.create_user(username="dup_user", password="Dup12345678")

    def test_user_table_schema_columns(self, auth_service, db_conn):
        """Verify all expected columns exist in user table."""
        cursor = db_conn.cursor()
        cursor.execute("PRAGMA table_info(game_knowledge_users)")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {
            "id", "username", "display_name", "password_hash", "password_salt",
            "status", "created_at", "updated_at", "last_login_at", "last_login_ip",
            "failed_login_count", "locked_until", "token_version",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"


class TestBoardSchema:
    """Validate BoardStore.ensure_tables() schema."""

    def test_board_tables_created(self, board_store, db_conn):
        """Board tables should exist after init."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "gk_board_threads" in tables
        assert "gk_board_posts" in tables

    def test_board_threads_columns(self, board_store, db_conn):
        """Verify thread table columns."""
        cursor = db_conn.cursor()
        cursor.execute("PRAGMA table_info(gk_board_threads)")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {
            "id", "title", "author_id", "author_nickname", "status",
            "source_group_id", "forwarded_at", "forwarded_message_id",
            "forward_target_group_id", "collected_until",
            "collected_message_count", "resolved_at", "resolved_by_id",
            "last_reply_at", "reply_count", "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing: {expected - columns}"

    def test_board_indices(self, board_store, db_conn):
        """Relevant indices should exist."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = {row["name"] for row in cursor.fetchall()}
        assert "idx_gk_board_threads_status" in indices
        assert "idx_gk_board_posts_thread" in indices


class TestAnnouncementSchema:
    """Validate AnnouncementStore.ensure_tables() schema."""

    def test_announcements_table_created(self, announcement_store, db_conn):
        """Announcement table should exist."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "gk_announcements" in tables

    def test_announcements_columns(self, announcement_store, db_conn):
        """Verify announcement columns."""
        cursor = db_conn.cursor()
        cursor.execute("PRAGMA table_info(gk_announcements)")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {
            "id", "title", "content", "severity", "pinned", "status",
            "starts_at", "ends_at", "author_id", "author_nickname",
            "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing: {expected - columns}"


class TestSchemaIntegrity:
    """Cross-service schema integrity tests."""

    def test_concurrent_init_no_conflict(self, mock_store):
        """All services can initialize concurrently on the same store."""
        from auth_service import GameKnowledgeAuthService
        from board_store import BoardStore
        from announcement_store import AnnouncementStore

        GameKnowledgeAuthService(store=mock_store)
        BoardStore(store=mock_store)
        AnnouncementStore(store=mock_store)

        cursor = mock_store._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "game_knowledge_users" in tables
        assert "gk_board_threads" in tables
        assert "gk_announcements" in tables

    def test_table_prefix_isolation(self, auth_service, board_store, announcement_store, db_conn):
        """Different services use distinct table prefixes."""
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row["name"] for row in cursor.fetchall()]
        # Auth uses 'game_knowledge_' prefix
        assert any(t.startswith("game_knowledge_") for t in tables)
        # Board uses 'gk_board_' prefix
        assert any(t.startswith("gk_board_") for t in tables)
        # Announcement uses 'gk_announce' prefix
        assert any(t.startswith("gk_announce") for t in tables)
