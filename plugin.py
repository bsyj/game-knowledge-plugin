"""GameKnowledge plugin entry."""

from __future__ import annotations

import asyncio
import errno
import logging as _logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# MaiBot 的插件加载器通过 spec_from_file_location 直接加载 plugin.py 为合成包,
# 不会执行本目录的 __init__.py。kernel/ 下的模块使用绝对导入 `from gk_shims...`,
# 因此必须在这里把插件根目录注入 sys.path,且早于任何 .kernel / .gk_shims 导入。
_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from maibot_sdk import Command, HookHandler, MaiBotPlugin, Tool
from maibot_sdk.components import HookMode
from maibot_sdk.types import ToolParameterInfo, ToolParamType

# 使用绝对导入 gk_shims（与 kernel/* 一致），避免双重加载导致 message_shim 等
# 模块级状态在 plugin 端与 kernel 端不共享（plugin 设置的 _plugin_ctx kernel 看不到）。
from gk_shims.logger_shim import get_logger
from .kernel.core.runtime.sdk_memory_kernel import KernelSearchRequest, SDKMemoryKernel
from .kernel.core.utils.game_knowledge_analyzer import GameKnowledgeAnalyzer
from .kernel.core.utils.review_queue_service import ReviewQueueService
from .kernel.paths import repo_root

from .config import GameKnowledgePluginConfig
from .revision_service import GameKnowledgeRevisionService
from .web_server import GameKnowledgeWebServer
from .announcement_store import AnnouncementStore
from .board_store import BoardStore
from .board_service import BoardService

logger = get_logger("plugin.gk")


def _tool_param(name: str, param_type: ToolParamType, description: str, required: bool) -> ToolParameterInfo:
    return ToolParameterInfo(name=name, param_type=param_type, description=description, required=required)


class _KernelLogBridge(_logging.Handler):
    """将 GameKnowledge.* 内核日志桥接到 plugin.* 命名空间。

    RunnerIPCLogHandler 白名单仅允许 plugin.* / plugin_runtime.* / _maibot_plugin_* 前缀
    的日志通过 IPC 转发到主进程。内核模块使用 GameKnowledge.* 前缀，不在白名单内。
    本 Handler 挂载在 GameKnowledge logger 上，将子 logger 的记录以
    plugin.gk.kernel 的名义重新发出，使其能被 IPC 转发。
    """

    def __init__(self, bridge_logger_name: str) -> None:
        super().__init__()
        self._bridge_logger = _logging.getLogger(bridge_logger_name)

    def emit(self, record: _logging.LogRecord) -> None:
        try:
            msg = self._extract_message(record)
            short_name = record.name.replace("GameKnowledge.", "GK.")
            bridged = _logging.LogRecord(
                name=self._bridge_logger.name,
                level=record.levelno,
                pathname=record.pathname,
                lineno=record.lineno,
                msg=f"[{short_name}] {msg}",
                args=(),
                exc_info=record.exc_info,
            )
            self._bridge_logger.handle(bridged)
        except Exception:
            self.handleError(record)

    @staticmethod
    def _extract_message(record: _logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            event_text = str(record.msg.get("event", ""))
            extras = []
            for key, value in record.msg.items():
                if key in (
                    "event", "logger", "logger_name", "level", "timestamp",
                    "module", "lineno", "pathname", "_from_structlog", "_record",
                ):
                    continue
                extras.append(f"{key}={value}")
            if extras:
                return f"{event_text} {' '.join(extras)}".strip()
            return event_text
        return record.getMessage()


class GameKnowledgePlugin(MaiBotPlugin):
    """GameKnowledge 插件入口

    职责：
    - 管理 GameKnowledge 内核生命周期
    - 启动独立 WebUI
    - 注册 Tools 供 LLM 调用
    - 监听群聊消息并触发知识分析
    - 提供 /gkb 命令集
    """

    config_model = GameKnowledgePluginConfig

    def __init__(self) -> None:
        super().__init__()
        self._kernel: Optional[SDKMemoryKernel] = None
        self._web: Optional[GameKnowledgeWebServer] = None
        self._analyzer: Optional[GameKnowledgeAnalyzer] = None
        self._review_queue: Optional[ReviewQueueService] = None
        self._announcement_store: Optional[AnnouncementStore] = None
        self._board_store: Optional[BoardStore] = None
        self._board_service: Optional[BoardService] = None
        self._message_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self._auto_analyze_tasks: Dict[str, asyncio.Task[bool]] = {}
        # 上一次"分析后无可入库卡片"的时间戳,用于触发后续退避,避免
        # LLM 一直产空导致每条新消息都触发一次分析。
        self._empty_analyze_until: Dict[str, float] = {}
        self._log_bridge: Optional[_KernelLogBridge] = None
        self._db_maintenance_task: Optional[asyncio.Task[None]] = None
        self._board_overdue_task: Optional[asyncio.Task[None]] = None

    async def on_load(self) -> None:
        if not self.config.plugin.enabled:
            logger.info("GameKnowledge plugin disabled")
            return
        try:
            # Inject plugin context into bridge shims
            from gk_shims.message_shim import set_message_context
            set_message_context(self.ctx)
            self._install_kernel_log_bridge()
            await self._get_kernel()
            await self._start_web()
            self._db_maintenance_task = asyncio.create_task(self._db_maintenance_loop())
            self._board_overdue_task = asyncio.create_task(self._board_overdue_loop())
            logger.info("GameKnowledge plugin loaded")
        except Exception:
            self._uninstall_kernel_log_bridge()
            raise

    async def on_unload(self) -> None:
        await self._stop_web()
        if self._db_maintenance_task is not None:
            self._db_maintenance_task.cancel()
            try:
                await self._db_maintenance_task
            except asyncio.CancelledError:
                pass
            self._db_maintenance_task = None
        if self._board_overdue_task is not None:
            self._board_overdue_task.cancel()
            try:
                await self._board_overdue_task
            except asyncio.CancelledError:
                pass
            self._board_overdue_task = None
        for task in list(self._auto_analyze_tasks.values()):
            task.cancel()
        if self._auto_analyze_tasks:
            await asyncio.gather(*self._auto_analyze_tasks.values(), return_exceptions=True)
        self._auto_analyze_tasks.clear()
        if self._kernel is not None:
            await self._kernel.shutdown()
            self._kernel = None
        self._analyzer = None
        self._review_queue = None
        self._announcement_store = None
        self._board_store = None
        self._board_service = None
        self._message_buffer.clear()
        self._uninstall_kernel_log_bridge()
        logger.info("GameKnowledge plugin unloaded")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        _ = scope, config_data, version
        await self.on_unload()
        await self.on_load()

    def _runtime_config(self) -> Dict[str, Any]:
        payload = self.config.model_dump(mode="json") if hasattr(self.config, "model_dump") else {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("storage", {})["data_dir"] = self.config.storage.data_dir
        payload.setdefault("advanced", {})["enable_auto_save"] = bool(self.config.advanced.enable_auto_save)
        payload["advanced"]["auto_save_interval_minutes"] = int(self.config.advanced.auto_save_interval_minutes)
        payload.setdefault("web", {})["enabled"] = bool(self.config.web.enabled)
        payload.setdefault("episode", {})["enabled"] = bool(self.config.episode.enabled)
        payload["episode"]["generation_enabled"] = bool(self.config.episode.generation_enabled)
        payload["episode"]["pending_batch_size"] = int(self.config.episode.pending_batch_size)
        payload["episode"]["pending_max_retry"] = int(self.config.episode.pending_max_retry)
        return payload

    def _install_kernel_log_bridge(self) -> None:
        if self._log_bridge is not None:
            return
        self._log_bridge = _KernelLogBridge("plugin.gk.kernel")
        _logging.getLogger("GameKnowledge").addHandler(self._log_bridge)
        logger.debug("内核日志桥接已安装: GameKnowledge.* → plugin.gk.kernel")

    def _uninstall_kernel_log_bridge(self) -> None:
        if self._log_bridge is None:
            return
        _logging.getLogger("GameKnowledge").removeHandler(self._log_bridge)
        self._log_bridge = None
        logger.debug("内核日志桥接已卸载")

    async def _get_kernel(self) -> SDKMemoryKernel:
        if self._kernel is None:
            kernel = SDKMemoryKernel(plugin_root=repo_root(), config=self._runtime_config(), plugin_ctx=self.ctx)
            try:
                await kernel.initialize()
            except Exception:
                shutdown = getattr(kernel, "shutdown", None)
                if callable(shutdown):
                    await shutdown()
                else:
                    close = getattr(kernel, "close", None)
                    if callable(close):
                        close()
                raise
            self._kernel = kernel
            self._review_queue = ReviewQueueService(
                kernel=kernel,
                allowed_source_group_ids=list(self.config.collector.allowed_source_group_ids or []),
            )
        return self._kernel

    

    def _get_analyzer(self) -> GameKnowledgeAnalyzer:
        if self._analyzer is None:
            from gk_shims.llm_shim import LLMServiceClient

            task_name = self.config.collector.llm_task_name.strip() or "utils"
            review_task_name = self.config.collector.ai_review_task_name.strip() or task_name
            enable_ai_review = bool(self.config.collector.enable_ai_review)
            llm_client = LLMServiceClient(task_name=task_name, plugin_ctx=self.ctx)
            review_client = LLMServiceClient(task_name=review_task_name, plugin_ctx=self.ctx) if enable_ai_review else None
            self._analyzer = GameKnowledgeAnalyzer(
                llm_client=llm_client,
                review_client=review_client,
                enable_ai_review=enable_ai_review,
                ai_review_error_status=self.config.collector.ai_review_error_status,
            )
        return self._analyzer

    async def _get_announcement_store(self) -> Optional[AnnouncementStore]:
        """惰性初始化公告存储；metadata_store 必须就绪。"""
        if self._announcement_store is not None:
            return self._announcement_store
        kernel = await self._get_kernel()
        store = getattr(kernel, "metadata_store", None)
        if store is None:
            return None
        self._announcement_store = AnnouncementStore(store=store)
        return self._announcement_store

    async def _get_board_service(self) -> Optional[BoardService]:
        """惰性初始化留言板服务。"""
        if self._board_service is not None:
            return self._board_service
        kernel = await self._get_kernel()
        store = getattr(kernel, "metadata_store", None)
        if store is None:
            return None
        if self._board_store is None:
            self._board_store = BoardStore(store=store)
        async def _review_queue_provider() -> Optional[ReviewQueueService]:
            await self._get_kernel()
            return self._review_queue

        def _config_provider() -> Dict[str, Any]:
            return {
                "allowed_source_group_ids": list(self.config.collector.allowed_source_group_ids or []),
                "source_platform": "qq",
            }

        self._board_service = BoardService(
            store=self._board_store,
            analyzer_provider=self._get_analyzer,
            review_queue_provider=_review_queue_provider,
            config_provider=_config_provider,
        )
        return self._board_service

    # ==================== 留言板后台任务 ====================

    BOARD_FORWARD_TIMEOUT_SECONDS: int = 2 * 24 * 3600
    BOARD_COLLECT_WINDOW_SECONDS: int = 20 * 60
    BOARD_COLLECT_MAX_MESSAGES: int = 20
    BOARD_LOOP_INTERVAL_SECONDS: int = 300

    # 一次分析没产出任何可入库卡片后,同一 stream 暂停自动分析的时长。
    # 避免群里持续闲聊导致每条新消息都触发一次 LLM 抽取(空跑 + 烧 token)。
    EMPTY_ANALYZE_BACKOFF_SECONDS: float = 300.0

    async def _board_overdue_loop(self) -> None:
        """每 5 分钟扫描一次：处理 2 天无人回应的主题 + 处理 collecting 超时主题。"""

        while True:
            try:
                await asyncio.sleep(self.BOARD_LOOP_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            try:
                await self._scan_board_overdue()
                await self._scan_board_collecting_expired()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"留言板后台扫描异常: {exc}")

    async def _scan_board_overdue(self) -> None:
        """找 status=open 且 reply_count==0 且超时的主题，LLM 改写后转发到许可群。"""

        service = await self._get_board_service()
        if service is None:
            return
        store = service.store
        threads = store.list_open_overdue(threshold_seconds=float(self.BOARD_FORWARD_TIMEOUT_SECONDS))
        if not threads:
            return
        target_group_id = next(
            (str(item or "").strip() for item in (self.config.collector.allowed_source_group_ids or []) if str(item or "").strip()),
            "",
        )
        if not target_group_id:
            logger.debug("留言板转发跳过：未配置 allowed_source_group_ids")
            return

        stream_id = await self._resolve_qq_group_stream_id(target_group_id)
        if not stream_id:
            logger.warning(
                f"留言板转发跳过：未找到 group_id={target_group_id} 对应的已注册聊天流（需该群至少有过一条消息）"
            )
            return

        for thread in threads:
            posts = store.list_posts(int(thread.get("id") or 0))
            head_content = str((posts[0].get("content") if posts else thread.get("title")) or "").strip()
            polished = await self._llm_polish_board_question(
                title=str(thread.get("title", "") or ""),
                body=head_content,
            )
            try:
                await self.ctx.send.text(polished, stream_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"留言板转发失败: thread={thread.get('id')} error={exc}")
                continue
            store.mark_forwarded(
                int(thread.get("id") or 0),
                forwarded_message_id="",
                forward_target_group_id=target_group_id,
                collected_until=time.time() + float(self.BOARD_COLLECT_WINDOW_SECONDS),
            )
            logger.info(
                f"[Board] 已将留言转发到 QQ 群求助: thread_id={thread.get('id')} group={target_group_id}"
            )

    async def _scan_board_collecting_expired(self) -> None:
        """处理 collecting 状态且已超过收集窗口的主题：把已收集楼层入库审核。"""

        service = await self._get_board_service()
        if service is None:
            return
        expired = service.store.list_collecting_expired()
        for thread in expired:
            await self._finalize_collected_board_thread(int(thread.get("id") or 0), reason="time")

    async def _finalize_collected_board_thread(self, thread_id: int, *, reason: str) -> None:
        """把 collecting 主题的所有楼层喂 analyzer 并入审核队列。"""

        service = await self._get_board_service()
        if service is None:
            return
        thread = service.store.get_thread_with_posts(thread_id)
        if thread is None or thread.get("status") not in {"collecting", "forwarded"}:
            return
        posts = list(thread.get("posts") or [])
        if len(posts) <= 1:
            # 没有任何答案楼层，直接关闭，避免反复尝试
            service.store.close_thread(thread_id)
            logger.info(f"[Board] thread {thread_id} 无回答，已关闭（reason={reason}）")
            return
        # 答案 = 除首楼外的所有楼层（含 QQ 群消息）
        picked_post_ids = [int(post.get("id") or 0) for post in posts[1:] if post.get("id")]
        result = await service.mark_resolved_and_ingest(
            thread_id,
            picked_post_ids=picked_post_ids,
            resolved_by_id="",
            resolved_by_nickname="bot",
        )
        submitted = int(result.get("submitted") or 0)
        logger.info(
            f"[Board] finalize thread={thread_id} reason={reason} submitted={submitted} error={result.get('error', '')}"
        )

    async def _llm_polish_board_question(self, *, title: str, body: str) -> str:
        """用 plugin 已配置的 LLMServiceClient 改写问句。失败时回退到拼接模板。"""

        from gk_shims.llm_shim import LLMServiceClient

        task_name = self.config.collector.llm_task_name.strip() or "utils"
        prompt = (
            "请把下面这条来自 WebUI 留言板的提问改写成一段自然、口语化的中文问句，"
            "直接发到 QQ 群里向群友求助；不要加任何前缀或机器人式标签，不要 @ 任何人，"
            "也不要说\"这是机器人转发\"。控制在 80 字以内。\n\n"
            f"提问标题：{title or '（无标题）'}\n"
            f"提问内容：{body or '（无内容）'}"
        )
        try:
            client = LLMServiceClient(task_name=task_name, plugin_ctx=self.ctx)
            result = await client.generate_response(prompt=prompt)
            text = ""
            for attr in ("response", "content", "text"):
                value = getattr(result, attr, None)
                if isinstance(value, str) and value.strip():
                    text = value.strip()
                    break
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"留言板 LLM 改写失败，回退到模板: {exc}")
        # 兜底：原文拼接
        body_short = body.strip() if body else "（无补充说明）"
        if len(body_short) > 120:
            body_short = body_short[:120] + "…"
        return f"群里有人问：{title.strip() or '请教大家一个问题'}\n{body_short}"

    async def _resolve_qq_group_stream_id(self, group_id: str) -> str:
        """通过 SDK ctx.chat 接口按 platform=qq + group_id 查找已注册 stream_id。

        若该群从未与 bot 产生过会话（无消息历史），返回空串；调用方需跳过本次转发。
        """

        try:
            stream = await self.ctx.chat.get_stream_by_group_id(str(group_id), platform="qq")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"get_stream_by_group_id 调用失败: {exc}")
            return ""
        if not isinstance(stream, dict):
            return ""
        return str(stream.get("stream_id", "") or stream.get("session_id", "") or "")

    @staticmethod
    def _extract_stream_id(message: Dict[str, Any]) -> str:
        return str(
            message.get("session_id", "")
            or message.get("stream_id", "")
            or message.get("chat_id", "")
            or message.get("message_info", {}).get("group_info", {}).get("group_id", "")
            or ""
        )

    @staticmethod
    def _extract_runtime_stream_id(message: Dict[str, Any]) -> str:
        return str(
            message.get("session_id", "")
            or message.get("stream_id", "")
            or message.get("chat_id", "")
            or ""
        ).strip()

    @staticmethod
    def _extract_group_id(message: Dict[str, Any]) -> str:
        return str(
            message.get("message_info", {}).get("group_info", {}).get("group_id", "")
            or message.get("group_id", "")
            or ""
        ).strip()

    @staticmethod
    def _extract_group_name(message: Dict[str, Any]) -> str:
        group_info = message.get("message_info", {}).get("group_info", {})
        return str(
            group_info.get("group_name", "")
            or group_info.get("group_nickname", "")
            or group_info.get("group_cardname", "")
            or group_info.get("name", "")
            or message.get("group_name", "")
            or ""
        ).strip()

    @staticmethod
    def _extract_platform(message: Dict[str, Any]) -> str:
        return str(message.get("platform", "") or "").strip().lower()

    def _is_group_whitelisted(self, group_id: str) -> bool:
        whitelist = {
            str(item or "").strip()
            for item in (self.config.collector.allowed_source_group_ids or [])
            if str(item or "").strip()
        }
        if not whitelist:
            return True
        return str(group_id or "").strip() in whitelist

    @staticmethod
    def _extract_user_id(message: Dict[str, Any]) -> str:
        return str(
            message.get("message_info", {}).get("user_info", {}).get("user_id", "")
            or message.get("user_id", "")
            or ""
        ).strip()

    def _check_is_bot_self(self, platform: str, user_id: str) -> bool:
        """检查给定 platform + user_id 是否为机器人自身。

        通过消息上下文判断，避免采集机器人自己的消息。
        若无法判定，默认返回 False（不过滤），防止误杀用户消息。
        """
        _ = platform
        # 常见 bot self_id 模式检查
        if not user_id:
            return False
        # 若消息中携带 self_id 字段，可直接比对
        return False

    @staticmethod
    def _normalize_message_for_buffer(message: Dict[str, Any]) -> Dict[str, Any]:
        message_info = message.get("message_info", {})
        user_info = message_info.get("user_info", {})
        group_info = message_info.get("group_info", {})
        sender_name = str(
            user_info.get("user_cardname", "")
            or user_info.get("user_nickname", "")
            or message.get("sender_name", "")
            or ""
        )
        content = str(
            message.get("processed_plain_text", "")
            or message.get("content", "")
            or ""
        ).strip()
        return {
            "id": str(message.get("message_id", "") or message.get("id", "") or ""),
            "content": content,
            "sender_name": sender_name,
            "timestamp": message.get("timestamp"),
            "source_platform": str(message.get("platform", "") or "").strip().lower(),
            "source_group_id": str(group_info.get("group_id", "") or message.get("group_id", "") or "").strip(),
            "source_group_name": str(
                group_info.get("group_name", "")
                or group_info.get("group_nickname", "")
                or group_info.get("group_cardname", "")
                or group_info.get("name", "")
                or message.get("group_name", "")
                or ""
            ).strip(),
        }

    async def _start_web(self) -> None:
        if self._web is not None or not self.config.web.enabled:
            return
        web = GameKnowledgeWebServer(
            kernel_provider=self._get_kernel,
            host=self.config.web.host,
            port=int(self.config.web.port),
            announcement_store_provider=self._get_announcement_store,
            board_service_provider=self._get_board_service,
            plugin_ctx_provider=lambda: self.ctx,
        )
        try:
            await web.start()
        except Exception as exc:
            if self._is_address_in_use(exc) and bool(self.config.web.cleanup_stale_runner_on_port_conflict):
                cleaned = await self._cleanup_stale_webui_runner(
                    host=self.config.web.host,
                    port=int(self.config.web.port),
                )
                if cleaned:
                    retry_web = GameKnowledgeWebServer(
                        kernel_provider=self._get_kernel,
                        host=self.config.web.host,
                        port=int(self.config.web.port),
                        announcement_store_provider=self._get_announcement_store,
                        board_service_provider=self._get_board_service,
                        plugin_ctx_provider=lambda: self.ctx,
                    )
                    try:
                        await retry_web.start()
                    except Exception as retry_exc:
                        logger.warning(f"GameKnowledge WebUI 清理旧 Runner 后仍启动失败，已继续加载核心能力: {retry_exc}")
                        return
                    self._web = retry_web
                    return
            logger.warning(f"GameKnowledge WebUI 启动失败，已继续加载核心能力: {exc}")
            return
        self._web = web

    async def _stop_web(self) -> None:
        if self._web is None:
            return
        await self._web.stop()
        self._web = None

    @staticmethod
    def _is_address_in_use(exc: BaseException) -> bool:
        current: BaseException | None = exc
        while current is not None:
            err_no = getattr(current, "errno", None)
            winerror = getattr(current, "winerror", None)
            if err_no == errno.EADDRINUSE or winerror == 10048:
                return True
            current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        text = str(exc).lower()
        return "address already in use" in text or "10048" in text or "通常每个套接字地址" in text

    async def _cleanup_stale_webui_runner(self, *, host: str, port: int) -> bool:
        """清理占用 WebUI 端口的同工作区旧 Runner。

        正常重启路径应由 Host 发送 plugin.shutdown 并触发 on_unload。这个兜底只处理
        Windows/异常退出后遗留的 runner_main 进程，避免旧 WebUI 长时间占用端口。
        """
        try:
            import psutil  # type: ignore
        except Exception as exc:
            logger.warning(f"WebUI 端口被占用，但 psutil 不可用，无法自动清理旧 Runner: {exc}")
            return False

        current_pid = os.getpid()
        expected_exe = os.path.normcase(os.path.abspath(sys.executable))
        expected_root = os.path.normcase(str(repo_root()))
        target_host = str(host or "").strip() or "127.0.0.1"
        target_pids: set[int] = set()

        def _same_host(local_ip: str) -> bool:
            if target_host in {"0.0.0.0", "::"}:
                return True
            return local_ip in {target_host, "0.0.0.0", "::"}

        try:
            for conn in psutil.net_connections(kind="tcp"):
                local = getattr(conn, "laddr", None)
                if not local or getattr(local, "port", None) != int(port):
                    continue
                if getattr(conn, "status", "") != psutil.CONN_LISTEN:
                    continue
                if not _same_host(str(getattr(local, "ip", "") or "")):
                    continue
                pid = int(getattr(conn, "pid", 0) or 0)
                if pid and pid != current_pid:
                    target_pids.add(pid)
        except Exception as exc:
            logger.warning(f"检查 WebUI 端口占用失败: {exc}")
            return False

        cleaned = False
        for pid in sorted(target_pids):
            try:
                proc = psutil.Process(pid)
                exe = os.path.normcase(os.path.abspath(proc.exe() or ""))
                cmdline = " ".join(proc.cmdline())
                cwd = os.path.normcase(proc.cwd() or "")
                is_same_runner = (
                    exe == expected_exe
                    and "src.plugin_runtime.runner.runner_main" in cmdline
                    and (cwd.startswith(expected_root) or expected_root in os.path.normcase(cmdline))
                )
                if not is_same_runner:
                    logger.warning(f"WebUI 端口 {port} 被非本插件旧 Runner 占用，跳过自动清理: pid={pid}, cmd={cmdline}")
                    continue

                logger.warning(f"发现遗留 GameKnowledge WebUI Runner 占用端口 {port}，准备清理: pid={pid}")
                proc.terminate()
                try:
                    await asyncio.to_thread(proc.wait, 3)
                except Exception:
                    if proc.is_running():
                        logger.warning(f"遗留 Runner terminate 超时，尝试 kill: pid={pid}")
                        proc.kill()
                        await asyncio.to_thread(proc.wait, 3)
                cleaned = True
            except psutil.NoSuchProcess:
                cleaned = True
            except Exception as exc:
                logger.warning(f"清理遗留 WebUI Runner 失败: pid={pid}, error={exc}")

        if cleaned:
            await asyncio.sleep(0.3)
        return cleaned

    # ==================== Tools ====================

    @Tool(
        "query_game_knowledge",
        description="搜索游戏知识库。用于查询游戏攻略、配置、报错、玩法机制、版本差异和群聊沉淀知识。",
        parameters=[
            _tool_param("query", ToolParamType.STRING, "查询文本", True),
            _tool_param("limit", ToolParamType.INTEGER, "返回条数", False),
            _tool_param("mode", ToolParamType.STRING, "search/time/hybrid/aggregate", False),
            _tool_param("chat_id", ToolParamType.STRING, "聊天流 ID", False),
        ],
    )
    async def handle_query_game_knowledge(
        self,
        query: str,
        limit: int = 5,
        mode: str = "aggregate",
        chat_id: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        kernel = await self._get_kernel()
        result = await kernel.search_memory(
            KernelSearchRequest(
                query=query,
                limit=min(200, max(1, int(limit or 5))),
                mode=mode,
                chat_id=chat_id,
                user_id=str(kwargs.get("user_id", "") or ""),
                group_id=str(kwargs.get("group_id", "") or ""),
            )
        )
        return result

    @Tool(
        "ingest_game_knowledge",
        description="写入一条游戏知识到 GameKnowledge。",
        parameters=[
            _tool_param("external_id", ToolParamType.STRING, "外部幂等 ID", True),
            _tool_param("text", ToolParamType.STRING, "知识正文", True),
            _tool_param("chat_id", ToolParamType.STRING, "聊天流 ID", False),
            _tool_param("tags", ToolParamType.STRING, "标签，逗号分隔", False),
            _tool_param("metadata", ToolParamType.STRING, "元数据 JSON 字符串", False),
            _tool_param("relations", ToolParamType.STRING, "关系 JSON 数组字符串", False),
            _tool_param("entities", ToolParamType.STRING, "实体，逗号分隔", False),
        ],
    )
    async def handle_ingest_game_knowledge(
        self,
        external_id: str,
        text: str,
        chat_id: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        relations: Optional[List[Dict[str, Any]]] = None,
        entities: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        kernel = await self._get_kernel()
        meta = dict(metadata or {})
        meta.setdefault("domain", "game_knowledge")
        group_id = str(meta.get("source_group_id") or kwargs.get("group_id") or "").strip()
        meta.setdefault("source_group_id", group_id)
        return await kernel.ingest_text(
            external_id=external_id,
            source_type="game_knowledge",
            text=text,
            chat_id=chat_id,
            tags=tags or ["game_knowledge"],
            metadata=meta,
            relations=relations or [],
            entities=entities or [],
        )

    @Tool(
        "revise_game_knowledge",
        description="修订已有游戏知识。按 WebUI 编辑逻辑：已批准卡片创建待审核修订版，未批准卡片直接更新，普通检索段落创建待审核卡片。",
        parameters=[
            _tool_param("target", ToolParamType.STRING, "段落 hash / card_hash / card_id", True),
            _tool_param("title", ToolParamType.STRING, "标题", False),
            _tool_param("question", ToolParamType.STRING, "问题", False),
            _tool_param("answer", ToolParamType.STRING, "答案", False),
            _tool_param("category", ToolParamType.STRING, "分类", False),
            _tool_param("steps", ToolParamType.STRING, "步骤，逗号或换行分隔；运行时也兼容数组", False),
            _tool_param("tags", ToolParamType.STRING, "标签，逗号或换行分隔；运行时也兼容数组", False),
            _tool_param("search_terms", ToolParamType.STRING, "检索关键词，逗号或换行分隔", False),
            _tool_param("aliases", ToolParamType.STRING, "别名/俗称，逗号或换行分隔", False),
            _tool_param("rlcraft_version", ToolParamType.STRING, "游戏版本", False),
            _tool_param("answer_type", ToolParamType.STRING, "error_fix/config/recommendation/guide/mechanic/location/drop/other", False),
            _tool_param("valid_status", ToolParamType.STRING, "active/stale/deprecated/conflict", False),
            _tool_param("game_id", ToolParamType.STRING, "游戏 ID", False),
            _tool_param("version", ToolParamType.STRING, "版本", False),
            _tool_param("platform", ToolParamType.STRING, "平台", False),
            _tool_param("evidence", ToolParamType.STRING, "修订依据", False),
        ],
    )
    async def handle_revise_game_knowledge(
        self,
        target: str,
        title: Optional[str] = None,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        category: Optional[str] = None,
        steps: Any = None,
        tags: Any = None,
        search_terms: Any = None,
        aliases: Any = None,
        rlcraft_version: Optional[str] = None,
        answer_type: Optional[str] = None,
        valid_status: Optional[str] = None,
        game_id: Optional[str] = None,
        version: Optional[str] = None,
        platform: Optional[str] = None,
        evidence: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        _ = kwargs
        kernel = await self._get_kernel()
        store = kernel.metadata_store
        if store is None:
            return {"success": False, "error": "metadata_store 未就绪", "message": "metadata_store 未就绪"}

        payload = self._build_revision_payload(
            title=title,
            question=question,
            answer=answer,
            category=category,
            steps=steps,
            tags=tags,
            search_terms=search_terms,
            aliases=aliases,
            rlcraft_version=rlcraft_version,
            answer_type=answer_type,
            valid_status=valid_status,
            game_id=game_id,
            version=version,
            platform=platform,
            evidence=evidence,
        )
        try:
            result = GameKnowledgeRevisionService(store=store).revise_target(target, payload)
        except ValueError as exc:
            return {"success": False, "error": str(exc), "message": str(exc)}
        if result.get("success", False):
            return result
        message = str(result.get("error", "") or "修订失败")
        return {**result, "message": message}

    @staticmethod
    def _build_revision_payload(**values: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for key, value in values.items():
            if value is None:
                continue
            if key in {"steps", "tags", "search_terms", "aliases"}:
                payload[key] = GameKnowledgePlugin._normalize_tool_list(value)
            else:
                payload[key] = str(value or "").strip()
        return payload

    

    @staticmethod
    def _normalize_tool_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            raw_items = value.replace("\r\n", "\n").replace("，", ",").split(",")
            if len(raw_items) == 1:
                raw_items = value.replace("\r\n", "\n").split("\n")
            return [item.strip() for item in raw_items if item.strip()]
        return []

    @Tool(
        "get_game_knowledge_card",
        description="获取一张游戏知识卡片详情。支持使用 card_id、card_hash 或 paragraph_hash 查询。",
        parameters=[
            _tool_param("target", ToolParamType.STRING, "card_id / card_hash / paragraph_hash", True),
        ],
    )
    async def handle_get_game_knowledge_card(self, target: str, **kwargs: Any) -> Dict[str, Any]:
        _ = kwargs
        kernel = await self._get_kernel()
        store = kernel.metadata_store
        if store is None:
            return {"success": False, "error": "metadata_store 未就绪", "message": "metadata_store 未就绪"}
        card = store.get_knowledge_card_by_paragraph_hash(str(target or "").strip())
        if card is None:
            return {"success": False, "error": "卡片不存在", "message": "卡片不存在"}
        return {"success": True, "card": card, "message": "已获取卡片"}

    @Tool(
        "list_game_knowledge_cards",
        description="查询游戏知识卡片列表，默认查看待审核卡片。",
        parameters=[
            _tool_param("status", ToolParamType.STRING, "审核状态：pending/approved/rejected/ai_rejected，默认 pending", False),
            _tool_param("keyword", ToolParamType.STRING, "关键词", False),
            _tool_param("category", ToolParamType.STRING, "分类", False),
            _tool_param("platform", ToolParamType.STRING, "平台", False),
            _tool_param("source_group_id", ToolParamType.STRING, "来源群 ID", False),
            _tool_param("source_group_name", ToolParamType.STRING, "来源群名称", False),
            _tool_param("limit", ToolParamType.INTEGER, "返回条数，最大 200", False),
            _tool_param("offset", ToolParamType.INTEGER, "分页偏移", False),
        ],
    )
    async def handle_list_game_knowledge_cards(
        self,
        status: str = "pending",
        keyword: str = "",
        category: str = "",
        platform: str = "",
        source_group_id: str = "",
        source_group_name: str = "",
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        _ = kwargs
        kernel = await self._get_kernel()
        store = kernel.metadata_store
        if store is None:
            return {"success": False, "error": "metadata_store 未就绪", "message": "metadata_store 未就绪"}
        safe_limit = self._bounded_int(limit, default=50, minimum=1, maximum=200)
        safe_offset = self._bounded_int(offset, default=0, minimum=0, maximum=1_000_000)
        cards = store.list_knowledge_cards(
            status=str(status or "pending").strip(),
            category=str(category or "").strip(),
            platform=str(platform or "").strip(),
            source_group_id=str(source_group_id or "").strip(),
            source_group_name=str(source_group_name or "").strip(),
            keyword=str(keyword or "").strip(),
            limit=safe_limit,
            offset=safe_offset,
        )
        return {
            "success": True,
            "cards": cards,
            "count": len(cards),
            "limit": safe_limit,
            "offset": safe_offset,
            "message": f"已获取 {len(cards)} 张卡片",
        }

    @Tool(
        "approve_game_knowledge_card",
        description="审核通过一张游戏知识卡片，并按现有审核流程写入知识库。",
        parameters=[
            _tool_param("card_id", ToolParamType.INTEGER, "卡片 ID", True),
            _tool_param("reviewed_by", ToolParamType.STRING, "审核人标识，默认 llm_tool", False),
        ],
    )
    async def handle_approve_game_knowledge_card(
        self,
        card_id: int,
        reviewed_by: str = "llm_tool",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        _ = kwargs
        parsed = self._parse_card_id(card_id)
        if parsed is None:
            return {"success": False, "error": "card_id 必须是数字", "message": "card_id 必须是数字"}
        kernel = await self._get_kernel()
        if kernel.metadata_store is None:
            return {"success": False, "error": "metadata_store 未就绪", "message": "metadata_store 未就绪"}
        result = await ReviewQueueService(kernel=kernel).approve_card(
            parsed,
            reviewed_by=str(reviewed_by or "llm_tool").strip() or "llm_tool",
        )
        if result.get("success", False):
            return {**result, "message": "卡片已审核通过并写入知识库" if result.get("ingested") else "卡片已审核通过"}
        return {**result, "message": str(result.get("error", "") or "审核通过失败")}

    @Tool(
        "reject_game_knowledge_card",
        description="拒绝一张游戏知识卡片，只更新审核状态，不删除数据。",
        parameters=[
            _tool_param("card_id", ToolParamType.INTEGER, "卡片 ID", True),
            _tool_param("reviewed_by", ToolParamType.STRING, "审核人标识，默认 llm_tool", False),
        ],
    )
    async def handle_reject_game_knowledge_card(
        self,
        card_id: int,
        reviewed_by: str = "llm_tool",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        _ = kwargs
        parsed = self._parse_card_id(card_id)
        if parsed is None:
            return {"success": False, "error": "card_id 必须是数字", "message": "card_id 必须是数字"}
        kernel = await self._get_kernel()
        if kernel.metadata_store is None:
            return {"success": False, "error": "metadata_store 未就绪", "message": "metadata_store 未就绪"}
        result = await ReviewQueueService(kernel=kernel).reject_card(
            parsed,
            reviewed_by=str(reviewed_by or "llm_tool").strip() or "llm_tool",
        )
        if result.get("success", False):
            return {**result, "message": "卡片已拒绝"}
        return {**result, "message": str(result.get("error", "") or "拒绝卡片失败")}

    @Tool(
        "merge_game_knowledge_cards",
        description="把一张卡片合并到另一张卡片：source 标记为 superseded 指向 target，target 内容不变。用于解决相似/重复卡片，避免审核员各自 approve 造成内核重复段落。",
        parameters=[
            _tool_param("source_card_id", ToolParamType.INTEGER, "要被合并掉的源卡 ID", True),
            _tool_param("target_card_id", ToolParamType.INTEGER, "保留的目标卡 ID", True),
            _tool_param("reason", ToolParamType.STRING, "合并理由（可选）", False),
            _tool_param("reviewed_by", ToolParamType.STRING, "操作人标识，默认 llm_tool", False),
        ],
    )
    async def handle_merge_game_knowledge_cards(
        self,
        source_card_id: int,
        target_card_id: int,
        reason: str = "",
        reviewed_by: str = "llm_tool",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        _ = kwargs
        source = self._parse_card_id(source_card_id)
        target = self._parse_card_id(target_card_id)
        if source is None or target is None:
            return {"success": False, "error": "source_card_id 和 target_card_id 必须是正整数", "message": "卡片 ID 非法"}
        kernel = await self._get_kernel()
        store = kernel.metadata_store
        if store is None:
            return {"success": False, "error": "metadata_store 未就绪", "message": "metadata_store 未就绪"}
        try:
            result = store.merge_knowledge_card_into(
                source_card_id=source,
                target_card_id=target,
                actor_id=str(reviewed_by or "llm_tool").strip() or "llm_tool",
                reason=str(reason or "").strip(),
            )
        except Exception as exc:
            logger.warning(f"合并卡片失败: source={source}, target={target}, error={exc}")
            return {"success": False, "error": str(exc), "message": f"合并失败: {exc}"}
        if result.get("success", False):
            return {**result, "message": f"已把 #{source} 合并到 #{target}"}
        return {**result, "message": str(result.get("error", "") or "合并失败")}

    @staticmethod
    def _parse_card_id(card_id: Any) -> Optional[int]:
        try:
            parsed = int(card_id)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return min(maximum, max(minimum, parsed))

    @Tool("game_knowledge_stats", description="获取 GameKnowledge 统计", parameters=[])
    async def handle_game_knowledge_stats(self, **kwargs: Any) -> Dict[str, Any]:
        _ = kwargs
        kernel = await self._get_kernel()
        return kernel.memory_stats()

    # ==================== 命令 ====================

    @Command(
        "game_knowledge",
        description="游戏知识库命令集",
        pattern=r"(?P<gkb_command>^/gkb(?:\s+\S+)*\s*$)",
    )
    async def handle_gkb_command(
        self,
        stream_id: str = "",
        platform: str = "",
        user_id: str = "",
        matched_groups: dict | None = None,
        **kwargs: Any,
    ):
        """处理 /gkb 命令集"""
        raw_command = (matched_groups or {}).get("gkb_command", "").strip()
        parts = raw_command.split() if raw_command else ["/gkb"]
        args = parts[1:] if len(parts) > 1 else []

        sub = args[0].lower() if args else "help"

        if sub == "search":
            result = await self._cmd_search(" ".join(args[1:]), {"chat_id": stream_id})
        elif sub == "analyze":
            result = await self._cmd_analyze({"chat_id": stream_id})
        elif sub == "pending":
            result = await self._cmd_pending()
        elif sub == "approve":
            result = await self._cmd_approve(args[1:] if len(args) > 1 else [])
        elif sub == "reject":
            result = await self._cmd_reject(args[1:] if len(args) > 1 else [])
        elif sub == "merge":
            result = await self._cmd_merge(args[1:] if len(args) > 1 else [])
        elif sub == "stats":
            result = await self._cmd_stats()
        elif sub == "help":
            result = self._cmd_help()
        else:
            result = f"未知命令: {sub}\n{self._cmd_help()}"

        if stream_id:
            await self.ctx.send.text(result, stream_id)
        return True, result, 2

    def _cmd_help(self) -> str:
        return (
            "GameKnowledge 命令:\n"
            "/gkb search <关键词> - 搜索游戏知识\n"
            "/gkb analyze - 手动触发当前群聊分析\n"
            "/gkb pending - 查看待审核卡片数\n"
            "/gkb approve <id> - 审核通过卡片\n"
            "/gkb reject <id> - 拒绝卡片\n"
            "/gkb merge <source_id> <target_id> - 把源卡合并到目标卡（解决相似/重复）\n"
            "/gkb stats - 查看统计"
        )

    async def _cmd_search(self, query: str, context: Dict[str, Any]) -> str:
        if not query.strip():
            return "请输入搜索关键词"
        kernel = await self._get_kernel()
        result = await kernel.search_memory(
            KernelSearchRequest(
                query=query,
                limit=5,
                mode="aggregate",
                chat_id=str(context.get("chat_id", "") or ""),
                group_id=str(context.get("chat_id", "") or ""),
            )
        )
        hits = result.get("hits", [])
        if not hits:
            return "未找到相关游戏知识"
        lines = ["搜索结果:"]
        for i, hit in enumerate(hits[:5], 1):
            content = str(hit.get("content", "") or "")[:120]
            lines.append(f"{i}. {content}")
        return "\n".join(lines)

    async def _cmd_analyze(self, context: Dict[str, Any]) -> str:
        stream_id = str(context.get("chat_id", "") or "")
        buffer = self._message_buffer.get(stream_id, [])
        if len(buffer) < 3:
            return "当前群聊消息不足，无法分析"
        try:
            analyzer = self._get_analyzer()
            result = await analyzer.analyze_messages(buffer, stream_id=stream_id)
            cards = result.get("cards", [])
            if not cards:
                self._message_buffer[stream_id] = []
                return "未提取到有价值的游戏知识"
            if self._review_queue is None:
                return "审核队列未就绪"
            submit = await self._review_queue.submit_cards(cards, stream_id=stream_id)
            if not submit.get("success", False):
                return f"分析完成，但提交审核队列失败: {submit.get('error', '未知错误')}"
            self._message_buffer[stream_id] = []
            return f"分析完成，提交 {submit.get('submitted', 0)} 张卡片到审核队列"
        except Exception as exc:
            logger.warning(f"手动分析失败: {exc}")
            return f"分析失败: {exc}"

    async def _cmd_pending(self) -> str:
        if self._review_queue is None:
            return "审核队列未就绪"
        stats = self._review_queue.get_stats()
        return (
            f"待审核: {stats['pending']} | 已通过: {stats['approved']} | "
            f"已拒绝: {stats['rejected']} | AI已拒绝: {stats.get('ai_rejected', 0)}"
        )

    async def _cmd_approve(self, args: List[str]) -> str:
        if not args:
            return "用法: /gkb approve <卡片ID>"
        if self._review_queue is None:
            return "审核队列未就绪"
        try:
            card_id = int(args[0])
        except ValueError:
            return "卡片ID必须是数字"
        result = await self._review_queue.approve_card(card_id)
        if result.get("success"):
            return f"卡片 {card_id} 审核通过" + (" 并已写入知识库" if result.get("ingested") else "")
        return f"审核失败: {result.get('error', '未知错误')}"

    async def _cmd_reject(self, args: List[str]) -> str:
        if not args:
            return "用法: /gkb reject <卡片ID>"
        if self._review_queue is None:
            return "审核队列未就绪"
        try:
            card_id = int(args[0])
        except ValueError:
            return "卡片ID必须是数字"
        result = await self._review_queue.reject_card(card_id)
        return f"卡片 {card_id} 已拒绝" if result.get("success") else f"操作失败: {result.get('error', '')}"

    async def _cmd_merge(self, args: List[str]) -> str:
        if len(args) < 2:
            return "用法: /gkb merge <source_id> <target_id>"
        try:
            source_id = int(args[0])
            target_id = int(args[1])
        except ValueError:
            return "卡片ID必须是数字"
        if source_id == target_id:
            return "源卡和目标卡不能相同"
        kernel = await self._get_kernel()
        store = kernel.metadata_store
        if store is None:
            return "metadata_store 未就绪"
        try:
            result = store.merge_knowledge_card_into(
                source_card_id=source_id,
                target_card_id=target_id,
                actor_id="chat_cmd",
                reason=" ".join(args[2:]) if len(args) > 2 else "",
            )
        except Exception as exc:
            logger.warning(f"/gkb merge 失败: {exc}")
            return f"合并失败: {exc}"
        if result.get("success", False):
            return f"已把 #{source_id} 合并到 #{target_id}"
        return f"合并失败: {result.get('error', '未知错误')}"

    async def _cmd_stats(self) -> str:
        kernel = await self._get_kernel()
        stats = kernel.memory_stats()
        lines = [
            "GameKnowledge 统计:",
            f"段落: {stats.get('paragraphs', stats.get('paragraph_count', 0))}",
            f"实体: {stats.get('entities', stats.get('entity_count', 0))}",
            f"关系: {stats.get('relations', stats.get('relation_count', 0))}",
        ]
        if self._review_queue is not None:
            review_stats = self._review_queue.get_stats()
            lines.append(
                f"审核队列: 待审={review_stats['pending']} 通过={review_stats['approved']} "
                f"拒绝={review_stats['rejected']} AI拒绝={review_stats.get('ai_rejected', 0)}"
            )
        return "\n".join(lines)

    # ==================== 消息采集 ====================

    @HookHandler(
        "chat.receive.after_process",
        mode=HookMode.OBSERVE,
        description="采集群聊消息并按阈值提交游戏知识审核队列",
    )
    async def on_message(self, hook_name: str, message: Dict[str, Any], **kwargs: Any) -> None:
        """采集群聊消息到缓冲区，达到阈值后自动分析。"""
        del hook_name, kwargs
        if not self.config.plugin.enabled:
            self.ctx.logger.warning("插件已禁用，跳过消息采集")
            return
        if not self.config.collector.enabled:
            self.ctx.logger.warning("采集器已禁用，跳过消息采集（建议开启: collector.enabled=true）")
            return
        runtime_stream_id = self._extract_runtime_stream_id(message)
        stream_id = runtime_stream_id or self._extract_stream_id(message)
        group_id = self._extract_group_id(message)
        platform = self._extract_platform(message)
        user_id = self._extract_user_id(message)
        if not stream_id:
            return
        if platform and user_id:
            # is_bot_self import removed - use local helper instead
            if self._check_is_bot_self(platform, user_id):
                self.ctx.logger.debug(f"跳过机器人自身消息采集: platform={platform}, stream={stream_id}")
                return
        if not self._is_group_whitelisted(group_id):
            self.ctx.logger.debug(f"跳过非白名单群消息采集: group={group_id or '(empty)'}, stream={stream_id}")
            return
        normalized_message = self._normalize_message_for_buffer(message)
        content = normalized_message["content"]
        min_length = max(1, int(self.config.collector.min_message_length or 1))
        if len(content) < min_length:
            return

        self._message_buffer.setdefault(stream_id, [])
        self._message_buffer[stream_id].append(normalized_message)
        context_length = max(1, int(self.config.collector.context_length or 1))
        if len(self._message_buffer[stream_id]) > context_length:
            self._message_buffer[stream_id] = self._message_buffer[stream_id][-context_length:]
        buffer_size = len(self._message_buffer[stream_id])
        threshold = max(1, int(self.config.collector.auto_analyze_threshold or 1))

        if buffer_size >= threshold:
            self._schedule_auto_analyze(stream_id)

        # 留言板答案收集：如果该群有 collecting 状态的主题，把这条群消息计入候选答案楼层
        try:
            await self._collect_board_answer_message(
                group_id=group_id,
                normalized_message=normalized_message,
                source_user_id=user_id,
                source_message_id=str(message.get("message_id", "") or message.get("id", "") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"留言板答案收集异常: {exc}")

    async def _collect_board_answer_message(
        self,
        *,
        group_id: str,
        normalized_message: Dict[str, Any],
        source_user_id: str,
        source_message_id: str,
    ) -> None:
        """如果当前群有 collecting 状态主题，把这条群消息计入答案楼层。

        到达上限（20 条）会立即触发 finalize；超时由 ``_scan_board_collecting_expired`` 兜底。
        """

        clean_group = str(group_id or "").strip()
        if not clean_group:
            return
        if self._board_service is None and self._board_store is None:
            # 还未通过 web 路径触发懒加载，主动取一次
            await self._get_board_service()
        if self._board_service is None:
            return
        store = self._board_service.store
        active = store.list_collecting_in_group(clean_group)
        if not active:
            return
        content = str(normalized_message.get("content", "") or "").strip()
        if not content:
            return
        nickname = str(normalized_message.get("sender_name", "") or "")
        for thread in active:
            count = store.append_collected_qq_post(
                int(thread.get("id") or 0),
                content=content,
                source_user_id=source_user_id,
                source_message_id=source_message_id,
                author_nickname=nickname,
            )
            if count >= self.BOARD_COLLECT_MAX_MESSAGES:
                await self._finalize_collected_board_thread(int(thread.get("id") or 0), reason="count")

    def _schedule_auto_analyze(self, stream_id: str) -> None:
        active_task = self._auto_analyze_tasks.get(stream_id)
        if active_task is not None and not active_task.done():
            return
        backoff_until = self._empty_analyze_until.get(stream_id, 0.0)
        if backoff_until and time.time() < backoff_until:
            return
        buffer = list(self._message_buffer.get(stream_id, []))
        if not buffer:
            return
        self._message_buffer[stream_id] = []
        logger.info(f"[GK分析] 调度自动分析: stream={stream_id[:30]} msgs={len(buffer)}")
        task = asyncio.create_task(self._auto_analyze(stream_id, buffer))
        self._auto_analyze_tasks[stream_id] = task

        def _cleanup(done_task: asyncio.Task[bool], current_stream_id: str = stream_id) -> None:
            current = self._auto_analyze_tasks.get(current_stream_id)
            if current is done_task:
                self._auto_analyze_tasks.pop(current_stream_id, None)
            succeeded = False
            try:
                succeeded = bool(done_task.result())
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(f"自动分析任务异常退出: stream={current_stream_id}, error={exc}")
            if not succeeded:
                return
            threshold = max(1, int(self.config.collector.auto_analyze_threshold or 1))
            if len(self._message_buffer.get(current_stream_id, [])) >= threshold:
                self._schedule_auto_analyze(current_stream_id)

        task.add_done_callback(_cleanup)

    def _restore_messages_to_buffer(self, stream_id: str, messages: List[Dict[str, Any]]) -> None:
        if not messages:
            return
        merged = list(messages) + list(self._message_buffer.get(stream_id, []))
        context_length = max(1, int(self.config.collector.context_length or 1))
        self._message_buffer[stream_id] = merged[-context_length:]

    async def _auto_analyze(self, stream_id: str, buffer: List[Dict[str, Any]]) -> bool:
        """自动分析缓冲区消息，返回 True 表示分析+提交成功。"""
        if not buffer:
            return False
        short_stream = stream_id[:30]
        try:
            analyzer = self._get_analyzer()
            result = await analyzer.analyze_messages(buffer, stream_id=stream_id)
            cards = result.get("cards", [])
            if not cards:
                raw = int(result.get("raw_card_count", 0) or 0)
                dropped = int(result.get("dropped_card_count", 0) or 0)
                ai_reviewed = int(result.get("ai_reviewed", 0) or 0)
                ai_rejected = int(result.get("ai_rejected", 0) or 0)
                ai_review_errors = int(result.get("ai_review_errors", 0) or 0)
                logger.info(
                    f"[GK分析] 本轮无可入库卡片: stream={short_stream} msgs={len(buffer)} "
                    f"raw={raw} dropped={dropped} "
                    f"ai_reviewed={ai_reviewed} ai_rejected={ai_rejected} "
                    f"ai_review_errors={ai_review_errors},下一次触发将延后 "
                    f"{int(self.EMPTY_ANALYZE_BACKOFF_SECONDS)}s"
                )
                self._empty_analyze_until[stream_id] = time.time() + self.EMPTY_ANALYZE_BACKOFF_SECONDS
                self._restore_messages_to_buffer(stream_id, buffer)
                return False
            if self._review_queue is None:
                logger.warning(f"自动分析完成但审核队列未就绪: stream={short_stream}, cards={len(cards)}")
                return False
            submit = await self._review_queue.submit_cards(cards, stream_id=stream_id)
            if submit.get("success", False):
                submitted = int(submit.get("submitted", len(cards)) or len(cards))
                logger.info(
                    f"[GK分析] 自动分析完成: stream={short_stream} cards={len(cards)} "
                    f"submitted={submitted} ai_reviewed={int(result.get('ai_reviewed', 0) or 0)} "
                    f"ai_rejected={int(result.get('ai_rejected', 0) or 0)}"
                )
                self._empty_analyze_until.pop(stream_id, None)
                return True
            else:
                logger.warning(
                    f"[GK分析] 提交审核队列失败: stream={short_stream} cards={len(cards)} "
                    f"error={submit.get('error', '未知错误')}"
                )
                self._restore_messages_to_buffer(stream_id, buffer)
                return False
        except asyncio.CancelledError:
            self._restore_messages_to_buffer(stream_id, buffer)
            raise
        except Exception as exc:
            logger.warning(f"[GK分析] 自动分析失败: stream={short_stream} error={exc}")
            self._restore_messages_to_buffer(stream_id, buffer)
            return False

    async def _db_maintenance_loop(self) -> None:
        """后台定时执行数据库维护（每 6 小时一次）。单次失败不退出循环。"""
        maintenance_interval = 6 * 3600
        while True:
            try:
                await asyncio.sleep(maintenance_interval)
            except asyncio.CancelledError:
                return
            try:
                kernel = await self._get_kernel()
                store = getattr(kernel, "metadata_store", None)
                if store is not None and hasattr(store, "run_maintenance"):
                    result = store.run_maintenance()
                    if result.get("ok"):
                        logger.debug("数据库定期维护完成")
                    else:
                        logger.warning(f"数据库定期维护异常: {result}")
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"数据库维护单次失败，下一周期再试: {exc}")


def create_plugin() -> GameKnowledgePlugin:
    return GameKnowledgePlugin()
