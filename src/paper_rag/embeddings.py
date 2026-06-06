"""Embedding client abstractions."""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from paper_rag.exceptions import EmbeddingError


class EmbeddingClient(Protocol):
    """A minimal interface for text embedding providers."""

    model_name: str

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts."""


@dataclass
class OpenAIEmbeddingClient:
    """OpenAI-compatible embedding client with small retry handling."""

    model_name: str = "text-embedding-3-small"
    api_key: str | None = None
    base_url: str | None = None
    max_retries: int = 2
    retry_delay_seconds: float = 1.0

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
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
    """Deterministic local embedding client for tests and offline smoke checks."""

    model_name: str = "hash-embedding-v1"
    dimensions: int = 64

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
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
    """Split a sequence into fixed-size batches."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    return [items[start : start + batch_size] for start in range(0, len(items), batch_size)]
