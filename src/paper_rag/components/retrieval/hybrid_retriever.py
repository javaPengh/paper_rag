"""向量与 BM25 候选的 RRF Hybrid Retriever。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from paper_rag.components.retrieval.bm25_retriever import Bm25Retriever
from paper_rag.components.retrieval.sparse_query import EnglishSparseQueryGenerator
from paper_rag.components.retrieval.vector_retriever import VectorRetriever
from paper_rag.domain import SearchResult


class RetrievalTraceCandidate(BaseModel):
    """一路检索或融合排序中的单个候选 chunk 记录。"""

    chunk_id: str = Field(description="候选 chunk 的稳定 ID。")
    rank: int = Field(ge=1, description="该 chunk 在对应候选列表或融合列表中的排名。")
    score: float = Field(description="该列表使用的归一化分数或 RRF 融合分数。")


class HybridRetrievalTrace(BaseModel):
    """一次 Hybrid 检索的两路候选、英文稀疏查询与融合结果。"""

    original_question: str = Field(description="传给向量检索和答案生成器的原始问题。")
    sparse_query: str = Field(description="传给英文 BM25 的自动生成稀疏检索词。")
    vector_candidates: list[RetrievalTraceCandidate] = Field(
        default_factory=list,
        description="向量检索内部候选池，按原始向量排名保存。",
    )
    bm25_candidates: list[RetrievalTraceCandidate] = Field(
        default_factory=list,
        description="BM25 检索内部候选池，按原始词法排名保存。",
    )
    fused_candidates: list[RetrievalTraceCandidate] = Field(
        default_factory=list,
        description="RRF 去重融合后的候选列表，按融合分数排序保存。",
    )


class HybridRetriever:
    """保持最终 Top-k 不变的向量与 BM25 RRF 融合 Retriever。"""

    def __init__(
        self,
        *,
        vector_retriever: VectorRetriever,
        bm25_retriever: Bm25Retriever,
        sparse_query_generator: EnglishSparseQueryGenerator,
        candidate_top_k: int = 10,
        rrf_k: int = 60,
    ) -> None:
        """绑定两路 Retriever、英文稀疏查询生成器和确定性 RRF 参数。"""
        if candidate_top_k <= 0:
            raise ValueError("candidate_top_k must be greater than 0")
        if rrf_k <= 0:
            raise ValueError("rrf_k must be greater than 0")
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.sparse_query_generator = sparse_query_generator
        self.candidate_top_k = candidate_top_k
        self.rrf_k = rrf_k
        self.last_trace: HybridRetrievalTrace | None = None

    def retrieve(self, question: str, *, top_k: int = 5) -> list[SearchResult]:
        """分别召回两路内部候选，RRF 融合后仅返回调用方要求的 Top-k。"""
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")
        sparse_query = self.sparse_query_generator.generate(question)
        vector_results = self.vector_retriever.retrieve(question, top_k=self.candidate_top_k)
        bm25_results = self.bm25_retriever.retrieve(sparse_query, top_k=self.candidate_top_k)
        fused_results, fused_candidates = _fuse_rrf(
            vector_results=vector_results,
            bm25_results=bm25_results,
            rrf_k=self.rrf_k,
        )
        self.last_trace = HybridRetrievalTrace(
            original_question=question,
            sparse_query=sparse_query,
            vector_candidates=_trace_candidates(vector_results),
            bm25_candidates=_trace_candidates(bm25_results),
            fused_candidates=fused_candidates,
        )
        return fused_results[:top_k]


def _fuse_rrf(
    *,
    vector_results: list[SearchResult],
    bm25_results: list[SearchResult],
    rrf_k: int,
) -> tuple[list[SearchResult], list[RetrievalTraceCandidate]]:
    """按 RRF 去重融合两路候选，并将融合分数归一化供答案过滤使用。"""
    records: dict[str, tuple[SearchResult, float]] = {}
    for results in (vector_results, bm25_results):
        for rank, result in enumerate(results, start=1):
            existing_result, existing_score = records.get(result.chunk.id, (result, 0.0))
            records[result.chunk.id] = (existing_result, existing_score + 1 / (rrf_k + rank))
    ranked = sorted(records.items(), key=lambda item: (-item[1][1], item[0]))
    if not ranked:
        return [], []
    maximum_score = ranked[0][1][1]
    fused_results = [
        result.model_copy(update={"score": score / maximum_score, "distance": None})
        for _, (result, score) in ranked
    ]
    fused_candidates = [
        RetrievalTraceCandidate(chunk_id=chunk_id, rank=rank, score=score)
        for rank, (chunk_id, (_, score)) in enumerate(ranked, start=1)
    ]
    return fused_results, fused_candidates


def _trace_candidates(results: list[SearchResult]) -> list[RetrievalTraceCandidate]:
    """将一路 Retriever 的候选结果转换为可写入评测报告的排名记录。"""
    return [
        RetrievalTraceCandidate(chunk_id=result.chunk.id, rank=rank, score=result.score)
        for rank, result in enumerate(results, start=1)
    ]
