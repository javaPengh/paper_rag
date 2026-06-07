"""OpenAI 兼容 Embedder 组件 provider。"""

from __future__ import annotations

from dataclasses import dataclass

from paper_rag.embeddings import OpenAIEmbeddingClient


@dataclass
class OpenAIEmbedder(OpenAIEmbeddingClient):
    """把 OpenAI 兼容 embedding 客户端包装成 Embedder 组件。"""
