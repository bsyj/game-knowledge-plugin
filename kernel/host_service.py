from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence

import tomlkit

from gk_shims.logger_shim import get_logger
from gk_shims.toml_utils_shim import _update_toml_doc

from .paths import repo_root, schema_path
from .core.utils.review_queue_service import ReviewQueueService
from .runtime_registry import set_runtime_kernel

if TYPE_CHECKING:
    from .core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("game_knowledge.host_service")

_INTERNAL_CONFIG_FIELDS = {"field_docs", "_validate_any", "suppress_any_warning"}


def _get_config_manager():
    from gk_shims.config_shim import config_manager

    return config_manager


def _get_bot_config_path() -> Path:
    # In plugin mode, use the plugin's own config.toml
    from .paths import package_root
    return package_root().parent / "config.toml"


def _to_builtin_data(obj: Any) -> Any:
    if hasattr(obj, "unwrap"):
        try:
            obj = obj.unwrap()
        except Exception:
            pass

    if isinstance(obj, dict):
        return {str(key): _to_builtin_data(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_to_builtin_data(value) for value in obj]
    return obj


def _strip_internal_config_fields(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            str(key): _strip_internal_config_fields(value)
            for key, value in obj.items()
            if str(key) not in _INTERNAL_CONFIG_FIELDS
        }
    if isinstance(obj, list):
        return [_strip_internal_config_fields(value) for value in obj]
    return obj


def _backup_config_file(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup_name = f"{path.name}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    backup_path = path.parent / backup_name
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


class GameKnowledgeHostService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._kernel: Optional[SDKMemoryKernel] = None
        self._review_queue: Optional[ReviewQueueService] = None
        self._config_cache: Dict[str, Any] | None = None
        self._reload_callback_registered = False

    async def start(self) -> None:
        if not self.is_enabled():
            logger.info("GameKnowledge 宿主服务未启用，跳过 GameKnowledge 宿主运行时初始化（插件入口不受影响）")
            return
        await self._ensure_kernel()

    async def stop(self) -> None:
        async with self._lock:
            await self._shutdown_locked()

    async def reload(self) -> None:
        async with self._lock:
            await self._shutdown_locked()
            self._config_cache = None
            config = self._read_config()

        if self._is_enabled_config(config):
            await self._ensure_kernel()
        else:
            logger.info("GameKnowledge 配置为未启用，运行时保持关闭")

    def get_config_path(self) -> Path:
        return _get_bot_config_path()

    def get_schema_path(self) -> Path:
        return schema_path()

    def get_config_schema(self) -> Dict[str, Any]:
        path = self.get_schema_path()
        if not path.exists():
            return {
                "plugin_id": "game_knowledge",
                "plugin_info": {
                    "name": "GameKnowledge",
                    "version": "",
                    "description": "GameKnowledge 配置结构",
                    "author": "A_Dawn",
                },
                "sections": {},
                "layout": {"type": "auto", "tabs": []},
            }

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def get_config(self) -> Dict[str, Any]:
        return dict(self._read_config())

    def is_enabled(self) -> bool:
        return self._is_enabled_config(self._read_config())

    @staticmethod
    def _is_enabled_config(config: Dict[str, Any]) -> bool:
        plugin_config = config.get("plugin") if isinstance(config, dict) else None
        if not isinstance(plugin_config, dict):
            return True
        return bool(plugin_config.get("enabled", True))

    def _build_default_config(self) -> Dict[str, Any]:
        return {
            "plugin": {"enabled": True},
            "storage": {"data_dir": "data/game-knowledge"},
            "embedding": {
                "dimension": 1024,
                "batch_size": 32,
                "max_concurrent": 5,
                "model_name": "auto",
                "enable_cache": False,
            },
            "collector": {
                "enabled": True,
                "auto_analyze_threshold": 30,
                "min_message_length": 5,
                "context_length": 50,
                "llm_task_name": "utils",
                "enable_ai_review": True,
                "ai_review_task_name": "utils",
                "ai_review_error_status": "pending",
            },
            "web": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 5810,
            },
            "episode": {
                "enabled": False,
                "generation_enabled": False,
                "pending_batch_size": 12,
                "pending_max_retry": 3,
            },
            "advanced": {
                "enable_auto_save": True,
                "auto_save_interval_minutes": 5,
            },
        }

    def get_raw_config_with_meta(self) -> Dict[str, Any]:
        config = self.get_config()
        default_config = self._build_default_config()
        raw_doc = tomlkit.document()
        raw_doc.add("game_knowledge", config)
        return {
            "config": tomlkit.dumps(raw_doc),
            "exists": self.get_config_path().exists(),
            "using_default": config == default_config,
        }

    def get_raw_config(self) -> str:
        payload = self.get_raw_config_with_meta()
        return str(payload.get("config", "") or "")

    async def update_raw_config(self, raw_config: str) -> Dict[str, Any]:
        loaded = tomlkit.loads(raw_config)
        raw_payload = _to_builtin_data(loaded) if isinstance(loaded, dict) else {}
        config_payload = raw_payload.get("game_knowledge") if isinstance(raw_payload.get("game_knowledge"), dict) else raw_payload
        path, backup_path = await self._write_config_to_bot_config(config_payload)
        return {
            "success": True,
            "message": "配置已保存",
            "backup_path": str(backup_path) if backup_path is not None else "",
            "config_path": str(path),
        }

    async def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        path, backup_path = await self._write_config_to_bot_config(config)
        return {
            "success": True,
            "message": "配置已保存",
            "backup_path": str(backup_path) if backup_path is not None else "",
            "config_path": str(path),
        }

    async def invoke(self, component_name: str, args: Dict[str, Any] | None = None, *, timeout_ms: int = 30000) -> Any:
        del timeout_ms
        payload = args or {}
        if not self.is_enabled():
            return self._disabled_response(component_name)
        kernel = await self._ensure_kernel()

        if component_name == "search_memory":
            from .core.runtime.sdk_memory_kernel import KernelSearchRequest

            return await kernel.search_memory(
                KernelSearchRequest(
                    query=str(payload.get("query", "") or ""),
                    limit=int(payload.get("limit", 5) or 5),
                    mode=str(payload.get("mode", "search") or "search"),
                    chat_id=str(payload.get("chat_id", "") or ""),
                    time_start=payload.get("time_start"),
                    time_end=payload.get("time_end"),
                    respect_filter=bool(payload.get("respect_filter", True)),
                    user_id=str(payload.get("user_id", "") or "").strip(),
                    group_id=str(payload.get("group_id", "") or "").strip(),
                )
            )

        if component_name == "enqueue_feedback_task":
            return await kernel.enqueue_feedback_task(
                query_tool_id=str(payload.get("query_tool_id", "") or ""),
                session_id=str(payload.get("session_id", "") or ""),
                query_timestamp=payload.get("query_timestamp"),
                structured_content=payload.get("structured_content")
                if isinstance(payload.get("structured_content"), dict)
                else {},
            )

        if component_name == "ingest_summary":
            return await kernel.ingest_summary(
                external_id=str(payload.get("external_id", "") or ""),
                chat_id=str(payload.get("chat_id", "") or ""),
                text=str(payload.get("text", "") or ""),
                participants=list(payload.get("participants") or []),
                time_start=payload.get("time_start"),
                time_end=payload.get("time_end"),
                tags=list(payload.get("tags") or []),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                respect_filter=bool(payload.get("respect_filter", True)),
                user_id=str(payload.get("user_id", "") or "").strip(),
                group_id=str(payload.get("group_id", "") or "").strip(),
            )

        if component_name == "ingest_text":
            relations = payload.get("relations") if isinstance(payload.get("relations"), list) else []
            entities = payload.get("entities") if isinstance(payload.get("entities"), list) else []
            return await kernel.ingest_text(
                external_id=str(payload.get("external_id", "") or ""),
                source_type=str(payload.get("source_type", "") or ""),
                text=str(payload.get("text", "") or ""),
                chat_id=str(payload.get("chat_id", "") or ""),
                participants=list(payload.get("participants") or []),
                timestamp=payload.get("timestamp"),
                time_start=payload.get("time_start"),
                time_end=payload.get("time_end"),
                tags=list(payload.get("tags") or []),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                entities=entities,
                relations=relations,
                respect_filter=bool(payload.get("respect_filter", True)),
                user_id=str(payload.get("user_id", "") or "").strip(),
                group_id=str(payload.get("group_id", "") or "").strip(),
            )

        if component_name == "maintain_memory":
            return await kernel.maintain_memory(
                action=str(payload.get("action", "") or ""),
                target=str(payload.get("target", "") or ""),
                hours=payload.get("hours"),
                reason=str(payload.get("reason", "") or ""),
                limit=max(1, int(payload.get("limit", 50) or 50)),
            )

        if component_name == "memory_stats":
            return kernel.memory_stats()

        admin_actions = {
            "memory_graph_admin": kernel.memory_graph_admin,
            "memory_source_admin": kernel.memory_source_admin,
            "memory_episode_admin": kernel.memory_episode_admin,
            "memory_feedback_admin": kernel.memory_feedback_admin,
            "memory_runtime_admin": kernel.memory_runtime_admin,
            "memory_import_admin": kernel.memory_import_admin,
            "memory_tuning_admin": kernel.memory_tuning_admin,
            "memory_v5_admin": kernel.memory_v5_admin,
            "memory_delete_admin": kernel.memory_delete_admin,
        }
        if component_name in admin_actions:
            kwargs = dict(payload)
            action = str(kwargs.pop("action", "") or "")
            return await admin_actions[component_name](action=action, **kwargs)

        if component_name == "review_queue_admin":
            return await self._handle_review_queue_admin(payload)

        raise RuntimeError(f"不支持的 GameKnowledge 调用: {component_name}")

    async def _ensure_kernel(self) -> SDKMemoryKernel:
        async with self._lock:
            if self._kernel is None:
                from .core.runtime.sdk_memory_kernel import SDKMemoryKernel

                config = self._read_config()
                if not self._is_enabled_config(config):
                    raise RuntimeError("GameKnowledge 未启用")
                kernel = SDKMemoryKernel(plugin_root=repo_root(), config=config)
                try:
                    await kernel.initialize()
                except Exception:
                    kernel.close()
                    raise
                self._kernel = kernel
                self._review_queue = ReviewQueueService(kernel=kernel)
                set_runtime_kernel(kernel)
            return self._kernel

    def _read_config(self) -> Dict[str, Any]:
        if self._config_cache is not None:
            return dict(self._config_cache)

        path = self.get_config_path()
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    doc = tomlkit.load(handle)
                config_payload = _to_builtin_data(doc).get("game_knowledge")
                if isinstance(config_payload, dict):
                    self._config_cache = self._config_model_to_runtime_dict(config_payload)
                    return dict(self._config_cache)
        except Exception as exc:
            logger.warning(f"读取 GameKnowledge 主配置失败，使用默认值: {exc}")

        self._config_cache = self._build_default_config()
        return dict(self._config_cache)

    @staticmethod
    def _config_model_to_runtime_dict(config_model: Any) -> Dict[str, Any]:
        if isinstance(config_model, dict):
            payload = dict(config_model)
        elif hasattr(config_model, "model_dump"):
            payload = config_model.model_dump(mode="json")
        else:
            payload = {}
        storage_config = payload.setdefault("storage", {})
        if isinstance(storage_config, dict):
            storage_config["data_dir"] = "data/game-knowledge"
        web_config = payload.get("web")
        if isinstance(web_config, dict) and "import_config" in web_config:
            web_config["import"] = web_config.pop("import_config")
        payload = _to_builtin_data(payload) if isinstance(payload, dict) else {}
        return _strip_internal_config_fields(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _runtime_dict_to_bot_config_dict(config: Dict[str, Any]) -> Dict[str, Any]:
        payload = _to_builtin_data(config)
        if not isinstance(payload, dict):
            return {}
        payload = _strip_internal_config_fields(payload)
        web_config = payload.get("web")
        if isinstance(web_config, dict) and "import_config" in web_config and "import" not in web_config:
            web_config["import"] = web_config.pop("import_config")
        return payload

    async def _write_config_to_bot_config(self, config: Dict[str, Any]) -> tuple[Path, Optional[Path]]:
        path = self.get_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = _backup_config_file(path)
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                doc = tomlkit.load(handle)
        else:
            doc = tomlkit.document()

        bot_config_payload = self._runtime_dict_to_bot_config_dict(config)
        current = doc.get("game_knowledge")
        if isinstance(current, dict):
            _update_toml_doc(current, bot_config_payload)
        else:
            doc["game_knowledge"] = bot_config_payload

        with path.open("w", encoding="utf-8") as handle:
            tomlkit.dump(doc, handle)

        await _get_config_manager().reload_config(changed_scopes=("bot",))
        if not self._reload_callback_registered:
            await self.reload()
        return path, backup_path

    def register_config_reload_callback(self) -> None:
        if self._reload_callback_registered:
            return
        _get_config_manager().register_reload_callback(self.on_config_reload)
        self._reload_callback_registered = True

    async def on_config_reload(self, changed_scopes: Sequence[str] | None = None) -> None:
        normalized = {str(scope or "").strip().lower() for scope in (changed_scopes or [])}
        if normalized and "bot" not in normalized:
            return
        await self.reload()

    @staticmethod
    def _disabled_response(component_name: str) -> Dict[str, Any]:
        reason = "game_knowledge_disabled"
        message = "GameKnowledge 宿主服务未启用，请在 GameKnowledge 宿主配置中开启后再使用。"

        if component_name == "search_memory":
            return {
                "success": True,
                "disabled": True,
                "reason": reason,
                "summary": "",
                "hits": [],
                "filtered": False,
            }

        if component_name in {"ingest_summary", "ingest_text"}:
            return {
                "success": True,
                "disabled": True,
                "reason": reason,
                "stored_ids": [],
                "skipped_ids": [reason],
                "detail": reason,
            }

        if component_name == "memory_stats":
            return {
                "success": True,
                "enabled": False,
                "disabled": True,
                "reason": reason,
                "message": message,
                "paragraph_count": 0,
                "relation_count": 0,
                "episode_count": 0,
            }

        if component_name == "memory_runtime_admin":
            return {
                "success": True,
                "enabled": False,
                "disabled": True,
                "reason": reason,
                "message": message,
                "runtime_ready": False,
                "embedding_degraded": False,
                "embedding_dimension": 0,
                "auto_save": False,
                "data_dir": "",
            }

        if component_name == "enqueue_feedback_task":
            return {
                "success": True,
                "queued": False,
                "disabled": True,
                "reason": reason,
            }

        return {
            "success": False,
            "enabled": False,
            "disabled": True,
            "reason": reason,
            "error": message,
        }

    async def _shutdown_locked(self) -> None:
        if self._kernel is None:
            return
        shutdown = getattr(self._kernel, "shutdown", None)
        if callable(shutdown):
            await shutdown()
        else:
            self._kernel.close()
        self._kernel = None
        self._review_queue = None
        set_runtime_kernel(None)

    async def _handle_review_queue_admin(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        kernel = await self._ensure_kernel()
        review_queue = self._review_queue or ReviewQueueService(kernel=kernel)
        self._review_queue = review_queue
        action = str(payload.get("action", "") or "").strip().lower()

        if action == "stats":
            stats = review_queue.get_stats()
            return {"success": True, "stats": stats, **stats}

        if action == "list":
            status = str(payload.get("status", "") or "").strip()
            category = str(payload.get("category", "") or "").strip()
            platform = str(payload.get("platform", "") or "").strip()
            source_group_id = str(payload.get("source_group_id", "") or "").strip()
            source_group_name = str(payload.get("source_group_name", "") or "").strip()
            keyword = str(payload.get("keyword", "") or "").strip()
            limit = max(1, min(500, int(payload.get("limit", 50) or 50)))
            offset = max(0, int(payload.get("offset", 0) or 0))
            store = kernel.metadata_store
            if store is None:
                return {"success": False, "cards": [], "count": 0, "error": "metadata_store 未就绪"}
            cards = store.list_knowledge_cards(
                status=status,
                category=category,
                platform=platform,
                source_group_id=source_group_id,
                source_group_name=source_group_name,
                keyword=keyword,
                limit=limit,
                offset=offset,
            )
            return {"success": True, "cards": cards, "count": len(cards)}

        if action == "groups":
            limit = max(1, min(1000, int(payload.get("limit", 200) or 200)))
            store = kernel.metadata_store
            if store is None:
                return {"success": False, "groups": [], "count": 0, "error": "metadata_store 未就绪"}
            groups = store.list_knowledge_card_groups(limit=limit)
            return {"success": True, "groups": groups, "count": len(groups)}

        if action == "approve":
            card_id = int(payload.get("card_id", 0) or 0)
            return await review_queue.approve_card(card_id, reviewed_by=str(payload.get("reviewed_by", "webui") or "webui"))

        if action == "reject":
            card_id = int(payload.get("card_id", 0) or 0)
            return await review_queue.reject_card(card_id, reviewed_by=str(payload.get("reviewed_by", "webui") or "webui"))

        if action == "delete":
            card_id = int(payload.get("card_id", 0) or 0)
            return await review_queue.delete_card(card_id)

        return {"success": False, "error": f"不支持的 review_queue action: {action}"}


game_knowledge_host_service = GameKnowledgeHostService()
