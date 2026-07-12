"""BM25、RRF Hybrid Retriever 与英文稀疏查询测试。"""

from __future__ import annotations

import pytest

from paper_rag.components.retrieval.bm25_retriever import Bm25Retriever
from paper_rag.components.retrieval.hybrid_retriever import HybridRetriever, _fuse_rrf
from paper_rag.components.retrieval.sparse_query import EnglishSparseQueryGenerator
from paper_rag.domain import Chunk, Document, SearchResult
from paper_rag.embeddings import HashEmbeddingClient
from paper_rag.exceptions import RetrievalError
from paper_rag.indexing import LocalPaperIndex


class _FakeSparseQueryClient:
    """返回固定英文 BM25 查询的聊天客户端替身。"""

    model_name = "fake-chat-model"
    source_name = "fake"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """确认提示词边界后返回固定英文检索词。"""
        assert "BM25" in system_prompt
        assert "Original question" in user_prompt
        return "benchmark construction"


class _FakeRetriever:
    """返回固定候选列表的最小 Retriever 替身。"""

    def __init__(self, results: list[SearchResult]) -> None:
        """保存调用时应返回的候选结果。"""
        self.results = results
        self.questions: list[str] = []

    def retrieve(self, question: str, *, top_k: int = 5) -> list[SearchResult]:
        """记录实际查询并按调用方限制截取候选。"""
        self.questions.append(question)
        return self.results[:top_k]


def test_bm25_retriever_returns_exact_english_chunk_with_tenant_isolation(tmp_path) -> None:
    """确认 BM25 从现有 tenant chunk 中按英文词面召回目标证据。"""
    index = LocalPaperIndex(tmp_path / "index")
    embedder = HashEmbeddingClient()
    target_document = _document("doc_target", "target.pdf")
    other_document = _document("doc_other", "other.pdf")
    target_chunk = _chunk(
        "chunk_target",
        "doc_target",
        "Benchmark Construction Data Collection and Unification",
        tenant_id="tenant_a",
    )
    other_chunk = _chunk(
        "chunk_other",
        "doc_other",
        "unrelated material",
        tenant_id="tenant_b",
    )
    index.upsert(
        [target_document, other_document],
        [target_chunk, other_chunk],
        embedder.embed_texts([target_chunk.text, other_chunk.text]),
    )

    results = Bm25Retriever(local_index=index, tenant_id="tenant_a").retrieve(
        "benchmark construction",
        top_k=3,
    )

    assert [result.chunk.id for result in results] == ["chunk_target"]
    assert results[0].score == 1.0


def test_hybrid_retriever_uses_rrf_and_keeps_final_top_k() -> None:
    """确认两路候选经 RRF 融合后，只返回调用方要求的最终数量。"""
    document = _document("doc", "paper.pdf")
    chunk_a = _chunk("chunk_a", "doc", "vector first")
    chunk_b = _chunk("chunk_b", "doc", "bm25 first")
    chunk_c = _chunk("chunk_c", "doc", "other")
    vector_retriever = _FakeRetriever(
        [
            SearchResult(chunk=chunk_a, document=document, score=0.9),
            SearchResult(chunk=chunk_c, document=document, score=0.8),
            SearchResult(chunk=chunk_b, document=document, score=0.7),
        ]
    )
    bm25_retriever = _FakeRetriever(
        [SearchResult(chunk=chunk_b, document=document, score=1.0)]
    )
    hybrid = HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25_retriever,
        sparse_query_generator=EnglishSparseQueryGenerator(_FakeSparseQueryClient()),
        candidate_top_k=3,
        rrf_k=60,
    )

    results = hybrid.retrieve("构建基准测试做了什么？", top_k=1)

    assert [result.chunk.id for result in results] == ["chunk_b"]
    assert vector_retriever.questions == ["构建基准测试做了什么？"]
    assert bm25_retriever.questions == ["benchmark construction"]
    assert hybrid.last_trace is not None
    assert len(hybrid.last_trace.vector_candidates) == 3
    assert len(hybrid.last_trace.fused_candidates) == 3


def test_sparse_query_generator_rejects_empty_model_output() -> None:
    """确认空英文稀疏检索词不会静默退化为纯向量检索。"""

    class _EmptySparseQueryClient:
        """返回空稀疏检索词的异常客户端替身。"""

        model_name = "fake-chat-model"

        def complete(self, *, system_prompt: str, user_prompt: str) -> str:
            """返回空文本，模拟模型无有效输出。"""
            return " "

    generator = EnglishSparseQueryGenerator(_EmptySparseQueryClient())

    with pytest.raises(RetrievalError, match="空结果"):
        generator.generate("构建基准测试做了什么？")


def test_rrf_uses_chunk_id_for_ties_and_accepts_empty_candidates() -> None:
    """确认 RRF 对同分候选按 chunk ID 稳定排序，并能返回空融合结果。"""
    document = _document("doc", "paper.pdf")
    chunk_a = _chunk("chunk_a", "doc", "first")
    chunk_b = _chunk("chunk_b", "doc", "second")
    first_results, first_trace = _fuse_rrf(
        vector_results=[SearchResult(chunk=chunk_b, document=document, score=0.9)],
        bm25_results=[SearchResult(chunk=chunk_a, document=document, score=1.0)],
        rrf_k=60,
    )
    empty_results, empty_trace = _fuse_rrf(
        vector_results=[],
        bm25_results=[],
        rrf_k=60,
    )

    assert [result.chunk.id for result in first_results] == ["chunk_a", "chunk_b"]
    assert [candidate.chunk_id for candidate in first_trace] == ["chunk_a", "chunk_b"]
    assert empty_results == []
    assert empty_trace == []


def _document(document_id: str, file_name: str) -> Document:
    """创建 Hybrid 检索测试使用的最小文档元数据。"""
    return Document(
        id=document_id,
        source_uri=file_name,
        file_name=file_name,
        page_count=1,
        current_version_id=f"{document_id}_version",
    )


def _chunk(
    chunk_id: str,
    document_id: str,
    text: str,
    *,
    tenant_id: str = "default",
) -> Chunk:
    """创建带 tenant 元数据的最小检索 chunk。"""
    return Chunk(
        id=chunk_id,
        document_id=document_id,
        document_version_id=f"{document_id}_version",
        text=text,
        page_start=1,
        page_end=1,
        chunk_index=0,
        metadata={"tenant_id": tenant_id},
    )
