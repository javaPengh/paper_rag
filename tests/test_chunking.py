from paper_rag.indexing.chunking import ChunkingConfig, chunk_pages
from paper_rag.schemas import Page


def test_chunk_pages_preserves_page_metadata() -> None:
    pages = [
        Page(document_id="doc-1", page_number=2, text="alpha beta gamma delta epsilon"),
        Page(document_id="doc-1", page_number=1, text="one two three four five"),
    ]

    chunks = chunk_pages(pages, config=ChunkingConfig(chunk_size=3, chunk_overlap=1))

    assert [chunk.page_start for chunk in chunks] == [1, 1, 2, 2]
    assert [chunk.page_end for chunk in chunks] == [1, 1, 2, 2]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    assert all(chunk.document_id == "doc-1" for chunk in chunks)
    assert all(chunk.id for chunk in chunks)


def test_chunk_pages_skips_empty_pages() -> None:
    pages = [
        Page(document_id="doc-1", page_number=1, text="   "),
        Page(document_id="doc-1", page_number=2, text="usable text"),
    ]

    chunks = chunk_pages(pages, config=ChunkingConfig(chunk_size=10, chunk_overlap=0))

    assert len(chunks) == 1
    assert chunks[0].page_start == 2

