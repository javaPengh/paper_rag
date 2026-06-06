"""Coordinator for the local paper index."""

from __future__ import annotations

from pathlib import Path

from paper_rag.indexing.metadata_store import MetadataStore
from paper_rag.indexing.vector_store import ChromaVectorStore
from paper_rag.schemas import Chunk, Document, DocumentVersion, SearchResult


class LocalPaperIndex:
    """High-level local index combining vector search and metadata lookup."""

    def __init__(self, index_dir: Path) -> None:
        self.index_dir = Path(index_dir)
        self.store = MetadataStore(self.index_dir)
        self.vector_store = ChromaVectorStore(self.index_dir)

    def upsert(
        self,
        documents: list[Document],
        chunks: list[Chunk],
        embeddings: list[list[float]],
        versions: list[DocumentVersion] | None = None,
    ) -> None:
        documents_by_id = {document.id: document for document in documents}
        self.store.upsert_documents(documents)
        if versions:
            self.store.upsert_versions(versions)
        self.store.upsert_chunks(chunks)
        self.vector_store.upsert_chunks(chunks, embeddings, documents_by_id)

    def delete_document_ids(self, document_ids: list[str]) -> None:
        version_ids = [
            version_id
            for document_id in document_ids
            if (document := self.store.get_document(document_id)) is not None
            if (version_id := document.current_version_id) is not None
        ]
        self.vector_store.delete_document_version_ids(version_ids)
        self.store.delete_document_ids(document_ids)

    def delete_document_version_ids(self, document_version_ids: list[str]) -> None:
        self.vector_store.delete_document_version_ids(document_version_ids)
        self.store.delete_document_version_ids(document_version_ids)

    def search(
        self,
        query_embedding: list[float],
        *,
        tenant_id: str,
        top_k: int,
    ) -> list[SearchResult]:
        hits = self.vector_store.search(query_embedding, tenant_id=tenant_id, top_k=top_k)
        results: list[SearchResult] = []
        for hit in hits:
            chunk = self.store.get_chunk(hit.chunk_id)
            if chunk is None:
                continue
            document = self.store.get_document(chunk.document_id)
            results.append(
                SearchResult(
                    chunk=chunk,
                    document=document,
                    score=hit.score,
                    distance=hit.distance,
                )
            )
        return results
