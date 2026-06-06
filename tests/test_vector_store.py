from pathlib import Path

from paper_rag.indexing.vector_store import ChromaVectorStore
from paper_rag.schemas import Chunk, Document


class FakeCollection:
    def __init__(self) -> None:
        self.upsert_kwargs = {}
        self.query_kwargs = {}

    def upsert(self, **kwargs) -> None:
        self.upsert_kwargs = kwargs

    def count(self) -> int:
        return 2

    def query(self, **kwargs):
        self.query_kwargs = kwargs
        return {"ids": [["chunk-1"]], "distances": [[0.25]]}


def test_chroma_vector_store_does_not_store_chunk_text_documents() -> None:
    collection = FakeCollection()
    store = ChromaVectorStore(Path(".paper_rag/test_vector_store"))
    store._collection = collection
    document = Document(
        id="doc-1",
        tenant_id="default",
        source_uri=str(Path("paper.pdf")),
        file_name="paper.pdf",
        page_count=1,
        current_version_id="version-1",
    )
    chunk = Chunk(
        id="chunk-1",
        document_id=document.id,
        document_version_id="version-1",
        text="this full chunk text belongs in sqlite only",
        page_start=1,
        page_end=1,
        chunk_index=0,
        token_count=8,
    )

    store.upsert_chunks([chunk], [[0.1, 0.2]], {document.id: document})

    assert "documents" not in collection.upsert_kwargs
    assert collection.upsert_kwargs["ids"] == ["chunk-1"]
    assert collection.upsert_kwargs["embeddings"] == [[0.1, 0.2]]
    assert collection.upsert_kwargs["metadatas"] == [
        {
            "tenant_id": "default",
            "document_id": "doc-1",
            "document_version_id": "version-1",
            "page_start": 1,
            "page_end": 1,
            "chunk_index": 0,
            "token_count": 8,
            "file_name": "paper.pdf",
        }
    ]


def test_chroma_vector_store_search_filters_by_tenant() -> None:
    collection = FakeCollection()
    store = ChromaVectorStore(Path(".paper_rag/test_vector_store"))
    store._collection = collection

    results = store.search([0.1, 0.2], tenant_id="tenant-a", top_k=5)

    assert collection.query_kwargs["where"] == {"tenant_id": "tenant-a"}
    assert collection.query_kwargs["n_results"] == 2
    assert results[0].chunk_id == "chunk-1"
    assert results[0].score == 0.75
