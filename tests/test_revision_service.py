"""Comprehensive tests for GameKnowledgeRevisionService.

Covers: card revision from search hits, card-by-ID revision, approved-card
revision creation, content update boundary checks, and search-hit-to-card building.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import pytest
from revision_service import GameKnowledgeRevisionService


# ═══════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════

def _make_card(store, **overrides) -> Dict[str, Any]:
    """Insert a card into the mock store and return it."""
    data = {
        "title": "Test Card",
        "question": "What is this?",
        "answer": "This is the answer content, long enough for testing purposes.",
        "category": "机制",
        "answer_type": "mechanic",
        "valid_status": "active",
        "platform": "qq",
        "source_platform": "qq",
        "tags": ["mechanic"],
        **overrides,
    }
    return store.upsert_knowledge_card(data)


# ═══════════════════════════════════════════════════════════════════════════
# Revise Target (entry point routing)
# ═══════════════════════════════════════════════════════════════════════════

class TestReviseTarget:

    def test_revise_target_empty(self, revision_service):
        """Empty target returns error."""
        result = revision_service.revise_target("", {"title": "X"})
        assert result["success"] is False
        assert "target" in result["error"]

    def test_revise_target_by_card_hash(self, revision_service, mock_store):
        """Revise an existing card by its card_hash."""
        card = _make_card(mock_store, card_hash="hash_abc")
        result = revision_service.revise_target(
            "hash_abc",
            {"title": "Updated Title", "answer": "Updated answer content long enough for test."},
        )
        assert result["success"] is True
        assert result["mode"] == "update"

    def test_revise_target_by_paragraph_hash(self, revision_service, mock_store):
        """Revise a card found by paragraph_hash."""
        _make_card(mock_store, paragraph_hash="ph_001", card_hash="ph_card")
        result = revision_service.revise_target(
            "ph_001",
            {"title": "From PH", "answer": "Content from paragraph hash revision."},
        )
        assert result["success"] is True

    def test_revise_target_not_found(self, revision_service, mock_store):
        """Nonexistent target returns 404."""
        # Ensure we have the table but no matching record
        result = revision_service.revise_target("no_such_hash", {"title": "X"})
        assert result["success"] is False
        assert result["status"] == 404

    def test_revise_target_paragraph_not_found(self, revision_service, mock_store):
        """Target not found in cards or paragraphs returns 404."""
        result = revision_service.revise_target(
            "nonexistent_hash",
            {"title": "Not Found"},
        )
        assert result["success"] is False
        assert result["status"] == 404


# ═══════════════════════════════════════════════════════════════════════════
# Revise by Card ID
# ═══════════════════════════════════════════════════════════════════════════

class TestReviseCardId:

    def test_revise_card_id_success(self, revision_service, mock_store):
        """Revise a pending card by ID."""
        card = _make_card(mock_store, review_status="pending", card_hash="pending_card")
        result = revision_service.revise_card_id(
            card["id"],
            {"title": "Revised Pending", "answer": "Revised answer content."},
        )
        assert result["success"] is True
        assert result["mode"] == "update"
        assert result["card"]["title"] == "Revised Pending"

    def test_revise_card_id_not_found(self, revision_service):
        """Nonexistent card ID returns 404."""
        result = revision_service.revise_card_id(99999, {"title": "X"})
        assert result["success"] is False
        assert result["status"] == 404

    def test_revise_approved_card_creates_revision(self, revision_service, mock_store):
        """Revising an approved card creates a revision instead of editing."""
        card = _make_card(mock_store, review_status="approved", card_hash="approved_rev")
        result = revision_service.revise_card_id(
            card["id"],
            {"title": "Revision Title", "answer": "Revision answer content long enough."},
            actor_id="reviewer_1",
            actor_name="Reviewer One",
        )
        assert result["success"] is True
        assert result["mode"] in ("revision", "revision_reused")
        assert result["card"]["review_status"] == "pending"

    def test_revise_approved_card_reuses_pending_revision(self, revision_service, mock_store):
        """Second revision of same approved card reuses the pending revision."""
        card = _make_card(mock_store, review_status="approved", card_hash="multi_rev")
        # First revision
        rev1 = revision_service.revise_card_id(
            card["id"],
            {"title": "Rev 1", "answer": "First revision answer."},
        )
        assert rev1["success"] is True
        # Second revision
        rev2 = revision_service.revise_card_id(
            card["id"],
            {"title": "Rev 2", "answer": "Second revision answer content."},
        )
        assert rev2["success"] is True
        assert rev2["mode"] == "revision_reused"
        assert rev2["card"]["title"] == "Rev 2"

    def test_revise_with_optimistic_lock(self, revision_service, mock_store):
        """Revision with expected_updated_at matching passes."""
        card = _make_card(mock_store, review_status="pending", card_hash="lock_card")
        result = revision_service.revise_card_id(
            card["id"],
            {"title": "Locked Update", "answer": "Updated with lock."},
            expected_updated_at=card["updated_at"],
        )
        assert result["success"] is True

    def test_revise_with_optimistic_lock_conflict(self, revision_service, mock_store):
        """Revision with stale expected_updated_at fails (ValueError)."""
        card = _make_card(mock_store, review_status="pending", card_hash="conflict_card")
        with pytest.raises(ValueError, match="已被他人修改"):
            revision_service.revise_card_id(
                card["id"],
                {"title": "Conflict", "answer": "Should fail."},
                expected_updated_at=1.0,  # Very old
            )


# ═══════════════════════════════════════════════════════════════════════════
# Build Card from Search Hit
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildCardFromSearchHit:

    def test_build_basic(self):
        """Build a card from a minimal search hit."""
        paragraph = {
            "content": "This is the answer content.",
            "metadata": {"title": "Test Title"},
        }
        payload = {"title": "My Title", "category": "机制"}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hit_hash_001", paragraph, payload,
        )
        assert card["title"] == "My Title"
        assert card["category"] == "机制"
        assert card["answer"] == "This is the answer content."
        assert card["review_status"] == "pending"
        assert card["ai_review_status"] == "manual_revision"
        assert "hit_hash_001" in card["evidence"]

    def test_build_derives_title_from_content(self):
        """Title is derived from content first line if not provided."""
        paragraph = {
            "content": "First line title\nSecond line details",
            "metadata": {},
        }
        payload = {}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert card["title"] == "First line title"

    def test_build_derives_question_from_content(self):
        """Question is extracted from 'Q:' prefixed lines."""
        paragraph = {
            "content": "Some text\nQ: How to craft?\nA: Use 4 iron.",
            "metadata": {},
        }
        payload = {}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert card["title"] == "Some text"
        assert card["question"] == "How to craft?"

    def test_build_fallback_title(self):
        """Fallback title when content is empty."""
        paragraph = {"content": "", "metadata": {}}
        payload = {}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert card["title"] == "检索结果修订"

    def test_build_preserves_metadata_fields(self):
        """Metadata fields are carried over."""
        paragraph = {
            "content": "Answer text here.",
            "metadata": {
                "title": "Meta Title",
                "question": "Meta Question?",
                "game_id": "game_123",
                "platform": "qq",
                "rlcraft_version": "2.9.3",
                "answer_type": "mechanic",
            },
        }
        payload = {}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert card["game_id"] == "game_123"
        assert card["rlcraft_version"] == "2.9.3"

    def test_build_payload_overrides_metadata(self):
        """Payload fields take precedence over metadata."""
        paragraph = {
            "content": "Text",
            "metadata": {"category": "old_cat"},
        }
        payload = {"category": "new_cat"}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert card["category"] == "new_cat"

    def test_build_default_values(self):
        """Default values are set for missing fields."""
        paragraph = {"content": "Content", "metadata": {}}
        payload = {}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert card["category"] == "其他"
        assert card["answer_type"] == "other"
        assert card["valid_status"] == "active"
        assert card["review_status"] == "pending"
        assert "game_knowledge" in card["tags"]


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestRevisionEdgeCases:

    def test_revise_with_empty_payload(self, revision_service, mock_store):
        """Empty-ish payload doesn't crash."""
        card = _make_card(mock_store, review_status="pending", card_hash="empty_payload")
        result = revision_service.revise_card_id(card["id"], {})
        assert result["success"] is True

    def test_revise_with_special_characters(self, revision_service, mock_store):
        """Unicode and special chars in payload are preserved."""
        card = _make_card(mock_store, review_status="pending", card_hash="unicode_card")
        result = revision_service.revise_card_id(
            card["id"],
            {
                "title": "🎮 修订【测试】",
                "answer": "中文：，。！？ 'quotes' — emoji ⚔️",
            },
        )
        assert result["success"] is True
        assert "🎮" in result["card"]["title"]
        assert "⚔️" in result["card"]["answer"]

    def test_build_card_steps_preserved(self):
        """Steps list is preserved if provided."""
        paragraph = {"content": "Steps content", "metadata": {}}
        payload = {"steps": ["Step 1: Mine", "Step 2: Craft", "Step 3: Use"]}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert isinstance(card["steps"], list)
        assert len(card["steps"]) == 3

    def test_build_card_aliases_preserved(self):
        """Aliases list is preserved."""
        paragraph = {"content": "Alias test", "metadata": {}}
        payload = {"aliases": ["alias1", "alias2", "alias3"]}
        card = GameKnowledgeRevisionService.build_card_from_search_hit(
            "hash", paragraph, payload,
        )
        assert card["aliases"] == ["alias1", "alias2", "alias3"]
