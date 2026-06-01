"""End-to-end integration tests simulating real production workflows.

Covers complete user journeys: registration → login → board thread creation →
answer collection → resolution → announcement publishing → user management.
All using the same in-memory SQLite backend without external dependencies.
"""

from __future__ import annotations

import time

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1: Full User Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestUserLifecycle:

    def test_full_registration_to_deletion(self, auth_service):
        """Complete user journey: register → login → change password → disable → delete."""
        # 1. Register
        user = auth_service.register_user(
            username="111222333", password="Initial1234",
            display_name="Alice",
        )
        assert user["username"] == "111222333"
        assert user["status"] == "active"

        # 2. Login
        logged_in = auth_service.authenticate_password("111222333", "Initial1234")
        assert logged_in is not None
        assert logged_in["display_name"] == "Alice"

        # 3. Issue token
        token = auth_service.issue_token(logged_in["id"])
        verified = auth_service.authenticate_token(token)
        assert verified is not None

        # 4. Change password
        ok = auth_service.change_password(
            user["id"], current_password="Initial1234", new_password="Updated5678",
        )
        assert ok is True

        # 5. Old password no longer works
        assert auth_service.authenticate_password("111222333", "Initial1234") is None

        # 6. Old token invalidated
        assert auth_service.authenticate_token(token) is None

        # 7. New password works
        assert auth_service.authenticate_password("111222333", "Updated5678") is not None

        # 8. Disable account
        auth_service.update_user(user["id"], status="disabled")
        assert auth_service.authenticate_password("111222333", "Updated5678") is None

        # 9. Delete
        assert auth_service.delete_user(user["id"]) is True
        assert auth_service.get_user(user["id"]) is None

    def test_multiple_user_registration_and_login(self, auth_service):
        """Create 5 users, all can log in independently."""
        users = []
        for i in range(5):
            user = auth_service.register_user(
                username=f"22233344{i}", password=f"MultiUser{i}Pass",
                display_name=f"User {i}",
            )
            users.append(user)

        for i, user in enumerate(users):
            result = auth_service.authenticate_password(
                user["username"], f"MultiUser{i}Pass",
            )
            assert result is not None
            assert result["display_name"] == f"User {i}"

    def test_login_lockout_and_recovery(self, auth_service):
        """Account locks after 5 failures, recovers after timeout simulation."""
        auth_service.create_user(username="lock_recover", password="GoodPass123")

        # 5 failed attempts
        for _ in range(5):
            auth_service.authenticate_password("lock_recover", "BadPass12345")

        # Account should be locked
        raw = auth_service._get_raw_user(
            [u for u in auth_service.list_users() if u["username"] == "lock_recover"][0]["id"]
        )
        assert raw["failed_login_count"] == 5
        assert raw["locked_until"] is not None

        # Clear lock manually (simulate timeout)
        cursor = auth_service._conn.cursor()
        cursor.execute(
            "UPDATE game_knowledge_users SET locked_until=NULL WHERE username='lock_recover'",
        )
        auth_service._conn.commit()

        # Now can log in
        result = auth_service.authenticate_password("lock_recover", "GoodPass123")
        assert result is not None
        assert result["failed_login_count"] == 0  # Reset on successful login


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 2: Board System Full Flow
# ═══════════════════════════════════════════════════════════════════════════

class TestBoardFullFlow:

    def test_complete_board_lifecycle(self, board_store):
        """Full board flow: create → reply → forward → collect → resolve → close."""
        # 1. User creates a question thread
        thread = board_store.create_thread(
            title="Dragon Eye Recipe?",
            content="I need the crafting recipe for Dragon's Eye in the game.",
            author_id="user_001",
            author_nickname="Player1",
        )
        assert thread["status"] == "open"
        tid = thread["id"]

        # 2. Other users reply
        r1 = board_store.add_post(tid, content="Dragon's Eye needs Glowing Gem + Dragon Skull.",
                                  author_id="user_002", author_nickname="Helper1")
        r2 = board_store.add_post(tid, content="Also requires a Diamond Block in the center.",
                                  author_id="user_003", author_nickname="Helper2")
        assert r1 is not None and r2 is not None

        # 3. Thread has 2 replies
        thread = board_store.get_thread(tid)
        assert thread["reply_count"] == 2

        # 4. Auto-forward to QQ group (simulated)
        collected_until = time.time() + 1200
        board_store.mark_forwarded(
            tid,
            forwarded_message_id="msg_forward_001",
            forward_target_group_id="100000001",
            collected_until=collected_until,
        )
        thread = board_store.get_thread(tid)
        assert thread["status"] == "collecting"
        assert thread["forward_target_group_id"] == "100000001"

        # 5. QQ users reply (collected)
        count = board_store.append_collected_qq_post(
            tid, content="You also need Nether Star!",
            source_user_id="qq_123", source_message_id="msg_qq_001",
            author_nickname="QQ Expert",
        )
        assert count == 1

        count = board_store.append_collected_qq_post(
            tid, content="Don't forget the blaze powder.",
            source_user_id="qq_456", source_message_id="msg_qq_002",
            author_nickname="QQ Helper",
        )
        assert count == 2

        thread = board_store.get_thread(tid)
        assert thread["collected_message_count"] == 2

        # 6. Moderator resolves
        board_store.mark_resolved(tid, resolved_by_id="mod_001")
        thread = board_store.get_thread(tid)
        assert thread["status"] == "resolved"

        # 7. Close
        board_store.close_thread(tid)
        thread = board_store.get_thread(tid)
        assert thread["status"] == "closed"

        # 8. Verify total posts
        posts = board_store.list_posts(tid)
        assert len(posts) >= 5  # OP + 2 web replies + 2 QQ collected

    def test_get_thread_with_all_posts(self, board_store):
        """get_thread_with_posts returns complete thread data."""
        t = board_store.create_thread(title="Full Thread", content="OP content",
                                      author_id="u1", author_nickname="OP")
        board_store.add_post(t["id"], content="R1", author_id="u2", author_nickname="U2")
        board_store.add_post(t["id"], content="R2", author_id="u3", author_nickname="U3")

        result = board_store.get_thread_with_posts(t["id"])
        assert result is not None
        assert "posts" in result
        assert len(result["posts"]) == 3
        # Posts are ordered
        assert result["posts"][0]["content"] == "OP content"
        assert result["posts"][1]["content"] == "R1"
        assert result["posts"][2]["content"] == "R2"

    def test_collected_post_sources_are_correct(self, board_store):
        """Web posts have source='web', QQ posts have source='qq'."""
        t = board_store.create_thread(title="Source Test", content="OP",
                                      author_id="u", author_nickname="U")
        board_store.add_post(t["id"], content="Web Reply", author_id="u", author_nickname="U",
                             source="web")
        board_store.mark_forwarded(t["id"], forwarded_message_id="m", forward_target_group_id="123",
                                    collected_until=time.time() + 1200)
        board_store.append_collected_qq_post(t["id"], content="QQ Reply",
                                              source_user_id="qq", source_message_id="msg")

        posts = board_store.list_posts(t["id"])
        sources = {p["source"] for p in posts}
        assert "web" in sources
        assert "qq" in sources


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 3: Announcement System
# ═══════════════════════════════════════════════════════════════════════════

class TestAnnouncementFullFlow:

    def test_announcement_lifecycle(self, announcement_store):
        """Create announcement → verify active → mark ended → verify inactive."""
        # 1. Create active announcement
        ann = announcement_store.create(
            title="Maintenance Tonight",
            content="System will be unavailable from 2-4 AM.",
            severity="warning", pinned=True, status="published",
            starts_at=time.time() - 100, ends_at=time.time() + 10000,
            author_id="admin", author_nickname="Admin",
        )
        assert ann["pinned"] is True
        assert ann["severity"] == "warning"

        # 2. It appears in active list
        active = announcement_store.list_active()
        assert any(a["id"] == ann["id"] for a in active)

        # 3. Create expired announcement
        expired = announcement_store.create(
            title="Old News", content="This already ended.",
            severity="info", pinned=False, status="published",
            starts_at=None, ends_at=time.time() - 1,
            author_id="admin", author_nickname="Admin",
        )

        # 4. Expired is not in active list
        active = announcement_store.list_active()
        expired_ids = {a["id"] for a in active}
        assert expired["id"] not in expired_ids

        # 5. Delete announcement
        assert announcement_store.delete(ann["id"]) is True
        assert announcement_store.get(ann["id"]) is None

    def test_multiple_active_announcements(self, announcement_store):
        """Multiple announcements can be active simultaneously."""
        now = time.time()
        ids = []
        for i in range(5):
            ann = announcement_store.create(
                title=f"Active {i}", content=f"Content {i}",
                severity="info", pinned=(i == 0), status="published",
                starts_at=now, ends_at=now + 86400,
                author_id="admin", author_nickname="Admin",
            )
            ids.append(ann["id"])

        active = announcement_store.list_active()
        assert len(active) >= 5

        # Pinned first
        assert active[0]["pinned"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 4: Cross-Service RBAC
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossServiceRBAC:

    def test_permissions_across_groups(self, auth_service):
        """Verify permission inheritance across all groups."""
        admin = auth_service.create_user(username="cross_admin", password="Adm123456",
                                          group_ids=["admin"])
        maintainer = auth_service.create_user(username="cross_maint", password="Mnt123456",
                                               group_ids=["maintainer"])
        reviewer = auth_service.create_user(username="cross_review", password="Rev123456",
                                              group_ids=["reviewer"])
        editor = auth_service.create_user(username="cross_editor", password="Edt123456",
                                           group_ids=["editor"])
        viewer = auth_service.create_user(username="cross_viewer", password="Vwr123456",
                                           group_ids=["viewer"])

        # Admin can do anything
        assert auth_service.user_has_permission(admin, "users.manage") is True
        assert auth_service.user_has_permission(admin, "board.delete_any") is True

        # Maintainer can manage sources and maintenance but not users
        assert auth_service.user_has_permission(maintainer, "sources.manage") is True
        assert auth_service.user_has_permission(maintainer, "users.manage") is False

        # Reviewer can approve but not delete
        assert auth_service.user_has_permission(reviewer, "review.approve") is True
        assert auth_service.user_has_permission(reviewer, "knowledge.delete") is False

        # Editor can create knowledge but not approve
        assert auth_service.user_has_permission(editor, "knowledge.create") is True
        assert auth_service.user_has_permission(editor, "review.approve") is False

        # Viewer can only search and view
        assert auth_service.user_has_permission(viewer, "knowledge.search") is True
        assert auth_service.user_has_permission(viewer, "knowledge.create") is False
        assert auth_service.user_has_permission(viewer, "knowledge.delete") is False

    def test_dual_role_user(self, auth_service):
        """User with two groups gets combined permissions."""
        user = auth_service.create_user(username="dual_role", password="Dual12345",
                                         group_ids=["editor", "reviewer"])
        assert auth_service.user_has_permission(user, "knowledge.create") is True  # editor
        assert auth_service.user_has_permission(user, "review.approve") is True    # reviewer
        assert auth_service.user_has_permission(user, "knowledge.delete") is False  # neither


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 5: Audit Trail Completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditCompleteness:

    def test_audit_captures_all_events(self, auth_service):
        """All major operations are recorded in the audit trail."""
        # User creation
        auth_service.create_user(username="audit_complete", password="Audit1234",
                                 display_name="Auditor")

        # Login + failed login
        auth_service.authenticate_password("audit_complete", "Audit1234", ip="10.0.0.1")
        auth_service.authenticate_password("audit_complete", "wrong", ip="10.0.0.1")

        # Get user ID
        user = [u for u in auth_service.list_users() if u["username"] == "audit_complete"][0]

        # Change password
        auth_service.change_password(user["id"], current_password="Audit1234",
                                      new_password="NewAudit5678")

        # Disable user
        auth_service.update_user(user["id"], status="disabled")

        # Delete user
        auth_service.delete_user(user["id"])

        # Check audit
        events = auth_service.list_audit_events(limit=50)
        event_types = {e["event"] for e in events}

        expected_events = {
            "user.create", "auth.login", "auth.change_password",
            "user.update", "user.delete",
        }
        for expected in expected_events:
            assert expected in event_types, f"Audit should contain {expected}"

        # Both success and failure events
        assert any(e["success"] == 1 for e in events), "Should have success events"
        assert any(e["success"] == 0 for e in events), "Should have failure events"

    def test_audit_limit(self, auth_service):
        """Audit respects limit parameter."""
        for i in range(30):
            auth_service.create_user(username=f"audit_limit_{i:03d}", password=f"Limit{i:03d}Pass")
        events = auth_service.list_audit_events(limit=10)
        assert len(events) <= 10


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 6: Data Integrity
# ═══════════════════════════════════════════════════════════════════════════

class TestDataIntegrity:

    def test_thread_post_consistency(self, board_store):
        """Deleting a thread also deletes all its posts."""
        t = board_store.create_thread(title="Cascade", content="OP",
                                      author_id="u", author_nickname="U")
        board_store.add_post(t["id"], content="R1", author_id="u", author_nickname="U")
        board_store.add_post(t["id"], content="R2", author_id="u", author_nickname="U")

        posts_before = len(board_store.list_posts(t["id"]))
        assert posts_before == 3

        board_store.delete_thread(t["id"])

        # Thread is gone
        assert board_store.get_thread(t["id"]) is None
        # Posts should be gone too (cascade delete)
        assert len(board_store.list_posts(t["id"])) == 0

    def test_reply_count_consistency(self, board_store):
        """reply_count stays consistent after add/delete operations."""
        t = board_store.create_thread(title="Count Check", content="OP",
                                      author_id="u", author_nickname="U")

        # Add 5 posts
        post_ids = []
        for i in range(5):
            p = board_store.add_post(t["id"], content=f"R{i}", author_id="u", author_nickname="U")
            post_ids.append(p["id"])

        t = board_store.get_thread(t["id"])
        assert t["reply_count"] == 5, f"Expected 5 replies, got {t['reply_count']}"

        # Delete 2 posts
        board_store.delete_post(post_ids[0])
        board_store.delete_post(post_ids[1])

        t = board_store.get_thread(t["id"])
        assert t["reply_count"] == 3, f"Expected 3 replies after delete, got {t['reply_count']}"

    def test_user_group_consistency(self, auth_service):
        """User group memberships are cleaned up on user deletion."""
        user = auth_service.create_user(username="cleanup_test", password="Cleanup123",
                                         group_ids=["editor", "reviewer"])

        # Verify group memberships exist
        groups = auth_service._groups_for_user(user["id"])
        assert len(groups) == 2

        # Delete user
        auth_service.delete_user(user["id"])

        # Group memberships should be gone
        groups_after = auth_service._groups_for_user(user["id"])
        assert len(groups_after) == 0
