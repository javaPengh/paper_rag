from pathlib import Path
from uuid import uuid4

from paper_rag.embeddings import EmbeddingClient, HashEmbeddingClient
from paper_rag.indexing.chunking import ChunkingConfig
from paper_rag.indexing.local_index import LocalPaperIndex
from paper_rag.indexing.pipeline import build_index_from_directory
from paper_rag.retrieval import Retriever


class CountingEmbeddingClient:
    model_name = "counting-hash-embedding-v1"

    def __init__(self) -> None:
        self.inner = HashEmbeddingClient(model_name=self.model_name, dimensions=32)
        self.call_count = 0
        self.text_count = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.text_count += len(texts)
        return self.inner.embed_texts(texts)


def test_build_index_reuses_unchanged_pdf_and_reindexes_changed_pdf() -> None:
    run_dir = Path(".paper_rag") / "test_pipeline" / uuid4().hex
    source_dir = run_dir / "source"
    index_dir = run_dir / "index"
    source_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = source_dir / "paper.pdf"
    _write_pdf(pdf_path, "alpha retrieval evidence")

    embedding_client = CountingEmbeddingClient()
    first = build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        chunking_config=ChunkingConfig(chunk_size=100, chunk_overlap=0),
    )

    assert len(first.indexed_documents) == 1
    assert first.indexed_chunk_count >= 1
    assert embedding_client.text_count >= 1
    assert first.status.document_count == 1
    assert first.status.chunk_count >= 1

    embedding_client.call_count = 0
    embedding_client.text_count = 0
    second = build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        chunking_config=ChunkingConfig(chunk_size=100, chunk_overlap=0),
    )

    assert len(second.reused_documents) == 1
    assert second.indexed_chunk_count == 0
    assert embedding_client.text_count == 0

    _write_pdf(pdf_path, "gamma changed evidence")
    third = build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        chunking_config=ChunkingConfig(chunk_size=100, chunk_overlap=0),
    )

    assert len(third.reindexed_documents) == 1
    assert third.indexed_chunk_count >= 1
    assert third.status.document_count == 1

    local_index = LocalPaperIndex(index_dir)
    retriever = Retriever(
        local_index=local_index,
        embedding_client=embedding_client.inner,
    )
    results = retriever.retrieve("gamma evidence", top_k=1)

    assert len(results) == 1
    assert "gamma" in results[0].chunk.text.lower()


def test_build_index_reuses_same_content_from_different_paths_without_embedding() -> None:
    run_dir = Path(".paper_rag") / "test_pipeline" / uuid4().hex
    source_dir = run_dir / "source"
    index_dir = run_dir / "index"
    source_dir.mkdir(parents=True, exist_ok=True)
    _write_pdf(source_dir / "paper-a.pdf", "shared duplicate evidence")

    embedding_client = CountingEmbeddingClient()
    first = build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        chunking_config=ChunkingConfig(chunk_size=100, chunk_overlap=0),
    )
    assert len(first.indexed_documents) == 1
    first_text_count = embedding_client.text_count

    _write_pdf(source_dir / "paper-b.pdf", "shared duplicate evidence")
    embedding_client.call_count = 0
    embedding_client.text_count = 0
    second = build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        chunking_config=ChunkingConfig(chunk_size=100, chunk_overlap=0),
    )

    assert len(second.reused_source_documents) == 1
    assert len(second.reused_content_documents) == 1
    assert second.indexed_chunk_count == 0
    assert embedding_client.text_count == 0
    assert first_text_count >= 1


def test_build_index_keeps_same_content_isolated_between_tenants() -> None:
    run_dir = Path(".paper_rag") / "test_pipeline" / uuid4().hex
    source_dir = run_dir / "source"
    index_dir = run_dir / "index"
    source_dir.mkdir(parents=True, exist_ok=True)
    _write_pdf(source_dir / "paper.pdf", "tenant isolated evidence")

    embedding_client = CountingEmbeddingClient()
    build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        tenant_id="tenant-a",
        chunking_config=ChunkingConfig(chunk_size=100, chunk_overlap=0),
    )
    build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        tenant_id="tenant-b",
        chunking_config=ChunkingConfig(chunk_size=100, chunk_overlap=0),
    )

    local_index = LocalPaperIndex(index_dir)
    tenant_a_docs = local_index.store.list_documents(tenant_id="tenant-a")
    tenant_b_docs = local_index.store.list_documents(tenant_id="tenant-b")

    assert len(tenant_a_docs) == 1
    assert len(tenant_b_docs) == 1
    assert tenant_a_docs[0].id != tenant_b_docs[0].id

    tenant_a_results = Retriever(
        local_index=local_index,
        embedding_client=embedding_client.inner,
        tenant_id="tenant-a",
    ).retrieve("tenant isolated", top_k=3)
    tenant_b_results = Retriever(
        local_index=local_index,
        embedding_client=embedding_client.inner,
        tenant_id="tenant-b",
    ).retrieve("tenant isolated", top_k=3)

    assert {result.document.tenant_id for result in tenant_a_results if result.document} == {
        "tenant-a"
    }
    assert {result.document.tenant_id for result in tenant_b_results if result.document} == {
        "tenant-b"
    }


def _write_pdf(path: Path, text: str) -> None:
    import fitz

    if path.exists():
        path.unlink()
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def assert_embedding_client(_: EmbeddingClient) -> None:
    """Keep the protocol import exercised for static readers."""
