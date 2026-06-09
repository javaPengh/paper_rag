"""RAG 组件 registry 和 provider 兼容性测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_rag.components import ComponentKind, get_component_registry
from paper_rag.components.chunking import TokenWindowChunker
from paper_rag.components.embedding import HashEmbedder, OpenAIEmbedder
from paper_rag.components.generation import ExtractiveGenerator, OpenAIGenerator
from paper_rag.components.reading import PdfReader
from paper_rag.components.retrieval import VectorRetriever
from paper_rag.config import Settings
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


def test_component_registry_exposes_model_source_catalog(monkeypatch) -> None:
    """确认 registry 能按 embedding/chat 分别返回来源和模型列表。"""
    monkeypatch.setenv("SILICONFLOW_API_KEY", "secret-key")
    monkeypatch.setenv("EMBEDDING_SOURCE", "siliconflow")
    monkeypatch.setenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
    monkeypatch.setenv("CHAT_SOURCE", "siliconflow")
    monkeypatch.setenv("CHAT_MODEL", "deepseek-ai/DeepSeek-V4-Pro")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODELS", "")
    monkeypatch.setenv("OPENAI_CHAT_MODELS", "")
    registry = get_component_registry()

    catalog = registry.model_catalog()

    assert catalog.embedding.source == "siliconflow"
    assert catalog.embedding.model == "Qwen/Qwen3-Embedding-4B"
    assert [source.id for source in catalog.embedding.sources] == ["siliconflow"]
    siliconflow = next(source for source in catalog.chat.sources if source.id == "siliconflow")
    assert siliconflow.api_key_configured is True
    assert [model.id for model in siliconflow.models][:1] == ["deepseek-ai/DeepSeek-V4-Pro"]
    assert "Qwen/Qwen3-Embedding-4B" not in [model.id for model in siliconflow.models]


def test_component_registry_hides_unconfigured_external_sources() -> None:
    """确认没有模型列表时，外部供应商不会被编造成前端可选来源。"""
    registry = get_component_registry(Settings())

    catalog = registry.model_catalog()

    assert catalog.embedding.sources == []
    assert catalog.embedding.source == ""
    assert catalog.embedding.model is None
    assert catalog.chat.sources == []
    assert catalog.chat.source == ""
    assert catalog.chat.model is None


def test_external_components_require_explicit_source_model_and_credentials() -> None:
    """确认外部组件缺少调用配置时直接报错，而不是使用默认供应商或模型。"""
    registry = get_component_registry(Settings())

    with pytest.raises(ValueError, match="缺少 embedding 模型来源"):
        registry.create_embedder("openai_embedder")
    with pytest.raises(ValueError, match="缺少对话模型来源"):
        registry.create_generator("openai_generator")

    source_only_registry = get_component_registry(
        Settings(
            embedding_source="siliconflow",
            embedding_model="Qwen/Qwen3-Embedding-4B",
            chat_source="siliconflow",
            llm_model="deepseek-ai/DeepSeek-V4-Pro",
        )
    )
    with pytest.raises(ValueError, match="SILICONFLOW_API_KEY"):
        source_only_registry.create_embedder("openai_embedder")
    with pytest.raises(ValueError, match="SILICONFLOW_API_KEY"):
        source_only_registry.create_generator("openai_generator")

    base_url_missing_registry = get_component_registry(
        Settings(
            embedding_source="siliconflow",
            embedding_model="Qwen/Qwen3-Embedding-4B",
            chat_source="siliconflow",
            llm_model="deepseek-ai/DeepSeek-V4-Pro",
            siliconflow_api_key="secret-key",
        )
    )
    with pytest.raises(ValueError, match="SILICONFLOW_BASE_URL"):
        base_url_missing_registry.create_embedder("openai_embedder")


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
