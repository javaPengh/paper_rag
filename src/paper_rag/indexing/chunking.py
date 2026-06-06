"""Token-aware chunking for parsed PDF pages."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

from paper_rag.schemas import Chunk, Page

Token: TypeAlias = int | str


@dataclass(frozen=True)
class ChunkingConfig:
    """Settings for token-window chunking."""

    chunk_size: int = 800
    chunk_overlap: int = 120
    encoding_name: str = "cl100k_base"

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be greater than or equal to 0")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")


class Tokenizer:
    """Small wrapper around tiktoken with a deterministic fallback for tests."""

    def __init__(self, encoding_name: str) -> None:
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
        if self._encoding is not None:
            return list(self._encoding.encode(text))
        return re.findall(r"\S+", text)

    def decode(self, tokens: Sequence[Token]) -> str:
        if self._encoding is not None:
            return self._encoding.decode([int(token) for token in tokens])
        return " ".join(str(token) for token in tokens)


def chunk_pages(
    pages: Sequence[Page],
    *,
    config: ChunkingConfig | None = None,
    tokenizer: Tokenizer | None = None,
) -> list[Chunk]:
    """Split parsed pages into token-limited chunks while preserving page provenance."""
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
    """Create a stable chunk ID from provenance and text content."""
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    material = (
        f"{document_id}:{document_version_id}:"
        f"{page_start}:{page_end}:{chunk_index}:{text_hash}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
