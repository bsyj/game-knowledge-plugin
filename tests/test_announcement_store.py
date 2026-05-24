"""Comprehensive tests for AnnouncementStore — CRUD, listing, filtering, activation checks.

Covers: create/read/delete announcements, severity validation, time-based
activation, pinning, and active announcement listing.
"""

from __future__ import annotations

import time

import pytest
from announcement_store import AnnouncementStore


# ═══════════════════════════════════════════════════════════════════════════
# CRUD Operations
# ═══════════════════════════════════════════════════════════════════════════

class TestAnnouncementCRUD:

    def test_create_announcement_success(self, announcement_store):
        """Create announcement with all fields."""
        ann = announcement_store.create(
            title="System Maintenance Notice",
            content="The knowledge base will be updated at 3 AM UTC.",
            severity="warning",
            pinned=True,
            status="published",
            starts_at=None,
            ends_at=None,
            author_id="admin_001",
            author_nickname="Admin",
        )
        assert ann["id"] >= 1
        assert ann["title"] == "System Maintenance Notice"
        assert ann["severity"] == "warning"
        assert ann["pinned"] is True
        assert ann["status"] == "published"

    def test_create_announcement_minimal(self, announcement_store):
        """Create announcement with only required fields."""
        ann = announcement_store.create(
            title="Hello",
            content="Welcome!",
            severity="info",
            pinned=False,
            status="published",
            starts_at=None,
            ends_at=None,
            author_id="u1",
            author_nickname="U",
        )
        assert ann is not None
        assert ann["id"] >= 1

    def test_create_empty_title(self, announcement_store):
        """Empty title raises ValueError."""
        with pytest.raises(ValueError, match="标题"):
            announcement_store.create(
                title="  ", content="Body",
                severity="info", pinned=False, status="published",
                starts_at=None, ends_at=None, author_id="a", author_nickname="A",
            )

    def test_create_long_title(self, announcement_store):
        """Title > 200 chars raises ValueError."""
        with pytest.raises(ValueError, match="标题"):
            announcement_store.create(
                title="X" * 201, content="Body",
                severity="info", pinned=False, status="published",
                starts_at=None, ends_at=None, author_id="a", author_nickname="A",
            )

    def test_create_empty_content(self, announcement_store):
        """Empty content raises ValueError."""
        with pytest.raises(ValueError, match="正文"):
            announcement_store.create(
                title="Title", content="  ",
                severity="info", pinned=False, status="published",
                starts_at=None, ends_at=None, author_id="a", author_nickname="A",
            )

    def test_create_long_content(self, announcement_store):
        """Content > 20000 chars raises ValueError."""
        with pytest.raises(ValueError, match="正文"):
            announcement_store.create(
                title="Title", content="X" * 20001,
                severity="info", pinned=False, status="published",
                starts_at=None, ends_at=None, author_id="a", author_nickname="A",
            )

    def test_get_announcement(self, announcement_store):
        """get returns announcement or None."""
        ann = announcement_store.create(
            title="Get Me", content="Content",
            severity="info", pinned=False, status="published",
            starts_at=None, ends_at=None, author_id="a", author_nickname="A",
        )
        fetched = announcement_store.get(ann["id"])
        assert fetched is not None
        assert fetched["title"] == "Get Me"

        assert announcement_store.get(99999) is None

    def test_delete_announcement(self, announcement_store):
        """delete removes announcement."""
        ann = announcement_store.create(
            title="Delete Me", content="Bye",
            severity="info", pinned=False, status="published",
            starts_at=None, ends_at=None, author_id="a", author_nickname="A",
        )
        assert announcement_store.delete(ann["id"]) is True
        assert announcement_store.get(ann["id"]) is None

    def test_delete_nonexistent(self, announcement_store):
        """Deleting nonexistent returns False."""
        assert announcement_store.delete(99999) is False


# ═══════════════════════════════════════════════════════════════════════════
# Severity & Status Validation
# ═══════════════════════════════════════════════════════════════════════════

class TestSeverityAndStatus:

    def test_severity_values(self, announcement_store):
        """Only info/warning/critical are valid severities."""
        for sev in ["info", "warning", "critical"]:
            ann = announcement_store.create(
                title=f"Sev {sev}", content="C",
                severity=sev, pinned=False, status="published",
                starts_at=None, ends_at=None, author_id="a", author_nickname="A",
            )
            assert ann["severity"] == sev

    def test_invalid_severity_normalized(self, announcement_store):
        """Invalid severity is normalized to 'info'."""
        ann = announcement_store.create(
            title="Bad Sev", content="C",
            severity="urgent", pinned=False, status="published",
            starts_at=None, ends_at=None, author_id="a", author_nickname="A",
        )
        assert ann["severity"] == "info"

    def test_status_values(self, announcement_store):
        """Only draft/published are valid statuses."""
        ann = announcement_store.create(
            title="Draft", content="C",
            severity="info", pinned=False, status="draft",
            starts_at=None, ends_at=None, author_id="a", author_nickname="A",
        )
        assert ann["status"] == "draft"

    def test_invalid_status_normalized(self, announcement_store):
        """Invalid status is normalized to 'published'."""
        ann = announcement_store.create(
            title="Bad Status", content="C",
            severity="info", pinned=False, status="archived",
            starts_at=None, ends_at=None, author_id="a", author_nickname="A",
        )
        assert ann["status"] == "published"

    def test_normalize_severity_classmethod(self):
        """normalize_severity returns valid values."""
        assert AnnouncementStore.normalize_severity("info") == "info"
        assert AnnouncementStore.normalize_severity("WARNING") == "warning"
        assert AnnouncementStore.normalize_severity("unknown") == "info"
        assert AnnouncementStore.normalize_severity(None) == "info"

    def test_normalize_status_classmethod(self):
        """normalize_status returns valid values."""
        assert AnnouncementStore.normalize_status("published") == "published"
        assert AnnouncementStore.normalize_status("DRAFT") == "draft"
        assert AnnouncementStore.normalize_status("unknown") == "published"


# ═══════════════════════════════════════════════════════════════════════════
# Listing & Filtering
# ═══════════════════════════════════════════════════════════════════════════

class TestAnnouncementListing:

    def test_list_default(self, announcement_store):
        """List returns all published announcements."""
        announcement_store.create(
            title="A1", content="C1", severity="info", pinned=False,
            status="published", starts_at=None, ends_at=None,
            author_id="a", author_nickname="A",
        )
        announcement_store.create(
            title="A2", content="C2", severity="info", pinned=False,
            status="published", starts_at=None, ends_at=None,
            author_id="b", author_nickname="B",
        )
        result = announcement_store.list()
        assert result["total"] >= 2

    def test_list_status_filter(self, announcement_store):
        """Filter by status."""
        announcement_store.create(
            title="Pub", content="C", severity="info", pinned=False,
            status="published", starts_at=None, ends_at=None,
            author_id="a", author_nickname="A",
        )
        announcement_store.create(
            title="Dft", content="C", severity="info", pinned=False,
            status="draft", starts_at=None, ends_at=None,
            author_id="b", author_nickname="B",
        )
        pub = announcement_store.list(status="published")
        assert all(a["status"] == "published" for a in pub["items"])
        draft = announcement_store.list(status="draft")
        assert all(a["status"] == "draft" for a in draft["items"])

    def test_list_include_inactive(self, announcement_store):
        """include_inactive=False filters out expired/timed announcements."""
        now = time.time()
        announcement_store.create(
            title="Active", content="C", severity="info", pinned=False,
            status="published",
            starts_at=now - 100, ends_at=now + 1000,
            author_id="a", author_nickname="A",
        )
        announcement_store.create(
            title="Expired", content="C", severity="info", pinned=False,
            status="published",
            starts_at=None, ends_at=now - 1,  # Already ended
            author_id="b", author_nickname="B",
        )
        result_active = announcement_store.list(include_inactive=False)
        assert result_active["total"] >= 1
        titles = {a["title"] for a in result_active["items"]}
        assert "Active" in titles

    def test_list_pagination(self, announcement_store):
        """Limit and offset work."""
        for i in range(10):
            announcement_store.create(
                title=f"A{i}", content=f"C{i}", severity="info", pinned=False,
                status="published", starts_at=None, ends_at=None,
                author_id="a", author_nickname="A",
            )
        result = announcement_store.list(limit=3, offset=0)
        assert len(result["items"]) <= 3
        assert result["total"] >= 10

    def test_list_pinned_first(self, announcement_store):
        """Pinned announcements come first."""
        announcement_store.create(
            title="Normal", content="C", severity="info", pinned=False,
            status="published", starts_at=None, ends_at=None,
            author_id="a", author_nickname="A",
        )
        announcement_store.create(
            title="Pinned", content="C", severity="info", pinned=True,
            status="published", starts_at=None, ends_at=None,
            author_id="b", author_nickname="B",
        )
        result = announcement_store.list()
        assert result["items"][0]["pinned"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Active Announcements
# ═══════════════════════════════════════════════════════════════════════════

class TestActiveAnnouncements:

    def test_list_active_default(self, announcement_store):
        """list_active returns currently active announcements."""
        now = time.time()
        announcement_store.create(
            title="Now Active", content="C", severity="info", pinned=False,
            status="published",
            starts_at=now - 100, ends_at=now + 1000,
            author_id="a", author_nickname="A",
        )
        active = announcement_store.list_active()
        assert len(active) >= 1
        assert any(a["title"] == "Now Active" for a in active)

    def test_list_active_excludes_future(self, announcement_store):
        """Announcements with future starts_at are not active."""
        now = time.time()
        announcement_store.create(
            title="Future", content="C", severity="info", pinned=False,
            status="published",
            starts_at=now + 10000, ends_at=None,
            author_id="a", author_nickname="A",
        )
        active = announcement_store.list_active()
        assert not any(a["title"] == "Future" for a in active)

    def test_list_active_excludes_ended(self, announcement_store):
        """Announcements past ends_at are not active."""
        now = time.time()
        announcement_store.create(
            title="Ended", content="C", severity="info", pinned=False,
            status="published",
            starts_at=None, ends_at=now - 1,
            author_id="a", author_nickname="A",
        )
        active = announcement_store.list_active()
        assert not any(a["title"] == "Ended" for a in active)

    def test_list_active_excludes_draft(self, announcement_store):
        """Draft announcements are never active."""
        announcement_store.create(
            title="Draft Active", content="C", severity="info", pinned=False,
            status="draft",
            starts_at=None, ends_at=None,
            author_id="a", author_nickname="A",
        )
        active = announcement_store.list_active()
        assert not any(a["title"] == "Draft Active" for a in active)

    def test_list_active_limit(self, announcement_store):
        """list_active respects limit parameter."""
        now = time.time()
        for i in range(10):
            announcement_store.create(
                title=f"Active {i}", content=f"C{i}", severity="info", pinned=False,
                status="published",
                starts_at=now - 10, ends_at=now + 10000,
                author_id="a", author_nickname="A",
            )
        active = announcement_store.list_active(limit=3)
        assert len(active) <= 3

    def test_is_currently_active(self):
        """_is_currently_active static method logic."""
        now = time.time()
        # Active
        assert AnnouncementStore._is_currently_active({
            "status": "published", "starts_at": now - 1, "ends_at": now + 1,
        }) is True
        # Draft not active
        assert AnnouncementStore._is_currently_active({
            "status": "draft", "starts_at": None, "ends_at": None,
        }) is False
        # Future starts_at
        assert AnnouncementStore._is_currently_active({
            "status": "published", "starts_at": now + 100, "ends_at": None,
        }) is False
        # Past ends_at
        assert AnnouncementStore._is_currently_active({
            "status": "published", "starts_at": None, "ends_at": now - 1,
        }) is False
        # No restrictions
        assert AnnouncementStore._is_currently_active({
            "status": "published", "starts_at": None, "ends_at": None,
        }) is True


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestAnnouncementEdgeCases:

    def test_create_many_announcements(self, announcement_store):
        """Create 30 announcements without issues."""
        for i in range(30):
            ann = announcement_store.create(
                title=f"Bulk A{i}", content=f"Content {i}",
                severity="info", pinned=False, status="published",
                starts_at=None, ends_at=None,
                author_id="a", author_nickname="A",
            )
            assert ann["id"] >= 1

    def test_special_characters(self, announcement_store):
        """Unicode and special chars are preserved."""
        ann = announcement_store.create(
            title="📢 系统升级通知【重要】",
            content="中英文混合 'single' \"double\" emoji 🎮⚔️",
            severity="critical", pinned=True, status="published",
            starts_at=None, ends_at=None,
            author_id="admin", author_nickname="管理员",
        )
        assert "📢" in ann["title"]
        assert "🎮⚔️" in ann["content"]

    def test_severity_constant_values(self):
        """SEVERITY_VALUES contains expected values."""
        assert AnnouncementStore.SEVERITY_VALUES == ("info", "warning", "critical")

    def test_status_constant_values(self):
        """STATUS_VALUES contains expected values."""
        assert AnnouncementStore.STATUS_VALUES == ("draft", "published")
