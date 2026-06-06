from pathlib import Path
from uuid import uuid4

from paper_rag.embeddings import HashEmbeddingClient
from paper_rag.exceptions import RetrievalError
from paper_rag.indexing.local_index import LocalPaperIndex
from paper_rag.retrieval import Retriever
from paper_rag.schemas import Chunk, Document, DocumentVersion


def test_local_index_upserts_and_retrieves_chunks() -> None:
    index_dir = Path(".paper_rag") / "test_indexes" / uuid4().hex
    embedding_client = HashEmbeddingClient(dimensions=32)
    local_index = LocalPaperIndex(index_dir)
    document = Document(
        id="doc-1",
        tenant_id="default",
        source_uri=str(Path("paper.pdf").resolve()),
        file_name="paper.pdf",
        page_count=1,
        current_version_id="version-1",
    )
    version = DocumentVersion(
        id="version-1",
        tenant_id="default",
        document_id=document.id,
        content_hash="hash-1",
        source_uri=document.source_uri,
        file_name=document.file_name,
        page_count=1,
    )
    chunks = [
        Chunk(
            id="chunk-1",
            document_id=document.id,
            document_version_id=version.id,
            text="alpha beta retrieval",
            page_start=1,
            page_end=1,
            chunk_index=0,
            token_count=3,
        ),
        Chunk(
            id="chunk-2",
            document_id=document.id,
            document_version_id=version.id,
            text="unrelated chemistry result",
            page_start=1,
            page_end=1,
            chunk_index=1,
            token_count=3,
        ),
    ]

    local_index.upsert(
        documents=[document],
        chunks=chunks,
        embeddings=embedding_client.embed_texts([chunk.text for chunk in chunks]),
        versions=[version],
    )
    retriever = Retriever(local_index=local_index, embedding_client=embedding_client)

    results = retriever.retrieve("alpha retrieval", top_k=1)

    assert len(results) == 1
    assert results[0].chunk.id == "chunk-1"
    assert results[0].document is not None
    assert results[0].document.file_name == "paper.pdf"
    assert results[0].score > 0


def test_retriever_reports_empty_index() -> None:
    index_dir = Path(".paper_rag") / "test_indexes" / uuid4().hex
    embedding_client = HashEmbeddingClient(dimensions=32)
    retriever = Retriever(
        local_index=LocalPaperIndex(index_dir),
        embedding_client=embedding_client,
    )

    try:
        retriever.retrieve("alpha", top_k=1)
    except RetrievalError as exc:
        assert "Build the index" in str(exc)
    else:
        raise AssertionError("Expected RetrievalError for an empty local index")
