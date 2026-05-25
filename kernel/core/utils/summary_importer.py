"""
聊天总结与知识导入工具

该模块负责从聊天记录中提取信息，生成总结，并将总结内容及提取的实体/关系
导入到 game_knowledge 的存储组件中。
"""
from __future__ import annotations


from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json
import re
import time
import traceback

from gk_shims.logger_shim import get_logger
from gk_shims import llm_shim as llm_api
from gk_shims import message_shim as message_api
from gk_shims.config_shim import config_manager, global_config
from gk_shims.config_shim import TaskConfig

from ..storage import (
    KnowledgeType,
    VectorStore,
    GraphStore,
    MetadataStore,
    resolve_stored_knowledge_type,
)
from ..embedding import EmbeddingAPIAdapter
from .model_routing import (
    find_text_generation_task_for_model,
    get_text_generation_model_tasks,
    pick_text_generation_task,
)
from .relation_write_service import RelationWriteService
from .runtime_self_check import ensure_runtime_self_check, run_embedding_runtime_self_check

logger = get_logger("GameKnowledge.SummaryImporter")

# 默认总结提示词模版
SUMMARY_PROMPT_TEMPLATE = """你是 {bot_name}的游戏知识提取专家。{personality_context}
从以下游戏群聊记录中提取**精准的问答对**，供另一个 AI（replyer）用来回答玩家问题。

聊天记录：
{chat_history}

════════════════════════════════════════════
提取策略（按优先级逐层筛选）
════════════════════════════════════════════
1. 显式问答 — 玩家直接问、有人直接答
   → 原样提取 Q 和 A，保留关键数值和配置项名
2. 推荐/建议 — 玩家问「xxx推荐什么」「xxx用什么装备/附魔/配置」
   → Q=“xxx推荐什么yyy”，A=群友推荐的选项（保留名称和数值）
   → 据统计：游戏群聊里推荐类问题占了约 30%，是最高频的知识类型之一
3. 隐含问答 — 玩家陈述问题、他人给出方案
   → Q="xxx怎么解决"，A=他人回复
4. 讨论结论 — 多人讨论后产生有价值的共识
   → Q=讨论核心问题，A=讨论结论
5. 无答案的问题 — 有人提问但无人回答
   → 只提取 Q，A=null（标记为待回答，后期可关联

════════════════════════════════════════════
Q 的格式规则（违反即不合格）
════════════════════════════════════════════
✅ "FTB编辑模式怎么关"
✅ "暗影词条怎么获取"
✅ "银套还免疫病毒吗"
✅ "机械升格什么时候打合适"
✅ "勇者之刃推荐什么附魔"
✅ "高级附魔台用什么材料"
✅ "龙棍怎么配附魔"
✅ "终有一死建议点到几级"
❌ "FTB相关讨论"        ← 话题概括，严禁
❌ "关于武器的内容"      ← 话题概括，严禁

════════════════════════════════════════════
A 的格式规则（违反即不合格）
════════════════════════════════════════════
✅ "在FTB Ranks配置里把 ftb.editing_mode 设为 false"
✅ "群内讨论：新版本银套只免疫寄巢之唤，不再完全免疫其他病毒"
✅ "龙前就可以打，不需要毕业装备"
✅ "设置血量200→-1即可常驻医疗护理显示"
✅ "致命一击3"          ← 推荐类 A 可以简短，但必须包含具体选项名
✅ "推荐穿透+穿刺+魔法祝福一起打"
✅ "群内推荐：冰龙斧+龙骨棍速通"
✅ "终有一死点到 5 级即可，别点太高"
❌ "群里讨论了FTB配置"   ← 无信息量，严禁
❌ "有人说可以有人说不行" ← 太模糊，严禁

要求：A 必须自包含，另一个 AI 拿着就能直接回复玩家。

════════════════════════════════════════════
示例
════════════════════════════════════════════
聊天："A: ftb编辑模式怎么关 B: ftb ranks里面把editing_mode改成false"
→ {{"q": "FTB编辑模式怎么关", "a": "在FTB Ranks配置里把 ftb.editing_mode 设为 false"}}

聊天："A: 银套现在还能免疫病毒吗 B: 德雷削了 现在只免疫寄巢之唤"
→ {{"q": "银套还免疫病毒吗", "a": "新版本德雷削弱了银套，现版本只免疫寄巢之唤，不再完全免疫其他病毒"}}

聊天："A: 勇者之刃推荐什么附魔 B: 致命一击3"
→ {{"q": "勇者之刃推荐什么附魔", "a": "致命一击3"}}

聊天："A: 为什么终有一死不建议搞太高 B: 别问 5就行了"
→ {{"q": "终有一死建议点到几级", "a": "终有一死点到5级即可，不建议更高"}}

聊天："A: 建议魔法祝福、穿刺和穿透打一起吗 B: 可以 推荐一起打"
→ {{"q": "魔法祝福穿刺穿透推荐一起打吗", "a": "推荐穿透+穿刺+魔法祝福一起打"}}

聊天："A: 有什么装备推荐 B: 推荐冰龙斧+龙骨棍速通"
→ {{"q": "前期速通推荐什么装备", "a": "群内推荐：冰龙斧+龙骨棍，可以速通"}}

聊天："A: 有人知道暗影词条怎么出吗"（无回复）
→ {{"q": "暗影词条怎么获取", "a": null}}

请严格输出 JSON（不要 markdown 代码块）：
{{
  "qa_pairs": [
    {{"q": "具体问题", "a": "具体答案或null"}},
    {{"q": "另一个问题", "a": "另一个答案"}}
  ],
  "entities": ["实体名1", "实体名2"],
  "relations": [
    {{"subject": "实体A", "predicate": "关系", "object": "实体B"}}
  ]
}}

注意：
- qa_pairs 中的 q 必须是具体的、可被搜索到的问题，a 必须是自包含且有信息量的答案。
- 没有答案的 Q 保留 a=null，后续可自动关联。
- 如果整段聊天都是闲聊，qa_pairs 为空数组 []。
- 实体名直接用中文，不要用 e1/e2 代号。
"""


def _normalize_entity_items(raw_entities: Any) -> List[str]:
    if not isinstance(raw_entities, list):
        return []
    entities: List[str] = []
    seen = set()
    for item in raw_entities:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("label") or item.get("entity") or "").strip()
        else:
            name = ""
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        entities.append(name)
    return entities


def _normalize_relation_items(raw_relations: Any) -> List[Dict[str, str]]:
    if not isinstance(raw_relations, list):
        return []
    relations: List[Dict[str, str]] = []
    for item in raw_relations:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject", "") or "").strip()
        predicate = str(item.get("predicate", "") or "").strip()
        obj = str(item.get("object", "") or "").strip()
        if not (subject and predicate and obj):
            continue
        relations.append({"subject": subject, "predicate": predicate, "object": obj})
    return relations


def _message_timestamp(message: Any) -> Optional[float]:
    for attr_name in ("timestamp", "time"):
        value = getattr(message, attr_name, None)
        if value is None:
            continue
        timestamp_func = getattr(value, "timestamp", None)
        if callable(timestamp_func):
            try:
                return float(timestamp_func())
            except Exception:
                continue
        try:
            return float(value)
        except Exception:
            continue
    return None


class SummaryImporter:
    """总结并导入知识的工具类"""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        metadata_store: MetadataStore,
        embedding_manager: EmbeddingAPIAdapter,
        plugin_config: dict
    ):
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.metadata_store = metadata_store
        self.embedding_manager = embedding_manager
        self.plugin_config = plugin_config
        self.relation_write_service: Optional[RelationWriteService] = (
            plugin_config.get("relation_write_service")
            if isinstance(plugin_config, dict)
            else None
        )

    def _allow_metadata_only_write(self) -> bool:
        plugin_instance = self.plugin_config.get("plugin_instance") if isinstance(self.plugin_config, dict) else None
        getter = getattr(plugin_instance, "get_config", None)
        if callable(getter):
            return bool(getter("embedding.fallback.allow_metadata_only_write", True))
        if isinstance(self.plugin_config, dict):
            embedding_cfg = self.plugin_config.get("embedding", {}) or {}
            fallback_cfg = embedding_cfg.get("fallback", {}) if isinstance(embedding_cfg, dict) else {}
            if isinstance(fallback_cfg, dict):
                return bool(fallback_cfg.get("allow_metadata_only_write", True))
        return True

    def _normalize_summary_model_selectors(self, raw_value: Any) -> List[str]:
        """标准化 summarization.model_name 配置。"""
        if raw_value is None:
            return ["auto"]
        if isinstance(raw_value, list):
            selectors = [str(x).strip() for x in raw_value if str(x).strip()]
            return selectors or ["auto"]
        if isinstance(raw_value, str):
            selector = raw_value.strip()
            if selector:
                logger.warning("summarization.model_name 建议使用 List[str]，当前字符串配置已兼容处理。")
                return [selector]
            return ["auto"]
        raise ValueError(
            "summarization.model_name 必须为 List[str] 或 str。"
            " 请执行 scripts/release_vnext_migrate.py migrate。"
        )

    def _pick_default_summary_task(self, available_tasks: Dict[str, TaskConfig]) -> Tuple[Optional[str], Optional[TaskConfig]]:
        """
        选择总结默认任务，避免错误落到 embedding/voice/vlm 等非文本生成任务。
        优先级：memory > utils > planner > tool_use > replyer > 其他文本生成任务。
        """
        return pick_text_generation_task(
            available_tasks,
            preferred=("memory", "utils", "planner", "tool_use", "replyer"),
        )

    @staticmethod
    def _current_model_dict() -> Dict[str, Any]:
        try:
            return getattr(config_manager.get_model_config(), "models_dict", {}) or {}
        except Exception as exc:
            logger.warning(f"读取当前模型字典失败: {exc}")
            return {}

    def _resolve_summary_model_config(self) -> Optional[Tuple[str, TaskConfig]]:
        """
        解析 summarization.model_name 为 (task_name, TaskConfig)。
        支持：
        - "auto"
        - "replyer"（任务名）
        - "some-model-name"（具体模型名）
        - ["utils:model1", "utils:model2", "replyer"]（数组混合语法）
        """
        available_tasks = get_text_generation_model_tasks(llm_api)
        if not available_tasks:
            return None

        # vNext 要求该字段为 List[str]；当配置缺失时回退到 ["auto"]，
        # 避免默认值本身触发类型校验异常。
        raw_cfg = self.plugin_config.get("summarization", {}).get("model_name", ["auto"])
        selectors = self._normalize_summary_model_selectors(raw_cfg)
        default_task_name, default_task_cfg = self._pick_default_summary_task(available_tasks)

        base_cfg: Optional[TaskConfig] = None
        base_task_name: Optional[str] = None
        model_dict = self._current_model_dict()

        def _find_task_for_model(model_name: str) -> Tuple[Optional[str], Optional[TaskConfig]]:
            return find_text_generation_task_for_model(available_tasks, model_name)

        for raw_selector in selectors:
            selector = raw_selector.strip()
            if not selector:
                continue

            if selector.lower() == "auto":
                if default_task_cfg:
                    if base_cfg is None:
                        base_cfg = default_task_cfg
                        base_task_name = default_task_name
                continue

            if ":" in selector:
                task_name, model_name = selector.split(":", 1)
                task_name = task_name.strip()
                model_name = model_name.strip()
                task_cfg = available_tasks.get(task_name)
                if not task_cfg:
                    logger.warning(f"总结模型选择器 '{selector}' 的任务 '{task_name}' 不存在，已跳过")
                    continue

                if base_cfg is None:
                    base_cfg = task_cfg
                    base_task_name = task_name

                if not model_name or model_name.lower() == "auto":
                    continue

                if model_name in task_cfg.model_list:
                    logger.info(
                        f"总结模型选择器 '{selector}' 已定位到任务 '{task_name}'；"
                        "当前 LLM 服务按任务候选列表执行，不单独覆盖具体模型。"
                    )
                else:
                    logger.warning(f"总结模型选择器 '{selector}' 的模型 '{model_name}' 不在任务 '{task_name}' 中，已跳过")
                continue

            task_cfg = available_tasks.get(selector)
            if task_cfg:
                if base_cfg is None:
                    base_cfg = task_cfg
                    base_task_name = selector
                continue

            if selector in model_dict:
                task_name, task_cfg = _find_task_for_model(selector)
                if task_name and task_cfg:
                    if base_cfg is None:
                        base_cfg = task_cfg
                        base_task_name = task_name
                    logger.info(
                        f"总结模型选择器 '{selector}' 已映射到任务 '{task_name}'；"
                        "当前 LLM 服务按任务候选列表执行，不单独覆盖具体模型。"
                    )
                    continue
                logger.warning(f"总结模型选择器 '{selector}' 未归属于任何任务，已跳过")
                continue

            logger.warning(f"总结模型选择器 '{selector}' 无法识别，已跳过")

        if base_cfg is None or not base_task_name:
            if default_task_cfg:
                if base_cfg is None:
                    base_cfg = default_task_cfg
                    base_task_name = default_task_name
            else:
                base_task_name, first_cfg = next(iter(available_tasks.items()))
                if base_cfg is None:
                    base_cfg = first_cfg

        if base_cfg is None or not base_task_name:
            return None

        template_cfg = base_cfg
        task_name_to_use = base_task_name
        return task_name_to_use, TaskConfig(
            model_list=list(template_cfg.model_list),
            max_tokens=template_cfg.max_tokens,
            temperature=template_cfg.temperature,
            slow_threshold=template_cfg.slow_threshold,
            selection_strategy=template_cfg.selection_strategy,
        )

    async def import_from_stream(
        self,
        stream_id: str,
        context_length: Optional[int] = None,
        include_personality: Optional[bool] = None,
        time_end: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        从指定的聊天流中提取记录并执行总结导入

        Args:
            stream_id: 聊天流 ID
            context_length: 总结的历史消息条数
            include_personality: 是否包含人设
            time_end: 用于截取聊天记录的时间上界（闭区间）

        Returns:
            Tuple[bool, str]: (是否成功, 结果消息)
        """
        try:
            self_check_ok, self_check_msg = await self._ensure_runtime_self_check()
            if not self_check_ok:
                return False, f"导入前自检失败: {self_check_msg}"

            # 1. 获取配置
            if context_length is None:
                context_length = self.plugin_config.get("summarization", {}).get("context_length", 50)
            
            if include_personality is None:
                include_personality = self.plugin_config.get("summarization", {}).get("include_personality", True)

            # 2. 获取历史消息
            query_time_end = time.time() if time_end is None else float(time_end)
            messages = message_api.get_messages_by_time_in_chat(
                chat_id=stream_id,
                start_time=0.0,
                end_time=query_time_end,
                limit=context_length,
                limit_mode="latest",
            )

            if not messages:
                return False, "未找到有效的聊天记录进行总结"

            # 转换为可读文本
            chat_history_text = message_api.build_readable_messages(messages)
            
            # 3. 准备提示词内容
            bot_name = global_config.bot.nickname or "机器人"
            personality_context = ""
            if include_personality:
                personality = getattr(global_config.bot, "personality", "")
                if personality:
                    personality_context = f"你的性格设定是：{personality}"

            # 4. 调用 LLM
            prompt = SUMMARY_PROMPT_TEMPLATE.format(
                bot_name=bot_name,
                personality_context=personality_context,
                chat_history=chat_history_text
            )

            resolved_model = self._resolve_summary_model_config()
            if resolved_model is None:
                return False, "未找到可用的总结模型配置"
            task_name_to_use, model_config_to_use = resolved_model

            logger.info(f"正在为流 {stream_id} 执行总结，消息条数: {len(messages)}")
            logger.info(f"总结模型任务: {task_name_to_use}")
            logger.info(f"总结模型候选列表: {model_config_to_use.model_list}")

            # 插件模式：通过宿主 SDK 调用
            plugin_ctx = self.plugin_config.get("plugin_ctx") if isinstance(self.plugin_config, dict) else None
            if plugin_ctx is not None:
                llm_proxy = getattr(plugin_ctx, "llm", None)
                sdk_generate = getattr(llm_proxy, "generate", None)
                if callable(sdk_generate):
                    raw = await sdk_generate(
                        prompt=prompt,
                        model=task_name_to_use,
                        temperature=getattr(model_config_to_use, "temperature", None),
                        max_tokens=getattr(model_config_to_use, "max_tokens", None),
                    )
                    if isinstance(raw, dict) and raw.get("success") is False:
                        return False, str(raw.get("error") or "宿主 LLM 调用失败")
                    result = llm_api.LLMServiceResult.from_response_result(
                        raw if isinstance(raw, dict) else {"response": str(raw)}
                    )
                else:
                    return False, "宿主 LLM 能力不可用"
            else:
                result = await llm_api.generate(
                    llm_api.LLMServiceRequest(
                        task_name=task_name_to_use,
                        request_type="GameKnowledge.ChatSummarization",
                        prompt=prompt,
                        temperature=getattr(model_config_to_use, "temperature", None),
                        max_tokens=getattr(model_config_to_use, "max_tokens", None),
                    )
                )
            success = bool(result.success)
            response = str(result.completion.response or "")

            if not success or not response:
                return False, "LLM 生成总结失败"

            # 5. 解析结果
            data = self._parse_llm_response(response)
            if not data:
                return False, "解析 LLM 响应失败"

            # 优先使用 qa_pairs（新格式），兼容旧 summary 字段
            qa_pairs = data.get("qa_pairs", [])
            if qa_pairs and isinstance(qa_pairs, list) and len(qa_pairs) > 0:
                # 用 qa_pairs 拼接为结构化总结文本，逐条 Q&A 换行
                lines = []
                for pair in qa_pairs:
                    q = str(pair.get("q", "")).strip()
                    a = pair.get("a")
                    if not q:
                        continue
                    if a is not None and str(a).strip():
                        lines.append(f"Q: {q}\nA: {str(a).strip()}")
                    else:
                        lines.append(f"Q: {q}\nA: 【待补充】")
                summary_text = "\n\n".join(lines)
                if not summary_text:
                    return False, "qa_pairs 中无有效问答"
            elif "summary" in data:
                # 兼容旧格式
                summary_text = str(data["summary"] or "").strip()
                if not summary_text:
                    return False, "解析 LLM 响应失败或总结为空"
            else:
                return False, "LLM 响应中既无 qa_pairs 也无 summary"
            entities = _normalize_entity_items(data.get("entities"))
            relations = _normalize_relation_items(data.get("relations"))
            msg_times = []
            for msg in messages:
                timestamp = _message_timestamp(msg)
                if timestamp is not None:
                    msg_times.append(timestamp)
            time_meta = {}
            if msg_times:
                time_meta = {
                    "event_time_start": min(msg_times),
                    "event_time_end": max(msg_times),
                    "time_granularity": "minute",
                    "time_confidence": 0.95,
                }

            # 6. 执行导入
            await self._execute_import(
                summary_text,
                entities,
                relations,
                stream_id,
                time_meta=time_meta,
                metadata=metadata,
            )

            # 7. 持久化
            self.vector_store.save()
            self.graph_store.save()

            result_msg = (
                f"✅ 总结导入成功\n"
                f"📝 总结长度: {len(summary_text)}\n"
                f"📌 提取实体: {len(entities)}\n"
                f"🔗 提取关系: {len(relations)}"
            )
            return True, result_msg

        except Exception as e:
            logger.error(f"总结导入过程中出错: {e}\n{traceback.format_exc()}")
            return False, f"错误: {str(e)}"

    async def _ensure_runtime_self_check(self) -> Tuple[bool, str]:
        plugin_instance = self.plugin_config.get("plugin_instance") if isinstance(self.plugin_config, dict) else None
        if plugin_instance is not None:
            report = await ensure_runtime_self_check(plugin_instance)
        else:
            report = await run_embedding_runtime_self_check(
                config=self.plugin_config,
                vector_store=self.vector_store,
                embedding_manager=self.embedding_manager,
            )
        if bool(report.get("ok", False)):
            return True, ""
        if self._allow_metadata_only_write():
            msg = (
                f"{report.get('message', 'unknown')} "
                f"(configured={report.get('configured_dimension', 0)}, "
                f"store={report.get('vector_store_dimension', 0)}, "
                f"encoded={report.get('encoded_dimension', 0)})"
            )
            logger.warning(f"总结导入进入 metadata-only 回退模式: {msg}")
            return True, "embedding_degraded_metadata_only"
        return (
            False,
            f"{report.get('message', 'unknown')} "
            f"(configured={report.get('configured_dimension', 0)}, "
            f"store={report.get('vector_store_dimension', 0)}, "
            f"encoded={report.get('encoded_dimension', 0)})",
        )

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON"""
        try:
            # 尝试查找 JSON
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {}
        except Exception as e:
            logger.warning(f"解析总结 JSON 失败: {e}")
            return {}

    async def _execute_import(
        self,
        summary: str,
        entities: List[str],
        relations: List[Dict[str, str]],
        stream_id: str,
        time_meta: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """将数据写入存储"""
        # 获取默认知识类型
        type_str = self.plugin_config.get("summarization", {}).get("default_knowledge_type", "narrative")
        try:
            knowledge_type = resolve_stored_knowledge_type(type_str, content=summary)
        except ValueError:
            logger.warning(f"非法 summarization.default_knowledge_type={type_str}，回退 narrative")
            knowledge_type = KnowledgeType.NARRATIVE

        # 导入总结文本
        hash_value = self.metadata_store.add_paragraph(
            content=summary,
            source=f"chat_summary:{stream_id}",
            metadata=metadata,
            knowledge_type=knowledge_type.value,
            time_meta=time_meta,
        )

        plugin_instance = self.plugin_config.get("plugin_instance") if isinstance(self.plugin_config, dict) else None
        vector_writer = getattr(plugin_instance, "write_paragraph_vector_or_enqueue", None)
        if callable(vector_writer):
            result = await vector_writer(
                paragraph_hash=hash_value,
                content=summary,
                context="summary_import",
            )
            if str(result.get("warning", "") or "").strip():
                logger.warning(f"总结导入段落进入回退写入: {result}")
        else:
            try:
                embedding = await self.embedding_manager.encode(summary)
                self.vector_store.add(
                    vectors=embedding.reshape(1, -1),
                    ids=[hash_value]
                )
            except Exception as exc:
                if not self._allow_metadata_only_write():
                    raise
                logger.warning(f"总结导入段落向量写入失败，改为回填队列: {exc}")
                self.metadata_store.enqueue_paragraph_vector_backfill(hash_value, error=str(exc))

        # 导入实体
        if entities:
            self.graph_store.add_nodes(entities)

        # 导入关系
        rv_cfg = self.plugin_config.get("retrieval", {}).get("relation_vectorization", {})
        if not isinstance(rv_cfg, dict):
            rv_cfg = {}
        write_vector = bool(rv_cfg.get("enabled", False)) and bool(rv_cfg.get("write_on_import", True))
        for rel in _normalize_relation_items(relations):
            s, p, o = rel["subject"], rel["predicate"], rel["object"]
            if all([s, p, o]):
                if self.relation_write_service is not None:
                    await self.relation_write_service.upsert_relation_with_vector(
                        subject=s,
                        predicate=p,
                        obj=o,
                        confidence=1.0,
                        source_paragraph=hash_value,
                        write_vector=write_vector,
                    )
                else:
                    # 写入元数据
                    rel_hash = self.metadata_store.add_relation(
                        subject=s,
                        predicate=p,
                        obj=o,
                        confidence=1.0,
                        source_paragraph=hash_value
                    )
                    # 写入图数据库（写入 relation_hashes，确保后续可按关系精确修剪）
                    self.graph_store.add_edges([(s, o)], relation_hashes=[rel_hash])
                    try:
                        self.metadata_store.set_relation_vector_state(rel_hash, "none")
                    except Exception:
                        pass
                
        logger.info(f"总结导入完成: hash={hash_value[:8]}")
