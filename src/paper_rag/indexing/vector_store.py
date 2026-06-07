"""基于 Chroma 的 chunk embedding 向量存储。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paper_rag.domain import Chunk, Document
from paper_rag.exceptions import ConfigurationError, IndexOperationError


@dataclass(frozen=True)
class VectorHit:
    """原始向量检索命中结果。"""

    chunk_id: str = field(metadata={"description": "向量搜索返回的 chunk ID。"})
    score: float = field(
        metadata={"description": "由后端距离换算得到的相似度分数。"},
    )
    distance: float | None = field(
        default=None,
        metadata={"description": "向量后端返回的原始距离（如有）。"},
    )


class ChromaVectorStore:
    """用于 chunk embedding 的持久化 Chroma 集合。"""

    def __init__(self, index_dir: Path, collection_name: str = "paper_rag_chunks_v2") -> None:
        """在本地索引目录下准备一个延迟初始化的 Chroma 集合。"""
        self.index_dir = Path(index_dir)
        self.chroma_dir = self.index_dir / "chroma"
        self.collection_name = collection_name
        self._collection = None

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        documents_by_id: dict[str, Document],
    ) -> None:
        """把 chunk embedding 和轻量元数据写入 Chroma。"""
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise IndexOperationError(
                f"Cannot index {len(chunks)} chunks with {len(embeddings)} embeddings."
            )

        collection = self._get_collection()
        collection.upsert(
            ids=[chunk.id for chunk in chunks],
            embeddings=embeddings,
            metadatas=[
                self._metadata_for_chunk(chunk, documents_by_id.get(chunk.document_id))
                for chunk in chunks
            ],
        )

    def delete_document_version_ids(self, document_version_ids: list[str]) -> None:
        """在重新索引时删除过期文档版本的向量。"""
        if not document_version_ids:
            return
        collection = self._get_collection()
        for document_version_id in document_version_ids:
            try:
                collection.delete(where={"document_version_id": document_version_id})
            except Exception as exc:
                raise IndexOperationError(
                    f"Could not delete vectors for version {document_version_id}: {exc}"
                ) from exc

    def search(
        self,
        query_embedding: list[float],
        *,
        tenant_id: str,
        top_k: int,
    ) -> list[VectorHit]:
        """搜索按租户过滤的 chunk，并返回原始向量命中结果。"""
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")

        collection = self._get_collection()
        count = collection.count()
        if count == 0:
            return []

        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            where={"tenant_id": tenant_id},
            include=["distances"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[VectorHit] = []
        for chunk_id, distance in zip(ids, distances, strict=False):
            numeric_distance = float(distance) if distance is not None else None
            score = 1.0 - numeric_distance if numeric_distance is not None else 0.0
            hits.append(VectorHit(chunk_id=str(chunk_id), score=score, distance=numeric_distance))
        return hits

    def _get_collection(self):
        """延迟创建或复用持久化的 Chroma 集合。"""
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
            from chromadb.config import Settings
        except ModuleNotFoundError as exc:
            raise ConfigurationError(
                "ChromaDB is required for local vector indexes. Install with "
                'pip install -e ".[dev]".'
            ) from exc

        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(self.chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    @staticmethod
    def _metadata_for_chunk(chunk: Chunk, document: Document | None) -> dict[str, Any]:
        """构建支持租户过滤和调试的紧凑元数据。"""
        tenant_id = (
            document.tenant_id
            if document is not None
            else chunk.metadata.get("tenant_id", "default")
        )
        metadata: dict[str, Any] = {
            "tenant_id": tenant_id,
            "document_id": chunk.document_id,
            "document_version_id": chunk.document_version_id,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count or 0,
        }
        if document is not None:
            metadata.update(
                {
                    "file_name": document.file_name,
                }
            )
        return metadata
