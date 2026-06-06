"""Embedding 客户端抽象。"""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from paper_rag.exceptions import EmbeddingError


class EmbeddingClient(Protocol):
    """文本 embedding 提供方的最小接口。"""

    # 该提供方/模型标识会持久化到索引状态中，用于兼容性检查。
    model_name: str

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """对一批文本生成 embedding。"""


@dataclass
class OpenAIEmbeddingClient:
    """带简单重试处理的 OpenAI 兼容 embedding 客户端。"""

    model_name: str = field(
        default="text-embedding-3-small",
        metadata={"description": "OpenAI-compatible embedding model name."},
    )
    api_key: str | None = field(
        default=None,
        metadata={"description": "API key for the embedding provider."},
    )
    base_url: str | None = field(
        default=None,
        metadata={"description": "Optional OpenAI-compatible embedding endpoint override."},
    )
    max_retries: int = field(
        default=2,
        metadata={"description": "Retry count for transient embedding provider failures."},
    )
    retry_delay_seconds: float = field(
        default=1.0,
        metadata={"description": "Base delay between embedding retries in seconds."},
    )

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """为每个非空输入文本返回一个 embedding 向量。"""
        cleaned_texts = [text for text in texts if text.strip()]
        if not cleaned_texts:
            return []

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._embed_once(cleaned_texts)
            except Exception as exc:  # OpenAI clients raise provider-specific subclasses.
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_delay_seconds * (attempt + 1))

        raise EmbeddingError(
            f"Embedding generation failed after {self.max_retries + 1} attempts: {last_error}"
        )

    def _embed_once(self, texts: Sequence[str]) -> list[list[float]]:
        """仅调用一次提供方，把重试策略留在 SDK 之外。"""
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise EmbeddingError(
                "OpenAI SDK is required for embeddings. Install dependencies with "
                'pip install -e ".[dev]".'
            ) from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.embeddings.create(model=self.model_name, input=list(texts))
        embeddings = [item.embedding for item in response.data]
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"Embedding provider returned {len(embeddings)} vectors for {len(texts)} texts."
            )
        return embeddings


@dataclass(frozen=True)
class HashEmbeddingClient:
    """用于测试和离线冒烟检查的确定性本地 embedding 客户端。"""

    model_name: str = field(
        default="hash-embedding-v1",
        metadata={"description": "Local deterministic embedding model identifier."},
    )
    dimensions: int = field(
        default=64,
        metadata={"description": "Fixed vector size for hash-based local embeddings."},
    )

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """在不依赖网络的情况下确定性地生成文本 embedding。"""
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        """将词汇 token 哈希为归一化向量，以支持可复现的本地检索。"""
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[\w-]+", text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def batched(items: Sequence[str], batch_size: int) -> list[Sequence[str]]:
    """把一个序列拆分成固定大小的批次。"""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    return [items[start : start + batch_size] for start in range(0, len(items), batch_size)]
