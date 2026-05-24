"""
文本分块工具

将超长文本拆分为多个 chunk，每个 chunk 独立进行 embedding，
避免请求体超过 embedding API 限制（bge-m3 约为 8192 tokens）。
"""

import re
from typing import List

_CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")

# bge-m3 最大 8192 tokens，中文字符约 1 token，取安全上限
DEFAULT_MAX_CHUNK_CHARS = 3000
# 块间重叠字符数，保留上下文连续性
DEFAULT_OVERLAP_CHARS = 200


def estimate_chinese_chars(text: str) -> int:
    """估算文本中的中文字符数"""
    return len(text)


def split_text_into_chunks(
    text: str,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> List[str]:
    text = str(text or "").strip()
    if not text:
        return []

    max_size = max(200, int(max_chunk_chars))
    overlap = max(0, min(int(overlap_chars), max_size // 3))

    if estimate_chinese_chars(text) <= max_size:
        return [text]

    paragraphs = _split_by_paragraphs(text)
    chunks: List[str] = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if estimate_chinese_chars(para) > max_size:
            # 单个段落仍然太长，按句子拆分
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            sub_chunks = _split_long_paragraph(para, max_size, overlap)
            chunks.extend(sub_chunks)
            continue

        candidate = f"{current_chunk}\n\n{para}" if current_chunk else para
        if estimate_chinese_chars(candidate) <= max_size:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # 带重叠：下一块的开头取上一块末尾的 overlap 字符
            if overlap > 0 and current_chunk:
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = f"{overlap_text}\n\n{para}"
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]


def _split_by_paragraphs(text: str) -> List[str]:
    """按双换行拆分段落"""
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def _split_long_paragraph(text: str, max_chars: int, overlap: int) -> List[str]:
    """对单个超长段落按句子边界拆分"""
    sentences = _split_by_sentences(text)
    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if estimate_chinese_chars(sentence) > max_chars:
            # 句子本身超长，硬截断
            if current:
                chunks.append(current.strip())
                current = ""
            hard_chunks = _hard_split(sentence, max_chars, overlap)
            chunks.extend(hard_chunks)
            continue

        candidate = f"{current}{sentence}" if current else sentence
        if estimate_chinese_chars(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = sentence

    if current:
        chunks.append(current.strip())

    return chunks if chunks else [text]


def _split_by_sentences(text: str) -> List[str]:
    """按句末标点拆分句子"""
    # 匹配中英文句末标点
    pattern = re.compile(r"(?<=[。！？.!?\n])\s*")
    parts = pattern.split(text)
    return [p for p in parts if p.strip()]


def _hard_split(text: str, max_chars: int, overlap: int) -> List[str]:
    """对无法按语义拆分的文本进行定长截断"""
    chunks: List[str] = []
    pos = 0
    while pos < len(text):
        end = pos + max_chars
        chunks.append(text[pos:end].strip())
        pos = end - overlap if end - overlap > pos else end
    return chunks