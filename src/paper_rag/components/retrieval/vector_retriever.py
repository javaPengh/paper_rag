"""Chroma 向量 Retriever 组件 provider。"""

from __future__ import annotations

from paper_rag.components.interfaces import Embedder
from paper_rag.domain import SearchResult
from paper_rag.exceptions import RetrievalError
from paper_rag.indexing.local_index import LocalPaperIndex


class VectorRetriever:
    """使用本地 Chroma 向量索引召回证据 chunk 的 Retriever 组件。"""

    def __init__(
        self,
        *,
        local_index: LocalPaperIndex,
        embedding_client: Embedder,
        tenant_id: str = "default",
    ) -> None:
        """把向量检索绑定到一个本地索引、embedding 组件和租户命名空间。"""
        self.local_index = local_index
        self.embedding_client = embedding_client
        self.tenant_id = tenant_id

    def retrieve(self, question: str, *, top_k: int = 5) -> list[SearchResult]:
        """对问题生成 embedding，并从本地向量索引召回 top-k chunk。"""
        if not question.strip():
            raise RetrievalError("Question cannot be empty.")
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")
        if self.local_index.store.count_chunks(tenant_id=self.tenant_id) == 0:
            raise RetrievalError("Local index has no chunks. Build the index before retrieval.")

        query_embedding = self.embedding_client.embed_texts([question])[0]
        return self.local_index.search(query_embedding, tenant_id=self.tenant_id, top_k=top_k)
