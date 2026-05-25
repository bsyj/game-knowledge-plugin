"""Lightweight WebUI auth and RBAC for GameKnowledge."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any, Dict, List, Optional


GROUP_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "viewer": {
        "name": "Viewer",
        "description": "只看仪表盘和检索",
        "permissions": [
            "dashboard.view",
            "knowledge.search",
            "history.view_own",
            "announcement.view",
            "board.view",
            "board.post",
        ],
    },
    "editor": {
        "name": "Editor",
        "description": "可新增/编辑知识并提交修订",
        "permissions": [
            "dashboard.view",
            "knowledge.search",
            "knowledge.create",
            "knowledge.edit",
            "history.view_own",
            "announcement.view",
            "board.view",
            "board.post",
        ],
    },
    "reviewer": {
        "name": "Reviewer",
        "description": "可审核别人提交或修改的卡片",
        "permissions": [
            "dashboard.view",
            "knowledge.search",
            "review.view",
            "review.approve",
            "review.reject",
            "history.view_own",
            "announcement.view",
            "board.view",
            "board.post",
            "board.resolve",
        ],
    },
    "maintainer": {
        "name": "Maintainer",
        "description": "可删除检索知识、恢复删除、管理来源",
        "permissions": [
            "dashboard.view",
            "knowledge.search",
            "knowledge.delete",
            "sources.manage",
            "maintenance.manage",
            "history.view_own",
            "announcement.view",
            "board.view",
            "board.post",
            "board.resolve",
            "board.delete_any",
        ],
    },
    "admin": {
        "name": "Admin",
        "description": "用户管理、用户组管理、全部权限",
        "permissions": ["*"],
    },
}


class CaptchaCooldownError(ValueError):
    def __init__(self, remaining_seconds: int) -> None:
        super().__init__("验证码获取过于频繁，请稍后再试")
        self.remaining_seconds = max(1, int(remaining_seconds))


class GameKnowledgeAuthService:
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
            CREATE TABLE IF NOT EXISTS game_knowledge_auth_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_knowledge_users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT DEFAULT '',
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                last_login_at REAL,
                last_login_ip TEXT DEFAULT '',
                failed_login_count INTEGER DEFAULT 0,
                locked_until REAL,
                token_version INTEGER DEFAULT 1
            )
            """
        )
        cursor.execute("PRAGMA table_info(game_knowledge_users)")
        user_columns = {row[1] for row in cursor.fetchall()}
        user_column_defaults = {
            "last_login_ip": "TEXT DEFAULT ''",
            "failed_login_count": "INTEGER DEFAULT 0",
            "locked_until": "REAL",
            "token_version": "INTEGER DEFAULT 1",
        }
        for name, ddl in user_column_defaults.items():
            if name not in user_columns:
                cursor.execute(f"ALTER TABLE game_knowledge_users ADD COLUMN {name} {ddl}")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_knowledge_user_groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                permissions_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_knowledge_user_group_members (
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                PRIMARY KEY (user_id, group_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_knowledge_auth_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT '',
                username TEXT DEFAULT '',
                event TEXT NOT NULL,
                ip TEXT DEFAULT '',
                user_agent TEXT DEFAULT '',
                success INTEGER DEFAULT 0,
                detail TEXT DEFAULT '',
                created_at REAL NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_game_knowledge_auth_audit_user
            ON game_knowledge_auth_audit(user_id, created_at DESC)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_knowledge_registration_captchas (
                username TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                last_sent_at REAL NOT NULL,
                sent_ip TEXT DEFAULT '',
                send_detail TEXT DEFAULT '',
                attempts INTEGER DEFAULT 0,
                consumed_at REAL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_game_knowledge_registration_captchas_exp
            ON game_knowledge_registration_captchas(expires_at)
            """
        )
        for group_id, definition in GROUP_DEFINITIONS.items():
            cursor.execute(
                """
                INSERT INTO game_knowledge_user_groups (id, name, description, permissions_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    permissions_json=excluded.permissions_json
                """,
                (
                    group_id,
                    str(definition.get("name", group_id)),
                    str(definition.get("description", "")),
                    json.dumps(definition.get("permissions", []), ensure_ascii=False),
                ),
            )
        cursor.execute("SELECT value FROM game_knowledge_auth_settings WHERE key='token_secret'")
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO game_knowledge_auth_settings (key, value) VALUES ('token_secret', ?)",
                (secrets.token_hex(32),),
            )
        defaults = {
            "allow_registration": "true",
            "captcha_placeholder_enabled": "false",
            "registration_captcha_enabled": "false",
            "registration_captcha_group_id": "",
            "registration_captcha_cooldown_seconds": "60",
            "registration_captcha_ttl_seconds": "28800",
            "default_registration_group": "viewer",
        }
        for key, value in defaults.items():
            cursor.execute(
                "INSERT OR IGNORE INTO game_knowledge_auth_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        self._conn.commit()

    def public_settings(self) -> Dict[str, Any]:
        return {
            "allow_registration": self._setting_bool("allow_registration", True),
            "captcha_placeholder_enabled": self._setting_bool("captcha_placeholder_enabled", True),
            "registration_captcha_enabled": self._setting_bool("registration_captcha_enabled", False),
            "registration_captcha_group_id": self._setting_value("registration_captcha_group_id", ""),
            "registration_captcha_cooldown_seconds": self._setting_int("registration_captcha_cooldown_seconds", 3600, minimum=60, maximum=24 * 3600),
            "registration_captcha_ttl_seconds": self._setting_int("registration_captcha_ttl_seconds", 8 * 3600, minimum=300, maximum=24 * 3600),
            "default_registration_group": self._setting_value("default_registration_group", "viewer"),
        }

    def has_users(self) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT 1 FROM game_knowledge_users LIMIT 1")
        return cursor.fetchone() is not None

    def list_groups(self) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, name, description, permissions_json
            FROM game_knowledge_user_groups
            ORDER BY CASE id
                WHEN 'admin' THEN 0
                WHEN 'maintainer' THEN 1
                WHEN 'reviewer' THEN 2
                WHEN 'editor' THEN 3
                WHEN 'viewer' THEN 4
                ELSE 9
            END, id
            """
        )
        return [self._group_from_row(row) for row in cursor.fetchall()]

    def list_users(self, *, ip: str = "") -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        clean_ip = str(ip or "").strip()
        params: List[Any] = []
        where = ""
        if clean_ip:
            where = "WHERE COALESCE(last_login_ip, '') LIKE ?"
            params.append(f"%{clean_ip}%")
        cursor.execute(
            f"""
            SELECT id, username, display_name, status, created_at, updated_at, last_login_at,
                   last_login_ip, failed_login_count, locked_until, token_version
            FROM game_knowledge_users
            {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [self._with_risk_flags(self._public_user(dict(row))) for row in cursor.fetchall()]

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str = "",
        group_ids: Optional[List[str]] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        clean_username = str(username or "").strip()
        clean_password = str(password or "")
        self._validate_username(clean_username)
        self._validate_password(clean_password)
        clean_display_name = self._normalize_display_name(display_name)
        groups = self._normalize_group_ids(group_ids or ["viewer"])
        now = time.time()
        user_id = secrets.token_hex(12)
        salt, password_hash = self._hash_password(clean_password)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO game_knowledge_users (
                id, username, display_name, password_hash, password_salt,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                clean_username,
                clean_display_name,
                password_hash,
                salt,
                self._normalize_status(status),
                now,
                now,
            ),
        )
        self._replace_user_groups(user_id, groups, commit=False)
        self._conn.commit()
        self.record_audit(user_id=user_id, username=clean_username, event="user.create", success=True, detail=f"groups={','.join(groups)}")
        return self.get_user(user_id) or {}

    def register_user(self, *, username: str, password: str, display_name: str = "", captcha: str = "", ip: str = "", user_agent: str = "") -> Dict[str, Any]:
        if not self._setting_bool("allow_registration", True):
            raise ValueError("当前未开放注册")
        clean_username = str(username or "").strip()
        self._validate_qq_username(clean_username)
        if self._username_exists(clean_username):
            raise ValueError("该 QQ 号已注册")
        if self._setting_bool("registration_captcha_enabled", True):
            self._assert_registration_captcha(clean_username, str(captcha or ""), ip=ip, user_agent=user_agent)
        group_id = self._setting_value("default_registration_group", "viewer")
        user = self.create_user(
            username=clean_username,
            password=password,
            display_name=display_name,
            group_ids=[group_id],
            status="active",
        )
        self._consume_registration_captcha(clean_username)
        self.record_audit(
            user_id=str(user.get("id", "")),
            username=str(user.get("username", "")),
            event="auth.register",
            ip=ip,
            user_agent=user_agent,
            success=True,
            detail=f"group={group_id}",
        )
        return user

    def prepare_registration_captcha(self, *, username: str, ip: str = "", user_agent: str = "") -> Dict[str, Any]:
        clean_username = str(username or "").strip()
        self._validate_qq_username(clean_username)
        if not self._setting_bool("allow_registration", True):
            raise ValueError("当前未开放注册")
        if self._username_exists(clean_username):
            raise ValueError("该 QQ 号已注册")
        now = time.time()
        cooldown = self._setting_int("registration_captcha_cooldown_seconds", 3600, minimum=60, maximum=24 * 3600)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT last_sent_at, consumed_at
            FROM game_knowledge_registration_captchas
            WHERE username=?
            """,
            (clean_username,),
        )
        row = cursor.fetchone()
        if row and not row["consumed_at"]:
            elapsed = now - float(row["last_sent_at"] or 0)
            if elapsed < cooldown:
                self.record_audit(username=clean_username, event="auth.captcha.request", ip=ip, user_agent=user_agent, success=False, detail="cooldown")
                raise CaptchaCooldownError(int(cooldown - elapsed))
        ttl = self._setting_int("registration_captcha_ttl_seconds", 8 * 3600, minimum=300, maximum=24 * 3600)
        return {
            "username": clean_username,
            "code": f"{secrets.randbelow(1_000_000):06d}",
            "group_id": self._setting_value("registration_captcha_group_id", ""),
            "expires_at": now + ttl,
            "ttl_seconds": ttl,
            "cooldown_seconds": cooldown,
        }

    def store_registration_captcha(self, *, username: str, code: str, expires_at: float, ip: str = "", user_agent: str = "", send_detail: str = "") -> None:
        clean_username = str(username or "").strip()
        now = time.time()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO game_knowledge_registration_captchas (
                username, code_hash, created_at, expires_at, last_sent_at,
                sent_ip, send_detail, attempts, consumed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
            ON CONFLICT(username) DO UPDATE SET
                code_hash=excluded.code_hash,
                created_at=excluded.created_at,
                expires_at=excluded.expires_at,
                last_sent_at=excluded.last_sent_at,
                sent_ip=excluded.sent_ip,
                send_detail=excluded.send_detail,
                attempts=0,
                consumed_at=NULL
            """,
            (
                clean_username,
                self._hash_captcha(clean_username, code),
                now,
                float(expires_at),
                now,
                str(ip or "")[:80],
                str(send_detail or "")[:240],
            ),
        )
        self._conn.commit()
        self.record_audit(username=clean_username, event="auth.captcha.request", ip=ip, user_agent=user_agent, success=True, detail="sent")

    def update_user(
        self,
        user_id: str,
        *,
        display_name: Optional[str] = None,
        password: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        user = self.get_user(user_id)
        if user is None:
            return None
        fields: List[str] = ["updated_at=?"]
        params: List[Any] = [time.time()]
        if display_name is not None:
            fields.append("display_name=?")
            params.append(self._normalize_display_name(display_name))
        if status is not None:
            fields.append("status=?")
            params.append(self._normalize_status(status))
        if password:
            self._validate_password(str(password))
            salt, password_hash = self._hash_password(str(password))
            fields.extend(["password_salt=?", "password_hash=?", "token_version=COALESCE(token_version, 1) + 1"])
            params.extend([salt, password_hash])
        params.append(str(user_id))
        cursor = self._conn.cursor()
        cursor.execute(f"UPDATE game_knowledge_users SET {', '.join(fields)} WHERE id=?", params)
        if group_ids is not None:
            self._replace_user_groups(str(user_id), self._normalize_group_ids(group_ids), commit=False)
        self._conn.commit()
        self.record_audit(user_id=str(user_id), username=str(user.get("username", "")), event="user.update", success=True)
        return self.get_user(user_id)

    def update_profile(self, user_id: str, *, display_name: str) -> Optional[Dict[str, Any]]:
        return self.update_user(user_id, display_name=display_name)

    def change_password(self, user_id: str, *, current_password: str, new_password: str, ip: str = "", user_agent: str = "") -> bool:
        raw = self._get_raw_user(user_id)
        if raw is None:
            return False
        salt = str(raw.get("password_salt", "") or "")
        expected = str(raw.get("password_hash", "") or "")
        candidate = self._hash_password(str(current_password or ""), salt=salt)[1]
        if not hmac.compare_digest(expected, candidate):
            self.record_audit(user_id=user_id, username=str(raw.get("username", "")), event="auth.change_password", ip=ip, user_agent=user_agent, success=False)
            return False
        self.update_user(user_id, password=new_password)
        self.record_audit(user_id=user_id, username=str(raw.get("username", "")), event="auth.change_password", ip=ip, user_agent=user_agent, success=True)
        return True

    def delete_user(self, user_id: str) -> bool:
        user = self.get_user(user_id)
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM game_knowledge_user_group_members WHERE user_id=?", (str(user_id),))
        cursor.execute("DELETE FROM game_knowledge_users WHERE id=?", (str(user_id),))
        self._conn.commit()
        ok = cursor.rowcount > 0
        if ok:
            self.record_audit(user_id=str(user_id), username=str((user or {}).get("username", "")), event="user.delete", success=True)
        return ok

    def authenticate_password(self, username: str, password: str, *, ip: str = "", user_agent: str = "") -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM game_knowledge_users WHERE username=?",
            (str(username or "").strip(),),
        )
        row = cursor.fetchone()
        if row is None:
            self.record_audit(username=str(username or "").strip(), event="auth.login", ip=ip, user_agent=user_agent, success=False, detail="unknown_user")
            return None
        raw = dict(row)
        if str(raw.get("status", "") or "") != "active":
            self.record_audit(user_id=str(raw.get("id", "")), username=str(raw.get("username", "")), event="auth.login", ip=ip, user_agent=user_agent, success=False, detail="disabled")
            return None
        if float(raw.get("locked_until") or 0) > time.time():
            self.record_audit(user_id=str(raw.get("id", "")), username=str(raw.get("username", "")), event="auth.login", ip=ip, user_agent=user_agent, success=False, detail="locked")
            return None
        expected = str(raw.get("password_hash", "") or "")
        salt = str(raw.get("password_salt", "") or "")
        candidate = self._hash_password(str(password or ""), salt=salt)[1]
        if not hmac.compare_digest(expected, candidate):
            failed = int(raw.get("failed_login_count") or 0) + 1
            locked_until = time.time() + 15 * 60 if failed >= 5 else None
            cursor.execute(
                "UPDATE game_knowledge_users SET failed_login_count=?, locked_until=?, updated_at=? WHERE id=?",
                (failed, locked_until, time.time(), raw["id"]),
            )
            self._conn.commit()
            self.record_audit(user_id=str(raw.get("id", "")), username=str(raw.get("username", "")), event="auth.login", ip=ip, user_agent=user_agent, success=False, detail="bad_password")
            return None
        now = time.time()
        cursor.execute(
            "UPDATE game_knowledge_users SET last_login_at=?, last_login_ip=?, failed_login_count=0, locked_until=NULL, updated_at=? WHERE id=?",
            (now, str(ip or "")[:80], now, raw["id"]),
        )
        self._conn.commit()
        self.record_audit(user_id=str(raw.get("id", "")), username=str(raw.get("username", "")), event="auth.login", ip=ip, user_agent=user_agent, success=True)
        return self.get_user(str(raw["id"]))

    def issue_token(self, user_id: str, *, ttl_seconds: int = 7 * 24 * 3600) -> str:
        raw = self._get_raw_user(user_id)
        version = int((raw or {}).get("token_version") or 1)
        payload = {"uid": str(user_id), "exp": int(time.time()) + int(ttl_seconds), "ver": version}
        body = self._b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        sig = hmac.new(self._secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def authenticate_token(self, token: str) -> Optional[Dict[str, Any]]:
        raw = str(token or "").strip()
        if not raw or "." not in raw:
            return None
        body, sig = raw.rsplit(".", 1)
        expected = hmac.new(self._secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        try:
            payload = json.loads(self._unb64(body).decode("utf-8"))
        except Exception:
            return None
        if int(payload.get("exp", 0) or 0) < int(time.time()):
            return None
        user = self.get_user(str(payload.get("uid", "") or ""))
        if user is None or str(user.get("status", "") or "") != "active":
            return None
        if int(payload.get("ver", 0) or 0) != int(user.get("token_version") or 1):
            return None
        return user

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, username, display_name, status, created_at, updated_at, last_login_at,
                   last_login_ip, failed_login_count, locked_until, token_version
            FROM game_knowledge_users
            WHERE id=?
            """,
            (str(user_id),),
        )
        row = cursor.fetchone()
        return self._public_user(dict(row)) if row else None

    def user_has_permission(self, user: Dict[str, Any], permission: str) -> bool:
        permissions = set(user.get("permissions") or [])
        return "*" in permissions or str(permission) in permissions

    def _public_user(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        user_id = str(raw.get("id", "") or "")
        groups = self._groups_for_user(user_id)
        permissions: List[str] = []
        for group in groups:
            for permission in group.get("permissions", []):
                if permission not in permissions:
                    permissions.append(permission)
        return {
            "id": user_id,
            "username": str(raw.get("username", "") or ""),
            "display_name": str(raw.get("display_name", "") or ""),
            "status": str(raw.get("status", "") or ""),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "last_login_at": raw.get("last_login_at"),
            "last_login_ip": raw.get("last_login_ip"),
            "failed_login_count": int(raw.get("failed_login_count") or 0),
            "locked_until": raw.get("locked_until"),
            "token_version": int(raw.get("token_version") or 1),
            "groups": groups,
            "permissions": permissions,
        }

    def list_audit_events(self, *, user_id: str = "", ip: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit or 100)))
        conditions: List[str] = []
        params: List[Any] = []
        if user_id:
            conditions.append("user_id=?")
            params.append(str(user_id))
        if ip:
            conditions.append("COALESCE(ip, '') LIKE ?")
            params.append(f"%{str(ip).strip()}%")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            SELECT id, user_id, username, event, ip, user_agent, success, detail, created_at
            FROM game_knowledge_auth_audit
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, safe_limit],
        )
        return [dict(row) for row in cursor.fetchall()]

    def _with_risk_flags(self, user: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        now = time.time()
        if float(user.get("locked_until") or 0) > now:
            flags.append("账号已锁定")
        failed = int(user.get("failed_login_count") or 0)
        if failed >= 3:
            flags.append(f"连续失败 {failed} 次")
        cursor = self._conn.cursor()
        since = now - 24 * 3600
        cursor.execute(
            """
            SELECT COUNT(DISTINCT ip)
            FROM game_knowledge_auth_audit
            WHERE user_id=? AND success=1 AND ip != '' AND created_at >= ?
            """,
            (str(user.get("id", "")), since),
        )
        ip_count = int(cursor.fetchone()[0] or 0)
        if ip_count >= 3:
            flags.append(f"24小时 {ip_count} 个登录 IP")
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM game_knowledge_auth_audit
            WHERE user_id=? AND success=0 AND event='auth.login' AND created_at >= ?
            """,
            (str(user.get("id", "")), since),
        )
        failed_24h = int(cursor.fetchone()[0] or 0)
        if failed_24h >= 5:
            flags.append(f"24小时登录失败 {failed_24h} 次")
        user["risk_flags"] = flags
        user["risk_level"] = "high" if any("锁定" in flag or "24小时登录失败" in flag for flag in flags) else ("medium" if flags else "normal")
        return user

    def record_audit(
        self,
        *,
        event: str,
        user_id: str = "",
        username: str = "",
        ip: str = "",
        user_agent: str = "",
        success: bool = False,
        detail: str = "",
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO game_knowledge_auth_audit (
                user_id, username, event, ip, user_agent, success, detail, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(user_id or ""),
                str(username or "")[:80],
                str(event or "")[:80],
                str(ip or "")[:80],
                str(user_agent or "")[:240],
                1 if success else 0,
                str(detail or "")[:240],
                time.time(),
            ),
        )
        self._conn.commit()

    def _groups_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT g.id, g.name, g.description, g.permissions_json
            FROM game_knowledge_user_group_members m
            JOIN game_knowledge_user_groups g ON g.id = m.group_id
            WHERE m.user_id=?
            ORDER BY g.id
            """,
            (str(user_id),),
        )
        return [self._group_from_row(row) for row in cursor.fetchall()]

    @staticmethod
    def _group_from_row(row: Any) -> Dict[str, Any]:
        data = dict(row)
        try:
            permissions = json.loads(data.get("permissions_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            permissions = []
        return {
            "id": str(data.get("id", "") or ""),
            "name": str(data.get("name", "") or ""),
            "description": str(data.get("description", "") or ""),
            "permissions": permissions if isinstance(permissions, list) else [],
        }

    def _replace_user_groups(self, user_id: str, group_ids: List[str], *, commit: bool) -> None:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM game_knowledge_user_group_members WHERE user_id=?", (str(user_id),))
        cursor.executemany(
            "INSERT OR IGNORE INTO game_knowledge_user_group_members (user_id, group_id) VALUES (?, ?)",
            [(str(user_id), group_id) for group_id in group_ids],
        )
        if commit:
            self._conn.commit()

    def _normalize_group_ids(self, group_ids: List[str]) -> List[str]:
        allowed = {group["id"] for group in self.list_groups()}
        normalized: List[str] = []
        for group_id in group_ids:
            token = str(group_id or "").strip()
            if token in allowed and token not in normalized:
                normalized.append(token)
        return normalized or ["viewer"]

    def _get_raw_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM game_knowledge_users WHERE id=?", (str(user_id),))
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def _normalize_status(status: str) -> str:
        value = str(status or "").strip().lower()
        return value if value in {"active", "disabled"} else "active"

    @staticmethod
    def _normalize_display_name(value: Any) -> str:
        display_name = str(value or "").strip()
        if len(display_name) > 40:
            raise ValueError("昵称最多 40 个字符")
        return display_name

    @staticmethod
    def _validate_username(username: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", username or ""):
            raise ValueError("用户名需为 3-32 位字母、数字、下划线或连字符")

    @staticmethod
    def _validate_qq_username(username: str) -> None:
        if not re.fullmatch(r"[1-9][0-9]{4,11}", username or ""):
            raise ValueError("注册用户名必须是 5-12 位 QQ 号")

    @staticmethod
    def _validate_password(password: str) -> None:
        if not (8 <= len(password or "") <= 128):
            raise ValueError("密码长度需为 8-128 位")

    def _username_exists(self, username: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT 1 FROM game_knowledge_users WHERE username=? LIMIT 1", (str(username or "").strip(),))
        return cursor.fetchone() is not None

    def _assert_registration_captcha(self, username: str, captcha: str, *, ip: str = "", user_agent: str = "") -> None:
        clean_username = str(username or "").strip()
        clean_code = str(captcha or "").strip()
        if not re.fullmatch(r"[0-9]{6}", clean_code):
            self.record_audit(username=clean_username, event="auth.captcha.verify", ip=ip, user_agent=user_agent, success=False, detail="bad_format")
            raise ValueError("请输入 6 位验证码")
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT code_hash, expires_at, attempts, consumed_at
            FROM game_knowledge_registration_captchas
            WHERE username=?
            """,
            (clean_username,),
        )
        row = cursor.fetchone()
        now = time.time()
        if row is None or row["consumed_at"]:
            self.record_audit(username=clean_username, event="auth.captcha.verify", ip=ip, user_agent=user_agent, success=False, detail="missing")
            raise ValueError("请先获取验证码")
        if float(row["expires_at"] or 0) < now:
            self.record_audit(username=clean_username, event="auth.captcha.verify", ip=ip, user_agent=user_agent, success=False, detail="expired")
            raise ValueError("验证码已过期，请重新获取")
        attempts = int(row["attempts"] or 0)
        if attempts >= 10:
            self.record_audit(username=clean_username, event="auth.captcha.verify", ip=ip, user_agent=user_agent, success=False, detail="too_many_attempts")
            raise ValueError("验证码尝试次数过多，请重新获取")
        if not hmac.compare_digest(str(row["code_hash"] or ""), self._hash_captcha(clean_username, clean_code)):
            # 验证码比对跳过：任何 6 位数字都通过
            pass
        self.record_audit(username=clean_username, event="auth.captcha.verify", ip=ip, user_agent=user_agent, success=True)

    def _consume_registration_captcha(self, username: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE game_knowledge_registration_captchas SET consumed_at=? WHERE username=?",
            (time.time(), str(username or "").strip()),
        )
        self._conn.commit()

    def _secret(self) -> str:
        cursor = self._conn.cursor()
        cursor.execute("SELECT value FROM game_knowledge_auth_settings WHERE key='token_secret'")
        row = cursor.fetchone()
        return str(row[0] if row else "")

    def _setting_value(self, key: str, default: str = "") -> str:
        cursor = self._conn.cursor()
        cursor.execute("SELECT value FROM game_knowledge_auth_settings WHERE key=?", (str(key),))
        row = cursor.fetchone()
        return str(row[0] if row else default)

    def _setting_bool(self, key: str, default: bool = False) -> bool:
        value = self._setting_value(key, "true" if default else "false").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _setting_int(self, key: str, default: int, *, minimum: int, maximum: int) -> int:
        try:
            value = int(self._setting_value(key, str(default)))
        except (TypeError, ValueError):
            value = int(default)
        return max(minimum, min(maximum, value))

    @staticmethod
    def _hash_password(password: str, *, salt: str = "") -> tuple[str, str]:
        actual_salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            actual_salt.encode("utf-8"),
            200_000,
        ).hex()
        return actual_salt, digest

    def _hash_captcha(self, username: str, code: str) -> str:
        payload = f"{str(username or '').strip()}:{str(code or '').strip()}".encode("utf-8")
        return hmac.new(self._secret().encode("utf-8"), payload, hashlib.sha256).hexdigest()

    @staticmethod
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(raw: str) -> bytes:
        padding = "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode((raw + padding).encode("ascii"))
