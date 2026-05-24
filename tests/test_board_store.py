"""Comprehensive tests for BoardStore — thread & post CRUD, state transitions.

Covers: thread lifecycle (open→forwarded→collecting→resolved→closed),
post operations, overdue scanning, collected message tracking.
"""

from __future__ import annotations

import time

import pytest
from board_store import BoardStore


# ═══════════════════════════════════════════════════════════════════════════
# Thread CRUD
# ═══════════════════════════════════════════════════════════════════════════

class TestThreadCRUD:

    def test_create_thread_success(self, board_store):
        """Create a thread with title and content."""
        thread = board_store.create_thread(
            title="How do I craft a Dragon Eye?",
            content="I need Baubles mod — what's the recipe?",
            author_id="user_001",
            author_nickname="Player1",
        )
        assert thread["id"] >= 1
        assert thread["title"] == "How do I craft a Dragon Eye?"
        assert thread["status"] == "open"
        assert thread["author_id"] == "user_001"
        assert thread["author_nickname"] == "Player1"
        assert thread["reply_count"] == 0
        assert thread["created_at"] > 0

    def test_create_thread_minimal(self, board_store):
        """Thread with minimal valid data."""
        thread = board_store.create_thread(
            title="Minimal",
            content="Test",
            author_id="",
            author_nickname="",
        )
        assert thread is not None
        assert thread["title"] == "Minimal"

    def test_create_thread_empty_title(self, board_store):
        """Empty title raises ValueError."""
        with pytest.raises(ValueError, match="标题不能为空"):
            board_store.create_thread(
                title="  ", content="Some content",
                author_id="u1", author_nickname="n1",
            )

    def test_create_thread_long_title(self, board_store):
        """Title > 200 chars raises ValueError."""
        with pytest.raises(ValueError, match="标题"):
            board_store.create_thread(
                title="A" * 201, content="content",
                author_id="u1", author_nickname="n1",
            )

    def test_create_thread_empty_content(self, board_store):
        """Empty content raises ValueError."""
        with pytest.raises(ValueError, match="正文"):
            board_store.create_thread(
                title="Valid Title", content="   ",
                author_id="u1", author_nickname="n1",
            )

    def test_create_thread_long_content(self, board_store):
        """Content > 8000 chars raises ValueError."""
        with pytest.raises(ValueError, match="正文"):
            board_store.create_thread(
                title="Valid", content="X" * 8001,
                author_id="u1", author_nickname="n1",
            )

    def test_get_thread(self, board_store):
        """get_thread returns thread or None."""
        t = board_store.create_thread(
            title="Get Me", content="Content here",
            author_id="u1", author_nickname="n1",
        )
        fetched = board_store.get_thread(t["id"])
        assert fetched is not None
        assert fetched["title"] == "Get Me"

        assert board_store.get_thread(99999) is None

    def test_get_thread_with_posts(self, board_store):
        """get_thread_with_posts includes the posts array."""
        t = board_store.create_thread(
            title="With Posts", content="OP content",
            author_id="u1", author_nickname="OP",
        )
        result = board_store.get_thread_with_posts(t["id"])
        assert result is not None
        assert "posts" in result
        assert len(result["posts"]) >= 1  # OP post is auto-created
        assert result["posts"][0]["content"] == "OP content"

    def test_delete_thread(self, board_store):
        """delete_thread removes thread and its posts."""
        t = board_store.create_thread(
            title="Delete Me", content="Bye",
            author_id="u1", author_nickname="n1",
        )
        assert board_store.delete_thread(t["id"]) is True
        assert board_store.get_thread(t["id"]) is None

    def test_delete_nonexistent_thread(self, board_store):
        """Deleting nonexistent thread returns False."""
        assert board_store.delete_thread(99999) is False

    def test_thread_has_auto_created_op_post(self, board_store):
        """Creating a thread also creates the first post (OP)."""
        t = board_store.create_thread(
            title="Auto OP", content="This is the first post",
            author_id="u1", author_nickname="Author",
        )
        posts = board_store.list_posts(t["id"])
        assert len(posts) == 1
        assert posts[0]["content"] == "This is the first post"
        assert posts[0]["author_id"] == "u1"
        assert posts[0]["source"] == "web"


# ═══════════════════════════════════════════════════════════════════════════
# Thread Listing
# ═══════════════════════════════════════════════════════════════════════════

class TestThreadListing:

    def test_list_threads_default(self, board_store):
        """List threads with default params."""
        board_store.create_thread(
            title="T1", content="C1", author_id="a", author_nickname="A",
        )
        board_store.create_thread(
            title="T2", content="C2", author_id="b", author_nickname="B",
        )
        result = board_store.list_threads()
        assert result["total"] >= 2
        assert len(result["items"]) >= 2

    def test_list_threads_status_filter(self, board_store):
        """Filter threads by status."""
        t1 = board_store.create_thread(
            title="Open", content="C", author_id="a", author_nickname="A",
        )
        t2 = board_store.create_thread(
            title="Resolved", content="C", author_id="b", author_nickname="B",
        )
        board_store.mark_resolved(t2["id"])

        open_result = board_store.list_threads(status="open")
        assert open_result["total"] >= 1
        assert all(t["status"] == "open" for t in open_result["items"])

    def test_list_threads_active_filter(self, board_store):
        """'active' filter returns open+forwarded+collecting."""
        t1 = board_store.create_thread(
            title="Active", content="C", author_id="a", author_nickname="A",
        )
        active = board_store.list_threads(status="active")
        assert active["total"] >= 1

    def test_list_threads_done_filter(self, board_store):
        """'done' filter returns resolved+closed."""
        t = board_store.create_thread(
            title="Done", content="C", author_id="a", author_nickname="A",
        )
        board_store.mark_resolved(t["id"])
        done = board_store.list_threads(status="done")
        assert done["total"] >= 1

    def test_list_threads_pagination(self, board_store):
        """Limit and offset work correctly."""
        for i in range(5):
            board_store.create_thread(
                title=f"T{i}", content=f"C{i}", author_id="a", author_nickname="A",
            )
        page1 = board_store.list_threads(limit=2, offset=0)
        page2 = board_store.list_threads(limit=2, offset=2)
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        # No overlap
        ids_p1 = {t["id"] for t in page1["items"]}
        ids_p2 = {t["id"] for t in page2["items"]}
        assert ids_p1.isdisjoint(ids_p2)
        assert page1["total"] >= 5


# ═══════════════════════════════════════════════════════════════════════════
# Thread State Transitions
# ═══════════════════════════════════════════════════════════════════════════

class TestThreadStateTransitions:

    def test_mark_forwarded(self, board_store):
        """Mark as forwarded transitions open→collecting."""
        t = board_store.create_thread(
            title="Forward", content="Q", author_id="a", author_nickname="A",
        )
        collected_until = time.time() + 1200  # 20 minutes
        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg_123",
            forward_target_group_id="100000001",
            collected_until=collected_until,
        )
        updated = board_store.get_thread(t["id"])
        assert updated["status"] == "collecting"
        assert updated["forward_target_group_id"] == "100000001"
        assert updated["collected_until"] == collected_until

    def test_mark_resolved(self, board_store):
        """Mark as resolved transitions to resolved status."""
        t = board_store.create_thread(
            title="Resolve", content="Q", author_id="a", author_nickname="A",
        )
        board_store.mark_resolved(t["id"], resolved_by_id="admin_001")
        updated = board_store.get_thread(t["id"])
        assert updated["status"] == "resolved"
        assert updated["resolved_by_id"] == "admin_001"
        assert updated["resolved_at"] is not None

    def test_close_thread(self, board_store):
        """Close a thread transitions to closed status."""
        t = board_store.create_thread(
            title="Close", content="Q", author_id="a", author_nickname="A",
        )
        board_store.close_thread(t["id"])
        updated = board_store.get_thread(t["id"])
        assert updated["status"] == "closed"

    def test_full_lifecycle(self, board_store):
        """Complete lifecycle: open → forwarded → collecting → resolved → closed."""
        t = board_store.create_thread(
            title="Lifecycle", content="Full test",
            author_id="a", author_nickname="A",
        )
        assert t["status"] == "open"

        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg_1",
            forward_target_group_id="123456",
            collected_until=time.time() + 1200,
        )
        t = board_store.get_thread(t["id"])
        assert t["status"] == "collecting"

        board_store.mark_resolved(t["id"], resolved_by_id="mod")
        t = board_store.get_thread(t["id"])
        assert t["status"] == "resolved"

        board_store.close_thread(t["id"])
        t = board_store.get_thread(t["id"])
        assert t["status"] == "closed"

    def test_mark_forwarded_only_open_threads(self, board_store):
        """Cannot mark forwarded on non-open/forwarded threads."""
        t = board_store.create_thread(
            title="Locked", content="C", author_id="a", author_nickname="A",
        )
        board_store.mark_resolved(t["id"])
        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg",
            forward_target_group_id="123",
            collected_until=time.time() + 1200,
        )
        # Should not change status
        updated = board_store.get_thread(t["id"])
        assert updated["status"] == "resolved"


# ═══════════════════════════════════════════════════════════════════════════
# Post Operations
# ═══════════════════════════════════════════════════════════════════════════

class TestPostOperations:

    def test_add_web_post(self, board_store):
        """Add a post from web source."""
        t = board_store.create_thread(
            title="Post Test", content="OP", author_id="a", author_nickname="A",
        )
        post = board_store.add_post(
            t["id"],
            content="Reply content",
            author_id="u2",
            author_nickname="Replier",
        )
        assert post["id"] >= 1
        assert post["content"] == "Reply content"
        assert post["source"] == "web"
        assert post["thread_id"] == t["id"]

    def test_add_qq_post(self, board_store):
        """Add a post from QQ source."""
        t = board_store.create_thread(
            title="QQ Post", content="OP", author_id="a", author_nickname="A",
        )
        post = board_store.add_post(
            t["id"],
            content="QQ reply",
            author_id="qq_user",
            author_nickname="QQ User",
            source="qq",
            source_user_id="123456789",
            source_message_id="msg_qq_001",
        )
        assert post["source"] == "qq"
        assert post["source_user_id"] == "123456789"

    def test_post_updates_thread_reply_count(self, board_store):
        """Adding posts increments reply_count on thread."""
        t = board_store.create_thread(
            title="Count Test", content="OP", author_id="a", author_nickname="A",
        )
        assert t["reply_count"] == 0

        board_store.add_post(t["id"], content="R1", author_id="u", author_nickname="U")
        t = board_store.get_thread(t["id"])
        assert t["reply_count"] == 1

        board_store.add_post(t["id"], content="R2", author_id="u", author_nickname="U")
        t = board_store.get_thread(t["id"])
        assert t["reply_count"] == 2

    def test_post_updates_last_reply_at(self, board_store):
        """Adding posts updates last_reply_at."""
        t = board_store.create_thread(
            title="Time Test", content="OP", author_id="a", author_nickname="A",
        )
        old_reply_at = t["last_reply_at"]
        time.sleep(0.01)  # Ensure timestamp difference
        board_store.add_post(t["id"], content="R", author_id="u", author_nickname="U")
        t = board_store.get_thread(t["id"])
        assert t["last_reply_at"] > old_reply_at

    def test_reply_to_specific_post(self, board_store):
        """Reply can target a specific post."""
        t = board_store.create_thread(
            title="Reply To", content="OP", author_id="a", author_nickname="A",
        )
        post1 = board_store.add_post(t["id"], content="R1", author_id="u", author_nickname="U")
        post2 = board_store.add_post(
            t["id"], content="Reply to R1", author_id="v", author_nickname="V",
            reply_to_post_id=post1["id"],
        )
        assert post2["reply_to_post_id"] == post1["id"]

    def test_reply_to_nonexistent_post(self, board_store):
        """Reply to nonexistent post_id is silently ignored."""
        t = board_store.create_thread(
            title="Bad Reply", content="OP", author_id="a", author_nickname="A",
        )
        post = board_store.add_post(
            t["id"], content="R", author_id="u", author_nickname="U",
            reply_to_post_id=99999,
        )
        assert post["reply_to_post_id"] is None

    def test_add_post_to_nonexistent_thread(self, board_store):
        """Adding post to nonexistent thread raises ValueError."""
        with pytest.raises(ValueError, match="主题不存在"):
            board_store.add_post(
                99999, content="R", author_id="u", author_nickname="U",
            )

    def test_add_post_empty_content(self, board_store):
        """Empty post content raises ValueError."""
        t = board_store.create_thread(
            title="Empty Post", content="OP", author_id="a", author_nickname="A",
        )
        with pytest.raises(ValueError, match="回复内容"):
            board_store.add_post(t["id"], content="  ", author_id="u", author_nickname="U")

    def test_list_posts(self, board_store):
        """list_posts returns all posts for a thread ordered by created_at."""
        t = board_store.create_thread(
            title="List Posts", content="OP", author_id="a", author_nickname="A",
        )
        board_store.add_post(t["id"], content="R1", author_id="u", author_nickname="U")
        board_store.add_post(t["id"], content="R2", author_id="v", author_nickname="V")

        posts = board_store.list_posts(t["id"])
        assert len(posts) == 3  # OP + 2 replies
        assert posts[0]["content"] == "OP"

    def test_get_post(self, board_store):
        """get_post returns single post."""
        t = board_store.create_thread(
            title="Get Post", content="OP", author_id="a", author_nickname="A",
        )
        posts = board_store.list_posts(t["id"])
        post_id = posts[0]["id"]
        post = board_store.get_post(post_id)
        assert post is not None
        assert post["content"] == "OP"

    def test_delete_post(self, board_store):
        """delete_post removes post and decrements reply_count."""
        t = board_store.create_thread(
            title="Del Post", content="OP", author_id="a", author_nickname="A",
        )
        board_store.add_post(t["id"], content="R1", author_id="u", author_nickname="U")
        posts = board_store.list_posts(t["id"])
        assert len(posts) == 2

        board_store.delete_post(posts[-1]["id"])
        posts_after = board_store.list_posts(t["id"])
        assert len(posts_after) == 1
        t = board_store.get_thread(t["id"])
        assert t["reply_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Collected QQ Posts
# ═══════════════════════════════════════════════════════════════════════════

class TestCollectedQQPosts:

    def test_append_collected_qq_post(self, board_store):
        """Append a QQ post to a collecting thread."""
        t = board_store.create_thread(
            title="Collect", content="OP", author_id="a", author_nickname="A",
        )
        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg_fwd",
            forward_target_group_id="100000001",
            collected_until=time.time() + 1200,
        )
        count = board_store.append_collected_qq_post(
            t["id"],
            content="QQ user reply",
            source_user_id="qq_123",
            source_message_id="msg_qq_001",
            author_nickname="QQ User",
        )
        assert count == 1
        t = board_store.get_thread(t["id"])
        assert t["collected_message_count"] == 1

    def test_append_collected_qq_post_empty_content(self, board_store):
        """Empty QQ post returns count 0."""
        t = board_store.create_thread(
            title="Empty QQ", content="OP", author_id="a", author_nickname="A",
        )
        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg",
            forward_target_group_id="123",
            collected_until=time.time() + 1200,
        )
        count = board_store.append_collected_qq_post(
            t["id"], content="  ",
            source_user_id="qq", source_message_id="msg",
        )
        assert count == 0

    def test_multiple_collected_posts(self, board_store):
        """Multiple collected posts increment counter."""
        t = board_store.create_thread(
            title="Multi Collect", content="OP", author_id="a", author_nickname="A",
        )
        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg",
            forward_target_group_id="123",
            collected_until=time.time() + 1200,
        )
        for i in range(5):
            count = board_store.append_collected_qq_post(
                t["id"], content=f"Answer {i}",
                source_user_id=f"u{i}", source_message_id=f"msg_{i}",
            )
            assert count == i + 1


# ═══════════════════════════════════════════════════════════════════════════
# Scanning / Overdue
# ═══════════════════════════════════════════════════════════════════════════

class TestOverdueScanning:

    def test_list_open_overdue(self, board_store):
        """list_open_overdue finds threads past threshold with no replies."""
        t1 = board_store.create_thread(
            title="Overdue 1", content="Q1", author_id="a", author_nickname="A",
        )
        t2 = board_store.create_thread(
            title="Overdue 2", content="Q2", author_id="b", author_nickname="B",
        )
        # Threads are just created — they should be found if threshold is small
        # Use a very small threshold to include them
        overdue = board_store.list_open_overdue(threshold_seconds=-1)
        assert len(overdue) >= 1

    def test_list_open_overdue_excludes_replied(self, board_store):
        """Threads with replies are not in overdue."""
        t = board_store.create_thread(
            title="Has Reply", content="Q", author_id="a", author_nickname="A",
        )
        board_store.add_post(t["id"], content="Answer!", author_id="u", author_nickname="U")
        # With threshold=-1 everything qualifies, but reply_count>0 excludes
        overdue = board_store.list_open_overdue(threshold_seconds=-1)
        overdue_ids = {o["id"] for o in overdue}
        assert t["id"] not in overdue_ids

    def test_list_collecting_in_group(self, board_store):
        """list_collecting_in_group finds threads in collecting state."""
        t = board_store.create_thread(
            title="In Group", content="Q", author_id="a", author_nickname="A",
        )
        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg",
            forward_target_group_id="100000001",
            collected_until=time.time() + 1200,
        )
        collecting = board_store.list_collecting_in_group("100000001")
        assert len(collecting) >= 1
        assert collecting[0]["id"] == t["id"]

    def test_list_collecting_in_group_empty(self, board_store):
        """Non-matching group returns empty list."""
        assert board_store.list_collecting_in_group("") == []
        assert board_store.list_collecting_in_group("000000") == []

    def test_list_collecting_expired(self, board_store):
        """Threads with past collected_until are listed as expired."""
        t = board_store.create_thread(
            title="Expired", content="Q", author_id="a", author_nickname="A",
        )
        board_store.mark_forwarded(
            t["id"],
            forwarded_message_id="msg",
            forward_target_group_id="123",
            collected_until=time.time() - 1,  # Already expired
        )
        expired = board_store.list_collecting_expired()
        assert len(expired) >= 1
        assert expired[0]["id"] == t["id"]


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestBoardEdgeCases:

    def test_create_many_threads(self, board_store):
        """Create 20 threads without issues."""
        ids = []
        for i in range(20):
            t = board_store.create_thread(
                title=f"Bulk T{i}", content=f"Content {i}",
                author_id="a", author_nickname="A",
            )
            ids.append(t["id"])
        assert len(ids) == 20
        assert len(set(ids)) == 20

    def test_special_characters_in_content(self, board_store):
        """Unicode, emoji, and special chars are preserved."""
        t = board_store.create_thread(
            title="🎮 游戏问题【测试】",
            content="中文内容：，。！？【】 — emoji 🎮⚔️ 日文テスト 'quotes'",
            author_id="a", author_nickname="测试用户",
        )
        assert "🎮" in t["title"]
        assert "🎮⚔️" in board_store.list_posts(t["id"])[0]["content"]

    def test_status_values_constant(self):
        """BoardStore.THREAD_STATUSES contains expected values."""
        assert BoardStore.THREAD_STATUSES == (
            "open", "forwarded", "collecting", "resolved", "closed",
        )

    def test_post_sources_constant(self):
        """BoardStore.POST_SOURCES contains expected values."""
        assert BoardStore.POST_SOURCES == ("web", "qq")
