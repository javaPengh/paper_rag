"""面向 token 的 PDF 页面分块。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeAlias

from paper_rag.domain import Chunk, Page

# 当可用 tiktoken 时，token 是整数；否则在回退分词器中它是一个单词字符串。
Token: TypeAlias = int | str


@dataclass(frozen=True)
class ChunkingConfig:
    """token 窗口分块的配置。"""

    chunk_size: int = field(
        default=800,
        metadata={"description": "单个 chunk 允许的最大 tokenizer 单元数。"},
    )
    chunk_overlap: int = field(
        default=120,
        metadata={"description": "相邻 chunk 之间重复的 tokenizer 单元数。"},
    )
    encoding_name: str = field(
        default="cl100k_base",
        metadata={"description": "用于模型感知分块边界的 tiktoken 编码。"},
    )

    def __post_init__(self) -> None:
        """拒绝会产生空切片或无法前进的分块窗口。"""
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be greater than or equal to 0")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")


class Tokenizer:
    """对 tiktoken 的轻量封装，并为测试提供确定性的回退实现。"""

    def __init__(self, encoding_name: str) -> None:
        """加载指定分词器，同时让离线测试对依赖更宽容。"""
        self._encoding = None
        try:
            import tiktoken  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            return

        try:
            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            self._encoding = None

    def encode(self, text: str) -> list[Token]:
        """把文本转换成 tokenizer 单元，用于分块窗口计算。"""
        if self._encoding is not None:
            return list(self._encoding.encode(text))
        return re.findall(r"\S+", text)

    def decode(self, tokens: Sequence[Token]) -> str:
        """把 tokenizer 单元转换回分块文本，用于存储和引用。"""
        if self._encoding is not None:
            return self._encoding.decode([int(token) for token in tokens])
        return " ".join(str(token) for token in tokens)


def chunk_pages(
    pages: Sequence[Page],
    *,
    config: ChunkingConfig | None = None,
    tokenizer: Tokenizer | None = None,
) -> list[Chunk]:
    """在保留页面来源信息的同时，把解析后的页面拆成 token 限制的块。"""
    if not pages:
        return []

    active_config = config or ChunkingConfig()
    active_tokenizer = tokenizer or Tokenizer(active_config.encoding_name)
    sorted_pages = sorted(pages, key=lambda page: (page.document_id, page.page_number))

    chunks: list[Chunk] = []
    chunk_indexes: dict[str, int] = {}

    for page in sorted_pages:
        text = page.text.strip()
        if not text:
            continue

        tokens = active_tokenizer.encode(text)
        if not tokens:
            continue

        start = 0
        while start < len(tokens):
            end = min(start + active_config.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = active_tokenizer.decode(chunk_tokens).strip()
            if chunk_text:
                chunk_index = chunk_indexes.get(page.document_id, 0)
                chunks.append(
                    Chunk(
                        id=make_chunk_id(
                            document_id=page.document_id,
                            document_version_id=page.document_version_id or page.document_id,
                            page_start=page.page_number,
                            page_end=page.page_number,
                            chunk_index=chunk_index,
                            text=chunk_text,
                        ),
                        document_id=page.document_id,
                        document_version_id=page.document_version_id or page.document_id,
                        text=chunk_text,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        chunk_index=chunk_index,
                        token_count=len(chunk_tokens),
                    )
                )
                chunk_indexes[page.document_id] = chunk_index + 1

            if end == len(tokens):
                break
            start = end - active_config.chunk_overlap

    return chunks


def make_chunk_id(
    *,
    document_id: str,
    document_version_id: str,
    page_start: int,
    page_end: int,
    chunk_index: int,
    text: str,
) -> str:
    """根据来源信息和文本内容创建稳定的 chunk ID。"""
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    material = (
        f"{document_id}:{document_version_id}:"
        f"{page_start}:{page_end}:{chunk_index}:{text_hash}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
