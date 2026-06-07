"""Hash Embedder 组件 provider。"""

from __future__ import annotations

from dataclasses import dataclass

from paper_rag.embeddings import HashEmbeddingClient


@dataclass(frozen=True)
class HashEmbedder(HashEmbeddingClient):
    """把确定性本地 hash embedding 包装成 Embedder 组件。"""
