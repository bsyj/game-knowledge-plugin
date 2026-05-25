"""GameKnowledge plugin configuration."""

from __future__ import annotations

from typing import List

from maibot_sdk import Field, PluginConfigBase


class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用 GameKnowledge")
    config_version: str = Field(default="1.0.2", description="配置版本")


class StorageConfig(PluginConfigBase):
    __ui_label__ = "存储"
    __ui_icon__ = "database"
    __ui_order__ = 1

    data_dir: str = Field(default="data/game-knowledge", description="游戏知识数据目录")


class EmbeddingConfig(PluginConfigBase):
    __ui_label__ = "Embedding"
    __ui_icon__ = "layers"
    __ui_order__ = 2

    dimension: int = Field(default=1024, description="默认向量维度")
    batch_size: int = Field(default=32, description="批量编码大小")
    max_concurrent: int = Field(default=5, description="最大并发请求数")
    model_name: str = Field(default="auto", description="Embedding 模型名")
    enable_cache: bool = Field(default=False, description="是否启用嵌入缓存")
    min_train_threshold: int = Field(default=40, description="向量索引训练阈值")


class WebConfig(PluginConfigBase):
    __ui_label__ = "独立 WebUI"
    __ui_icon__ = "globe"
    __ui_order__ = 3

    enabled: bool = Field(default=True, description="是否启用独立 WebUI")
    host: str = Field(default="127.0.0.1", description="监听地址")
    port: int = Field(default=5810, description="监听端口")
    cleanup_stale_runner_on_port_conflict: bool = Field(
        default=True,
        description="端口被同一 MaiBot 旧 Runner 占用时自动清理并重试启动 WebUI",
    )


class EpisodeConfig(PluginConfigBase):
    __ui_label__ = "Episode"
    __ui_icon__ = "book-open"
    __ui_order__ = 4

    enabled: bool = Field(default=False, description="是否启用 Episode 情景记忆检索")
    generation_enabled: bool = Field(default=False, description="是否自动生成 Episode")
    pending_batch_size: int = Field(default=12, description="待处理批量大小")
    pending_max_retry: int = Field(default=3, description="最大重试次数")


class CollectorConfig(PluginConfigBase):
    __ui_label__ = "消息采集"
    __ui_icon__ = "message-circle"
    __ui_order__ = 5

    enabled: bool = Field(default=True, description="是否启用群聊消息自动采集")
    allowed_source_group_ids: List[str] = Field(
        default_factory=list,
        description="允许采集/分析的群 ID 白名单；留空表示不限制（采集所有群）",
    )
    auto_analyze_threshold: int = Field(default=30, description="自动分析触发阈值（消息数）")
    min_message_length: int = Field(default=3, description="消息最小长度")
    context_length: int = Field(default=50, description="上下文保留消息数")
    llm_task_name: str = Field(default="utils", description="游戏知识抽取使用的 MaiBot 模型任务名")
    enable_ai_review: bool = Field(default=True, description="是否启用游戏知识 AI 预审核")
    ai_review_task_name: str = Field(default="utils", description="游戏知识 AI 预审核使用的 MaiBot 模型任务名")
    ai_review_error_status: str = Field(default="pending", description="AI 预审核失败时写入的审核状态")


class AdvancedConfig(PluginConfigBase):
    __ui_label__ = "高级"
    __ui_icon__ = "settings"
    __ui_order__ = 6

    enable_auto_save: bool = Field(default=True, description="是否自动保存")
    auto_save_interval_minutes: int = Field(default=5, description="自动保存间隔")
    debug: bool = Field(default=False, description="调试日志")


class GameKnowledgePluginConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    episode: EpisodeConfig = Field(default_factory=EpisodeConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    advanced: AdvancedConfig = Field(default_factory=AdvancedConfig)
