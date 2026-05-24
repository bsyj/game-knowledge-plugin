"""Comprehensive tests for GameKnowledgeAuthService.

Covers: user CRUD, authentication, token lifecycle, RBAC permissions,
password hashing, login lockout, captcha flow, and audit trails.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import pytest
from auth_service import (
    CaptchaCooldownError,
    GameKnowledgeAuthService,
    GROUP_DEFINITIONS,
)


# ═══════════════════════════════════════════════════════════════════════════
# User CRUD
# ═══════════════════════════════════════════════════════════════════════════

class TestUserCRUD:

    def test_create_user_success(self, auth_service):
        """Create user with valid data returns user dict."""
        user = auth_service.create_user(
            username="test_user",
            password="Test123456",
            display_name="Testy McTestface",
            group_ids=["viewer"],
        )
        assert user["username"] == "test_user"
        assert user["display_name"] == "Testy McTestface"
        assert user["status"] == "active"
        assert "id" in user
        assert len(user["id"]) == 24  # token_hex(12)
        assert "viewer" in [g["id"] for g in user.get("groups", [])]

    def test_create_user_default_group(self, auth_service):
        """User without explicit group gets 'viewer'."""
        user = auth_service.create_user(
            username="default_group_user", password="Test1234567",
        )
        assert any(g["id"] == "viewer" for g in user.get("groups", []))

    def test_create_user_invalid_username(self, auth_service):
        """Invalid usernames raise ValueError."""
        cases = [
            ("ab", "too short"),       # < 3 chars
            ("a" * 33, "too long"),    # > 32 chars
            ("with space", "has space"),
            ("中文名", "non-ASCII"),
        ]
        for name, reason in cases:
            with pytest.raises(ValueError, match="用户名"):
                auth_service.create_user(username=name, password="Valid12345")

    def test_create_user_invalid_password(self, auth_service):
        """Password length must be 8-128."""
        with pytest.raises(ValueError, match="密码"):
            auth_service.create_user(username="valid_user", password="short")
        with pytest.raises(ValueError, match="密码"):
            auth_service.create_user(username="valid_user", password="a" * 129)

    def test_get_user(self, auth_service):
        """get_user returns user or None."""
        user = auth_service.create_user(username="get_me", password="GetMe1234")
        fetched = auth_service.get_user(user["id"])
        assert fetched is not None
        assert fetched["username"] == "get_me"

        assert auth_service.get_user("nonexistent_id") is None

    def test_list_users(self, auth_service):
        """list_users returns all users."""
        auth_service.create_user(username="list_a", password="ListA1234")
        auth_service.create_user(username="list_b", password="ListB1234")
        users = auth_service.list_users()
        assert len(users) >= 2

    def test_list_users_ip_filter(self, auth_service):
        """list_users can filter by IP."""
        user = auth_service.create_user(username="ip_user", password="IpUser12345")
        # Simulate login to set IP
        auth_service.authenticate_password("ip_user", "IpUser12345", ip="192.168.1.1")
        results = auth_service.list_users(ip="192.168")
        found = any(r["id"] == user["id"] for r in results)
        assert found, "User should be found by IP filter"

    def test_update_user_display_name(self, auth_service):
        """Update display name."""
        user = auth_service.create_user(username="upd_name", password="UpdName1234")
        updated = auth_service.update_user(user["id"], display_name="New Name")
        assert updated["display_name"] == "New Name"

    def test_update_user_status(self, auth_service):
        """Change user status."""
        user = auth_service.create_user(username="upd_stat", password="UpdStat1234")
        updated = auth_service.update_user(user["id"], status="disabled")
        assert updated["status"] == "disabled"

    def test_update_user_password_invalidates_tokens(self, auth_service):
        """Changing password increments token_version, invalidating old tokens."""
        user = auth_service.create_user(username="pw_user", password="OldPass1234")
        old_token = auth_service.issue_token(user["id"])
        auth_service.update_user(user["id"], password="NewPass5678")
        # Old token should be rejected
        assert auth_service.authenticate_token(old_token) is None

    def test_update_nonexistent_user(self, auth_service):
        """Updating nonexistent user returns None."""
        assert auth_service.update_user("no_one", display_name="x") is None

    def test_delete_user(self, auth_service):
        """Delete user removes from DB and group memberships."""
        user = auth_service.create_user(username="del_me", password="DelMe12345")
        assert auth_service.delete_user(user["id"]) is True
        assert auth_service.get_user(user["id"]) is None

    def test_delete_nonexistent_user(self, auth_service):
        """Deleting nonexistent user returns False."""
        assert auth_service.delete_user("ghost") is False

    def test_update_profile(self, auth_service):
        """update_profile is shorthand for updating display_name."""
        user = auth_service.create_user(username="prof_user", password="ProfUser123")
        updated = auth_service.update_profile(user["id"], display_name="Profile Name")
        assert updated["display_name"] == "Profile Name"

    def test_display_name_max_length(self, auth_service):
        """Display name longer than 40 chars rejected."""
        with pytest.raises(ValueError, match="昵称"):
            auth_service.create_user(
                username="long_name", password="LongName123",
                display_name="a" * 41,
            )


# ═══════════════════════════════════════════════════════════════════════════
# Authentication
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthentication:

    def test_authenticate_correct_password(self, auth_service):
        """Correct password returns user dict."""
        auth_service.create_user(username="auth_ok", password="AuthOk1234")
        result = auth_service.authenticate_password("auth_ok", "AuthOk1234")
        assert result is not None
        assert result["username"] == "auth_ok"

    def test_authenticate_wrong_password(self, auth_service):
        """Wrong password returns None."""
        auth_service.create_user(username="auth_wrong", password="RightPass1")
        result = auth_service.authenticate_password("auth_wrong", "WrongPass12")
        assert result is None

    def test_authenticate_unknown_user(self, auth_service):
        """Unknown user returns None."""
        assert auth_service.authenticate_password("nobody", "AnyPassword1") is None

    def test_authenticate_disabled_user(self, auth_service):
        """Disabled user cannot log in."""
        user = auth_service.create_user(username="disabled_p", password="DisabledP1")
        auth_service.update_user(user["id"], status="disabled")
        result = auth_service.authenticate_password("disabled_p", "DisabledP1")
        assert result is None

    def test_login_lockout_after_5_failures(self, auth_service):
        """After 5 failed attempts, account is locked for 15 min."""
        auth_service.create_user(username="lock_me", password="LockMe1234")
        for _ in range(5):
            auth_service.authenticate_password("lock_me", "WrongPass12")
        # 6th attempt locked
        result = auth_service.authenticate_password("lock_me", "LockMe1234")
        assert result is None  # should be locked

        # Verify locked_until is set
        raw = auth_service._get_raw_user(
            auth_service.get_user(
                auth_service._get_raw_user(
                    [u for u in auth_service.list_users() if u["username"] == "lock_me"][0]["id"]
                )["id"]
            )
        )
        user_list = [u for u in auth_service.list_users() if u["username"] == "lock_me"]
        assert len(user_list) == 1
        assert user_list[0]["failed_login_count"] >= 5
        assert user_list[0]["locked_until"] is not None
        assert user_list[0]["locked_until"] > time.time()

    def test_login_resets_failed_count(self, auth_service):
        """Successful login resets failed_login_count to 0."""
        auth_service.create_user(username="reset_me", password="ResetMe1234")
        auth_service.authenticate_password("reset_me", "WrongPass1")
        auth_service.authenticate_password("reset_me", "WrongPass2")
        # Successful login
        result = auth_service.authenticate_password("reset_me", "ResetMe1234")
        assert result is not None
        assert result["failed_login_count"] == 0

    def test_change_password(self, auth_service):
        """change_password with correct current password succeeds."""
        user = auth_service.create_user(username="cpw_user", password="OldPass1234")
        ok = auth_service.change_password(
            user["id"], current_password="OldPass1234", new_password="NewPass5678",
        )
        assert ok is True
        # Old password no longer works
        assert auth_service.authenticate_password("cpw_user", "OldPass1234") is None
        # New password works
        assert auth_service.authenticate_password("cpw_user", "NewPass5678") is not None

    def test_change_password_wrong_current(self, auth_service):
        """change_password with wrong current password fails."""
        user = auth_service.create_user(username="cpw_bad", password="RealPass1234")
        ok = auth_service.change_password(
            user["id"], current_password="WrongPass12", new_password="NewPass5678",
        )
        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════
# Token
# ═══════════════════════════════════════════════════════════════════════════

class TestTokenLifecycle:

    def test_issue_and_verify_token(self, auth_service):
        """Issue a token and verify it."""
        user = auth_service.create_user(username="token_user", password="TokenUser12")
        token = auth_service.issue_token(user["id"])
        verified = auth_service.authenticate_token(token)
        assert verified is not None
        assert verified["username"] == "token_user"

    def test_token_endpoints(self, auth_service):
        """Tokens have correct endpoint format."""
        user = auth_service.create_user(username="tok_fmt", password="TokFmt1234")
        token = auth_service.issue_token(user["id"])
        # Format: body.signature
        assert "." in token
        assert len(token.split(".")) >= 2

    def test_invalid_token_rejected(self, auth_service):
        """Garbage tokens are rejected."""
        assert auth_service.authenticate_token("bad_token") is None
        assert auth_service.authenticate_token("") is None
        assert auth_service.authenticate_token("a.b.c.d") is None

    def test_token_expired(self, auth_service):
        """Negative TTL token is rejected."""
        user = auth_service.create_user(username="exp_user", password="ExpUser1234")
        token = auth_service.issue_token(user["id"], ttl_seconds=-1)
        assert auth_service.authenticate_token(token) is None

    def test_token_version_invalidated(self, auth_service):
        """Token with wrong version is rejected."""
        user = auth_service.create_user(username="ver_user", password="VerUser1234")
        token = auth_service.issue_token(user["id"])
        # Invalidate by changing password
        auth_service.update_user(user["id"], password="NewPassword123")
        assert auth_service.authenticate_token(token) is None

    def test_token_disabled_user(self, auth_service):
        """Token for disabled user is rejected."""
        user = auth_service.create_user(username="dis_tok", password="DisTok1234")
        token = auth_service.issue_token(user["id"])
        auth_service.update_user(user["id"], status="disabled")
        assert auth_service.authenticate_token(token) is None


# ═══════════════════════════════════════════════════════════════════════════
# RBAC / Permissions
# ═══════════════════════════════════════════════════════════════════════════

class TestRBAC:

    def test_admin_has_wildcard(self, auth_service):
        """Admin group has wildcard '*' permission."""
        admin = auth_service.create_user(
            username="rbac_admin", password="RbacAdmin123",
            group_ids=["admin"],
        )
        assert "*" in admin.get("permissions", [])

    def test_viewer_permissions(self, auth_service):
        """Viewer has limited permissions."""
        viewer = auth_service.create_user(
            username="rbac_viewer", password="RbacView123",
            group_ids=["viewer"],
        )
        perms = viewer.get("permissions", [])
        assert "knowledge.search" in perms
        assert "review.approve" not in perms

    def test_reviewer_permissions(self, auth_service):
        """Reviewer can approve and reject."""
        reviewer = auth_service.create_user(
            username="rbac_review", password="RbacReview1",
            group_ids=["reviewer"],
        )
        perms = reviewer.get("permissions", [])
        assert "review.approve" in perms
        assert "review.reject" in perms

    def test_user_has_permission_check(self, auth_service):
        """user_has_permission works correctly."""
        admin = auth_service.create_user(
            username="perm_admin", password="PermAdmin12",
            group_ids=["admin"],
        )
        assert auth_service.user_has_permission(admin, "anything.at.all") is True
        assert auth_service.user_has_permission(admin, "users.manage") is True

        viewer = auth_service.create_user(
            username="perm_viewer", password="PermViewer1",
            group_ids=["viewer"],
        )
        assert auth_service.user_has_permission(viewer, "knowledge.search") is True
        assert auth_service.user_has_permission(viewer, "users.manage") is False

    def test_multiple_groups_merge_permissions(self, auth_service):
        """User in multiple groups gets union of permissions."""
        user = auth_service.create_user(
            username="multi_group", password="MultiGr1234",
            group_ids=["editor", "reviewer"],
        )
        perms = user.get("permissions", [])
        assert "knowledge.create" in perms  # from editor
        assert "review.approve" in perms    # from reviewer

    def test_invalid_group_falls_back_to_viewer(self, auth_service):
        """Non-existent group falls back to viewer."""
        user = auth_service.create_user(
            username="bad_group", password="BadGroup123",
            group_ids=["nonexistent_group"],
        )
        assert any(g["id"] == "viewer" for g in user.get("groups", []))

    def test_group_definitions_complete(self):
        """All 5 default groups are defined."""
        assert set(GROUP_DEFINITIONS.keys()) == {
            "viewer", "editor", "reviewer", "maintainer", "admin",
        }

    def test_group_definitions_have_permissions(self):
        """Each group has at least one permission."""
        for group_id, definition in GROUP_DEFINITIONS.items():
            assert len(definition["permissions"]) > 0, f"{group_id} has no permissions"


# ═══════════════════════════════════════════════════════════════════════════
# Registration & Captcha
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistration:

    def test_register_user_qq_format(self, auth_service, db_conn):
        """Registration requires QQ number format (5-12 digits starting with 1-9)."""
        # Valid QQ format
        user = auth_service.register_user(
            username="123456789", password="RegPass1234",
        )
        assert user["username"] == "123456789"

    def test_register_invalid_qq(self, auth_service):
        """Non-QQ format username rejected."""
        with pytest.raises(ValueError, match="QQ"):
            auth_service.register_user(username="not_qq", password="RegPass1234")

    def test_register_duplicate(self, auth_service):
        """Duplicate QQ registration rejected."""
        auth_service.register_user(username="111222333", password="DupReg1234")
        with pytest.raises(ValueError, match="已注册"):
            auth_service.register_user(username="111222333", password="DupReg1234")

    def test_has_users(self, auth_service):
        """has_users returns correct state."""
        assert auth_service.has_users() is False
        auth_service.register_user(username="222333444", password="HasUsers123")
        assert auth_service.has_users() is True

    def test_public_settings(self, auth_service):
        """public_settings returns expected keys."""
        settings = auth_service.public_settings()
        assert "allow_registration" in settings
        assert "registration_captcha_enabled" in settings
        assert isinstance(settings["allow_registration"], bool)


class TestCaptcha:

    def test_prepare_captcha(self, auth_service):
        """prepare_registration_captcha returns captcha data."""
        result = auth_service.prepare_registration_captcha(username="555666777")
        assert result["username"] == "555666777"
        assert len(result["code"]) == 6
        assert result["code"].isdigit()
        assert result["expires_at"] > time.time()

    def test_captcha_cooldown(self, auth_service):
        """Captcha cooldown prevents rapid requests."""
        result = auth_service.prepare_registration_captcha(username="666777888")
        auth_service.store_registration_captcha(
            username="666777888", code=result["code"],
            expires_at=result["expires_at"],
        )
        # Immediate re-request should raise cooldown error
        with pytest.raises(CaptchaCooldownError):
            auth_service.prepare_registration_captcha(username="666777888")

    def test_captcha_full_flow(self, auth_service):
        """Complete captcha registration flow."""
        result = auth_service.prepare_registration_captcha(username="777888999")
        auth_service.store_registration_captcha(
            username="777888999", code=result["code"],
            expires_at=result["expires_at"],
        )
        # Directly test the assertion method by calling register with correct code
        user = auth_service.register_user(
            username="777888999", password="FlowPass1234",
            captcha=result["code"],
        )
        assert user["username"] == "777888999"

    def test_captcha_wrong_code(self, auth_service):
        """Wrong captcha code is rejected."""
        # Disable captcha requirement for registration so we can test captcha verification directly
        cursor = auth_service._conn.cursor()
        cursor.execute(
            "UPDATE game_knowledge_auth_settings SET value='false' WHERE key='registration_captcha_enabled'"
        )
        auth_service._conn.commit()

        result = auth_service.prepare_registration_captcha(username="888999000")
        auth_service.store_registration_captcha(
            username="888999000", code=result["code"],
            expires_at=result["expires_at"],
        )
        # Verify wrong code fails via _assert
        with pytest.raises(ValueError, match="验证码"):
            auth_service._assert_registration_captcha(
                "888999000", "000000",
            )


# ═══════════════════════════════════════════════════════════════════════════
# Audit
# ═══════════════════════════════════════════════════════════════════════════

class TestAudit:

    def test_audit_events_recorded(self, auth_service):
        """Login events are recorded in audit trail."""
        user = auth_service.create_user(username="audit_user", password="AuditUser12")
        auth_service.authenticate_password("audit_user", "AuditUser12", ip="10.0.0.1")
        auth_service.authenticate_password("audit_user", "wrong", ip="10.0.0.2")

        events = auth_service.list_audit_events(limit=10)
        assert len(events) >= 2
        # Check we have both success and failure
        success_events = [e for e in events if e["success"] == 1]
        failure_events = [e for e in events if e["success"] == 0]
        assert len(success_events) >= 1
        assert len(failure_events) >= 1

    def test_audit_filter_by_user(self, auth_service):
        """Audit can filter by user_id."""
        user_a = auth_service.create_user(username="audit_a", password="AuditA1234")
        user_b = auth_service.create_user(username="audit_b", password="AuditB1234")
        auth_service.authenticate_password("audit_a", "AuditA1234")
        auth_service.authenticate_password("audit_b", "AuditB1234")

        events_a = auth_service.list_audit_events(user_id=user_a["id"], limit=10)
        assert all(e["user_id"] == user_a["id"] for e in events_a)
        assert len(events_a) >= 1

    def test_audit_ip_filter(self, auth_service):
        """Audit can filter by IP."""
        user = auth_service.create_user(username="audit_ip", password="AuditIP1234")
        auth_service.authenticate_password("audit_ip", "AuditIP1234", ip="172.16.0.1")
        events = auth_service.list_audit_events(ip="172.16", limit=10)
        assert len(events) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_creating_multiple_users(self, auth_service):
        """Create 10 users rapidly without issues."""
        for i in range(10):
            user = auth_service.create_user(
                username=f"batch_{i:03d}", password=f"Batch{i:03d}Pass",
            )
            assert user["username"] == f"batch_{i:03d}"

    def test_password_hash_not_reversible(self, auth_service):
        """Password hash is PBKDF2-based, not reversible."""
        user = auth_service.create_user(username="hash_test", password="HashTest123")
        raw = auth_service._get_raw_user(user["id"])
        password_hash = raw["password_hash"]
        assert password_hash != "HashTest123"
        assert len(password_hash) == 64  # SHA-256 hex

    def test_password_hash_different_salts(self, auth_service):
        """Two users with same password have different hashes."""
        salt1, hash1 = auth_service._hash_password("SamePassword123")
        salt2, hash2 = auth_service._hash_password("SamePassword123")
        assert hash1 != hash2  # Different salts produce different hashes

    def test_group_order_in_list(self, auth_service):
        """Groups are listed in a specific order."""
        groups = auth_service.list_groups()
        group_ids = [g["id"] for g in groups]
        assert group_ids[:5] == ["admin", "maintainer", "reviewer", "editor", "viewer"]
