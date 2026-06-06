"""问题 embedding 和 top-k 向量检索。"""

from __future__ import annotations

from paper_rag.embeddings import EmbeddingClient
from paper_rag.exceptions import RetrievalError
from paper_rag.indexing.local_index import LocalPaperIndex
from paper_rag.schemas import SearchResult


class Retriever:
    """为自然语言问题检索证据 chunk。"""

    def __init__(
        self,
        *,
        local_index: LocalPaperIndex,
        embedding_client: EmbeddingClient,
        tenant_id: str = "default",
    ) -> None:
        """将一个租户范围内的检索器绑定到一个索引和 embedding 提供方。"""
        self.local_index = local_index
        self.embedding_client = embedding_client
        self.tenant_id = tenant_id

    def retrieve(self, question: str, *, top_k: int = 5) -> list[SearchResult]:
        """对问题生成 embedding，并为配置的租户检索最匹配的 chunk。"""
        if not question.strip():
            raise RetrievalError("Question cannot be empty.")
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")
        if self.local_index.store.count_chunks(tenant_id=self.tenant_id) == 0:
            raise RetrievalError("Local index has no chunks. Build the index before retrieval.")

        query_embedding = self.embedding_client.embed_texts([question])[0]
        return self.local_index.search(query_embedding, tenant_id=self.tenant_id, top_k=top_k)
