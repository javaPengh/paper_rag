"""Token window Chunker 组件 provider。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from paper_rag.domain import Chunk, Page
from paper_rag.indexing.chunking import ChunkingConfig, chunk_pages


@dataclass(frozen=True)
class TokenWindowChunker:
    """把现有 token 窗口切分函数包装成 Chunker 组件。"""

    config: ChunkingConfig = field(
        default_factory=ChunkingConfig,
        metadata={"description": "token 窗口大小、重叠和编码名等切分参数。"},
    )

    def chunk(self, pages: Sequence[Page]) -> list[Chunk]:
        """按配置切分页面文本，保持旧 chunk_pages 行为不变。"""
        return chunk_pages(pages, config=self.config)
