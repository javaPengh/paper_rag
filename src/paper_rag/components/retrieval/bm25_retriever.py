"""基于现有 chunk 的确定性 BM25 Retriever。"""

from __future__ import annotations

import math
import re
from collections import Counter

from paper_rag.domain import SearchResult
from paper_rag.exceptions import RetrievalError
from paper_rag.indexing.local_index import LocalPaperIndex

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._/-]*")


class Bm25Retriever:
    """从指定 tenant 的现有 chunk 构建内存 BM25 词法索引并召回证据。"""

    def __init__(
        self,
        *,
        local_index: LocalPaperIndex,
        tenant_id: str = "default",
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """加载 tenant chunk 并初始化固定参数的 BM25 词法索引。"""
        if k1 <= 0:
            raise ValueError("BM25 k1 must be greater than 0")
        if not 0 <= b <= 1:
            raise ValueError("BM25 b must be between 0 and 1")
        self.local_index = local_index
        self.tenant_id = tenant_id
        self.k1 = k1
        self.b = b
        self._chunks = local_index.store.list_chunks(tenant_id=tenant_id)
        self._term_frequencies = [Counter(_tokenize(chunk.text)) for chunk in self._chunks]
        self._document_frequencies = _document_frequencies(self._term_frequencies)
        self._average_length = _average_document_length(self._term_frequencies)

    @property
    def chunk_count(self) -> int:
        """返回词法索引覆盖的 chunk 数量。"""
        return len(self._chunks)

    def retrieve(self, question: str, *, top_k: int = 5) -> list[SearchResult]:
        """按 BM25 词法相关性返回 tenant 内的前若干 chunk。"""
        if not question.strip():
            raise RetrievalError("Question cannot be empty.")
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")
        if not self._chunks:
            raise RetrievalError("Local index has no chunks. Build the index before retrieval.")
        query_terms = _tokenize(question)
        if not query_terms:
            return []
        raw_scores = [
            self._score(query_terms, term_frequencies)
            for term_frequencies in self._term_frequencies
        ]
        ranked_indexes = sorted(
            (index for index, score in enumerate(raw_scores) if score > 0),
            key=lambda index: (-raw_scores[index], self._chunks[index].id),
        )[:top_k]
        if not ranked_indexes:
            return []
        maximum_score = raw_scores[ranked_indexes[0]]
        return [
            SearchResult(
                chunk=self._chunks[index],
                document=self.local_index.store.get_document(self._chunks[index].document_id),
                score=raw_scores[index] / maximum_score,
                distance=None,
            )
            for index in ranked_indexes
        ]

    def _score(self, query_terms: list[str], term_frequencies: Counter[str]) -> float:
        """计算一个 chunk 相对于查询词的 BM25 原始分数。"""
        document_length = sum(term_frequencies.values())
        score = 0.0
        corpus_size = len(self._chunks)
        for term in set(query_terms):
            frequency = term_frequencies.get(term, 0)
            if frequency == 0:
                continue
            document_frequency = self._document_frequencies.get(term, 0)
            inverse_document_frequency = math.log(
                1 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            denominator = frequency + self.k1 * (
                1 - self.b + self.b * document_length / self._average_length
            )
            score += inverse_document_frequency * frequency * (self.k1 + 1) / denominator
        return score


def _tokenize(text: str) -> list[str]:
    """提取英文论文和英文稀疏查询可共享的确定性词法 token。"""
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


def _document_frequencies(term_frequencies: list[Counter[str]]) -> Counter[str]:
    """统计每个 token 出现在多少 chunk 中，供 BM25 计算逆文档频率。"""
    frequencies: Counter[str] = Counter()
    for terms in term_frequencies:
        frequencies.update(terms.keys())
    return frequencies


def _average_document_length(term_frequencies: list[Counter[str]]) -> float:
    """计算 BM25 长度归一化使用的平均 chunk token 数。"""
    if not term_frequencies:
        return 1.0
    return max(sum(sum(terms.values()) for terms in term_frequencies) / len(term_frequencies), 1.0)
