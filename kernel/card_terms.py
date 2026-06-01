"""Shared helpers for normalizing game-knowledge card search terms."""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Sequence, Set


GLOBAL_NOISE_TERMS = {
    "",
    "game_knowledge",
    "标签",
    "证据",
    "由检索结果",
    "人工修订生成",
    "检索结果",
    "当前知识",
    "游戏知识",
    "知识",
    "问题",
    "答案",
    "方法",
    "方式",
    "情况",
    "这个",
    "那个",
    "什么",
    "怎么",
    "如何",
    "是否",
    "可以",
    "需要",
    "建议",
    "推荐",
    "目前",
    "当前",
    "现在",
    "已经",
    "不再",
    "使用",
    "进行",
    "一个",
    "一种",
    "时候",
    "如果",
    "因为",
    "所以",
    "然后",
    "直接",
    "通过",
    "相关",
    "原始",
    "内容",
    "标签证据",
    "待补充",
    "active",
    "stale",
    "deprecated",
    "conflict",
    "pending",
    "approved",
    "rejected",
    "similar",
    "needs_answer",
    "superseded",
    "other",
    "mechanic",
    "recommendation",
    "config",
    "drop",
    "guide",
    "location",
    "error_fix",
}

GENERIC_CJK = {
    "攻略",
    "机制",
    "玩法",
    "版本",
    "有效",
    "无效",
    "分类",
    "类型",
    "状态",
    "获取",
    "获得",
    "解决",
    "处理",
    "区别",
    "位置",
    "来源",
    "说明",
    "操作",
    "更新",
    "变更",
}

SENTENCE_FRAGMENT_MARKERS = {
    "可以",
    "需要",
    "建议",
    "然后",
    "如果",
    "不是",
    "就是",
    "已经",
    "不会",
    "不能",
    "才能",
    "即可",
    "通过",
    "使用",
    "放入",
    "放在",
    "导致",
    "避免",
    "主要",
    "属于",
    "存在",
    "进行",
    "出来",
    "进去",
    "应该",
    "仍然",
    "没有",
    "不要",
    "不需要",
    "不影响",
    "没必要",
    "没用",
    "默认",
    "可尝试",
    "若仍",
    "查询",
    "可以去",
}

DOMAIN_SUFFIXES = (
    "双手剑",
    "之刃",
    "戒指",
    "护符",
    "项链",
    "腰带",
    "卷轴",
    "书袋",
    "石英花",
    "符文阅读器",
    "符文",
    "诅咒",
    "附魔",
    "流派",
    "维度",
    "地牢",
    "高塔",
    "村民",
    "交易",
    "图腾",
    "套",
    "盔甲",
    "饰品栏",
    "饰品",
    "武器",
    "装备",
    "配置",
    "指令",
    "报错",
    "闪退",
    "崩溃",
    "病毒",
    "免疫",
    "掉落",
    "箱子",
    "渠道服",
    "模拟器",
    "材质包",
    "快捷键",
)

QUESTION_SUFFIX_RE = re.compile(
    r"(是什么|有什么区别|有什么用|怎么(?:办|打|用|做|获取|获得|操作|处理|解决|配置|设置|升级|发育|开局)?|"
    r"如何|在哪(?:里)?|能用吗|可以吗|吗|嘛|呢|？|\?)$"
)
HASH_RE = re.compile(r"[a-f0-9]{24,}", re.I)
VERSION_RE = re.compile(r"\b(?:v)?[0-9]+(?:\.[0-9]+){1,3}\b", re.I)
CJK_ONLY_RE = re.compile(r"^[\u4e00-\u9fff]+$")

DOMAIN_PATTERNS = [
    r"[\u4e00-\u9fffA-Za-z0-9+._-]{1,14}(?:双手剑|之刃|戒指|护符|项链|腰带|卷轴|书袋|石英花|符文阅读器|符文|诅咒|附魔|流派|维度|地牢|高塔|村民|交易|图腾|龙|套|盔甲|饰品栏|饰品|武器|装备|配置|指令|报错|闪退|崩溃|病毒|免疫|掉落|箱子|渠道服|模拟器)",
    r"(?:高级|低级|中级|致命|灰烬|烈火|时来运转|熟能生巧|生命吸收|经验修补|教育|抢夺|穿透|穿刺|魔法祝福)[\u4e00-\u9fff]{0,6}",
    r"[\u4e00-\u9fff]{2,8}(?:III|II|IV|V|VI|3|2|4|5)",
]
DOMAIN_RES = [re.compile(pattern) for pattern in DOMAIN_PATTERNS]
QUERY_VERB_RE = re.compile(
    r"(?:怎么(?:办|打|用|做|获取|获得|操作|处理|解决|配置|设置|升级|发育|开局|优化)?|掉几个|几个|"
    r"如何|为什么|是否|能不能|有没有|可以吗|能用吗|是什么|有什么用|有什么区别|在哪里|在哪|吗|嘛|呢)"
)


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_terms(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple):
        raw = list(value)
    elif isinstance(value, str):
        raw = re.split(r"[,，\n;/；]+", value)
    else:
        raw = []
    out: List[str] = []
    for item in raw:
        text = normalize_text(item).strip()
        if text:
            out.append(text)
    return out


def strip_question_suffix(text: str) -> str:
    value = normalize_text(text).strip(" ：:，,。.!！?？")
    for _ in range(2):
        value = QUESTION_SUFFIX_RE.sub("", value).strip(" ：:，,。.!！?？")
    return value


def is_noisy_term(term: str) -> bool:
    value = normalize_text(term).strip(" ：:，,。.!！?？[]【】（）()「」\"'")
    if not value:
        return True
    lower = value.lower()
    if lower in GLOBAL_NOISE_TERMS:
        return True
    if HASH_RE.fullmatch(value):
        return True
    if len(value) == 1:
        return True
    if len(value) > 28:
        return True
    if re.fullmatch(r"\d+", value):
        return True
    if value in GENERIC_CJK:
        return True
    if value.startswith(("由检索结果", "人工修订", "原始内容", "标签", "证据")):
        return True
    if value.endswith(("标签", "证据")):
        return True
    if value.startswith(("的", "了", "在", "中", "里", "把", "将", "再", "若", "如")):
        return True
    if "由检索结果" in value or "人工修订生成" in value:
        return True
    if len(value) >= 9 and any(value.endswith(suffix) for suffix in ("可以", "需要", "即可", "然后", "建议", "方式", "方法")):
        return True
    return False


def is_sentence_fragment(term: str, *, protected: Sequence[str]) -> bool:
    value = normalize_text(term)
    if value in protected:
        return False
    if len(value) < 3:
        return False
    if any(marker in value for marker in SENTENCE_FRAGMENT_MARKERS):
        return True
    if "的" in value and len(value) >= 9 and not any(suffix in value for suffix in DOMAIN_SUFFIXES):
        return True
    if value.endswith(("了", "的", "吗", "呢", "吧", "后", "前", "时", "中", "里", "上", "下")):
        return True
    return False


def normalize_search_terms(
    value: Any,
    *,
    protected: Sequence[str] = (),
    max_terms: int = 24,
) -> List[str]:
    protected_set = {normalize_text(item) for item in protected if normalize_text(item)}
    out: List[str] = []
    seen: Set[str] = set()
    for raw in split_terms(value):
        text = normalize_text(raw).strip(" ：:，,。.!！?？[]【】（）()「」\"'")
        if len(text) > 28:
            continue
        if is_noisy_term(text):
            continue
        if text in protected_set:
            continue
        if is_sentence_fragment(text, protected=tuple(protected_set)):
            continue
        lower = text.lower()
        if lower in seen:
            continue
        if len(text) <= 4 and any(text in existing for existing in out if len(existing) > len(text)):
            continue
        if CJK_ONLY_RE.fullmatch(text):
            if len(text) > 12:
                continue
            if len(text) > 8 and not any(suffix in text for suffix in DOMAIN_SUFFIXES):
                continue
        seen.add(lower)
        out.append(text)
        if len(out) >= max_terms:
            break
    return out


def normalize_aliases(value: Any) -> List[str]:
    global_aliases = {"游戏", "手游", "端游"}
    aliases: List[str] = []
    for item in split_terms(value):
        text = normalize_text(item)
        if not text or text.lower() in global_aliases:
            continue
        if text not in aliases:
            aliases.append(text)
    return aliases[:16]


def iter_domain_terms(text: str) -> Iterable[str]:
    for regex in DOMAIN_RES:
        for match in regex.finditer(text):
            yield match.group(0)


def iter_query_core_terms(text: str) -> Iterable[str]:
    cleaned = normalize_text(text)
    cleaned = VERSION_RE.sub(" ", cleaned)
    cleaned = QUERY_VERB_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[？?。.!！,，、:：;；()（）【】\\[\\]\"'“”‘’]+", " ", cleaned)
    for part in re.split(r"\s+", cleaned):
        token = normalize_text(part)
        if 2 <= len(token) <= 12:
            yield token


def derive_search_terms_from_text(
    title: Any,
    question: Any,
    answer: Any,
    *,
    category: Any = "",
    meta_tags: Sequence[Any] | None = None,
    max_terms: int = 24,
) -> List[str]:
    title_text = normalize_text(title)
    question_text = normalize_text(question)
    answer_text = normalize_text(answer)
    category_text = normalize_text(category)
    raw_terms: List[str] = []
    for item in meta_tags or []:
        text = normalize_text(item)
        if text:
            raw_terms.append(text)

    high_signal_text = " ".join([title_text, question_text])
    full_text = " ".join([title_text, question_text, answer_text, category_text])
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9_\-]{2,}", full_text):
        raw_terms.append(match.group(0))
    for match in VERSION_RE.finditer(full_text):
        raw_terms.append(match.group(0))
    for term in iter_domain_terms(high_signal_text):
        raw_terms.append(term)
    for term in iter_query_core_terms(high_signal_text):
        raw_terms.append(term)

    for core in (
        strip_question_suffix(title_text),
        strip_question_suffix(question_text),
    ):
        if core and not is_sentence_fragment(core, protected=()):
            raw_terms.append(core)
    if category_text and category_text not in {"其他", "玩法", "攻略", "机制"}:
        raw_terms.append(category_text)
    protected = [title_text, question_text, strip_question_suffix(title_text), strip_question_suffix(question_text)]
    return normalize_search_terms(raw_terms, protected=protected, max_terms=max_terms)
