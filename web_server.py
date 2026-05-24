"""Independent WebUI for GameKnowledge."""

from __future__ import annotations

import asyncio
import gzip
import json
import mimetypes
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, web
from gk_shims.logger_shim import get_logger
from .kernel.core.utils.game_knowledge_analyzer import GameKnowledgeAnalyzer, _AI_REVIEW_PROMPT
from gk_shims.llm_shim import LLMServiceClient

from .auth_service import CaptchaCooldownError, GameKnowledgeAuthService
from .revision_service import GameKnowledgeRevisionService

logger = get_logger("plugin.gk.web")

_DIST_DIR = Path(__file__).resolve().parent / "webui" / "dist"


class GameKnowledgeWebServer:
    def __init__(
        self,
        *,
        kernel_provider: Any,
        host: str,
        port: int,
        announcement_store_provider: Any = None,
        board_service_provider: Any = None,
        qa_bridge_token: str = "",
    ) -> None:
        self._kernel_provider = kernel_provider
        self._host = host
        self._port = int(port)
        self._announcement_store_provider = announcement_store_provider
        self._board_service_provider = board_service_provider
        self._qa_bridge_token = str(qa_bridge_token or "").strip()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._auth_attempts: Dict[str, list[float]] = {}
        self._compressed_asset_cache: Dict[str, tuple[int, bytes]] = {}
        self._quality_tuning_tasks: Dict[str, Dict[str, Any]] = {}
        self._quality_tuning_queue: deque[str] = deque()
        self._quality_tuning_worker_task: asyncio.Task | None = None
        self._quality_tuning_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._runner is not None:
            return
        app = web.Application(client_max_size=32 * 1024 * 1024, middlewares=[self._security_headers_middleware, self._auth_middleware])
        app.router.add_get("/", self._page)
        assets_dir = _DIST_DIR / "assets"
        if assets_dir.is_dir():
            app.router.add_get("/assets/{tail:.*}", self._asset)
        napcat_assets_dir = _DIST_DIR / "napcat-assets"
        if napcat_assets_dir.is_dir():
            app.router.add_static("/napcat-assets", napcat_assets_dir)

        # 仪表盘
        app.router.add_get("/api/game-knowledge/auth/bootstrap", self._auth_bootstrap_status)
        app.router.add_post("/api/game-knowledge/auth/bootstrap", self._auth_bootstrap)
        app.router.add_post("/api/game-knowledge/auth/captcha/request", self._auth_request_captcha)
        app.router.add_post("/api/game-knowledge/auth/register", self._auth_register)
        app.router.add_post("/api/game-knowledge/auth/login", self._auth_login)
        app.router.add_get("/api/game-knowledge/auth/me", self._auth_me)
        app.router.add_patch("/api/game-knowledge/auth/profile", self._auth_update_profile)
        app.router.add_post("/api/game-knowledge/auth/password", self._auth_change_password)
        app.router.add_post("/api/game-knowledge/auth/logout", self._auth_logout)
        app.router.add_get("/api/game-knowledge/auth/groups", self._auth_groups)
        app.router.add_get("/api/game-knowledge/auth/audit", self._auth_audit)
        app.router.add_get("/api/game-knowledge/auth/users", self._auth_list_users)
        app.router.add_post("/api/game-knowledge/auth/users", self._auth_create_user)
        app.router.add_patch("/api/game-knowledge/auth/users/{id}", self._auth_update_user)
        app.router.add_delete("/api/game-knowledge/auth/users/{id}", self._auth_delete_user)
        app.router.add_get("/api/game-knowledge/me/history", self._my_history)
        app.router.add_get("/api/game-knowledge/stats", self._stats)

        # 搜索
        app.router.add_post("/api/game-knowledge/search", self._search)
        app.router.add_post("/api/game-knowledge/qa-bridge", self._qa_bridge_search)
        app.router.add_get("/api/game-knowledge/search/random", self._random_search)
        app.router.add_get("/api/game-knowledge/search/hits/{hash}/card", self._get_search_hit_card)
        app.router.add_post("/api/game-knowledge/search/hits/{hash}/question", self._question_search_hit)
        app.router.add_patch("/api/game-knowledge/search/hits/{hash}", self._update_search_hit)
        app.router.add_delete("/api/game-knowledge/search/hits/{hash}", self._delete_search_hit)

        # 写入
        app.router.add_post("/api/game-knowledge/ingest", self._ingest)
        app.router.add_post("/api/game-knowledge/ingest/upload", self._ingest_upload)

        # 导入任务管理
        app.router.add_get("/api/game-knowledge/import/settings", self._import_settings)
        app.router.add_get("/api/game-knowledge/import/tasks", self._import_list_tasks)
        app.router.add_get("/api/game-knowledge/import/tasks/{task_id}", self._import_get_task)
        app.router.add_get("/api/game-knowledge/import/files", self._import_get_files)
        app.router.add_get("/api/game-knowledge/import/chunks", self._import_get_chunks)
        app.router.add_post("/api/game-knowledge/import/cancel", self._import_cancel)
        app.router.add_post("/api/game-knowledge/import/retry", self._import_retry)

        # 审核队列
        app.router.add_get("/api/game-knowledge/cards", self._list_cards)
        app.router.add_get("/api/game-knowledge/cards/stats", self._card_stats)
        app.router.add_get("/api/game-knowledge/cards/groups", self._list_card_groups)
        app.router.add_get("/api/game-knowledge/cards/{id}", self._get_card)
        app.router.add_patch("/api/game-knowledge/cards/{id}", self._update_card)
        app.router.add_post("/api/game-knowledge/cards/{id}/approve", self._approve_card)
        app.router.add_post("/api/game-knowledge/cards/{id}/reject", self._reject_card)
        app.router.add_post("/api/game-knowledge/cards/{id}/question", self._question_card)
        app.router.add_post("/api/game-knowledge/cards/{id}/merge", self._merge_card)
        app.router.add_delete("/api/game-knowledge/cards/{id}", self._delete_card)

        # 知识卡片随机调优（仅管理员）
        app.router.add_get("/api/game-knowledge/quality-tuning/cards", self._quality_tuning_cards)
        app.router.add_get("/api/game-knowledge/quality-tuning/tasks", self._quality_tuning_tasks_list)
        app.router.add_post("/api/game-knowledge/quality-tuning/run", self._quality_tuning_run)

        # 图谱
        app.router.add_get("/api/game-knowledge/graph", self._graph_get)
        app.router.add_get("/api/game-knowledge/graph/search", self._graph_search)
        app.router.add_post("/api/game-knowledge/graph/node", self._graph_create_node)
        app.router.add_delete("/api/game-knowledge/graph/node", self._graph_delete_node)
        app.router.add_post("/api/game-knowledge/graph/node/rename", self._graph_rename_node)
        app.router.add_post("/api/game-knowledge/graph/edge", self._graph_create_edge)
        app.router.add_delete("/api/game-knowledge/graph/edge", self._graph_delete_edge)

        # 来源
        app.router.add_get("/api/game-knowledge/sources", self._source_list)
        app.router.add_post("/api/game-knowledge/sources/delete", self._source_delete)

        # 公告
        app.router.add_get("/api/game-knowledge/announcements", self._announcement_list)
        app.router.add_get("/api/game-knowledge/announcements/active", self._announcement_active)
        app.router.add_post("/api/game-knowledge/announcements", self._announcement_create)
        app.router.add_delete("/api/game-knowledge/announcements/{id}", self._announcement_delete)

        # 留言板
        app.router.add_get("/api/game-knowledge/board/threads", self._board_list_threads)
        app.router.add_post("/api/game-knowledge/board/threads", self._board_create_thread)
        app.router.add_get("/api/game-knowledge/board/threads/{id}", self._board_get_thread)
        app.router.add_delete("/api/game-knowledge/board/threads/{id}", self._board_delete_thread)
        app.router.add_post("/api/game-knowledge/board/threads/{id}/posts", self._board_reply)
        app.router.add_post("/api/game-knowledge/board/threads/{id}/resolve", self._board_resolve)
        app.router.add_delete("/api/game-knowledge/board/posts/{id}", self._board_delete_post)

        # 情景
        app.router.add_get("/api/game-knowledge/episodes", self._episode_list)
        app.router.add_get("/api/game-knowledge/episodes/status", self._episode_status)
        app.router.add_get("/api/game-knowledge/episodes/{episode_id}", self._episode_get)
        app.router.add_delete("/api/game-knowledge/episodes/{episode_id}", self._episode_delete)
        app.router.add_post("/api/game-knowledge/episodes/rebuild", self._episode_rebuild)
        app.router.add_post("/api/game-knowledge/episodes/process-pending", self._episode_process_pending)

        # 维护 (V5)
        app.router.add_get("/api/game-knowledge/recycle-bin", self._v5_recycle_bin)
        app.router.add_post("/api/game-knowledge/v5/{action}", self._v5_action)

        # 运行时
        app.router.add_get("/api/game-knowledge/config", self._runtime_config)
        app.router.add_post("/api/game-knowledge/save", self._runtime_save)
        app.router.add_post("/api/game-knowledge/self-check", self._runtime_self_check)
        app.router.add_post("/api/game-knowledge/refresh-self-check", self._runtime_refresh_self_check)
        app.router.add_post("/api/game-knowledge/config/auto-save", self._runtime_auto_save)
        app.router.add_post("/api/game-knowledge/vectors/rebuild", self._runtime_rebuild_vectors)

        # 调优
        app.router.add_get("/api/game-knowledge/tuning/profile", self._tuning_get_profile)
        app.router.add_get("/api/game-knowledge/tuning/tasks", self._tuning_list_tasks)
        app.router.add_post("/api/game-knowledge/tuning/create-task", self._tuning_create_task)
        app.router.add_post("/api/game-knowledge/tuning/cancel-task", self._tuning_cancel_task)
        app.router.add_post("/api/game-knowledge/tuning/apply-best", self._tuning_apply_best)
        app.router.add_post("/api/game-knowledge/tuning/apply-profile", self._tuning_apply_profile)
        app.router.add_post("/api/game-knowledge/tuning/rollback", self._tuning_rollback)

        # 删除管理
        app.router.add_post("/api/game-knowledge/delete/preview", self._delete_preview)
        app.router.add_post("/api/game-knowledge/delete/execute", self._delete_execute)
        app.router.add_post("/api/game-knowledge/delete/restore", self._delete_restore)
        app.router.add_get("/api/game-knowledge/delete/operations", self._delete_list_operations)
        app.router.add_get("/api/game-knowledge/delete/operations/{operation_id}", self._delete_get_operation)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        try:
            await self._site.start()
            logger.info(f"GameKnowledge WebUI started: http://{self._host}:{self._port}")
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self._quality_tuning_worker_task is not None and not self._quality_tuning_worker_task.done():
            self._quality_tuning_worker_task.cancel()
            try:
                await self._quality_tuning_worker_task
            except asyncio.CancelledError:
                pass
        self._quality_tuning_worker_task = None
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def _kernel(self):
        return await self._kernel_provider()

    @staticmethod
    async def _page(request: web.Request) -> web.Response:
        index_path = _DIST_DIR / "index.html"
        if not index_path.is_file():
            return web.Response(text="前端未构建，请运行 cd webui && npm run build", status=503)
        response = web.FileResponse(index_path)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    async def _asset(self, request: web.Request) -> web.StreamResponse:
        tail = str(request.match_info.get("tail", "") or "").strip("/")
        asset_root = (_DIST_DIR / "assets").resolve()
        asset_path = (asset_root / tail).resolve()
        if not str(asset_path).startswith(str(asset_root)) or not asset_path.is_file():
            return self._error_response("资源不存在", status=404)

        content_type = mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream"
        headers = {
            "Cache-Control": "public, max-age=31536000, immutable",
            "Vary": "Accept-Encoding",
            "Content-Type": content_type,
        }
        accepts_gzip = "gzip" in str(request.headers.get("Accept-Encoding", "") or "").lower()
        if accepts_gzip and asset_path.suffix.lower() in {".js", ".css", ".json", ".svg", ".txt", ".html"}:
            stat = asset_path.stat()
            cache_key = str(asset_path)
            cached = self._compressed_asset_cache.get(cache_key)
            if cached is None or cached[0] != int(stat.st_mtime_ns):
                cached = (int(stat.st_mtime_ns), gzip.compress(asset_path.read_bytes(), compresslevel=6))
                self._compressed_asset_cache[cache_key] = cached
            headers["Content-Encoding"] = "gzip"
            return web.Response(body=cached[1], headers=headers)

        return web.FileResponse(asset_path, headers=headers)

    @staticmethod
    def _error_response(message: str, *, status: int = 400) -> web.Response:
        return web.json_response({"success": False, "error": message}, status=status)

    @staticmethod
    def _int_query(request: web.Request, name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
        try:
            value = int(request.query.get(name, default) or default)
        except (TypeError, ValueError):
            value = default
        value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    @staticmethod
    def _int_value(value: Any, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
        try:
            parsed = int(value if value is not None else default)
        except (TypeError, ValueError):
            parsed = default
        parsed = max(minimum, parsed)
        if maximum is not None:
            parsed = min(maximum, parsed)
        return parsed

    @web.middleware
    async def _security_headers_middleware(self, request: web.Request, handler: Any) -> web.StreamResponse:
        response = await handler(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        return response

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler: Any) -> web.StreamResponse:
        path = request.path
        if not path.startswith("/api/game-knowledge/"):
            return await handler(request)
        if path in {
            "/api/game-knowledge/auth/bootstrap",
            "/api/game-knowledge/auth/captcha/request",
            "/api/game-knowledge/auth/login",
            "/api/game-knowledge/auth/register",
            "/api/game-knowledge/qa-bridge",
        }:
            return await handler(request)

        user = await self._authenticate_request(request)
        if user is None:
            return web.json_response({"success": False, "error": "请先登录"}, status=401)
        request["gk_user"] = user

        permission = self._permission_for_request(request)
        if permission and not self._user_has_permission(user, permission):
            return web.json_response({"success": False, "error": "权限不足", "permission": permission}, status=403)
        return await handler(request)

    async def _authenticate_request(self, request: web.Request) -> Dict[str, Any] | None:
        auth_header = str(request.headers.get("Authorization", "") or "").strip()
        token = ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        token = token or str(request.headers.get("X-GameKnowledge-Token", "") or "").strip()
        if not token:
            return None
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return None
        try:
            return GameKnowledgeAuthService(store=store).authenticate_token(token)
        except Exception as exc:
            logger.warning(f"WebUI 认证失败: {exc}")
            return None

    @staticmethod
    def _current_user(request: web.Request) -> Dict[str, Any]:
        user = request.get("gk_user")
        return user if isinstance(user, dict) else {}

    @staticmethod
    def _actor_name(user: Dict[str, Any]) -> str:
        return str(user.get("display_name", "") or user.get("username", "") or user.get("id", "") or "").strip()

    @staticmethod
    def _user_has_permission(user: Dict[str, Any], permission: str) -> bool:
        permissions = set(user.get("permissions") or [])
        return "*" in permissions or permission in permissions

    @staticmethod
    def _permission_for_request(request: web.Request) -> str:
        path = request.path.removeprefix("/api/game-knowledge")
        method = request.method.upper()
        if path in {"/auth/me", "/auth/logout", "/auth/profile", "/auth/password"}:
            return ""
        if path == "/auth/groups" or path == "/auth/audit":
            return "users.manage"
        if path.startswith("/auth/users"):
            return "users.manage"
        if path == "/me/history":
            return "history.view_own"
        if path == "/stats":
            return "dashboard.view"
        if path.startswith("/announcements"):
            if method == "POST" and path == "/announcements":
                return "announcement.publish"
            if method == "DELETE":
                return "announcement.delete"
            return "announcement.view"
        if path.startswith("/board"):
            # 删除主题/楼层走 board.view，由 handler 内进一步校验本人/`board.delete_any`
            if method == "POST" and path.endswith("/resolve"):
                return "board.resolve"
            if method == "POST":
                return "board.post"
            return "board.view"
        if path == "/search" and method == "POST":
            return "knowledge.search"
        if path == "/search/random" and method == "GET":
            return "knowledge.search"
        if path.startswith("/search/hits/") and path.endswith("/card") and method == "GET":
            return "knowledge.search"
        if path.startswith("/search/hits/") and path.endswith("/question") and method == "POST":
            return "knowledge.search"
        if path.startswith("/search/hits/") and method == "PATCH":
            return "knowledge.edit"
        if path.startswith("/search/hits/") and method == "DELETE":
            return "knowledge.delete"
        if path.startswith("/ingest") or path.startswith("/import"):
            return "knowledge.create"
        if path == "/cards" and method == "GET":
            return "review.view"
        if path == "/cards/stats" and method == "GET":
            return "review.view"
        if path == "/cards/groups" and method == "GET":
            return "review.view"
        if path.startswith("/cards/") and method == "GET":
            return "review.view"
        if path.startswith("/cards/") and method == "PATCH":
            return "knowledge.edit"
        if path.startswith("/cards/") and path.endswith("/approve"):
            return "review.approve"
        if path.startswith("/cards/") and path.endswith("/reject"):
            return "review.reject"
        if path.startswith("/cards/") and path.endswith("/question"):
            return "review.reject"
        if path.startswith("/cards/") and path.endswith("/merge"):
            return "review.approve"
        if path.startswith("/cards/") and method == "DELETE":
            return "knowledge.delete"
        if path.startswith("/sources"):
            return "sources.manage"
        if path.startswith("/delete") or path.startswith("/recycle-bin") or path.startswith("/v5"):
            return "maintenance.manage"
        if path.startswith("/config") or path.startswith("/save") or path.startswith("/self-check"):
            return "maintenance.manage"
        if path.startswith("/quality-tuning"):
            return "users.manage"
        if path.startswith("/refresh-self-check") or path.startswith("/vectors") or path.startswith("/tuning"):
            return "maintenance.manage"
        if path.startswith("/episodes"):
            return "*"
        if path.startswith("/graph"):
            return "maintenance.manage"
        return "users.manage"

    @staticmethod
    def _client_ip(request: web.Request) -> str:
        forwarded = str(request.headers.get("X-Forwarded-For", "") or "").split(",", 1)[0].strip()
        peer = request.transport.get_extra_info("peername") if request.transport else None
        return forwarded or (str(peer[0]) if isinstance(peer, tuple) and peer else "")

    def _allow_auth_attempt(self, key: str, *, limit: int = 12, window_seconds: int = 300) -> bool:
        now = time.time()
        attempts = [item for item in self._auth_attempts.get(key, []) if now - item < window_seconds]
        if len(attempts) >= limit:
            self._auth_attempts[key] = attempts
            return False
        attempts.append(now)
        self._auth_attempts[key] = attempts
        return True

    # ==================== 认证与用户 ====================

    async def _auth_service(self) -> GameKnowledgeAuthService:
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            raise RuntimeError("metadata_store 未就绪")
        return GameKnowledgeAuthService(store=store)

    async def _auth_bootstrap_status(self, request: web.Request) -> web.Response:
        _ = request
        auth = await self._auth_service()
        return web.json_response({
            "success": True,
            "has_users": auth.has_users(),
            "groups": auth.list_groups(),
            "settings": auth.public_settings(),
        })

    async def _auth_bootstrap(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        if auth.has_users():
            return self._error_response("管理员已初始化", status=409)
        payload = await self._json(request)
        try:
            user = auth.create_user(
                username=str(payload.get("username", "") or ""),
                password=str(payload.get("password", "") or ""),
                display_name=str(payload.get("display_name", "") or ""),
                group_ids=["admin"],
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        token = auth.issue_token(str(user.get("id", "")))
        return web.json_response({"success": True, "token": token, "user": user})

    async def _auth_register(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        ip = self._client_ip(request)
        payload = await self._json(request)
        username = str(payload.get("username", "") or "")
        if not self._allow_auth_attempt(f"register:{ip}", limit=8, window_seconds=300):
            return self._error_response("注册尝试过于频繁，请稍后再试", status=429)
        try:
            user = auth.register_user(
                username=username,
                password=str(payload.get("password", "") or ""),
                display_name=str(payload.get("display_name", "") or ""),
                captcha=str(payload.get("captcha", "") or ""),
                ip=ip,
                user_agent=str(request.headers.get("User-Agent", "") or ""),
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        except Exception:
            return self._error_response("注册失败，请换一个用户名后重试", status=400)
        token = auth.issue_token(str(user.get("id", "")))
        return web.json_response({"success": True, "token": token, "user": user})

    async def _auth_request_captcha(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        ip = self._client_ip(request)
        payload = await self._json(request)
        username = str(payload.get("username", "") or "").strip()
        if not self._allow_auth_attempt(f"captcha:{ip}:{username}", limit=6, window_seconds=300):
            return self._error_response("验证码请求过于频繁，请稍后再试", status=429)
        try:
            captcha = auth.prepare_registration_captcha(
                username=username,
                ip=ip,
                user_agent=str(request.headers.get("User-Agent", "") or ""),
            )
            send_detail = await self._send_registration_captcha(captcha)
            auth.store_registration_captcha(
                username=str(captcha["username"]),
                code=str(captcha["code"]),
                expires_at=float(captcha["expires_at"]),
                ip=ip,
                user_agent=str(request.headers.get("User-Agent", "") or ""),
                send_detail=send_detail,
            )
        except CaptchaCooldownError as exc:
            return web.json_response(
                {
                    "success": False,
                    "error": str(exc),
                    "cooldown_remaining": exc.remaining_seconds,
                },
                status=429,
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        except Exception as exc:
            logger.warning(f"发送注册验证码失败: {exc}")
            return self._error_response("验证码发送失败，请确认 Yunzai/bs-plugin 已启动且机器人可私聊该 QQ", status=502)
        return web.json_response(
            {
                "success": True,
                "message": "验证码已发送，请查看群临时会话或私聊",
                "cooldown_seconds": int(captcha.get("cooldown_seconds") or 3600),
                "ttl_seconds": int(captcha.get("ttl_seconds") or 8 * 3600),
            }
        )

    async def _send_registration_captcha(self, captcha: Dict[str, Any]) -> str:
        bridge_url = str(captcha.get("bridge_url", "") or "").strip()
        if not self._is_loopback_bridge_url(bridge_url):
            raise ValueError("验证码桥接地址必须是本机地址")
        headers = {"Content-Type": "application/json"}
        token = str(captcha.get("bridge_token", "") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        timeout = ClientTimeout(total=10)
        payload = {
            "group_id": str(captcha.get("group_id", "") or ""),
            "user_id": str(captcha.get("username", "") or ""),
            "code": str(captcha.get("code", "") or ""),
            "ttl_seconds": int(captcha.get("ttl_seconds") or 8 * 3600),
        }
        async with ClientSession(timeout=timeout) as session:
            async with session.post(bridge_url, json=payload, headers=headers) as response:
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = {"message": await response.text()}
                if response.status >= 400 or not data.get("success", data.get("ok", False)):
                    message = str(data.get("error") or data.get("message") or "验证码桥接发送失败")
                    raise ValueError(message)
                detail = data.get("detail") if isinstance(data, dict) else None
                return str(detail or "bs-plugin")

    @staticmethod
    def _is_loopback_bridge_url(raw_url: str) -> bool:
        try:
            parsed = urlparse(raw_url)
        except Exception:
            return False
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and host in {"127.0.0.1", "localhost", "::1"}

    async def _auth_login(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        ip = self._client_ip(request)
        payload = await self._json(request)
        username = str(payload.get("username", "") or "")
        if not self._allow_auth_attempt(f"login:{ip}:{username}", limit=10, window_seconds=300):
            return self._error_response("登录尝试过于频繁，请稍后再试", status=429)
        user = auth.authenticate_password(
            username,
            str(payload.get("password", "") or ""),
            ip=ip,
            user_agent=str(request.headers.get("User-Agent", "") or ""),
        )
        if user is None:
            return self._error_response("用户名或密码错误", status=401)
        token = auth.issue_token(str(user.get("id", "")))
        return web.json_response({"success": True, "token": token, "user": user})

    async def _auth_me(self, request: web.Request) -> web.Response:
        return web.json_response({"success": True, "user": self._current_user(request)})

    async def _auth_update_profile(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        current_user = self._current_user(request)
        payload = await self._json(request)
        try:
            user = auth.update_profile(
                str(current_user.get("id", "") or ""),
                display_name=str(payload.get("display_name", "") or ""),
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        if user is None:
            return self._error_response("用户不存在", status=404)
        return web.json_response({"success": True, "user": user})

    async def _auth_change_password(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        current_user = self._current_user(request)
        payload = await self._json(request)
        try:
            ok = auth.change_password(
                str(current_user.get("id", "") or ""),
                current_password=str(payload.get("current_password", "") or ""),
                new_password=str(payload.get("new_password", "") or ""),
                ip=self._client_ip(request),
                user_agent=str(request.headers.get("User-Agent", "") or ""),
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        if not ok:
            return self._error_response("当前密码不正确", status=400)
        user = auth.get_user(str(current_user.get("id", "") or ""))
        token = auth.issue_token(str(current_user.get("id", "") or ""))
        return web.json_response({"success": True, "token": token, "user": user})

    async def _auth_logout(self, request: web.Request) -> web.Response:
        _ = request
        return web.json_response({"success": True})

    async def _auth_groups(self, request: web.Request) -> web.Response:
        _ = request
        auth = await self._auth_service()
        return web.json_response({"success": True, "groups": auth.list_groups()})

    async def _auth_list_users(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        ip = str(request.query.get("ip", "") or "")
        return web.json_response({"success": True, "users": auth.list_users(ip=ip), "groups": auth.list_groups()})

    async def _auth_audit(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        limit = self._int_query(request, "limit", 100, minimum=1, maximum=500)
        user_id = str(request.query.get("user_id", "") or "")
        ip = str(request.query.get("ip", "") or "")
        return web.json_response({"success": True, "events": auth.list_audit_events(user_id=user_id, ip=ip, limit=limit)})

    async def _auth_create_user(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        payload = await self._json(request)
        try:
            user = auth.create_user(
                username=str(payload.get("username", "") or ""),
                password=str(payload.get("password", "") or ""),
                display_name=str(payload.get("display_name", "") or ""),
                group_ids=list(payload.get("group_ids") or ["viewer"]),
                status=str(payload.get("status", "active") or "active"),
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        except Exception as exc:
            return self._error_response(f"创建用户失败: {exc}", status=400)
        return web.json_response({"success": True, "user": user})

    async def _auth_update_user(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        user_id = str(request.match_info.get("id", "") or "").strip()
        payload = await self._json(request)
        try:
            user = auth.update_user(
                user_id,
                display_name=payload.get("display_name") if "display_name" in payload else None,
                password=str(payload.get("password", "") or "") if payload.get("password") else None,
                group_ids=list(payload.get("group_ids")) if isinstance(payload.get("group_ids"), list) else None,
                status=str(payload.get("status", "")) if "status" in payload else None,
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        if user is None:
            return self._error_response("用户不存在", status=404)
        return web.json_response({"success": True, "user": user})

    async def _auth_delete_user(self, request: web.Request) -> web.Response:
        auth = await self._auth_service()
        user_id = str(request.match_info.get("id", "") or "").strip()
        current_user = self._current_user(request)
        if user_id == str(current_user.get("id", "") or ""):
            return self._error_response("不能删除当前登录用户", status=400)
        ok = auth.delete_user(user_id)
        return web.json_response({"success": ok, "user_id": user_id})

    async def _my_history(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        user = self._current_user(request)
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        offset = self._int_query(request, "offset", 0, minimum=0)
        user_id = str(user.get("id", "") or "")
        history = store.list_knowledge_card_history(actor_id=user_id, limit=limit, offset=offset)
        stats = store.get_knowledge_user_activity_stats(user_id) if hasattr(store, "get_knowledge_user_activity_stats") else {}
        return web.json_response({"success": True, "history": history, "stats": stats, "count": len(history)})

    # ==================== 仪表盘 ====================

    async def _stats(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        stats = kernel.memory_stats()
        store = kernel.metadata_store
        if store is not None:
            sources = store.get_all_sources()
            stats["source_count"] = len(sources)
            graph_node_count = 0
            graph_edge_count = 0
            try:
                graph = await kernel.memory_graph_admin(action="get_graph")
                if isinstance(graph, dict) and graph.get("success"):
                    graph_payload = graph.get("graph", graph)
                    nodes = graph_payload.get("nodes", []) if isinstance(graph_payload, dict) else []
                    edges = graph_payload.get("edges", []) if isinstance(graph_payload, dict) else []
                    if isinstance(graph_payload, dict):
                        graph_node_count = int(graph_payload.get("total_nodes", len(nodes)) or 0)
                        graph_edge_count = int(graph_payload.get("total_edges", len(edges)) or 0)
            except Exception:
                graph_node_count = 0
                graph_edge_count = 0
            if hasattr(store, "get_statistics"):
                store_stats = store.get_statistics()
                stats["paragraph_count"] = int(store_stats.get("paragraph_count", 0) or 0)
                stats["entity_count"] = int(store_stats.get("entity_count", 0) or 0)
                stats["relation_count"] = int(store_stats.get("relation_count", 0) or 0)
                stats["knowledge_cards_pending"] = int(store_stats.get("knowledge_cards_pending", 0) or 0)
                stats["knowledge_cards_needs_answer"] = int(store_stats.get("knowledge_cards_needs_answer", 0) or 0)
                stats["knowledge_cards_approved"] = int(store_stats.get("knowledge_cards_approved", 0) or 0)
                stats["knowledge_cards_rejected"] = int(store_stats.get("knowledge_cards_rejected", 0) or 0)
                stats["knowledge_cards_ai_rejected"] = int(store_stats.get("knowledge_cards_ai_rejected", 0) or 0)
                stats["knowledge_cards_total"] = int(store_stats.get("knowledge_cards_total", 0) or 0)
                stats["knowledge_cards_searchable"] = int(store_stats.get("knowledge_cards_searchable", 0) or 0)
                stats["knowledge_cards_unsearchable"] = int(store_stats.get("knowledge_cards_unsearchable", 0) or 0)
                stats["total_words"] = int(store_stats.get("total_words", 0) or 0)
            if hasattr(store, "get_review_event_stats"):
                review_stats = store.get_review_event_stats()
                for key, value in review_stats.items():
                    stats[key] = int(value or 0)
            stats["paragraph_count"] = int(stats.get("paragraph_count", stats.get("paragraphs", 0)) or 0)
            stats["entity_count"] = int(stats.get("entity_count", stats.get("entities", 0)) or 0)
            stats["relation_count"] = int(stats.get("relation_count", stats.get("relations", 0)) or 0)
            stats["episode_count"] = int(stats.get("episode_count", stats.get("episodes", 0)) or 0)
            stats["card_count"] = int(stats.get("knowledge_cards_total", 0) or 0)
            stats["searchable_card_count"] = int(stats.get("knowledge_cards_searchable", 0) or 0)
            stats["unsearchable_card_count"] = int(stats.get("knowledge_cards_unsearchable", 0) or 0)
            stats["approved_count"] = int(stats.get("knowledge_cards_approved", 0) or 0)
            stats["pending_count"] = int(stats.get("knowledge_cards_pending", 0) or 0)
            stats["needs_answer_count"] = int(stats.get("knowledge_cards_needs_answer", 0) or 0)
            stats["rejected_count"] = int(stats.get("knowledge_cards_rejected", 0) or 0)
            stats["ai_rejected_count"] = int(stats.get("knowledge_cards_ai_rejected", 0) or 0)
            stats["auto_review_today"] = int(stats.get("auto_review_today", 0) or 0)
            stats["ai_review_today"] = int(stats.get("ai_review_today", 0) or 0)
            stats["ai_review_approved_today"] = int(stats.get("ai_review_approved_today", 0) or 0)
            stats["ai_review_needs_answer_today"] = int(stats.get("ai_review_needs_answer_today", 0) or 0)
            stats["ai_review_rejected_today"] = int(stats.get("ai_review_rejected_today", 0) or 0)
            stats["ai_review_error_today"] = int(stats.get("ai_review_error_today", 0) or 0)
            stats["auto_review_24h"] = int(stats.get("auto_review_24h", 0) or 0)
            stats["ai_review_24h"] = int(stats.get("ai_review_24h", 0) or 0)
            stats["ai_review_approved_24h"] = int(stats.get("ai_review_approved_24h", 0) or 0)
            stats["ai_review_needs_answer_24h"] = int(stats.get("ai_review_needs_answer_24h", 0) or 0)
            stats["ai_review_rejected_24h"] = int(stats.get("ai_review_rejected_24h", 0) or 0)
            stats["ai_review_error_24h"] = int(stats.get("ai_review_error_24h", 0) or 0)
            stats["auto_review_total"] = int(stats.get("auto_review_total", 0) or 0)
            stats["ai_review_total"] = int(stats.get("ai_review_total", 0) or 0)
            stats["ai_review_approved_total"] = int(stats.get("ai_review_approved_total", 0) or 0)
            stats["ai_review_needs_answer_total"] = int(stats.get("ai_review_needs_answer_total", 0) or 0)
            stats["ai_review_rejected_total"] = int(stats.get("ai_review_rejected_total", 0) or 0)
            stats["ai_review_error_total"] = int(stats.get("ai_review_error_total", 0) or 0)
            stats["node_count"] = graph_node_count or int(stats.get("entity_count", 0) or 0)
            stats["edge_count"] = graph_edge_count or int(stats.get("relation_count", 0) or 0)
            try:
                stats["total_embeddings"] = int(len(kernel.vector_store)) if kernel.vector_store is not None else 0
            except Exception:
                stats["total_embeddings"] = 0
        return web.json_response(stats)

    # ==================== 搜索 ====================

    async def _search(self, request: web.Request) -> web.Response:
        from .kernel.core.runtime.sdk_memory_kernel import KernelSearchRequest

        payload = await self._json(request)
        query = str(payload.get("query", "") or "").strip()
        if len(query) > 500:
            return self._error_response("搜索内容过长，请控制在 500 字以内", status=400)
        kernel = await self._kernel()
        requested_limit = self._int_value(payload.get("limit", 8), 8, minimum=1, maximum=200)
        internal_limit = min(200, max(requested_limit, requested_limit * 4))
        result = await kernel.search_memory(
            KernelSearchRequest(
                query=query,
                mode=str(payload.get("mode", "aggregate") or "aggregate"),
                limit=internal_limit,
                chat_id=str(payload.get("chat_id", "") or ""),
                time_start=payload.get("time_start"),
                time_end=payload.get("time_end"),
            )
        )
        store = kernel.metadata_store
        if store is not None:
            result = self._decorate_search_result(store, result)
            result = self._rank_search_result(query, result)
            result = self._trim_search_result(result, requested_limit)
            result = self._refresh_search_summary(result)
        return web.json_response(result)

    async def _qa_bridge_search(self, request: web.Request) -> web.Response:
        """供 bs-plugin /QA 命令使用的轻量搜索桥。

        - 只允许 loopback 调用
        - 配置了 ``web.qa_bridge_token`` 时强制 Bearer 校验
        - 不需要登录态；复用 ``_search`` 的检索流水线
        """

        from .kernel.core.runtime.sdk_memory_kernel import KernelSearchRequest

        if not self._is_loopback_request(request):
            return self._error_response("qa-bridge 仅允许本机调用", status=403)
        if self._qa_bridge_token:
            auth = str(request.headers.get("Authorization", "") or "").strip()
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            token = token or str(request.headers.get("X-GameKnowledge-Token", "") or "").strip()
            if token != self._qa_bridge_token:
                return self._error_response("qa-bridge 鉴权失败", status=401)

        payload = await self._json(request)
        query = str(payload.get("query", "") or "").strip()
        if not query:
            return self._error_response("query 不能为空", status=400)
        if len(query) > 500:
            return self._error_response("搜索内容过长，请控制在 500 字以内", status=400)

        requested_limit = self._int_value(payload.get("limit", 12), 12, minimum=1, maximum=20)
        internal_limit = min(200, max(requested_limit, requested_limit * 4))
        kernel = await self._kernel()
        result = await kernel.search_memory(
            KernelSearchRequest(
                query=query,
                mode=str(payload.get("mode", "aggregate") or "aggregate"),
                limit=internal_limit,
                chat_id=str(payload.get("chat_id", "") or ""),
            )
        )
        store = kernel.metadata_store
        if store is not None:
            result = self._decorate_search_result(store, result)
            result = self._rank_search_result(query, result)
            result = self._trim_search_result(result, requested_limit)
            result = self._refresh_search_summary(result)
        return web.json_response(result)

    @staticmethod
    def _is_loopback_request(request: web.Request) -> bool:
        peer = request.transport.get_extra_info("peername") if request.transport else None
        host = str(peer[0]).replace("::ffff:", "") if isinstance(peer, tuple) and peer else ""
        return host in {"127.0.0.1", "::1", "localhost"}

    async def _random_search(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        limit = self._int_query(request, "limit", 12, minimum=1, maximum=200)
        cards = store.random_knowledge_cards(limit=limit, status="approved")
        cards = self._decorate_knowledge_cards(store, cards)
        hits = [self._card_to_search_hit(card, index) for index, card in enumerate(cards)]
        return web.json_response({
            "success": True,
            "summary": f"随机抽取 {len(hits)} 条已通过知识",
            "hits": hits,
            "count": len(hits),
            "random": True,
        })

    @staticmethod
    def _card_to_search_hit(card: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
        text_parts = []
        title = str(card.get("title", "") or "").strip()
        question = str(card.get("question", "") or "").strip()
        answer = str(card.get("answer", "") or "").strip()
        if title:
            text_parts.append(title)
        if question:
            text_parts.append(f"Q: {question}")
        if answer:
            text_parts.append(f"A: {answer}")
        tags = card.get("tags", [])
        if isinstance(tags, list) and tags:
            text_parts.append("标签: " + " ".join(str(tag).strip() for tag in tags if str(tag).strip()))
        search_terms = card.get("search_terms", [])
        aliases = card.get("aliases", [])
        if isinstance(search_terms, list) and search_terms:
            text_parts.insert(0, "关键词: " + " ".join(str(item).strip() for item in search_terms if str(item).strip()))
        if isinstance(aliases, list) and aliases:
            text_parts.insert(0, "别名: " + " ".join(str(item).strip() for item in aliases if str(item).strip()))
        evidence = str(card.get("evidence", "") or "").strip()
        if evidence:
            text_parts.append(f"证据: {evidence}")
        paragraph_hash = str(card.get("paragraph_hash", "") or "").strip()
        card_hash = str(card.get("card_hash", "") or "").strip()
        metadata = {
            "title": title,
            "question": question,
            "category": card.get("category", ""),
            "platform": card.get("platform", ""),
            "source_platform": card.get("source_platform", "") or card.get("platform", ""),
            "rlcraft_version": card.get("rlcraft_version", ""),
            "answer_type": card.get("answer_type", "other"),
            "valid_status": card.get("valid_status", "active"),
            "search_terms": search_terms if isinstance(search_terms, list) else [],
            "aliases": aliases if isinstance(aliases, list) else [],
            "tags": tags if isinstance(tags, list) else [],
            "evidence": evidence,
            "source_group_id": card.get("source_group_id", ""),
            "source_group_name": card.get("source_group_name", ""),
            "source_stream_id": card.get("source_stream_id", ""),
            "paragraph_hash": paragraph_hash,
            "card_hash": card_hash,
            "created_at": card.get("created_at"),
            "reviewed_by": card.get("reviewed_by", ""),
            "reviewed_by_name": card.get("reviewed_by_name", ""),
            "edit_count": int(card.get("edit_count", 0) or 0),
        }
        return {
            "hash": paragraph_hash or card_hash or str(card.get("id", "")),
            "id": paragraph_hash or card_hash or str(card.get("id", "")),
            "type": "random_card",
            "source": "random_approved_card",
            "score": max(0.0, float(card.get("confidence", 0.0) or 0.0)) + (index * 0.000001),
            "content": "\n".join(text_parts).strip(),
            "title": title,
            "metadata": metadata,
        }

    @staticmethod
    def _decorate_knowledge_cards(store: Any, cards: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        if not cards:
            return cards
        decorated = [dict(card) for card in cards]
        card_ids = []
        reviewer_ids = set()
        for card in decorated:
            try:
                card_ids.append(int(card.get("id") or 0))
            except (TypeError, ValueError):
                pass
            reviewed_by = str(card.get("reviewed_by", "") or "").strip()
            if reviewed_by:
                reviewer_ids.add(reviewed_by)

        edit_counts: Dict[int, int] = {}
        if hasattr(store, "get_knowledge_card_edit_counts"):
            edit_counts = store.get_knowledge_card_edit_counts(card_ids)

        reviewer_names: Dict[str, str] = {}
        try:
            cursor = store._conn.cursor()
            if reviewer_ids:
                placeholders = ", ".join("?" for _ in reviewer_ids)
                cursor.execute(
                    f"""
                    SELECT id, username, display_name
                    FROM game_knowledge_users
                    WHERE id IN ({placeholders})
                    """,
                    list(reviewer_ids),
                )
                for row in cursor.fetchall():
                    reviewer_names[str(row["id"])] = str(row["display_name"] or row["username"] or row["id"])
        except Exception:
            reviewer_names = {}

        # 收集所有相似候选的 ID，批量查它们的当前 review_status，避免缓存的旧状态把已拒绝的候选又渲染回来
        similar_candidate_ids: list[int] = []
        for card in decorated:
            similar = card.get("similar_cards")
            if isinstance(similar, list):
                for item in similar:
                    if not isinstance(item, dict):
                        continue
                    try:
                        similar_candidate_ids.append(int(item.get("id") or 0))
                    except (TypeError, ValueError):
                        pass
        status_map: Dict[int, str] = {}
        if similar_candidate_ids and hasattr(store, "fetch_knowledge_card_statuses"):
            try:
                status_map = store.fetch_knowledge_card_statuses(similar_candidate_ids)
            except Exception:
                status_map = {}

        for card in decorated:
            try:
                card_id = int(card.get("id") or 0)
            except (TypeError, ValueError):
                card_id = 0
            reviewed_by = str(card.get("reviewed_by", "") or "").strip()
            card["edit_count"] = int(edit_counts.get(card_id, 0) or 0)
            card["reviewed_by_name"] = reviewer_names.get(reviewed_by, reviewed_by)
            similar = card.get("similar_cards")
            if isinstance(similar, list):
                refreshed: list[Dict[str, Any]] = []
                for item in similar:
                    if not isinstance(item, dict):
                        continue
                    try:
                        sid = int(item.get("id") or 0)
                    except (TypeError, ValueError):
                        sid = 0
                    # 用 DB 最新状态覆盖写入时的缓存状态，让工作台准确反映候选当前的处置情况
                    current_status = status_map.get(sid, str(item.get("review_status", "") or "")).strip().lower()
                    new_item = dict(item)
                    if current_status:
                        new_item["review_status"] = current_status
                    refreshed.append(new_item)
                card["similar_cards"] = refreshed
        return decorated

    def _decorate_search_result(self, store: Any, result: Any) -> Any:
        if not isinstance(result, dict):
            return result
        hits = result.get("hits")
        if not isinstance(hits, list):
            hits = result.get("results")
        if not isinstance(hits, list):
            return result

        tokens_by_hit_index: Dict[int, str] = {}
        for index, hit in enumerate(hits):
            if not isinstance(hit, dict):
                continue
            token = self._search_hit_token(hit)
            if not token:
                continue
            tokens_by_hit_index[index] = token

        cards_by_token = self._knowledge_cards_by_tokens(store, list(tokens_by_hit_index.values()))
        cards_by_hit_index: Dict[int, Dict[str, Any]] = {}
        for index, token in tokens_by_hit_index.items():
            card = cards_by_token.get(token)
            if card:
                cards_by_hit_index[index] = card

        decorated_cards = self._decorate_knowledge_cards(store, list(cards_by_hit_index.values()))
        decorated_by_id = {str(card.get("id")): card for card in decorated_cards}
        for index, card in cards_by_hit_index.items():
            decorated_card = decorated_by_id.get(str(card.get("id")), card)
            hit = dict(hits[index])
            metadata = dict(hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {})
            metadata.update({
                "card_id": decorated_card.get("id"),
                "card_hash": decorated_card.get("card_hash", metadata.get("card_hash", "")),
                "title": decorated_card.get("title", metadata.get("title", "")),
                "question": decorated_card.get("question", metadata.get("question", "")),
                "answer": decorated_card.get("answer", metadata.get("answer", "")),
                "reviewed_by": decorated_card.get("reviewed_by", ""),
                "reviewed_by_name": decorated_card.get("reviewed_by_name", ""),
                "edit_count": int(decorated_card.get("edit_count", 0) or 0),
                "review_status": decorated_card.get("review_status", metadata.get("review_status", "")),
                "category": decorated_card.get("category", metadata.get("category", "")),
                "source_platform": decorated_card.get("source_platform", metadata.get("source_platform", "")),
                "rlcraft_version": decorated_card.get("rlcraft_version", metadata.get("rlcraft_version", "")),
                "answer_type": decorated_card.get("answer_type", metadata.get("answer_type", "other")),
                "valid_status": decorated_card.get("valid_status", metadata.get("valid_status", "active")),
                "search_terms": decorated_card.get("search_terms", metadata.get("search_terms", [])),
                "aliases": decorated_card.get("aliases", metadata.get("aliases", [])),
                "tags": decorated_card.get("tags", metadata.get("tags", [])),
            })
            hit["metadata"] = metadata
            hit["edit_count"] = metadata["edit_count"]
            hits[index] = hit
        return result

    def _rank_search_result(self, query: str, result: Any) -> Any:
        if not isinstance(result, dict):
            return result
        hits = result.get("hits")
        hit_key = "hits"
        if not isinstance(hits, list):
            hits = result.get("results")
            hit_key = "results"
        if not isinstance(hits, list) or not hits:
            return result
        query_text = str(query or "").strip().lower()
        query_compact = "".join(query_text.split())

        def list_values(value: Any) -> list[str]:
            if isinstance(value, list):
                return [str(item or "").strip().lower() for item in value if str(item or "").strip()]
            text = str(value or "").strip().lower()
            return [text] if text else []

        def numeric(hit: Any) -> float:
            try:
                return float(hit.get("score", 0.0) or 0.0) if isinstance(hit, dict) else 0.0
            except (TypeError, ValueError):
                return 0.0

        def priority(hit: Any) -> tuple[float, int]:
            if not isinstance(hit, dict):
                return (0.0, 0)
            metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            bonus = 0
            review_status = str(metadata.get("review_status", "") or "").strip().lower()
            valid_status = str(metadata.get("valid_status", "active") or "active").strip().lower()
            if review_status == "approved":
                bonus += 8
            if valid_status == "active":
                bonus += 3
            elif valid_status in {"stale", "deprecated"}:
                bonus -= 4
            elif valid_status == "conflict":
                bonus -= 2
            fields = [
                str(metadata.get("question", "") or ""),
                str(metadata.get("title", "") or ""),
                str(hit.get("title", "") or ""),
                str(hit.get("content", "") or ""),
            ]
            exact_terms = 0
            for value in list_values(metadata.get("search_terms")) + list_values(metadata.get("aliases")):
                compact_value = value.replace(" ", "")
                if value and (value == query_text or (query_compact and compact_value == query_compact)):
                    exact_terms += 1
                elif value and (value in query_text or query_text in value or (query_compact and (compact_value in query_compact or query_compact in compact_value))):
                    bonus += 6
            bonus += min(18, exact_terms * 9)
            for value in fields:
                lowered = value.lower()
                compact = "".join(lowered.split())
                if query_text and (query_text == lowered.strip() or query_compact == compact):
                    bonus += 12
                    break
                if query_text and (query_text in lowered or query_compact in compact):
                    bonus += 5
                    break
            return (numeric(hit) + bonus, bonus)

        ranked = sorted(enumerate(hits), key=lambda item: (priority(item[1]), -item[0]), reverse=True)
        for _, hit in ranked:
            if not isinstance(hit, dict):
                continue
            final_score, rank_bonus = priority(hit)
            hit["rank_score"] = round(final_score, 4)
            metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            metadata["rank_score"] = round(final_score, 4)
            metadata["rank_bonus"] = int(rank_bonus)
            hit["metadata"] = metadata
        result[hit_key] = [item for _, item in ranked]
        return result

    @staticmethod
    def _refresh_search_summary(result: Any) -> Any:
        if not isinstance(result, dict):
            return result
        hits = result.get("hits")
        if not isinstance(hits, list):
            hits = result.get("results")
        if not isinstance(hits, list) or not hits:
            result["summary"] = ""
            return result
        lines = []
        for index, item in enumerate(hits[:5], start=1):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "") or item.get("title", "") or "").strip()
            content = re.sub(r"\s+", " ", content)
            if content:
                lines.append(f"{index}. {(content[:120] + '...') if len(content) > 120 else content}")
        result["summary"] = "\n".join(lines)
        return result

    @staticmethod
    def _trim_search_result(result: Any, limit: int) -> Any:
        if not isinstance(result, dict):
            return result
        hits = result.get("hits")
        hit_key = "hits"
        if not isinstance(hits, list):
            hits = result.get("results")
            hit_key = "results"
        if not isinstance(hits, list):
            return result
        safe_limit = max(1, int(limit or 8))
        result[hit_key] = hits[:safe_limit]
        result["count"] = len(result[hit_key])
        return result

    @staticmethod
    def _search_hit_token(hit: Dict[str, Any]) -> str:
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        return str(
            hit.get("paragraph_hash")
            or metadata.get("paragraph_hash")
            or metadata.get("paragraph_id")
            or hit.get("hash")
            or hit.get("id")
            or hit.get("hash_value")
            or metadata.get("hash")
            or metadata.get("card_hash")
            or ""
        ).strip()

    @staticmethod
    def _knowledge_cards_by_tokens(store: Any, tokens: list[str]) -> Dict[str, Dict[str, Any]]:
        unique_tokens = [token for token in dict.fromkeys(str(item or "").strip() for item in tokens) if token]
        if not unique_tokens:
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        try:
            cursor = store._conn.cursor()
            placeholders = ", ".join("?" for _ in unique_tokens)
            numeric_tokens = [int(token) for token in unique_tokens if token.isdigit()]
            id_clause = ""
            params: list[Any] = [*unique_tokens, *unique_tokens]
            if numeric_tokens:
                id_placeholders = ", ".join("?" for _ in numeric_tokens)
                id_clause = f" OR id IN ({id_placeholders})"
                params.extend(numeric_tokens)
            cursor.execute(
                f"""
                SELECT *
                FROM game_knowledge_cards
                WHERE paragraph_hash IN ({placeholders}) OR card_hash IN ({placeholders}){id_clause}
                """,
                params,
            )
            for row in cursor.fetchall():
                card = store._knowledge_card_row_to_dict(row)
                for key in (
                    str(card.get("paragraph_hash", "") or "").strip(),
                    str(card.get("card_hash", "") or "").strip(),
                    str(card.get("id", "") or "").strip(),
                ):
                    if key:
                        result.setdefault(key, card)
        except Exception as exc:
            logger.warning(f"批量装饰检索结果失败: {exc}")

        remaining = [t for t in unique_tokens if t not in result]
        if remaining:
            try:
                cursor = store._conn.cursor()
                placeholders = ", ".join("?" for _ in remaining)
                numeric_remaining = [int(t) for t in remaining if t.isdigit()]
                id_clause = ""
                params: list[Any] = [*remaining, *remaining]
                if numeric_remaining:
                    id_placeholders = ", ".join("?" for _ in numeric_remaining)
                    id_clause = f" OR id IN ({id_placeholders})"
                    params.extend(numeric_remaining)
                cursor.execute(
                    f"""
                    SELECT *
                    FROM game_knowledge_cards
                    WHERE paragraph_hash IN ({placeholders}) OR card_hash IN ({placeholders}){id_clause}
                    """,
                    params,
                )
                for row in cursor.fetchall():
                    card = store._knowledge_card_row_to_dict(row)
                    for key in (
                        str(card.get("paragraph_hash", "") or "").strip(),
                        str(card.get("card_hash", "") or "").strip(),
                        str(card.get("id", "") or "").strip(),
                    ):
                        if key and key not in result:
                            result[key] = card
            except Exception:
                pass

        return result

    async def _get_search_hit_card(self, request: web.Request) -> web.Response:
        hit_hash = str(request.match_info.get("hash", "") or "").strip()
        if not hit_hash:
            return self._error_response("hash 不能为空")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        card = store.get_knowledge_card_by_paragraph_hash(hit_hash)
        if card is None:
            return self._error_response("未找到对应知识卡片", status=404)
        card = self._decorate_knowledge_cards(store, [card])[0]
        return web.json_response({"success": True, "card": card})

    async def _question_search_hit(self, request: web.Request) -> web.Response:
        hit_hash = str(request.match_info.get("hash", "") or "").strip()
        if not hit_hash:
            return self._error_response("hash 不能为空")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        payload = await self._json(request)
        user = self._current_user(request)
        actor_id = str(user.get("id", "") or "")
        actor_name = self._actor_name(user)
        doubt = str(payload.get("question") or payload.get("doubt") or payload.get("reason") or "").strip()
        if not doubt:
            return self._error_response("疑问内容不能为空", status=400)

        base_card = store.get_knowledge_card_by_paragraph_hash(hit_hash)
        paragraph = None
        if base_card is None:
            paragraph = store.get_paragraph(hit_hash)
            if not paragraph or bool(paragraph.get("is_deleted", 0)):
                return self._error_response("未找到可提疑问的检索结果", status=404)
            base_payload = dict(payload)
            base_payload.pop("question", None)
            base_payload.pop("doubt", None)
            base_payload.pop("reason", None)
            base_card = GameKnowledgeRevisionService.build_card_from_search_hit(hit_hash, paragraph, base_payload)

        now = time.time()
        base_id = int(base_card.get("id", 0) or 0) if isinstance(base_card, dict) else 0
        if base_id > 0 and hasattr(store, "find_pending_question_of"):
            existing_question = store.find_pending_question_of(base_id)
            if existing_question is not None:
                updated_card = store.append_question_doubt(
                    int(existing_question.get("id", 0) or 0),
                    actor_id=actor_id,
                    actor_name=actor_name,
                    doubt=doubt,
                    source_hash=hit_hash,
                )
                if updated_card is not None:
                    if hasattr(store, "record_knowledge_card_history"):
                        store.record_knowledge_card_history(
                            card_id=int(updated_card.get("id", 0) or 0),
                            base_card_id=base_id,
                            action="question_doubter_appended",
                            actor_id=actor_id,
                            actor_name=actor_name,
                            before=existing_question,
                            after=updated_card,
                        )
                    return web.json_response({
                        "success": True,
                        "mode": "question_appended",
                        "card": self._decorate_knowledge_cards(store, [updated_card])[0],
                        "message": "已合并到现有疑问卡片，新增一名疑问人",
                    })
        title = str(payload.get("title") or base_card.get("title") or base_card.get("question") or "检索结果疑问").strip()
        original_question = str(base_card.get("question", "") or "").strip()
        original_answer = str(base_card.get("answer", "") or "").strip()
        question = original_question or title
        evidence_parts = [
            str(base_card.get("evidence", "") or "").strip(),
            f"疑问人: {actor_name or actor_id or '未知用户'}",
            f"疑问理由: {doubt}",
            f"来源检索: {hit_hash}",
        ]
        if original_answer:
            evidence_parts.append(f"原答案摘要: {original_answer[:500]}")
        draft = {
            "card_hash": f"question:{hit_hash}:{actor_id or 'anonymous'}:{int(now * 1000)}",
            "title": title,
            "category": str(payload.get("category") or base_card.get("category") or "其他"),
            "question": question,
            "answer": "",
            "steps": [],
            "tags": ["疑问", "待回答"],
            "search_terms": base_card.get("search_terms", []) if isinstance(base_card.get("search_terms"), list) else [],
            "aliases": base_card.get("aliases", []) if isinstance(base_card.get("aliases"), list) else [],
            "game_id": str(base_card.get("game_id", "") or ""),
            "version": str(base_card.get("version", "") or ""),
            "platform": str(base_card.get("platform", "") or ""),
            "source_platform": str(base_card.get("source_platform") or base_card.get("platform") or ""),
            "rlcraft_version": str(base_card.get("rlcraft_version", "") or ""),
            "answer_type": str(base_card.get("answer_type", "") or "other"),
            "valid_status": "active",
            "confidence": 1.0,
            "review_status": "needs_answer",
            "source_stream_id": str(base_card.get("source_stream_id") or ""),
            "source_group_id": str(base_card.get("source_group_id") or ""),
            "source_group_name": str(base_card.get("source_group_name") or ""),
            "evidence": "\n".join(item for item in evidence_parts if item),
            "paragraph_hash": "",
            "ai_review_status": "manual_question",
            "ai_review_reason": doubt,
            "ai_review_score": 1.0,
            "created_at": now,
            "updated_at": now,
            "created_by": actor_id,
            "updated_by": actor_id,
            "last_editor_id": actor_id,
            "last_editor_name": actor_name,
            "revision_of_card_id": base_id or None,
            "revision_reason": f"用户疑问: {doubt}",
        }
        card = store.upsert_knowledge_card(draft)
        if hasattr(store, "record_knowledge_card_history"):
            store.record_knowledge_card_history(
                card_id=int(card.get("id", 0) or 0),
                base_card_id=base_id,
                action="question_from_search",
                actor_id=actor_id,
                actor_name=actor_name,
                before=base_card if isinstance(base_card, dict) else paragraph,
                after=card,
            )
        return web.json_response({
            "success": True,
            "mode": "question",
            "card": self._decorate_knowledge_cards(store, [card])[0] if card else card,
            "message": "已提交疑问，进入审核队列疑问分组",
        })

    async def _update_search_hit(self, request: web.Request) -> web.Response:
        hit_hash = str(request.match_info.get("hash", "") or "").strip()
        if not hit_hash:
            return self._error_response("hash 不能为空")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        payload = await self._json(request)
        user = self._current_user(request)
        try:
            result = GameKnowledgeRevisionService(store=store).revise_target(
                hit_hash,
                payload,
                actor_id=str(user.get("id", "") or ""),
                actor_name=self._actor_name(user),
            )
            if not result.get("success", False):
                return self._error_response(str(result.get("error", "保存卡片失败")), status=int(result.get("status", 500) or 500))
            if result.get("mode") == "created_from_paragraph":
                result = {**result, "mode": "revision"}
            return web.json_response(result)
        except ValueError as exc:
            return self._error_response(str(exc), status=400)

    async def _delete_search_hit(self, request: web.Request) -> web.Response:
        hit_hash = str(request.match_info.get("hash", "") or "").strip()
        if not hit_hash:
            return self._error_response("hash 不能为空")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)

        delete_result = await kernel.memory_delete_admin(
            action="execute",
            mode="paragraph",
            selector={"hashes": [hit_hash]},
            reason="webui_search_hit_delete",
            requested_by=str(self._current_user(request).get("id", "") or "webui"),
        )
        if not delete_result.get("success"):
            error = str(delete_result.get("error", "") or "删除失败")
            status = 404 if "未命中" in error else 500
            return self._error_response(error, status=status)

        card = store.get_knowledge_card_by_paragraph_hash(hit_hash)
        deleted_card = False
        if card is not None:
            try:
                deleted_card = store.delete_knowledge_card(int(card.get("id", 0) or 0))
            except ValueError:
                deleted_card = False
        return web.json_response({"success": True, "deleted_card": deleted_card, "delete_result": delete_result})

    # ==================== 写入 ====================

    async def _ingest(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        kernel = await self._kernel()
        metadata: Dict[str, Any] = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata.setdefault("domain", "game_knowledge")
        metadata.setdefault("created_by", str(self._current_user(request).get("id", "") or "webui"))
        result = await kernel.ingest_text(
            external_id=str(payload.get("external_id", "") or ""),
            source_type=str(payload.get("source_type", "game_knowledge") or "game_knowledge"),
            text=str(payload.get("text", "") or ""),
            chat_id=str(payload.get("chat_id", "") or ""),
            tags=list(payload.get("tags") or ["game_knowledge"]),
            metadata=metadata,
            relations=list(payload.get("relations") or []),
            entities=list(payload.get("entities") or []),
        )
        return web.json_response(result)

    async def _ingest_upload(self, request: web.Request) -> web.Response:
        """接收 multipart/form-data 文件上传，逐个调用 ingest_text"""
        import json as _json

        try:
            reader = await request.multipart()
        except Exception:
            return web.json_response({"success": False, "error": "请求不是 multipart/form-data 格式"}, status=400)

        kernel = await self._kernel()
        files_content: list[tuple[str, str]] = []  # (filename, text)
        tags: list[str] = ["game_knowledge"]
        metadata: Dict[str, Any] = {"domain": "game_knowledge"}

        while True:
            part = await reader.next()
            if part is None:
                break
            field_name = part.name or ""
            if field_name == "files":
                filename = part.filename or "unknown"
                text = await part.text()
                files_content.append((filename, text))
            elif field_name == "tags":
                try:
                    tags = _json.loads(await part.text())
                except Exception:
                    pass
            elif field_name == "metadata":
                try:
                    extra = _json.loads(await part.text())
                    if isinstance(extra, dict):
                        metadata.update(extra)
                except Exception:
                    pass

        if not files_content:
            return web.json_response({"success": False, "error": "未接收到任何文件"}, status=400)

        results: list[Dict[str, Any]] = []
        for filename, text in files_content:
            res = await kernel.ingest_text(
                external_id=f"upload:{filename}",
                source_type="game_knowledge",
                text=text,
                chat_id="",
                tags=tags,
                metadata={**metadata, "source_file": filename},
                relations=[],
                entities=[],
            )
            results.append({"file": filename, "size": len(text), **res})

        return web.json_response({"success": True, "files_processed": len(results), "results": results})

    # ==================== 导入任务管理 ====================

    async def _import_settings(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_import_admin(action="settings"))

    async def _import_list_tasks(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        return web.json_response(await kernel.memory_import_admin(action="list", limit=limit))

    async def _import_get_task(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        task_id = str(request.match_info.get("task_id", "") or "")
        include_chunks = request.query.get("include_chunks", "false").lower() in ("1", "true", "yes")
        return web.json_response(await kernel.memory_import_admin(
            action="get", task_id=task_id, include_chunks=include_chunks,
        ))

    async def _import_get_files(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        task_id = str(request.query.get("task_id", "") or "")
        return web.json_response(await kernel.memory_import_admin(action="get_files", task_id=task_id))

    async def _import_get_chunks(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        task_id = str(request.query.get("task_id", "") or "")
        file_id = str(request.query.get("file_id", "") or "")
        offset = self._int_query(request, "offset", 0, minimum=0)
        limit = self._int_query(request, "limit", 30, minimum=1, maximum=200)
        return web.json_response(await kernel.memory_import_admin(
            action="get_chunks", task_id=task_id, file_id=file_id, offset=offset, limit=limit,
        ))

    async def _import_cancel(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        task_id = str(payload.get("task_id", "") or "")
        return web.json_response(await kernel.memory_import_admin(action="cancel", task_id=task_id))

    async def _import_retry(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        task_id = str(payload.get("task_id", "") or "")
        return web.json_response(await kernel.memory_import_admin(action="retry_failed", task_id=task_id))

    # ==================== 审核队列 ====================

    async def _list_cards(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        status = request.query.get("status", "")
        category = request.query.get("category", "")
        platform = request.query.get("platform", "")
        source_group_id = request.query.get("source_group_id", "")
        source_group_name = request.query.get("source_group_name", "")
        keyword = request.query.get("keyword", "")
        editor_scope = str(request.query.get("editor_scope", "exclude_self") or "exclude_self").strip()
        sort_by = str(request.query.get("sort_by", "updated_desc") or "updated_desc").strip()
        source_filter = str(request.query.get("source", "") or "").strip().lower()
        ai_review_status = ""
        if source_filter == "legacy_import":
            ai_review_status = "legacy_import_migration"
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        offset = self._int_query(request, "offset", 0, minimum=0)
        user = self._current_user(request)
        exclude_editor = ""
        only_editor = ""
        other_editor = ""
        user_id = str(user.get("id", "") or "")
        if editor_scope == "self":
            only_editor = user_id
        elif editor_scope == "others":
            other_editor = user_id
        elif editor_scope == "exclude_self" or (status.strip().lower() == "pending" and not self._user_has_permission(user, "*") and editor_scope != "all"):
            exclude_editor = str(user.get("id", "") or "")
        cards = store.list_knowledge_cards(
            status=status,
            category=category,
            platform=platform,
            source_group_id=source_group_id,
            source_group_name=source_group_name,
            keyword=keyword,
            exclude_last_editor_id=exclude_editor,
            only_last_editor_id=only_editor,
            require_other_editor_id=other_editor,
            ai_review_status=ai_review_status,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )
        cards = self._decorate_knowledge_cards(store, cards)
        return web.json_response({"success": True, "cards": cards, "count": len(cards)})

    async def _list_card_groups(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        limit = self._int_query(request, "limit", 200, minimum=1, maximum=1000)
        groups = store.list_knowledge_card_groups(limit=limit)
        return web.json_response({"success": True, "groups": groups, "count": len(groups)})

    async def _card_stats(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        raw = store.count_knowledge_cards_by_status()
        keys = ("pending", "needs_answer", "similar", "conflict", "processing", "approved", "rejected", "ai_rejected", "superseded")
        stats = {key: int(raw.get(key, 0)) for key in keys}
        total = sum(raw.values())
        return web.json_response({"success": True, "stats": stats, "total": total})

    async def _get_card(self, request: web.Request) -> web.Response:
        try:
            card_id = int(request.match_info.get("id", 0))
        except (TypeError, ValueError):
            return self._error_response("卡片ID必须是数字")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        card = store.get_knowledge_card_by_id(card_id)
        if not card:
            return self._error_response("卡片不存在", status=404)
        decorated = self._decorate_knowledge_cards(store, [card])[0]
        try:
            related = store.find_similar_knowledge_cards(card, limit=10, threshold=0.6, include_archived=True)
            archived_statuses = {"rejected", "superseded", "ai_rejected"}
            decorated["similar_history"] = [
                item for item in related
                if str(item.get("review_status", "") or "").lower() in archived_statuses
            ]
        except Exception as exc:
            logger.warning(f"查询卡片相似历史失败: card_id={card_id}, error={exc}")
            decorated["similar_history"] = []
        return web.json_response({"success": True, "card": decorated})

    async def _update_card(self, request: web.Request) -> web.Response:
        try:
            card_id = int(request.match_info.get("id", 0))
        except (TypeError, ValueError):
            return self._error_response("卡片ID必须是数字")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        payload = await self._json(request)
        user = self._current_user(request)
        expected_updated_at: Optional[float] = None
        raw_if = payload.pop("if_updated_at", None)
        if raw_if is None:
            raw_if = payload.pop("_etag_updated_at", None)
        if raw_if is not None:
            try:
                expected_updated_at = float(raw_if)
            except (TypeError, ValueError):
                expected_updated_at = None
        try:
            result = GameKnowledgeRevisionService(store=store).revise_card_id(
                card_id,
                payload,
                actor_id=str(user.get("id", "") or ""),
                actor_name=self._actor_name(user),
                expected_updated_at=expected_updated_at,
            )
            if not result.get("success", False):
                return self._error_response(str(result.get("error", "保存卡片失败")), status=int(result.get("status", 500) or 500))
            return web.json_response(result)
        except ValueError as exc:
            message = str(exc)
            if "已被他人修改" in message:
                status_code = 409
            elif "不能编辑" in message or "不能原地编辑" in message:
                status_code = 409
            else:
                status_code = 400
            return self._error_response(message, status=status_code)
        except Exception as exc:
            logger.exception(f"编辑卡片失败: card_id={card_id}")
            return self._error_response(f"保存卡片失败: {exc.__class__.__name__}: {exc}", status=500)

    async def _approve_card(self, request: web.Request) -> web.Response:
        try:
            card_id = int(request.match_info.get("id", 0))
        except (TypeError, ValueError):
            return self._error_response("卡片ID必须是数字")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)

        from .kernel.core.utils.review_queue_service import ReviewQueueService

        review_queue = ReviewQueueService(kernel=kernel)
        user = self._current_user(request)
        result = await review_queue.approve_card(
            card_id,
            reviewed_by=str(user.get("id", "") or "webui"),
            allow_self_review=self._user_has_permission(user, "*"),
            wait_for_ingest=False,
        )
        if result.get("success"):
            return web.json_response(result)
        if result.get("error") == "卡片不存在":
            return self._error_response("卡片不存在", status=404)
        error = str(result.get("error", "审核通过失败"))
        status = 409 if ("处理中" in error or "状态" in error or "占用" in error or "重复" in error) else 500
        return self._error_response(error, status=status)

    async def _reject_card(self, request: web.Request) -> web.Response:
        try:
            card_id = int(request.match_info.get("id", 0))
        except (TypeError, ValueError):
            return self._error_response("卡片ID必须是数字")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        from .kernel.core.utils.review_queue_service import ReviewQueueService

        user = self._current_user(request)
        result = await ReviewQueueService(kernel=kernel).reject_card(
            card_id,
            reviewed_by=str(user.get("id", "") or "webui"),
            allow_self_review=self._user_has_permission(user, "*"),
        )
        if result.get("success"):
            return web.json_response(result)
        if result.get("error") == "卡片不存在":
            return self._error_response("卡片不存在", status=404)
        error = str(result.get("error", "审核拒绝失败"))
        status = 409 if ("处理中" in error or "状态" in error or "占用" in error or "重复" in error) else 500
        return self._error_response(error, status=status)

    async def _question_card(self, request: web.Request) -> web.Response:
        try:
            card_id = int(request.match_info.get("id", 0))
        except (TypeError, ValueError):
            return self._error_response("卡片ID必须是数字")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        payload = await self._json(request)
        from .kernel.core.utils.review_queue_service import ReviewQueueService

        user = self._current_user(request)
        reason = str(payload.get("reason", "") or "").strip()
        result = await ReviewQueueService(kernel=kernel).question_card(
            card_id,
            reviewed_by=str(user.get("id", "") or "webui"),
            reviewer_name=self._actor_name(user),
            reason=reason,
            allow_self_review=self._user_has_permission(user, "*"),
        )
        if result.get("success"):
            return web.json_response(result)
        if result.get("error") == "卡片不存在":
            return self._error_response("卡片不存在", status=404)
        error = str(result.get("error", "置疑问失败"))
        status = 409 if ("处理中" in error or "状态" in error or "占用" in error or "已入库" in error) else 500
        return self._error_response(error, status=status)

    async def _merge_card(self, request: web.Request) -> web.Response:
        try:
            source_id = int(request.match_info.get("id", 0))
        except (TypeError, ValueError):
            return self._error_response("卡片ID必须是数字")
        payload = await self._json(request)
        try:
            target_id = int(payload.get("target_card_id") or payload.get("target_id") or 0)
        except (TypeError, ValueError):
            return self._error_response("target_card_id 必须是数字")
        if target_id <= 0:
            return self._error_response("target_card_id 必须是正整数")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        user = self._current_user(request)
        try:
            result = store.merge_knowledge_card_into(
                source_card_id=source_id,
                target_card_id=target_id,
                actor_id=str(user.get("id", "") or ""),
                actor_name=self._actor_name(user),
                reason=str(payload.get("reason", "") or ""),
            )
        except Exception as exc:
            logger.exception(f"合并卡片失败: source={source_id}, target={target_id}")
            return self._error_response(f"合并失败: {exc.__class__.__name__}: {exc}", status=500)
        if not result.get("success", False):
            error = str(result.get("error", "合并失败"))
            status = 404 if "不存在" in error else (409 if "状态" in error or "相同" in error else 400)
            return self._error_response(error, status=status)
        return web.json_response({**result, "message": f"已把 #{source_id} 合并到 #{target_id}"})

    async def _delete_card(self, request: web.Request) -> web.Response:
        try:
            card_id = int(request.match_info.get("id", 0))
        except (TypeError, ValueError):
            return self._error_response("卡片ID必须是数字")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        card = store.get_knowledge_card_by_id(card_id)
        if card is None:
            scrub = store.scrub_stale_similar_reference(card_id) if hasattr(store, "scrub_stale_similar_reference") else {"scrubbed_rows": 0}
            if scrub.get("scrubbed_rows", 0) > 0:
                return web.json_response({
                    "success": True,
                    "card_id": card_id,
                    "phantom": True,
                    "scrubbed": scrub,
                    "message": f"卡片已不在库中，已清理 {scrub['scrubbed_rows']} 处幻影引用",
                })
            return self._error_response("卡片不存在", status=404)
        if str(card.get("review_status", "") or "").strip().lower() == "approved":
            paragraph_hash = str(card.get("paragraph_hash", "") or "").strip()
            if not paragraph_hash:
                return self._error_response("已通过卡片缺少入库 paragraph_hash，无法删除入库知识", status=409)
            delete_result = await kernel.memory_delete_admin(
                action="execute",
                mode="paragraph",
                selector={"hashes": [paragraph_hash]},
                reason="webui_review_card_delete",
                requested_by=str(self._current_user(request).get("id", "") or "webui"),
            )
            if not delete_result.get("success"):
                return self._error_response(str(delete_result.get("error", "删除入库知识失败")), status=500)
            store.update_knowledge_card_status(
                card_id,
                "rejected",
                reviewed_by=str(self._current_user(request).get("id", "") or "webui"),
            )
            return web.json_response({"success": True, "card_id": card_id, "deleted_ingested": True, "delete_result": delete_result})
        try:
            ok = store.delete_knowledge_card(card_id)
        except ValueError as exc:
            return self._error_response(str(exc), status=409)
        return web.json_response({"success": ok, "card_id": card_id})

    async def _quality_tuning_cards(self, request: web.Request) -> web.Response:
        user = self._current_user(request)
        if "*" not in set(user.get("permissions") or []):
            return self._error_response("仅 admin 可查看随机调优", status=403)
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            return self._error_response("metadata_store 未就绪", status=503)
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        status = str(request.query.get("status", "") or "").strip().lower()
        conditions = ["ai_review_status IN ('tuning_approved', 'tuning_rejected', 'tuning_similar', 'tuning_needs_answer', 'tuning_error')"]
        params: list[Any] = []
        if status in {"approved", "ai_rejected", "similar", "needs_answer"}:
            conditions.append("review_status = ?")
            params.append(status)
        cursor = store._conn.cursor()
        cursor.execute(
            f"""
            SELECT *
            FROM game_knowledge_cards
            WHERE {' AND '.join(conditions)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        cards = [store._knowledge_card_row_to_dict(row) for row in cursor.fetchall()]
        cards = self._decorate_knowledge_cards(store, cards)
        return web.json_response({"success": True, "cards": cards, "count": len(cards)})

    async def _quality_tuning_tasks_list(self, request: web.Request) -> web.Response:
        user = self._current_user(request)
        if "*" not in set(user.get("permissions") or []):
            return self._error_response("仅 admin 可查看随机调优", status=403)
        limit = self._int_query(request, "limit", 20, minimum=1, maximum=100)
        async with self._quality_tuning_lock:
            task_snapshots = [dict(task) for task in self._quality_tuning_tasks.values()]
        tasks = [self._public_quality_tuning_task(task) for task in task_snapshots]
        tasks.sort(key=lambda item: float(item.get("created_at", 0) or 0), reverse=True)
        active = [task for task in tasks if task.get("status") in {"queued", "running"}]
        summary = {
            "queued": sum(1 for task in tasks if task.get("status") == "queued"),
            "running": sum(1 for task in tasks if task.get("status") == "running"),
            "completed": sum(1 for task in tasks if task.get("status") == "completed"),
            "failed": sum(1 for task in tasks if task.get("status") == "failed"),
        }
        return web.json_response({"success": True, "tasks": tasks[:limit], "active": active, "summary": summary})

    async def _quality_tuning_run(self, request: web.Request) -> web.Response:
        user = self._current_user(request)
        if "*" not in set(user.get("permissions") or []):
            return self._error_response("仅 admin 可执行随机调优", status=403)
        payload = await self._json(request)
        limit = self._int_value(payload.get("limit", 10), 10, minimum=1, maximum=50)
        task = await self._enqueue_quality_tuning_task(
            limit=limit,
            reviewer=str(user.get("id", "") or "admin"),
            reviewer_name=str(user.get("display_name") or user.get("username") or "admin"),
            task_name=str(payload.get("task_name", "") or "utils"),
        )
        return web.json_response({"success": True, "queued": True, "task": self._public_quality_tuning_task(task)})

    async def _enqueue_quality_tuning_task(self, *, limit: int, reviewer: str, reviewer_name: str, task_name: str) -> Dict[str, Any]:
        now = time.time()
        task = {
            "id": uuid.uuid4().hex[:12],
            "status": "queued",
            "limit": limit,
            "processed": 0,
            "total": 0,
            "counts": {"approved": 0, "similar": 0, "needs_answer": 0, "ai_rejected": 0, "error": 0},
            "results": [],
            "card_ids": [],
            "error": "",
            "reviewer": reviewer,
            "reviewer_name": reviewer_name,
            "task_name": task_name,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "updated_at": now,
        }
        async with self._quality_tuning_lock:
            self._quality_tuning_tasks[task["id"]] = task
            self._quality_tuning_queue.append(task["id"])
            self._trim_quality_tuning_tasks_locked()
            if self._quality_tuning_worker_task is None or self._quality_tuning_worker_task.done():
                self._quality_tuning_worker_task = asyncio.create_task(self._quality_tuning_worker())
        return task

    def _trim_quality_tuning_tasks_locked(self) -> None:
        if len(self._quality_tuning_tasks) <= 80:
            return
        finished = sorted(
            [
                (str(task.get("id", "")), float(task.get("created_at", 0) or 0))
                for task in self._quality_tuning_tasks.values()
                if task.get("status") in {"completed", "failed"}
            ],
            key=lambda item: item[1],
        )
        for task_id, _ in finished[: max(0, len(self._quality_tuning_tasks) - 80)]:
            self._quality_tuning_tasks.pop(task_id, None)

    @staticmethod
    def _public_quality_tuning_task(task: Dict[str, Any]) -> Dict[str, Any]:
        counts = dict(task.get("counts") or {})
        total = int(task.get("total", 0) or 0)
        processed = int(task.get("processed", 0) or 0)
        return {
            "id": task.get("id"),
            "status": task.get("status"),
            "limit": task.get("limit"),
            "processed": processed,
            "total": total,
            "progress": (processed / total) if total > 0 else (1 if task.get("status") == "completed" else 0),
            "counts": counts,
            "result_count": len(task.get("results") or []),
            "card_ids": list(task.get("card_ids") or []),
            "error": task.get("error") or "",
            "reviewer_name": task.get("reviewer_name") or "",
            "created_at": task.get("created_at"),
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "updated_at": task.get("updated_at"),
        }

    async def _quality_tuning_worker(self) -> None:
        while True:
            async with self._quality_tuning_lock:
                if not self._quality_tuning_queue:
                    return
                task_id = self._quality_tuning_queue.popleft()
                task = self._quality_tuning_tasks.get(task_id)
                if not task or task.get("status") != "queued":
                    continue
                task["status"] = "running"
                task["started_at"] = time.time()
                task["updated_at"] = task["started_at"]
            try:
                await self._run_quality_tuning_task(task_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"随机调优任务失败: task={task_id}, error={exc}")
                async with self._quality_tuning_lock:
                    task = self._quality_tuning_tasks.get(task_id)
                    if task:
                        task["status"] = "failed"
                        task["error"] = str(exc)
                        task["finished_at"] = time.time()
                        task["updated_at"] = task["finished_at"]

    async def _run_quality_tuning_task(self, task_id: str) -> None:
        async with self._quality_tuning_lock:
            task = self._quality_tuning_tasks.get(task_id)
            if not task:
                return
            limit = int(task.get("limit", 10) or 10)
            reviewer = str(task.get("reviewer") or "admin")
            task_name = str(task.get("task_name") or "utils")
        kernel = await self._kernel()
        store = kernel.metadata_store
        if store is None:
            raise RuntimeError("metadata_store 未就绪")
        cards = store.random_knowledge_cards(
            limit=limit,
            status="approved",
            prioritize_review_risk=True,
        )
        review_client = LLMServiceClient(task_name=task_name)
        async with self._quality_tuning_lock:
            task = self._quality_tuning_tasks.get(task_id)
            if task:
                task["total"] = len(cards)
                task["updated_at"] = time.time()
        counts = {"approved": 0, "similar": 0, "needs_answer": 0, "ai_rejected": 0, "error": 0}
        results: list[Dict[str, Any]] = []
        for card in cards:
            result = await self._quality_tune_one_card(store, card, review_client=review_client, reviewed_by=reviewer)
            status = str(result.get("status", "") or "error")
            counts[status if status in counts else "error"] += 1
            results.append(result)
            async with self._quality_tuning_lock:
                task = self._quality_tuning_tasks.get(task_id)
                if task:
                    task["processed"] = len(results)
                    task["counts"] = dict(counts)
                    task["results"] = list(results)
                    task["card_ids"] = [int(item.get("id", 0) or 0) for item in results if item.get("id")]
                    task["updated_at"] = time.time()
        if hasattr(store, "record_review_event") and results:
            try:
                for status, count in counts.items():
                    if count > 0:
                        store.record_review_event(
                            "ai_review",
                            status if status != "ai_rejected" else "rejected",
                            count=count,
                            source_stream_id="quality_tuning",
                        )
            except Exception as exc:
                logger.warning(f"记录随机调优统计失败: {exc}")
        async with self._quality_tuning_lock:
            task = self._quality_tuning_tasks.get(task_id)
            if task:
                task["status"] = "completed"
                task["processed"] = len(results)
                task["total"] = len(cards)
                task["counts"] = dict(counts)
                task["results"] = list(results)
                task["card_ids"] = [int(item.get("id", 0) or 0) for item in results if item.get("id")]
                task["finished_at"] = time.time()
                task["updated_at"] = task["finished_at"]

    async def _quality_tune_one_card(self, store: Any, card: Dict[str, Any], *, review_client: Any, reviewed_by: str) -> Dict[str, Any]:
        card_id = int(card.get("id", 0) or 0)
        try:
            ai_result = await self._quality_tuning_ai_review(card, review_client=review_client)
            similar_cards = store.find_similar_knowledge_cards(card, limit=5, threshold=0.72) if hasattr(store, "find_similar_knowledge_cards") else []
            approved = bool(ai_result.get("approved", False))
            now = time.time()
            if not approved and bool(ai_result.get("needs_answer", False)):
                review_status = "needs_answer"
                ai_status = "tuning_needs_answer"
            elif not approved:
                review_status = "ai_rejected"
                ai_status = "tuning_rejected"
            elif similar_cards:
                review_status = "similar"
                ai_status = "tuning_similar"
            else:
                review_status = "approved"
                ai_status = "tuning_approved"
            cursor = store._conn.cursor()
            cursor.execute(
                """
                UPDATE game_knowledge_cards
                SET review_status=?,
                    ai_review_status=?,
                    ai_review_reason=?,
                    ai_review_score=?,
                    ai_review_issues_json=?,
                    similar_cards_json=?,
                    reviewed_at=?,
                    reviewed_by=?,
                    updated_at=?
                WHERE id=? AND review_status='approved'
                """,
                (
                    review_status,
                    ai_status,
                    str(ai_result.get("reason", "") or ""),
                    float(ai_result.get("score", 0.0) or 0.0),
                    json.dumps(ai_result.get("issues", []) if isinstance(ai_result.get("issues"), list) else [], ensure_ascii=False),
                    json.dumps(similar_cards[:5], ensure_ascii=False),
                    now,
                    reviewed_by,
                    now,
                    card_id,
                ),
            )
            store._conn.commit()
            if review_status != "approved":
                old_hash = str(card.get("paragraph_hash", "") or "").strip()
                if old_hash:
                    try:
                        store.mark_as_deleted([old_hash], "paragraph")
                        if hasattr(store, "fts_delete_paragraph"):
                            store.fts_delete_paragraph(old_hash)
                    except Exception as exc:
                        logger.warning(f"随机调优移除未通过段落失败: card_id={card_id}, hash={old_hash}, error={exc}")
            return {
                "id": card_id,
                "title": card.get("title", ""),
                "status": review_status,
                "ai_review_status": ai_status,
                "similar_count": len(similar_cards),
                "reason": str(ai_result.get("reason", "") or ""),
            }
        except Exception as exc:
            logger.warning(f"随机调优卡片失败: id={card_id}, error={exc}")
            return {"id": card_id, "title": card.get("title", ""), "status": "error", "error": str(exc)}

    @staticmethod
    async def _quality_tuning_ai_review(card: Dict[str, Any], *, review_client: Any) -> Dict[str, Any]:
        raw = await review_client.generate_response(
            prompt=(
                f"{_AI_REVIEW_PROMPT}\n\n"
                "这是对已入库卡片的随机质量复审。不要改写内容，只判断是否仍适合保留在知识库。\n\n"
                f"卡片:\n{GameKnowledgeAnalyzer._format_review_card(card)}"
            ),
        )
        payload = GameKnowledgeAnalyzer._parse_llm_output(GameKnowledgeAnalyzer._llm_text(raw))
        if not isinstance(payload, dict) or "approved" not in payload:
            raise ValueError("AI 调优审核输出缺少 approved 字段")
        issues = payload.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)] if issues else []
        return {
            "approved": bool(payload.get("approved")),
            "needs_answer": bool(payload.get("needs_answer") or payload.get("question_worth_answering")),
            "reason": str(payload.get("reason", "") or "").strip(),
            "score": GameKnowledgeAnalyzer._parse_review_score(payload.get("score", 0.0)),
            "issues": [str(item).strip() for item in issues if str(item).strip()],
        }

    # ==================== 图谱 ====================

    async def _graph_get(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        limit = self._int_query(request, "limit", 200, minimum=1, maximum=5000)
        return web.json_response(await kernel.memory_graph_admin(action="get_graph", limit=limit))

    async def _graph_search(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        query = request.query.get("query", "")
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        return web.json_response(await kernel.memory_graph_admin(action="search", query=query, limit=limit))

    async def _graph_create_node(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(await kernel.memory_graph_admin(action="create_node", name=payload.get("name", "")))

    async def _graph_delete_node(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(await kernel.memory_graph_admin(action="delete_node", name=payload.get("name", "")))

    async def _graph_rename_node(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        old_name = str(payload.get("old_name") or payload.get("name") or "").strip()
        return web.json_response(
            await kernel.memory_graph_admin(action="rename_node", old_name=old_name, new_name=payload.get("new_name", ""))
        )

    async def _graph_create_edge(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        try:
            confidence = float(payload.get("confidence", payload.get("weight", 1.0)) or 1.0)
        except (TypeError, ValueError):
            confidence = 1.0
        return web.json_response(
            await kernel.memory_graph_admin(
                action="create_edge",
                subject=payload.get("subject", ""),
                predicate=payload.get("predicate", ""),
                object=payload.get("object", ""),
                confidence=confidence,
            )
        )

    async def _graph_delete_edge(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        kwargs: Dict[str, Any] = {}
        if payload.get("hash"):
            kwargs["hash"] = payload["hash"]
        if payload.get("subject"):
            kwargs["subject"] = payload["subject"]
        if payload.get("object"):
            kwargs["object"] = payload["object"]
        return web.json_response(await kernel.memory_graph_admin(action="delete_edge", **kwargs))

    # ==================== 来源 ====================

    async def _source_list(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_source_admin(action="list"))

    async def _source_delete(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(await kernel.memory_source_admin(action="delete", source=payload.get("source", "")))

    # ==================== 情景 ====================

    async def _episode_list(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        kwargs: Dict[str, Any] = {"action": "list"}
        query = request.query.get("query", "")
        if query:
            kwargs["query"] = query
        source = request.query.get("source", "")
        if source:
            kwargs["source"] = source
        person_id = request.query.get("person_id", "")
        if person_id:
            kwargs["person_id"] = person_id
        limit = self._int_query(request, "limit", 20, minimum=1, maximum=200)
        kwargs["limit"] = limit
        return web.json_response(await kernel.memory_episode_admin(**kwargs))

    async def _episode_status(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        limit = self._int_query(request, "limit", 20, minimum=1, maximum=200)
        return web.json_response(await kernel.memory_episode_admin(action="status", limit=limit))

    async def _episode_get(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        episode_id = request.match_info.get("episode_id", "")
        return web.json_response(await kernel.memory_episode_admin(action="get", episode_id=episode_id))

    async def _episode_delete(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        episode_id = request.match_info.get("episode_id", "")
        return web.json_response(await kernel.memory_episode_admin(action="delete", episode_id=episode_id))

    async def _episode_rebuild(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        kwargs: Dict[str, Any] = {"action": "rebuild"}
        if payload.get("all"):
            kwargs["all"] = True
        elif payload.get("source"):
            kwargs["source"] = payload["source"]
        elif payload.get("sources"):
            kwargs["sources"] = payload["sources"]
        return web.json_response(await kernel.memory_episode_admin(**kwargs))

    async def _episode_process_pending(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(
            await kernel.memory_episode_admin(
                action="process_pending",
                limit=self._int_value(payload.get("limit", 20), 20, minimum=1, maximum=200),
                max_retry=self._int_value(payload.get("max_retry", 3), 3, minimum=1, maximum=10),
            )
        )

    # ==================== 维护 (V5) ====================

    async def _v5_recycle_bin(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        return web.json_response(await kernel.memory_v5_admin(action="recycle_bin", limit=limit))

    async def _v5_action(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        action = request.match_info.get("action", "").replace("-", "_")
        payload = await self._json(request)
        kwargs: Dict[str, Any] = {
            "action": action,
            "target": payload.get("target", ""),
            "reason": payload.get("reason", "webui_manual"),
            "updated_by": str(self._current_user(request).get("id", "") or payload.get("updated_by", "webui")),
        }
        if "strength" in payload:
            try:
                kwargs["strength"] = float(payload.get("strength", 1.0) or 1.0)
            except (TypeError, ValueError):
                kwargs["strength"] = 1.0
        return web.json_response(await kernel.memory_v5_admin(**kwargs))

    # ==================== 运行时 ====================

    async def _runtime_config(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_runtime_admin(action="get_config"))

    async def _runtime_save(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_runtime_admin(action="save"))

    async def _runtime_self_check(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_runtime_admin(action="self_check"))

    async def _runtime_refresh_self_check(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_runtime_admin(action="refresh_self_check"))

    async def _runtime_auto_save(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(await kernel.memory_runtime_admin(action="set_auto_save", enabled=bool(payload.get("enabled", False))))

    async def _runtime_rebuild_vectors(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        try:
            batch_size = int(payload.get("batch_size", 32) or 32)
        except (TypeError, ValueError):
            batch_size = 32
        return web.json_response(
            await kernel.memory_runtime_admin(
                action="rebuild_all_vectors",
                timeout_ms=600000,
                dry_run=bool(payload.get("dry_run", False)),
                batch_size=max(1, min(512, batch_size)),
            )
        )

    # ==================== 调优 ====================

    async def _tuning_get_profile(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_tuning_admin(action="get_profile"))

    async def _tuning_list_tasks(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        return web.json_response(await kernel.memory_tuning_admin(action="list_tasks", limit=limit))

    async def _tuning_create_task(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(await kernel.memory_tuning_admin(action="create_task", payload=payload))

    async def _tuning_cancel_task(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(await kernel.memory_tuning_admin(action="cancel", task_id=str(payload.get("task_id", ""))))

    async def _tuning_apply_best(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(await kernel.memory_tuning_admin(action="apply_best", task_id=str(payload.get("task_id", ""))))

    async def _tuning_apply_profile(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        profile: Dict[str, Any] = payload.get("profile", payload)
        return web.json_response(await kernel.memory_tuning_admin(action="apply_profile", profile=profile, reason=str(payload.get("reason", "webui"))))

    async def _tuning_rollback(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        return web.json_response(await kernel.memory_tuning_admin(action="rollback_profile"))

    # ==================== 删除管理 ====================

    async def _delete_preview(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        mode = str(payload.get("mode", "mixed") or "mixed")
        selector = payload.get("selector", {})
        if not isinstance(selector, dict):
            selector = {}
        return web.json_response(await kernel.memory_delete_admin(action="preview", mode=mode, selector=selector))

    async def _delete_execute(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        mode = str(payload.get("mode", "mixed") or "mixed")
        selector = payload.get("selector", {})
        if not isinstance(selector, dict):
            selector = {}
        return web.json_response(
            await kernel.memory_delete_admin(
                action="execute",
                mode=mode,
                selector=selector,
                reason=str(payload.get("reason", "webui_manual")),
                requested_by=str(self._current_user(request).get("id", "") or "webui"),
            )
        )

    async def _delete_restore(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        payload = await self._json(request)
        return web.json_response(
            await kernel.memory_delete_admin(
                action="restore",
                mode=str(payload.get("mode", "") or ""),
                selector=payload.get("selector", {}) if isinstance(payload.get("selector"), dict) else {},
                operation_id=str(payload.get("operation_id", "") or ""),
                requested_by=str(self._current_user(request).get("id", "") or "webui"),
            )
        )

    async def _delete_list_operations(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        mode = str(request.query.get("mode", "") or "")
        return web.json_response(await kernel.memory_delete_admin(action="list_operations", limit=limit, mode=mode))

    async def _delete_get_operation(self, request: web.Request) -> web.Response:
        kernel = await self._kernel()
        operation_id = str(request.match_info.get("operation_id", "") or "")
        return web.json_response(await kernel.memory_delete_admin(action="get_operation", operation_id=operation_id))

    @staticmethod
    async def _json(request: web.Request) -> Dict[str, Any]:
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    # ==================== 公告 ====================

    async def _announcement_store(self):
        provider = self._announcement_store_provider
        if provider is None:
            return None
        result = provider()
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def _board_service(self):
        provider = self._board_service_provider
        if provider is None:
            return None
        result = provider()
        if asyncio.iscoroutine(result):
            return await result
        return result

    @staticmethod
    def _parse_optional_timestamp(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("时间字段必须是 unix 时间戳（秒，可带小数）") from exc

    async def _announcement_list(self, request: web.Request) -> web.Response:
        store = await self._announcement_store()
        if store is None:
            return self._error_response("公告模块未就绪", status=503)
        status = str(request.query.get("status", "") or "")
        include_inactive_param = str(request.query.get("include_inactive", "true") or "true").strip().lower()
        include_inactive = include_inactive_param not in {"0", "false", "no", "off"}
        limit = self._int_query(request, "limit", 50, minimum=1, maximum=200)
        offset = self._int_query(request, "offset", 0, minimum=0, maximum=10000)
        payload = store.list(status=status, include_inactive=include_inactive, limit=limit, offset=offset)
        return web.json_response({"success": True, **payload})

    async def _announcement_active(self, request: web.Request) -> web.Response:
        store = await self._announcement_store()
        if store is None:
            return web.json_response({"success": True, "items": []})
        limit = self._int_query(request, "limit", 5, minimum=1, maximum=20)
        items = store.list_active(limit=limit)
        return web.json_response({"success": True, "items": items})

    async def _announcement_create(self, request: web.Request) -> web.Response:
        store = await self._announcement_store()
        if store is None:
            return self._error_response("公告模块未就绪", status=503)
        payload = await self._json(request)
        user = self._current_user(request)
        try:
            record = store.create(
                title=str(payload.get("title", "") or ""),
                content=str(payload.get("content", "") or ""),
                severity=str(payload.get("severity", "info") or "info"),
                pinned=bool(payload.get("pinned", False)),
                status=str(payload.get("status", "published") or "published"),
                starts_at=self._parse_optional_timestamp(payload.get("starts_at")),
                ends_at=self._parse_optional_timestamp(payload.get("ends_at")),
                author_id=str(user.get("id", "") or ""),
                author_nickname=self._actor_name(user) or str(payload.get("author_nickname", "") or ""),
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        return web.json_response({"success": True, "item": record})

    async def _announcement_delete(self, request: web.Request) -> web.Response:
        store = await self._announcement_store()
        if store is None:
            return self._error_response("公告模块未就绪", status=503)
        try:
            announcement_id = int(request.match_info.get("id", "0") or 0)
        except ValueError:
            return self._error_response("公告 ID 非法", status=400)
        ok = store.delete(announcement_id)
        return web.json_response({"success": True, "deleted": ok})

    # ==================== 留言板 ====================

    async def _board_list_threads(self, request: web.Request) -> web.Response:
        service = await self._board_service()
        if service is None:
            return self._error_response("留言板模块未就绪", status=503)
        status = str(request.query.get("status", "") or "")
        limit = self._int_query(request, "limit", 20, minimum=1, maximum=100)
        offset = self._int_query(request, "offset", 0, minimum=0, maximum=10000)
        payload = service.store.list_threads(status=status, limit=limit, offset=offset)
        return web.json_response({"success": True, **payload})

    async def _board_create_thread(self, request: web.Request) -> web.Response:
        service = await self._board_service()
        if service is None:
            return self._error_response("留言板模块未就绪", status=503)
        payload = await self._json(request)
        user = self._current_user(request)
        try:
            thread = service.store.create_thread(
                title=str(payload.get("title", "") or ""),
                content=str(payload.get("content", "") or ""),
                author_id=str(user.get("id", "") or ""),
                author_nickname=self._actor_name(user) or str(payload.get("author_nickname", "") or ""),
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        thread_with_posts = service.store.get_thread_with_posts(int(thread.get("id") or 0))
        return web.json_response({"success": True, "item": thread_with_posts or thread})

    async def _board_get_thread(self, request: web.Request) -> web.Response:
        service = await self._board_service()
        if service is None:
            return self._error_response("留言板模块未就绪", status=503)
        try:
            thread_id = int(request.match_info.get("id", "0") or 0)
        except ValueError:
            return self._error_response("主题 ID 非法", status=400)
        thread = service.store.get_thread_with_posts(thread_id)
        if thread is None:
            return self._error_response("主题不存在", status=404)
        return web.json_response({"success": True, "item": thread})

    async def _board_delete_thread(self, request: web.Request) -> web.Response:
        service = await self._board_service()
        if service is None:
            return self._error_response("留言板模块未就绪", status=503)
        try:
            thread_id = int(request.match_info.get("id", "0") or 0)
        except ValueError:
            return self._error_response("主题 ID 非法", status=400)
        thread = service.store.get_thread(thread_id)
        if thread is None:
            return self._error_response("主题不存在", status=404)
        user = self._current_user(request)
        if not self._board_can_delete(user, thread.get("author_id")):
            return self._error_response("无权删除该主题", status=403)
        ok = service.store.delete_thread(thread_id)
        return web.json_response({"success": True, "deleted": ok})

    async def _board_reply(self, request: web.Request) -> web.Response:
        service = await self._board_service()
        if service is None:
            return self._error_response("留言板模块未就绪", status=503)
        try:
            thread_id = int(request.match_info.get("id", "0") or 0)
        except ValueError:
            return self._error_response("主题 ID 非法", status=400)
        payload = await self._json(request)
        user = self._current_user(request)
        reply_to_raw = payload.get("reply_to_post_id")
        reply_to: Optional[int] = None
        if reply_to_raw is not None and reply_to_raw != "":
            try:
                reply_to = int(reply_to_raw)
            except (TypeError, ValueError):
                return self._error_response("引用楼层 ID 非法", status=400)
        try:
            post = service.store.add_post(
                thread_id,
                content=str(payload.get("content", "") or ""),
                author_id=str(user.get("id", "") or ""),
                author_nickname=self._actor_name(user) or str(payload.get("author_nickname", "") or ""),
                reply_to_post_id=reply_to,
            )
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        return web.json_response({"success": True, "item": post})

    async def _board_resolve(self, request: web.Request) -> web.Response:
        service = await self._board_service()
        if service is None:
            return self._error_response("留言板模块未就绪", status=503)
        try:
            thread_id = int(request.match_info.get("id", "0") or 0)
        except ValueError:
            return self._error_response("主题 ID 非法", status=400)
        payload = await self._json(request)
        picked_raw = payload.get("picked_post_ids") or payload.get("answer_post_ids") or []
        picked_ids: List[int] = []
        if isinstance(picked_raw, list):
            for value in picked_raw:
                try:
                    picked_ids.append(int(value))
                except (TypeError, ValueError):
                    continue
        user = self._current_user(request)
        result = await service.mark_resolved_and_ingest(
            thread_id,
            picked_post_ids=picked_ids or None,
            resolved_by_id=str(user.get("id", "") or ""),
            resolved_by_nickname=self._actor_name(user),
        )
        status = 200 if result.get("success") else 400
        thread_after = service.store.get_thread_with_posts(thread_id)
        return web.json_response({**result, "thread": thread_after}, status=status)

    async def _board_delete_post(self, request: web.Request) -> web.Response:
        service = await self._board_service()
        if service is None:
            return self._error_response("留言板模块未就绪", status=503)
        try:
            post_id = int(request.match_info.get("id", "0") or 0)
        except ValueError:
            return self._error_response("楼层 ID 非法", status=400)
        post = service.store.get_post(post_id)
        if post is None:
            return self._error_response("楼层不存在", status=404)
        user = self._current_user(request)
        if not self._board_can_delete(user, post.get("author_id")):
            return self._error_response("无权删除该楼层", status=403)
        ok = service.store.delete_post(post_id)
        return web.json_response({"success": True, "deleted": ok})

    @staticmethod
    def _board_can_delete(user: Dict[str, Any], target_author_id: Any) -> bool:
        permissions = set(user.get("permissions") or [])
        if "*" in permissions or "board.delete_any" in permissions:
            return True
        return bool(target_author_id) and str(target_author_id) == str(user.get("id", "") or "")
