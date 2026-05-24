"""游戏知识分析器

从群聊消息中提取结构化游戏知识卡片。
复用旧 group_knowledge_plugin 的 prompt 设计，但输出适配新内核。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from gk_shims.logger_shim import get_logger
from gk_shims.llm_shim import LLMServiceClient

logger = get_logger("GameKnowledge.Analyzer")

_LLM_SYSTEM_PROMPT = """你是 RLCraft / Minecraft 整合包知识提取专家。把 QQ 群聊内容整理成结构化问答卡片，供 replyer AI 回答玩家问题。

════════════════════════════════════════════
提取策略（按优先级）
════════════════════════════════════════════
1. 显式问答 — 玩家直接问、有人直接答 → 提取 Q&A
2. 推荐/建议 — 玩家问「xxx推荐什么」「用什么附魔/装备」→ Q=推荐问题，A=推荐选项
   游戏群聊中推荐类问答占比极高（≈30%），务必重点关注
3. 隐含问答 — 玩家陈述问题、他人给出方案 → Q=概括问题，A=方案
4. 讨论结论 — 多人讨论产生共识 → Q=核心问题，A=结论
5. 无答案的问题 — 默认不要提取；只有问题本身明确、可搜索、后续值得补答时才保留，并设置 answer=""、needs_answer=true、need_review=true

════════════════════════════════════════════
question 字段规则（违反即不合格）
════════════════════════════════════════════
✅ "FTB编辑模式怎么关"
✅ "暗影词条怎么获取"
✅ "银套还免疫病毒吗"
✅ "勇者之刃推荐什么附魔"
✅ "龙棍怎么配附魔"
✅ "终有一死建议点到几级"
❌ "FTB相关讨论"       ← 话题概括，严禁
❌ "关于武器的内容"     ← 话题概括，严禁
规则：question 必须是带问句的、可被搜索到的具体问题，不能是话题名称。
规则：禁止输出依赖上下文的短问题，如"高塔有没有"、"要去地下吗"、"这个呢"；必须补全为"大地之心高塔箱子有没有"这类完整问题，补不全就丢弃。

════════════════════════════════════════════
answer 字段规则（违反即不合格）
════════════════════════════════════════════
✅ "在FTB Ranks配置里把 ftb.editing_mode 设为 false"
✅ "龙前就可以打，不需要毕业装备"
✅ "设置血量200→-1即可常驻医疗护理显示"
✅ "致命一击3"            ← 推荐类 A 可简短
✅ "推荐穿透+穿刺+魔法祝福一起打"
✅ "终有一死点到5级即可，不建议更高"
❌ "群里讨论了FTB配置"   ← 无信息量，严禁
❌ "有人说可以有人说不行" ← 太模糊，严禁
规则：answer 必须自包含，replyer AI 拿着就能直接回复玩家。

════════════════════════════════════════════
知识卡片输出格式
════════════════════════════════════════════
每条 knowledge_cards 包含：
- title: 简短标题，尽量口语化（如"银套免疫效果变更"、"勇者之刃附魔推荐"）
- category: 只能从 攻略/机制/推荐/配置/报错/装备/版本/模组/掉落/位置/其他 中选择一个，禁止输出"装备/推荐"这类组合分类
- question: 这条知识回答的具体问题（必须有问句感，不是话题名）
- answer: 具体答案或建议；若确实是值得补答的问题但群聊没有答案，可以为空字符串
- steps: 分步骤内容（可选，字符串数组）
- tags: 主题标签数组，只放少量中等粒度主题；不要放 RLCraft/Minecraft/MC/游戏知识 等全局背景词，不要重复 category/answer_type，不要把具体物品名、附魔名、boss 名、报错词当标签
- search_terms: 检索关键词数组，优先放物品名、附魔名、boss名、维度名、配置项、报错原文关键词、群内简称
- aliases: 别名数组，必须谨慎填写；只放该知识核心对象真实存在的同义名、英文名、缩写、群内稳定俗称。没有明确别名就填 []。禁止把全局游戏名、普通关键词、分类词、标签重复塞进 aliases
- rlcraft_version: 版本表达，如 2.9/3.0/3.3/新版本/旧版本/当前服版本；不确定可留空
- answer_type: error_fix/config/recommendation/guide/mechanic/location/drop/other
- valid_status: active/stale/deprecated/conflict，默认 active；版本冲突或答案互斥时用 conflict
- source_message_ids: 来源消息 ID 数组
- confidence: 0~1，越明确越高，粗略讨论给 0.5
- need_review: true/false，低置信度或信息不完整时 true
- needs_answer: true/false，问题有价值但当前消息没有可靠答案时 true
- evidence: 1 句说明这条知识来自哪些相邻发言，便于审核

质量门槛：
- answer 为空、"待补充"、"不知道"、"可能吧"时，默认不输出 knowledge_cards；只有 needs_answer=true 且 question 很明确时才输出
- 若同一问题在多条消息里连续追问，请合并成一张卡片，不要拆成多个短问句
- 不要把玩笑、闲聊、管理通知、单纯情绪表情提取为知识
- 每批最多输出 6 张卡片，宁可少，不要为了凑数输出弱知识

输出结构：
{
  "summary": "本批消息的简要总结（1-2句话）",
  "knowledge_cards": [
    {
      "title": "银套免疫效果变更",
      "category": "装备",
      "question": "银套还免疫病毒吗",
      "answer": "新版本德雷削弱了银套，沐包有回调，现版本只免疫寄巢之唤",
      "steps": [],
      "tags": ["版本差异", "装备机制"],
      "search_terms": ["银套", "病毒", "寄巢之唤", "德雷", "沐包"],
      "aliases": [],
      "rlcraft_version": "新版本",
      "answer_type": "mechanic",
      "valid_status": "conflict",
      "source_message_ids": ["id1"],
      "confidence": 0.85,
      "need_review": false,
      "evidence": "玩家问银套是否还免疫病毒，后续回复说明版本削弱后的免疫范围"
    },
    {
      "title": "勇者之刃附魔推荐",
      "category": "推荐",
      "question": "勇者之刃推荐什么附魔",
      "answer": "致命一击3",
      "steps": [],
      "tags": ["附魔系统", "装备构筑"],
      "search_terms": ["勇者之刃", "附魔", "致命一击", "致命一击3"],
      "aliases": [],
      "rlcraft_version": "",
      "answer_type": "recommendation",
      "valid_status": "active",
      "source_message_ids": ["id2"],
      "confidence": 0.9,
      "need_review": false
    }
  ],
  "entities": ["银套", "寄巢之唤", "德雷", "勇者之刃", "致命一击"],
  "relations": []
}

════════════════════════════════════════════
核心原则
════════════════════════════════════════════
1. QQ 群聊口语化，尽量保留有价值信息
2. 优先识别：攻略、配置建议、玩法机制、报错解决、装备/附魔推荐、掉落/位置
3. 遇到"3.3/新版本/旧版本/以前/削弱/回调/删除/没了"必须尝试填写 rlcraft_version 或 valid_status
4. 质量优先，宁少勿滥
5. 找不到有价值知识点 → 输出空 knowledge_cards: []
6. 不要花 token 构造复杂 relations，默认 relations 输出 []
7. 输出必须只包含 JSON，不要 markdown 代码块或其他文字"""


_AI_REVIEW_PROMPT = """你是游戏知识卡片的质量审核员。请判断这张卡片是否适合进入人工审核队列。

请把卡片分为三类：
1. approved=true：有可靠答案，适合进入待审核队列。
2. needs_answer=true：当前没有可靠答案，但 question 明确、可搜索、玩家后续值得补答。
3. approved=false 且 needs_answer=false：没价值、太含糊或不适合保留。

通过标准：
- question 是具体、可搜索、可被玩家自然提问的问题，不是话题名或上下文残片。
- answer 自包含、能直接回答 question，有实际信息量。
- 内容确实是游戏知识、玩法、机制、配置、报错、装备、推荐等。
- 不是广告、群通知、公开 token/接口/群号引流、闲聊、情绪、玩笑或无关内容。
- 不把没有结论、猜测、互相矛盾的讨论包装成确定答案。

拒绝标准：
- 问答不相干，或问题和答案明显对不上。
- 缺上下文才能理解，例如“这个怎么弄”“高塔有没有”且卡片没有补全对象。
- answer 只有“信息不足/不清楚/看情况/不强”等低信息量内容，且问题本身不值得后续补答。
- 包含公益 token、通知群、广告、招募、外部引流、敏感私密信息。

待回答标准：
- question 已经补全对象，玩家自然会搜索这个问题。
- 当前群聊没有可靠 answer，或 answer 明确表示“未提供/不清楚/需要进一步信息”。
- 这个问题属于游戏机制、配置、玩法、报错、装备、推荐等，后续补答案有价值。

只输出 JSON，不要 markdown：
{
  "approved": true,
  "needs_answer": false,
  "question_worth_answering": false,
  "reason": "一句话说明",
  "score": 0.0,
  "issues": []
}"""


class GameKnowledgeAnalyzer:
    """游戏知识分析器

    职责：
    - 接收群聊消息上下文
    - 调用 LLM 提取结构化知识卡片
    - 解析并校验输出格式
    - 返回标准化的知识卡片列表
    """

    _GLOBAL_TAGS = {"rlcraft", "rlc", "mc", "minecraft", "我的世界", "游戏知识", "game_knowledge", "知识", "问题", "答案"}
    _STRUCTURAL_TAGS = {
        "攻略", "机制", "推荐", "配置", "报错", "装备", "版本", "模组", "掉落", "位置", "其他",
        "error_fix", "config", "recommendation", "guide", "mechanic", "location", "drop", "other",
        "active", "stale", "deprecated", "conflict",
        "获取", "获取方式", "打法", "资源获取", "装备推荐", "版本机制", "版本变更", "版本更新",
    }
    _TAG_REWRITE = {
        "联机": "联机问题",
        "服务器": "联机问题",
        "卡顿": "性能优化",
        "性能": "性能优化",
        "bug": "异常问题",
        "游戏崩溃": "异常问题",
        "崩溃": "异常问题",
        "附魔": "附魔系统",
        "饰品": "饰品系统",
        "饰品栏": "饰品系统",
        "机械": "机械流派",
        "深渊": "深渊流派",
        "咒术": "咒术流派",
        "版本": "版本差异",
        "版本机制": "版本差异",
        "版本变更": "版本差异",
        "版本更新": "版本差异",
        "装备": "装备构筑",
        "装备推荐": "装备构筑",
        "武器": "装备构筑",
        "boss": "Boss战",
        "Boss": "Boss战",
        "BOSS": "Boss战",
        "掉落": "材料获取",
        "获取": "材料获取",
        "获取方式": "材料获取",
        "资源获取": "材料获取",
        "位置": "位置探索",
        "配置": "配置问题",
        "报错": "异常问题",
        "模组": "模组兼容",
        "新手": "新手开局",
        "前期": "新手开局",
    }
    _ALLOWED_THEME_TAGS = {
        "附魔系统", "饰品系统", "机械流派", "深渊流派", "咒术流派", "联机问题", "性能优化", "异常问题",
        "版本差异", "装备构筑", "维度探索", "结构探索", "Boss战", "材料获取", "位置探索", "配置问题",
        "模组兼容", "新手开局", "农业种植", "召唤机制",
    }
    _SEARCH_TERM_BLOCKLIST = _GLOBAL_TAGS | {
        "攻略", "机制", "推荐", "配置", "报错", "装备", "版本", "模组", "掉落", "位置", "其他",
        "获取", "获取方式", "打法", "资源获取", "装备推荐", "版本机制", "版本变更", "版本更新",
        "深渊流派", "附魔系统", "饰品系统", "机械流派", "异常问题", "新手开局", "联机问题", "性能优化",
        "Boss战", "咒术流派", "材料获取", "装备构筑", "版本差异", "配置问题", "模组兼容", "位置探索",
        "知识卡片", "说明", "方案", "问题", "相关", "信息", "内容", "确认", "建议", "方法",
        "深渊", "附魔", "饰品", "机械", "召唤", "联机", "配置", "获取", "推荐", "版本", "模组",
        "掉落", "位置", "前期", "新手", "武器", "装备", "伤害", "事件", "数量", "建筑", "防御",
        "合成", "资源", "任务", "结构", "打法", "开局", "卡顿", "崩溃", "服务器", "报错", "性能",
        "boss", "bug", "drop", "config", "guide", "mechanic", "location", "recommendation", "other",
        "active", "pending", "approved", "rejected", "similar", "needs_answer", "processing", "conflict",
        "玩法", "教程", "介绍", "分类", "类型", "主题", "总结", "背景", "相关性", "知识点",
    }
    _SEARCH_TERM_REWRITE = {
        "BUG": "bug",
        "Bug": "bug",
        "BOSS": "boss",
        "Boss": "boss",
        "Debuff": "debuff",
        "Buff": "buff",
        "MOD": "mod",
        "Mod": "mod",
        "RS": "rs",
    }

    def __init__(
        self,
        *,
        llm_client: Optional[LLMServiceClient] = None,
        review_client: Optional[LLMServiceClient] = None,
        enable_ai_review: bool = False,
        ai_review_error_status: str = "pending",
    ) -> None:
        self._llm_client = llm_client
        self._review_client = review_client
        self._enable_ai_review = enable_ai_review
        self._ai_review_error_status = self._normalize_review_status(ai_review_error_status, default="pending")

    async def analyze_messages(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream_id: str = "",
    ) -> Dict[str, Any]:
        """分析一批消息，提取游戏知识卡片。

        Args:
            messages: 消息列表，每条至少包含 id, content, sender_name
            stream_id: 聊天流ID，用于溯源

        Returns:
            {"success": bool, "cards": [...], "entities": [...], "relations": [...], "error": ""}
        """
        if not messages:
            return {"success": True, "cards": [], "entities": [], "relations": [], "error": ""}

        text = self._format_messages(messages)
        try:
            result = await self._extract_with_llm(text)
        except Exception as exc:
            logger.warning(f"LLM 提取失败: {exc}")
            result = self._extract_with_rules(text, messages)

        cards = result.get("knowledge_cards", [])
        normalized_cards = []
        ai_reviewed = 0
        ai_rejected = 0
        ai_review_errors = 0
        for card in cards:
            if not isinstance(card, dict):
                continue
            normalized = await self._normalize_card_with_llm(card, messages, stream_id)
            if normalized:
                review_result = await self._review_normalized_card(normalized, messages)
                if review_result:
                    ai_reviewed += 1
                    normalized.update(review_result)
                    if normalized.get("review_status") == "ai_rejected":
                        ai_rejected += 1
                    if str(normalized.get("ai_review_status", "")) == "error":
                        ai_review_errors += 1
                normalized_cards.append(normalized)

        return {
            "success": True,
            "cards": normalized_cards,
            "entities": result.get("entities", []),
            "relations": result.get("relations", []),
            "summary": result.get("summary", ""),
            "ai_reviewed": ai_reviewed,
            "ai_rejected": ai_rejected,
            "ai_review_errors": ai_review_errors,
            "error": "",
        }

    async def _extract_with_llm(self, text: str) -> Dict[str, Any]:
        """调用 LLM 提取知识。

        使用 MaiBot 统一的 LLMServiceClient，通过 task_name 选择模型。
        默认使用 "utils" 任务配置，可在初始化时指定其他 task_name。
        """
        if self._llm_client is None:
            raise RuntimeError("LLM client 未配置")

        result = await self._llm_client.generate_response(
            prompt=f"{_LLM_SYSTEM_PROMPT}\n\n群聊内容:\n{text}",
        )
        content = self._llm_text(result)
        parsed = self._parse_llm_output(content)
        if isinstance(parsed, list):
            return {"knowledge_cards": parsed}
        if isinstance(parsed, dict):
            return parsed
        return {}

    @staticmethod
    def _llm_text(result: Any) -> str:
        """兼容 MaiBot LLMResponseResult(response=...) 与 OpenAI 风格 content 字段。"""
        for attr in ("response", "content", "text"):
            value = getattr(result, attr, None)
            if isinstance(value, str) and value.strip():
                return value
        return str(result)

    @staticmethod
    def _parse_llm_output(content: str) -> Any:
        """多格式容错解析 LLM 输出。"""
        content = content.strip()
        if not content:
            return {}

        # 尝试提取 JSON 代码块
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if code_block_match:
            content = code_block_match.group(1).strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试从文本中提取第一个 JSON 对象
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return {}

    async def _review_normalized_card(
        self,
        card: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """用 AI 对标准化卡片做预审核，返回可直接并入卡片的审核字段。"""
        if not self._enable_ai_review or self._review_client is None:
            return {"review_status": "pending"}

        try:
            raw = await self._review_client.generate_response(
                prompt=f"{_AI_REVIEW_PROMPT}\n\n卡片:\n{self._format_review_card(card)}\n\n来源消息:\n{self._format_review_messages(messages)}",
            )
            payload = self._parse_llm_output(self._llm_text(raw))
            if not isinstance(payload, dict) or "approved" not in payload:
                raise ValueError("AI 审核输出缺少 approved 字段")

            approved = bool(payload.get("approved"))
            needs_answer = bool(payload.get("needs_answer") or payload.get("question_worth_answering"))
            score = self._parse_review_score(payload.get("score", 0.0))
            issues = payload.get("issues", [])
            if not isinstance(issues, list):
                issues = [str(issues)] if issues else []
            issues = [str(item).strip() for item in issues if str(item).strip()]
            reason = str(payload.get("reason", "") or "").strip()

            if needs_answer and not approved:
                return {
                    "review_status": "needs_answer",
                    "ai_review_status": "needs_answer",
                    "ai_review_reason": reason,
                    "ai_review_score": score,
                    "ai_review_issues": list(dict.fromkeys([*issues, "missing_answer"])),
                }

            return {
                "review_status": "pending" if approved else "ai_rejected",
                "ai_review_status": "approved" if approved else "rejected",
                "ai_review_reason": reason,
                "ai_review_score": score,
                "ai_review_issues": issues,
            }
        except Exception as exc:
            logger.warning(f"AI 预审核失败，按配置放行: {exc}")
            return {
                "review_status": self._ai_review_error_status,
                "ai_review_status": "error",
                "ai_review_reason": f"AI 预审核失败: {exc}",
                "ai_review_score": 0.0,
                "ai_review_issues": ["ai_review_error"],
            }

    @staticmethod
    def _format_review_card(card: Dict[str, Any]) -> str:
        payload = {
            "title": card.get("title", ""),
            "category": card.get("category", ""),
            "question": card.get("question", ""),
            "answer": card.get("answer", ""),
            "steps": card.get("steps", []),
            "tags": card.get("tags", []),
            "search_terms": card.get("search_terms", []),
            "aliases": card.get("aliases", []),
            "rlcraft_version": card.get("rlcraft_version", ""),
            "answer_type": card.get("answer_type", "other"),
            "valid_status": card.get("valid_status", "active"),
            "confidence": card.get("confidence", 0.0),
            "evidence": card.get("evidence", ""),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _format_review_messages(messages: List[Dict[str, Any]], *, limit: int = 12) -> str:
        if not messages:
            return ""
        return GameKnowledgeAnalyzer._format_messages(messages[-limit:])

    @staticmethod
    def _parse_review_score(value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.0
        return max(0.0, min(1.0, score))

    @staticmethod
    def _normalize_review_status(status: Any, *, default: str = "pending") -> str:
        value = str(status or "").strip().lower()
        allowed = {"pending", "approved", "rejected", "ai_rejected", "needs_answer"}
        return value if value in allowed else default

    @staticmethod
    def _extract_with_rules(
        text: str, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """规则引擎兜底：按关键词提取简单知识卡片。"""
        cards: List[Dict[str, Any]] = []
        message_ids = [str(m.get("id", "")) for m in messages if m.get("id")]

        # 问答模式
        qa_patterns = [
            r"(.+?)[\?？]\s*(.+)",
            r"(.+?)怎么(.+?)[\?？]\s*(.+)",
            r"(.+?)如何(.+?)[\?？]\s*(.+)",
        ]
        for pattern in qa_patterns:
            for match in re.finditer(pattern, text, re.DOTALL):
                groups = match.groups()
                if len(groups) >= 2:
                    question = groups[0].strip()
                    answer = groups[-1].strip()
                    if len(question) > 5 and len(answer) > 5:
                        cards.append({
                            "title": question[:30],
                            "category": GameKnowledgeAnalyzer._detect_category(question + answer),
                            "question": question,
                            "answer": answer,
                            "steps": [],
                            "tags": [],
                            "source_message_ids": message_ids[:3],
                            "confidence": 0.5,
                            "need_review": True,
                        })

        # 去重
        seen = set()
        unique_cards = []
        for card in cards:
            key = card.get("question", "") + card.get("answer", "")[:20]
            if key not in seen:
                seen.add(key)
                unique_cards.append(card)

        return {
            "knowledge_cards": unique_cards[:5],
            "entities": [],
            "relations": [],
        }

    @staticmethod
    def _detect_category(text: str) -> str:
        """根据文本内容检测知识分类。"""
        text_lower = text.lower()
        category_keywords = {
            "攻略": ["攻略", "教程", "指南", "步骤", "流程", "打法", "阵容", "配队"],
            "配置": ["配置", "设置", "参数", "选项", "优化", "性能", "画质"],
            "报错": ["报错", "错误", "失败", "崩溃", "闪退", "卡死", "bug", "异常"],
            "机制": ["机制", "原理", "算法", "公式", "概率"],
            "版本": ["版本", "更新", "补丁", "改动"],
            "模组": ["模组", "mod", "插件", "forge", "fabric"],
            "装备": ["装备", "武器", "道具", "材料"],
            "推荐": ["推荐", "建议", "哪个好", "用什么", "附魔"],
            "掉落": ["掉落", "爆率", "掉什么", "刷什么"],
            "位置": ["在哪", "哪里", "位置", "刷新", "生成"],
        }
        scores = {}
        for cat, keywords in category_keywords.items():
            scores[cat] = sum(1 for kw in keywords if kw in text_lower)
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                return best
        return "其他"

    @staticmethod
    def _normalize_category(value: Any, fallback_text: str = "") -> str:
        raw = str(value or "").strip()
        allowed = {"攻略", "机制", "推荐", "配置", "报错", "装备", "版本", "模组", "掉落", "位置", "其他"}
        if raw in allowed:
            return raw
        for part in re.split(r"[/／,，\s]+", raw):
            if part in allowed:
                return part
        return GameKnowledgeAnalyzer._detect_category(fallback_text)

    @staticmethod
    def _normalize_answer_type(value: Any, text: str = "") -> str:
        raw = str(value or "").strip().lower()
        allowed = {"error_fix", "config", "recommendation", "guide", "mechanic", "location", "drop", "other"}
        if raw in allowed:
            return raw
        lower = text.lower()
        if any(token in lower for token in ["报错", "崩溃", "闪退", "bug", "错误"]):
            return "error_fix"
        if any(token in lower for token in ["配置", "设置", "按键", "cfg", "config"]):
            return "config"
        if any(token in lower for token in ["推荐", "建议", "哪个好", "用什么", "附魔"]):
            return "recommendation"
        if any(token in lower for token in ["哪里", "在哪", "位置", "刷新"]):
            return "location"
        if any(token in lower for token in ["掉落", "掉什么", "爆率"]):
            return "drop"
        if any(token in lower for token in ["机制", "概率", "效果", "为什么"]):
            return "mechanic"
        if any(token in lower for token in ["怎么", "如何", "方法"]):
            return "guide"
        return "other"

    @staticmethod
    def _normalize_valid_status(value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"active", "stale", "deprecated", "conflict"} else "active"

    @staticmethod
    def _normalize_list(value: Any) -> List[str]:
        if isinstance(value, list):
            raw = value
        elif isinstance(value, str):
            raw = re.split(r"[,，\n;/；]+", value)
        else:
            raw = []
        out: List[str] = []
        for item in raw:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
        return out[:32]

    @staticmethod
    def _normalize_aliases(value: Any) -> List[str]:
        global_aliases = {"rlcraft", "rlc", "mc", "minecraft", "我的世界"}
        aliases = []
        for item in GameKnowledgeAnalyzer._normalize_list(value):
            token = str(item or "").strip()
            if not token or token.lower() in global_aliases:
                continue
            if token not in aliases:
                aliases.append(token)
        return aliases[:16]

    @staticmethod
    def _normalize_tags(value: Any, *, category: str = "", answer_type: str = "", valid_status: str = "") -> List[str]:
        blocked = set(GameKnowledgeAnalyzer._GLOBAL_TAGS)
        blocked.update(item.lower() for item in GameKnowledgeAnalyzer._STRUCTURAL_TAGS)
        for item in (category, answer_type, valid_status):
            token = str(item or "").strip()
            if token:
                blocked.add(token.lower())
        tags: List[str] = []
        for item in GameKnowledgeAnalyzer._normalize_list(value):
            token = str(item or "").strip()
            if not token:
                continue
            rewritten = GameKnowledgeAnalyzer._TAG_REWRITE.get(token, token)
            if rewritten.lower() in blocked:
                continue
            if rewritten not in GameKnowledgeAnalyzer._ALLOWED_THEME_TAGS:
                continue
            if rewritten not in tags:
                tags.append(rewritten)
        return tags[:3]

    @staticmethod
    def _looks_like_search_sentence(text: str) -> bool:
        if re.fullmatch(r"[A-Za-z0-9 .+_\-]{15,}", text):
            return False
        if len(text) > 14:
            return True
        return bool(re.search(r"(怎么|为什么|如何|是否|能不能|有没有|可以|需要|建议|解决|说明|方案|设置|修改|使用|获取|在哪里|怎么办)", text)) and len(text) > 8

    @staticmethod
    def _normalize_search_terms(value: Any) -> List[str]:
        terms: List[str] = []
        for item in GameKnowledgeAnalyzer._normalize_list(value):
            token = str(item or "").strip().strip(" ，,。.!！?？:：;；、")
            if not token:
                continue
            token = GameKnowledgeAnalyzer._SEARCH_TERM_REWRITE.get(token, token)
            lowered = token.lower()
            if lowered in GameKnowledgeAnalyzer._SEARCH_TERM_BLOCKLIST:
                continue
            if token in GameKnowledgeAnalyzer._ALLOWED_THEME_TAGS:
                continue
            if GameKnowledgeAnalyzer._looks_like_search_sentence(token):
                continue
            if token not in terms:
                terms.append(token)
        return terms[:24]

    async def _polish_search_terms_with_llm(
        self,
        *,
        title: str,
        question: str,
        answer: str,
        category: str,
        answer_type: str,
        valid_status: str,
        tags: List[str],
        aliases: List[str],
        rule_search_terms: List[str],
        text: str,
        max_terms: int = 24,
    ) -> List[str]:
        if self._llm_client is None:
            return rule_search_terms
        payload = {
            "title": title,
            "question": question,
            "answer": answer,
            "category": category,
            "answer_type": answer_type,
            "valid_status": valid_status,
            "tags": tags,
            "aliases": aliases,
            "rule_search_terms": rule_search_terms,
        }
        prompt = (
            "你是 RLCraft / RLCraft 七咒知识库的检索关键词编辑器。\n"
            "任务：先基于卡片内容给出更好的 search_terms，再交给规则清洗。\n\n"
            "要求：\n"
            f"- 返回 3 到 {max_terms} 个关键词；不足时可更少。\n"
            "- 只保留短词、装备名、机制名、别名、常见问法中的核心名词。\n"
            "- 不要输出泛词、完整问句、完整答案、长句、解释句。\n"
            "- 不要编造不存在的内容。\n"
            "- 优先保留 rule_search_terms 中的准确词。\n\n"
            "只返回 JSON 数组。\n\n"
            f"卡片：\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            f"上下文：\n{text}"
        )
        try:
            result = await self._llm_client.generate_response(prompt=prompt)
            parsed = self._parse_llm_output(self._llm_text(result))
            if isinstance(parsed, list):
                polished = self._normalize_search_terms(parsed)
                return polished or rule_search_terms
            if isinstance(parsed, dict):
                raw_terms = parsed.get("search_terms", [])
                if isinstance(raw_terms, list):
                    polished = self._normalize_search_terms(raw_terms)
                    return polished or rule_search_terms
        except Exception as exc:
            logger.warning(f"LLM 关键词精修失败，回退规则结果: {exc}")
        return rule_search_terms

    def _normalize_card(
        self,
        card: Dict[str, Any],
        messages: List[Dict[str, Any]],
        stream_id: str,
    ) -> Optional[Dict[str, Any]]:
        """标准化单张知识卡片。"""
        title = str(card.get("title", "") or "").strip()
        answer = str(card.get("answer", "") or "").strip()
        needs_answer = bool(card.get("needs_answer", False))
        missing_answer_values = {"待补充", "【待补充】", "不知道", "不清楚", "可能吧", "信息不足", "无明确答案"}
        if (not answer or answer in missing_answer_values) and not needs_answer:
            return None
        if needs_answer and answer in missing_answer_values:
            answer = ""
        if not title:
            title = str(card.get("question", "") or "").strip()[:30] if needs_answer else answer[:30]
        if not title:
            return None

        question = str(card.get("question", "") or "").strip()
        if not question:
            return None
        if not GameKnowledgeAnalyzer._is_valid_question(question):
            return None
        if answer and not GameKnowledgeAnalyzer._is_valid_answer(answer):
            return None

        combined_text = f"{title} {question} {answer}"
        category = GameKnowledgeAnalyzer._normalize_category(card.get("category", ""), combined_text)

        source_ids = card.get("source_message_ids", [])
        if not isinstance(source_ids, list):
            source_ids = []
        source_ids = [str(s) for s in source_ids if s]
        if not source_ids and messages:
            source_ids = [str(m.get("id", "")) for m in messages[:3] if m.get("id")]

        source_platform = GameKnowledgeAnalyzer._first_message_value(messages, "source_platform")
        source_group_id = GameKnowledgeAnalyzer._first_message_value(messages, "source_group_id")
        source_group_name = GameKnowledgeAnalyzer._first_message_value(messages, "source_group_name")

        steps = card.get("steps", [])
        if not isinstance(steps, list):
            steps = []
        steps = [str(s) for s in steps if s]

        answer_type = GameKnowledgeAnalyzer._normalize_answer_type(card.get("answer_type", ""), combined_text)
        valid_status = GameKnowledgeAnalyzer._normalize_valid_status(card.get("valid_status", "active"))
        raw_tags = GameKnowledgeAnalyzer._normalize_list(card.get("tags", []))
        tags = GameKnowledgeAnalyzer._normalize_tags(raw_tags, category=category, answer_type=answer_type, valid_status=valid_status)
        aliases = GameKnowledgeAnalyzer._normalize_aliases(card.get("aliases", []))
        search_terms = GameKnowledgeAnalyzer._normalize_search_terms(card.get("search_terms", []))
        for item in [*raw_tags, title, *re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}|[\u4e00-\u9fff]{2,}", combined_text)[:8]]:
            token = str(item or "").strip()
            normalized_tokens = GameKnowledgeAnalyzer._normalize_search_terms([token])
            for normalized_token in normalized_tokens:
                if normalized_token not in search_terms:
                    search_terms.append(normalized_token)
        search_terms = GameKnowledgeAnalyzer._normalize_search_terms(search_terms)
        version = str(card.get("rlcraft_version", "") or "").strip()
        if not version:
            version_match = re.search(r"(?:RLCraft\s*)?(?:v)?([23]\.\d+(?:\.\d+)?)|新版本|旧版本|当前版本|当前服版本", combined_text, re.I)
            version = version_match.group(0) if version_match else ""

        try:
            confidence = float(card.get("confidence", 0.5) or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        need_review = bool(card.get("need_review", confidence < 0.7))

        return {
            "title": title,
            "category": category,
            "question": question,
            "answer": answer,
            "steps": steps,
            "tags": tags,
            "search_terms": search_terms,
            "aliases": aliases,
            "rlcraft_version": version,
            "answer_type": answer_type,
            "valid_status": valid_status,
            "source_message_ids": source_ids,
            "source_stream_id": stream_id,
            "source_platform": source_platform,
            "platform": source_platform,
            "source_group_id": source_group_id,
            "source_group_name": source_group_name,
            "confidence": max(0.0, min(1.0, confidence)),
            "need_review": need_review or needs_answer,
            "needs_answer": needs_answer,
            "evidence": str(card.get("evidence", "") or "").strip(),
        }

    async def _normalize_card_with_llm(
        self,
        card: Dict[str, Any],
        messages: List[Dict[str, Any]],
        stream_id: str,
    ) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_card(card, messages, stream_id)
        if not normalized:
            return None
        try:
            llm_search_terms = await self._polish_search_terms_with_llm(
                title=str(normalized.get("title", "") or ""),
                question=str(normalized.get("question", "") or ""),
                answer=str(normalized.get("answer", "") or ""),
                category=str(normalized.get("category", "") or ""),
                answer_type=str(normalized.get("answer_type", "") or ""),
                valid_status=str(normalized.get("valid_status", "") or ""),
                tags=list(normalized.get("tags", []) or []),
                aliases=list(normalized.get("aliases", []) or []),
                rule_search_terms=list(normalized.get("search_terms", []) or []),
                text=" ".join([
                    str(normalized.get("title", "") or ""),
                    str(normalized.get("question", "") or ""),
                    str(normalized.get("answer", "") or ""),
                ]),
            )
            normalized["search_terms"] = GameKnowledgeAnalyzer._normalize_search_terms(
                llm_search_terms or normalized.get("search_terms", [])
            )
        except Exception as exc:
            logger.warning(f"LLM 关键词精修失败，回退规则结果: {exc}")
        return normalized

    @staticmethod
    def _first_message_value(messages: List[Dict[str, Any]], key: str) -> str:
        for msg in messages:
            value = str(msg.get(key, "") or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _is_valid_question(question: str) -> bool:
        text = str(question or "").strip()
        if len(text) < 4:
            return False
        low = text.lower()
        topic_patterns = [
            r".*相关讨论$",
            r"^关于.+(内容|讨论|情况)$",
            r".*(内容|情况|问题)汇总$",
        ]
        if any(re.fullmatch(pattern, text) for pattern in topic_patterns):
            return False
        if text in {"这个呢", "那个呢", "有没有", "怎么弄", "怎么搞", "怎么办", "要去地下吗"}:
            return False
        if re.fullmatch(r"(这个|那个|这里|那里|它|他|她|这|那).{0,6}", text):
            return False

        intent_terms = (
            "怎么",
            "如何",
            "什么",
            "为啥",
            "为什么",
            "哪里",
            "在哪",
            "多少",
            "能不能",
            "可不可以",
            "是否",
            "有没有",
            "是不是",
            "推荐",
            "用什么",
            "好用",
            "哪个好",
            "吗",
            "?",
            "？",
        )
        if any(term in low for term in intent_terms):
            return True
        # Allow compact recommendation-style questions such as "勇者之刃附魔推荐".
        return bool(re.search(r"(推荐|获取|获得|打法|配置|配队|附魔|机制|解决|修复|关闭|打开|升级|合成|掉落)", text))

    @staticmethod
    def _is_valid_answer(answer: str) -> bool:
        text = str(answer or "").strip()
        if len(text) < 2:
            return False
        bad_answers = {
            "信息不足",
            "无法确定",
            "无法提供具体推荐",
            "无明确答案",
            "没有结论",
            "看情况",
        }
        if text in bad_answers:
            return False
        if re.fullmatch(r"(有人说|群里说|可能|大概|应该|也许).{0,8}", text):
            return False
        return True

    @staticmethod
    def _format_messages(messages: List[Dict[str, Any]]) -> str:
        """将消息列表格式化为 LLM 输入文本。"""
        lines = []
        for msg in messages:
            sender = str(msg.get("sender_name", "未知") or "未知")
            content = str(msg.get("content", "") or "").strip()
            msg_id = str(msg.get("id", "") or "")
            if content:
                lines.append(f"[{msg_id}] {sender}: {content}")
        return "\n".join(lines)
