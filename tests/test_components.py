"""RAG 组件 registry 和 provider 兼容性测试。"""

from __future__ import annotations

from pathlib import Path

from paper_rag.components import ComponentKind, get_component_registry
from paper_rag.components.chunking import TokenWindowChunker
from paper_rag.components.embedding import HashEmbedder, OpenAIEmbedder
from paper_rag.components.generation import ExtractiveGenerator, OpenAIGenerator
from paper_rag.components.reading import PdfReader
from paper_rag.components.retrieval import VectorRetriever
from paper_rag.domain import Chunk, Document, SearchResult
from paper_rag.indexing import LocalPaperIndex
from paper_rag.indexing.chunking import ChunkingConfig, chunk_pages


def test_component_registry_lists_five_component_kinds() -> None:
    """确认默认 registry 暴露完整 RAG 五段能力。"""
    registry = get_component_registry()

    grouped = registry.grouped_descriptors()

    assert set(grouped) == {
        ComponentKind.READER,
        ComponentKind.CHUNKER,
        ComponentKind.EMBEDDER,
        ComponentKind.RETRIEVER,
        ComponentKind.GENERATOR,
    }
    assert grouped[ComponentKind.READER][0].id == "pdf_reader"
    assert grouped[ComponentKind.CHUNKER][0].id == "token_window_chunker"
    assert {descriptor.id for descriptor in grouped[ComponentKind.EMBEDDER]} == {
        "hash_embedder",
        "openai_embedder",
    }
    assert grouped[ComponentKind.RETRIEVER][0].id == "vector_retriever"
    assert {descriptor.id for descriptor in grouped[ComponentKind.GENERATOR]} == {
        "extractive_generator",
        "openai_generator",
    }


def test_embedder_components_keep_existing_embedding_protocol() -> None:
    """确认本地和 OpenAI 兼容 embedder 仍暴露 model_name 与 embed_texts 边界。"""
    hash_embedder = HashEmbedder(dimensions=8)
    openai_embedder = OpenAIEmbedder(model_name="embedding-test")

    vectors = hash_embedder.embed_texts(["Paper RAG indexes papers."])

    assert hash_embedder.model_name == "hash-embedding-v1"
    assert len(vectors) == 1
    assert len(vectors[0]) == 8
    assert openai_embedder.model_name == "embedding-test"


def test_generator_components_keep_existing_answer_protocol() -> None:
    """确认本地和 OpenAI 兼容 generator 都能通过 generate 返回 Answer。"""
    result = _search_result()
    extractive_answer = ExtractiveGenerator().generate("What does Paper RAG index?", [result])
    openai_answer = OpenAIGenerator(chat_client=_FakeChatClient()).generate(
        "What does Paper RAG index?",
        [result],
    )

    assert extractive_answer.model_name == "extractive-local-v1"
    assert extractive_answer.citations
    assert openai_answer.model_name == "fake-chat-model"
    assert openai_answer.citations


def test_pdf_reader_and_token_window_chunker_match_existing_functions(tmp_path: Path) -> None:
    """确认 Reader/Chunker 包装层不改变现有解析和切分行为。"""
    pdf_path = _write_test_pdf(tmp_path / "paper.pdf")
    reader = PdfReader()
    parsed = reader.read_pdf(pdf_path, tenant_id="test")
    config = ChunkingConfig(chunk_size=20, chunk_overlap=5)
    chunker = TokenWindowChunker(config=config)

    component_chunks = chunker.chunk(parsed.pages)
    legacy_chunks = chunk_pages(parsed.pages, config=config)

    assert parsed.document.file_name == "paper.pdf"
    assert parsed.pages[0].text
    assert [chunk.model_dump() for chunk in component_chunks] == [
        chunk.model_dump() for chunk in legacy_chunks
    ]


def test_vector_retriever_wraps_local_vector_search(tmp_path: Path) -> None:
    """确认 VectorRetriever 能按现有本地索引协议召回 chunk。"""
    index = LocalPaperIndex(tmp_path / "index")
    embedder = HashEmbedder(dimensions=16)
    document = _document()
    chunk = _chunk()
    index.upsert([document], [chunk], embedder.embed_texts([chunk.text]))
    retriever = VectorRetriever(local_index=index, embedding_client=embedder)

    results = retriever.retrieve("What does Paper RAG index?", top_k=1)

    assert len(results) == 1
    assert results[0].chunk.id == chunk.id
    assert results[0].document is not None
    assert results[0].document.file_name == "paper.pdf"


class _FakeChatClient:
    """用于 OpenAI generator 测试的最小聊天客户端替身。"""

    model_name = "fake-chat-model"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """返回带允许引用的确定性答案，避免测试触发网络调用。"""
        assert system_prompt
        assert user_prompt
        return "Paper RAG indexes local PDF papers. [paper.pdf, p.1]"


def _document() -> Document:
    """创建检索测试使用的最小文档元数据。"""
    return Document(
        id="doc1",
        source_uri="paper.pdf",
        file_name="paper.pdf",
        page_count=1,
        current_version_id="version1",
    )


def _chunk() -> Chunk:
    """创建检索和答案测试使用的最小 chunk。"""
    return Chunk(
        id="chunk1",
        document_id="doc1",
        document_version_id="version1",
        text="Paper RAG indexes local PDF papers and stores vectors.",
        page_start=1,
        page_end=1,
        chunk_index=0,
        metadata={"tenant_id": "default"},
    )


def _search_result() -> SearchResult:
    """创建答案生成测试使用的检索结果。"""
    return SearchResult(chunk=_chunk(), document=_document(), score=0.9)


def _write_test_pdf(path: Path) -> Path:
    """创建一个包含简单文本的 PDF，供 Reader 组件测试使用。"""
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 260),
        "Paper RAG indexes local PDF papers and stores vectors.",
        fontsize=11,
    )
    document.save(path)
    document.close()
    return path
