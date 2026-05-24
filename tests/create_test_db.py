"""Test Database Builder for game-knowledge-plugin.

Creates a fully-populated SQLite test database with realistic production data
for manual inspection, WebUI testing, and load testing. All data is self-contained
and requires no external services.

Usage:
    python tests/create_test_db.py [--output <path>] [--scale <small|medium|large>]

Output:
    A metadata.db SQLite file with all tables populated.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# ── path setup ──────────────────────────────────────────────────────────
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from auth_service import GameKnowledgeAuthService, GROUP_DEFINITIONS
from board_store import BoardStore
from announcement_store import AnnouncementStore


# ═══════════════════════════════════════════════════════════════════════════
# Data Generators
# ═══════════════════════════════════════════════════════════════════════════

GAME_NICKNAMES = [
    "史蒂夫", "Alex", "Herobrine", "末影龙克星", "RLCraft大师",
    "附魔师老王", "红石专家小张", "建筑狂魔", "PVP战神",
    "挖矿小能手", "药水商人", "指令方块侠", "跑酷达人",
    "生存专家", "创造建筑师", "凋零杀手", "远古守卫",
    "潜行刺客", "弓箭手", "附魔书收集者",
]

GAME_QUESTIONS = [
    ("如何制作龙之吐息？", "使用玻璃瓶右键末影龙的吐息粒子来收集龙之吐息。"),
    ("龙眼装备的合成配方是什么？", "龙眼需要发光宝石、龙的头骨和钻石块在工作台合成。"),
    ("如何找到末地传送门？", "使用末影之眼投掷，跟随其飞行方向即可找到要塞中的末地传送门。"),
    ("RLCraft中如何获得灵魂绑定附魔？", "通过与图书管理员村民交易或在地牢宝箱中找到灵魂绑定附魔书。"),
    ("如何驯服冰与火之歌中的龙？", "需要找到龙蛋并孵化，用龙食喂养幼龙直到成年。"),
    ("下界合金装备怎么升级？", "使用下界合金锭在锻造台将钻石装备升级为下界合金装备。"),
    ("如何制作抗火药水？", "使用地狱疣+岩浆膏在酿造台中制作，或击杀岩浆怪获取。"),
    ("末影珍珠怎么大量获取？", "建造末影人农场，利用末影螨吸引末影人自动击杀获取。"),
    ("如何获得鞘翅？", "击败末影龙后通过末地折跃门到达末地外岛，在末地船中找到鞘翅。"),
    ("信标需要什么材料激活？", "需要铁块/金块/钻石块/绿宝石块搭建金字塔底座，顶部放置信标"),
    ("海龟壳头盔有什么作用？", "提供10秒水下呼吸效果，配合水下呼吸附魔可长时间潜水。"),
    ("如何繁殖村民？", "提供足够的床和食物（面包/胡萝卜/土豆），村民会自动繁殖。"),
    ("女巫小屋里的猫怎么驯服？", "使用生鱼（生鳕鱼或生鲑鱼）右键猫即可驯服。"),
    ("如何制作附魔台？", "需要一本书、两颗钻石和四块黑曜石在工作台合成。"),
    ("冰霜行者附魔有什么用？", "在水面上行走时会自动生成霜冰，可以跨越大片水域。"),
]

BOARD_TITLES = [
    "RLCraft 2.9.3 龙之吐息获取方法",
    "求问：冰与火之歌龙怎么驯服？",
    "下界合金装备升级细节问题",
    "末地传送门找不到怎么办",
    "附魔台最佳摆放方式求教",
    "海龟壳怎么获得？",
    "村民繁殖条件到底是什么",
    "末影珍珠农场建造指南",
    "灵魂绑定附魔的获取途径",
    "抗火药水配方和材料",
]

ANNOUNCEMENTS = [
    ("系统升级通知", "游戏知识库将于今晚22:00-02:00进行系统升级，届时检索服务可能短暂不可用。", "warning"),
    ("新版本已上线", "支持了冰与火之歌 mod 2.0 的知识条目，欢迎大家贡献新的游戏知识！", "info"),
    ("安全提醒", "请勿在留言板中分享个人敏感信息。管理员团队会定期审查内容。", "warning"),
    ("数据库维护完成", "凌晨的数据库优化已完成，检索速度提升约30%，如遇问题请反馈。", "info"),
    ("规则更新", "知识卡片审核标准已更新，请各位审核员查看最新的审核指南。", "info"),
]


def generate_users(auth: GameKnowledgeAuthService, count: int) -> List[Dict[str, Any]]:
    """Generate users with realistic data."""
    users = []
    groups = [
        (["admin"], "管理员"),
        (["maintainer"], "维护员"),
        (["reviewer"], "审核员"),
        (["reviewer"], "审核员"),
        (["editor"], "编辑者"),
        (["editor"], "编辑者"),
        (["editor"], "编辑者"),
        (["viewer"], "浏览者"),
        (["viewer"], "浏览者"),
        (["viewer"], "浏览者"),
    ]

    for i in range(count):
        group_ids, display_name = groups[i % len(groups)]
        username = f"test_user_{i:03d}" if i < 3 else str(10000000000 + i)
        try:
            if i < 3:
                user = auth.create_user(
                    username=username,
                    password=f"Test{i:03d}Pass!",
                    display_name=display_name,
                    group_ids=group_ids,
                )
            else:
                user = auth.register_user(
                    username=username,
                    password=f"Test{i:03d}Pass!",
                    display_name=display_name,
                )
            users.append(user)
            print(f"  ✅ 创建用户: {username} ({display_name})")
        except Exception as e:
            print(f"  ⚠️ 用户创建失败 {username}: {e}")

    return users


def generate_board_data(board_store: BoardStore, count: int) -> None:
    """Generate board threads with realistic Q&A."""
    for i in range(min(count, len(BOARD_TITLES))):
        t = board_store.create_thread(
            title=BOARD_TITLES[i],
            content=f"大家好，我想问一下关于 {BOARD_TITLES[i]} 的问题，有知道的大佬帮忙解答一下吗？\n\n具体情况是：{GAME_QUESTIONS[i][0]}",
            author_id=f"test_user_{i % 3:03d}",
            author_nickname=GAME_NICKNAMES[i % len(GAME_NICKNAMES)],
        )
        # Add some replies
        for j in range(3):
            board_store.add_post(
                t["id"],
                content=f"回复#{j+1}: {GAME_QUESTIONS[(i+j) % len(GAME_QUESTIONS)][1]}",
                author_id=f"qq_{100000+j}",
                author_nickname=GAME_NICKNAMES[(i+j+1) % len(GAME_NICKNAMES)],
                source="web" if j % 2 == 0 else "qq",
                source_user_id=f"user_{j}" if j % 2 == 0 else f"qq_{100000+j}",
                source_message_id=f"msg_{i}_{j}",
            )

        # Resolve some threads
        if i % 3 == 0:
            board_store.mark_resolved(t["id"], resolved_by_id="test_user_000")
            board_store.close_thread(t["id"])

        print(f"  ✅ 创建主题: {BOARD_TITLES[i][:40]}... ({'已解决' if i % 3 == 0 else '开放中'})")


def generate_announcements(ann_store: AnnouncementStore) -> None:
    """Generate announcements."""
    for title, content, severity in ANNOUNCEMENTS:
        ann_store.create(
            title=title, content=content, severity=severity,
            pinned=(severity == "warning"),
            status="published",
            starts_at=None, ends_at=None,
            author_id="test_user_000", author_nickname="管理员",
        )
        print(f"  ✅ 创建公告: {title}")


def generate_audit_log(auth: GameKnowledgeAuthService) -> None:
    """Generate audit log entries to simulate realistic usage."""
    events = [
        ("auth.login", True, "正常登录"),
        ("auth.login", False, "密码错误"),
        ("auth.login", True, "正常登录"),
        ("auth.login", True, "异地登录"),
        ("user.create", True, "管理员创建用户"),
        ("auth.change_password", True, "修改密码"),
        ("auth.register", True, "新用户注册"),
        ("auth.login", False, "账号已锁定"),
        ("auth.login", True, "解锁后重新登录"),
        ("user.update", True, "更新用户组"),
    ]
    for event, success, detail in events:
        auth.record_audit(
            user_id="test_user_000",
            username="test_user_000",
            event=event,
            ip=f"192.168.{secrets.randbelow(255)}.{secrets.randbelow(255)}",
            success=success,
            detail=detail,
        )


def generate_knowledge_cards(conn: sqlite3.Connection, count: int) -> None:
    """Generate knowledge cards directly in SQLite."""
    cursor = conn.cursor()
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

    categories = ["机制", "装备", "掉落", "报错", "配置", "攻略", "指令", "其他"]
    answer_types = ["mechanic", "guide", "drop", "error_fix", "config", "recommendation", "other"]

    for i in range(count):
        qa = GAME_QUESTIONS[i % len(GAME_QUESTIONS)]
        cat = categories[i % len(categories)]
        atype = answer_types[i % len(answer_types)]
        status = "approved" if i % 3 == 0 else ("rejected" if i % 5 == 0 else "pending")

        cursor.execute(
            """
            INSERT INTO game_knowledge_cards (
                title, category, question, answer, tags, search_terms,
                rlcraft_version, answer_type, valid_status, review_status,
                ai_review_status, ai_review_score,
                source_group_id, source_group_name,
                card_hash, created_by, last_editor_id, last_editor_name,
                evidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                qa[0], cat, qa[0], qa[1],
                json.dumps(["game_knowledge", "rlcraft", cat], ensure_ascii=False),
                json.dumps(["龙", "配方", "合成", "RLCraft"], ensure_ascii=False),
                "2.9.3", atype, "active", status,
                "auto_approved" if status == "approved" else ("ai_rejected" if status == "rejected" else "pending"),
                0.9 if status == "approved" else (0.3 if status == "rejected" else 0.5),
                "100000001", "RLCraft交流群",
                f"card_hash_{i:04d}", "test_user_000", "test_user_000", "测试脚本",
                f"由群聊消息自动提取 #{i}", time.time() - (count - i) * 3600, time.time() - (count - i) * 1800,
            ),
        )
    conn.commit()
    print(f"  ✅ 创建 {count} 张知识卡片")

    # Stats
    cursor.execute("SELECT review_status, COUNT(*) FROM game_knowledge_cards GROUP BY review_status")
    for row in cursor.fetchall():
        print(f"     {row[0]}: {row[1]} 张")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

SCALES = {
    "small": {"users": 5, "boards": 5, "cards": 15},
    "medium": {"users": 20, "boards": 10, "cards": 50},
    "large": {"users": 50, "boards": 30, "cards": 200},
}


def main():
    parser = argparse.ArgumentParser(description="Build test database for game-knowledge-plugin")
    parser.add_argument("--output", "-o", default=None, help="Output directory (default: temp dir)")
    parser.add_argument("--scale", "-s", choices=["small", "medium", "large"],
                        default="small", help="Data scale")
    parser.add_argument("--db-name", default="metadata.db", help="Database filename")
    args = parser.parse_args()

    scale = SCALES[args.scale]
    print(f"\n{'='*60}")
    print(f"  GameKnowledge 测试数据库构建器")
    print(f"  规模: {args.scale} (用户:{scale['users']}, 主题:{scale['boards']}, 卡片:{scale['cards']})")
    print(f"{'='*60}\n")

    # Setup output directory
    if args.output:
        output_dir = args.output
    else:
        import tempfile
        output_dir = tempfile.mkdtemp(prefix="gk_test_")

    os.makedirs(output_dir, exist_ok=True)
    db_path = os.path.join(output_dir, args.db_name)

    # Initialize store
    from conftest import MockMetadataStore
    store = MockMetadataStore(db_path)

    try:
        # 1. Auth
        print("1. 初始化认证服务...")
        auth = GameKnowledgeAuthService(store=store)
        generate_users(auth, scale["users"])

        # 2. Board
        print("\n2. 初始化留言板...")
        board_store = BoardStore(store=store)
        generate_board_data(board_store, scale["boards"])

        # 3. Announcements
        print("\n3. 初始化公告...")
        ann_store = AnnouncementStore(store=store)
        generate_announcements(ann_store)

        # 4. Knowledge Cards
        print("\n4. 初始化知识卡片...")
        generate_knowledge_cards(store._conn, scale["cards"])

        # 5. Audit
        print("\n5. 生成审计日志...")
        generate_audit_log(auth)

        # Print summary
        print(f"\n{'='*60}")
        print(f"  构建完成!")
        print(f"  数据库文件: {db_path}")
        print(f"  文件大小: {os.path.getsize(db_path):,} bytes")
        print(f"{'='*60}")
        print(f"\n  使用方式:")
        print(f"    查看数据: sqlite3 {db_path} '.tables'")
        print(f"    用户列表: sqlite3 {db_path} 'SELECT username,display_name FROM game_knowledge_users'")
        print(f"    主题统计: sqlite3 {db_path} 'SELECT status,COUNT(*) FROM gk_board_threads GROUP BY status'")
        print(f"    卡片统计: sqlite3 {db_path} 'SELECT review_status,COUNT(*) FROM game_knowledge_cards GROUP BY review_status'")
        print()

    finally:
        store.close()

    return db_path


if __name__ == "__main__":
    main()
