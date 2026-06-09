"""FastAPI 与 Web Inspector 集成测试。"""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from paper_rag.api import create_app
from paper_rag.embeddings import HashEmbeddingClient
from paper_rag.indexing.chunking import ChunkingConfig
from paper_rag.indexing.pipeline import build_index_from_directory

TEST_PDF_TEXT = (
    "Paper RAG is a learning project for citation-backed retrieval augmented generation. "
    "It indexes local PDF papers, splits pages into chunks, embeds each chunk, and stores "
    "the vectors in a local index. The command line workflow can answer questions with "
    "file names and page citations."
)


def test_api_inspector_lists_existing_index_without_local_qa_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认 Inspector 仍能展示既有索引，但问答不会再走本地模式。"""
    run_dir = tmp_path / "test_api" / uuid4().hex
    source_dir = run_dir / "papers"
    index_dir = run_dir / "index"
    _write_test_pdf(source_dir / "paper_rag_test.pdf")
    build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=HashEmbeddingClient(),
        tenant_id="default",
        chunking_config=ChunkingConfig(chunk_size=120, chunk_overlap=20),
    )

    _clear_model_env(monkeypatch)
    client = TestClient(create_app())
    params = {"index_dir": str(index_dir), "tenant_id": "default"}

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    status = client.get("/api/index/status", params=params)
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert status.json()["document_count"] == 1

    documents = client.get("/api/documents", params=params)
    assert documents.status_code == 200
    document_payload = documents.json()
    assert len(document_payload) == 1
    assert document_payload[0]["file_name"] == "paper_rag_test.pdf"
    assert document_payload[0]["content_hash"]

    chunks = client.get(
        f"/api/documents/{document_payload[0]['id']}/chunks",
        params={**params, "limit": 1},
    )
    assert chunks.status_code == 200
    chunk_payload = chunks.json()
    assert len(chunk_payload) == 1
    assert chunk_payload[0]["document_version_id"] == document_payload[0]["current_version_id"]

    answer = client.post(
        "/api/ask",
        json={
            "question": "What does Paper RAG index?",
            "index_dir": str(index_dir),
            "tenant_id": "default",
            "top_k": 3,
        },
    )
    assert answer.status_code == 400


def test_api_serves_inspector_upload_ui() -> None:
    """确认 Inspector 页面仍保留上传与问答所需的控件骨架。"""
    client = TestClient(create_app())

    page = client.get("/")
    assert page.status_code == 200
    assert 'id="index-dir"' in page.text
    assert 'id="upload-form"' in page.text
    assert 'id="upload-file"' in page.text
    assert 'id="upload-embedding-source"' in page.text
    assert 'id="upload-embedding-model"' in page.text
    assert 'id="ask-embedding-source"' in page.text
    assert 'id="ask-embedding-model"' in page.text
    assert 'id="ask-chat-source"' in page.text
    assert 'id="ask-chat-model"' in page.text
    assert 'src="/static/inspector.js"' in page.text


def test_api_config_exposes_model_names_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认运行时配置仅暴露当前模型选择，不泄露密钥。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("EMBEDDING_SOURCE", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("CHAT_SOURCE", "openai")
    monkeypatch.setenv("CHAT_MODEL", "llm-model")

    client = TestClient(create_app())
    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_source"] == "openai"
    assert payload["embedding_model"] == "embedding-model"
    assert payload["chat_source"] == "openai"
    assert payload["chat_model"] == "llm-model"
    assert payload["llm_model"] == "llm-model"
    assert payload["api_key_configured"] is True
    assert payload["base_url_configured"] is True
    assert payload["recommended_api_index_dir"] == ".paper_rag/api_index"
    assert "secret-key" not in response.text


def test_api_components_exposes_catalog_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认组件 catalog 仍覆盖五类组件，且模型来源按能力分开。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "siliconflow-secret")
    monkeypatch.setenv("EMBEDDING_SOURCE", "siliconflow")
    monkeypatch.setenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
    monkeypatch.setenv("CHAT_SOURCE", "siliconflow")
    monkeypatch.setenv("CHAT_MODEL", "deepseek-ai/DeepSeek-V4-Pro")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODELS", "")
    monkeypatch.setenv("OPENAI_CHAT_MODELS", "")

    client = TestClient(create_app())
    response = client.get("/api/components")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "model_catalog",
        "reader",
        "chunker",
        "embedder",
        "retriever",
        "generator",
    }
    assert {item["id"] for item in payload["embedder"]} == {
        "hash_embedder",
        "openai_embedder",
    }
    assert {item["id"] for item in payload["generator"]} == {
        "extractive_generator",
        "openai_generator",
    }

    embedding_catalog = payload["model_catalog"]["embedding"]
    assert embedding_catalog["source"] == "siliconflow"
    assert embedding_catalog["model"] == "Qwen/Qwen3-Embedding-4B"
    assert [source["id"] for source in embedding_catalog["sources"]] == ["siliconflow"]
    siliconflow_embedding = embedding_catalog["sources"][0]
    assert siliconflow_embedding["api_key_configured"] is True
    assert "Qwen/Qwen3-Embedding-4B" in [
        model["id"] for model in siliconflow_embedding["models"]
    ]

    chat_catalog = payload["model_catalog"]["chat"]
    assert chat_catalog["source"] == "siliconflow"
    assert chat_catalog["model"] == "deepseek-ai/DeepSeek-V4-Pro"
    assert [source["id"] for source in chat_catalog["sources"]] == ["siliconflow"]
    chat_models = [model["id"] for model in chat_catalog["sources"][0]["models"]]
    assert "deepseek-ai/DeepSeek-V4-Pro" in chat_models
    assert "Qwen/Qwen3-Embedding-4B" not in chat_models
    assert "secret-key" not in response.text
    assert "siliconflow-secret" not in response.text


def test_api_components_hides_unconfigured_external_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认未配置模型列表时，前端下拉不会出现任何伪造来源。"""
    monkeypatch.chdir(tmp_path)
    _clear_model_env(monkeypatch)

    client = TestClient(create_app())
    response = client.get("/api/components")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_catalog"]["embedding"]["sources"] == []
    assert payload["model_catalog"]["embedding"]["source"] == ""
    assert payload["model_catalog"]["embedding"]["model"] is None
    assert payload["model_catalog"]["chat"]["sources"] == []
    assert payload["model_catalog"]["chat"]["source"] == ""
    assert payload["model_catalog"]["chat"]["model"] is None

    config = client.get("/api/config")
    assert config.status_code == 200
    config_payload = config.json()
    assert config_payload["embedding_source"] is None
    assert config_payload["embedding_model"] is None
    assert config_payload["chat_source"] is None
    assert config_payload["chat_model"] is None


def test_api_ask_requires_external_model_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认问答缺少外部模型配置时会直接返回明确错误。"""
    monkeypatch.chdir(tmp_path)
    _clear_model_env(monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/ask",
        json={
            "question": "What does this knowledge base say?",
            "index_dir": str(tmp_path / "index"),
        },
    )

    assert response.status_code == 400
    assert "缺少 embedding 模型来源" in response.json()["detail"]


def test_api_upload_requires_external_model_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认上传索引在缺少 embedding 配置时会直接失败。"""
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    source_dir = run_dir / "source"
    index_dir = run_dir / "index"
    upload_dir = run_dir / "uploads"
    pdf_path = _write_test_pdf(source_dir / "paper_rag_test.pdf")
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(upload_dir))
    _clear_model_env(monkeypatch)

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(index_dir),
            "chunk_size": "120",
            "chunk_overlap": "20",
        },
        files={"file": ("paper_rag_test.pdf", pdf_path.read_bytes(), "application/pdf")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "indexing"
    assert "缺少 embedding 模型来源" in detail["message"]


def test_api_upload_rejects_non_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认上传接口仍会在文件校验阶段拒绝非 PDF。"""
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
        },
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "upload"
    assert detail["error_type"] == "DocumentUploadError"
    assert "Only PDF" in detail["message"]


def test_api_upload_rejects_empty_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认空 PDF 会在上传阶段被拦截。"""
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
        },
        files={"file": ("paper.pdf", b"", "application/pdf")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "upload"
    assert detail["error_type"] == "DocumentUploadError"
    assert "empty" in detail["message"]


def test_api_upload_rejects_pdf_over_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认大小限制仍在上传阶段生效。"""
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))
    monkeypatch.setenv("PAPER_RAG_UPLOAD_MAX_BYTES", "5")

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
        },
        files={"file": ("paper.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "upload"
    assert "too large" in detail["message"]


def test_api_upload_returns_missing_model_error_before_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认未配置模型时，上传不会继续进入解析阶段。"""
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))
    _clear_model_env(monkeypatch)

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
        },
        files={"file": ("broken.pdf", b"%PDF-this is not parseable", "application/pdf")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "indexing"
    assert "缺少 embedding 模型来源" in detail["message"]


def test_api_upload_returns_missing_model_error_before_chunk_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认未配置模型时，索引参数校验不会掩盖缺配置错误。"""
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    source_dir = run_dir / "source"
    index_dir = run_dir / "index"
    upload_dir = run_dir / "uploads"
    pdf_path = _write_test_pdf(source_dir / "paper_rag_test.pdf")
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(upload_dir))
    _clear_model_env(monkeypatch)

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(index_dir),
            "chunk_size": "10",
            "chunk_overlap": "10",
        },
        files={"file": ("paper.pdf", pdf_path.read_bytes(), "application/pdf")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "indexing"
    assert "缺少 embedding 模型来源" in detail["message"]


def _write_test_pdf(path: Path, text: str = TEST_PDF_TEXT) -> Path:
    """创建一个极小 PDF 夹具，避免依赖生产示例文件。"""
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 520, 240), text, fontsize=11)
    document.save(path)
    document.close()
    return path


def _clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理会影响模型 catalog 与外部模型调用的环境变量。"""
    for key in [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_EMBEDDING_MODELS",
        "OPENAI_CHAT_MODELS",
        "SILICONFLOW_API_KEY",
        "SILICONFLOW_BASE_URL",
        "SILICONFLOW_EMBEDDING_MODELS",
        "SILICONFLOW_CHAT_MODELS",
        "EMBEDDING_SOURCE",
        "EMBEDDING_MODEL",
        "CHAT_SOURCE",
        "CHAT_MODEL",
        "PAPER_RAG_EMBEDDING_MODEL",
        "PAPER_RAG_LLM_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PAPER_RAG_ENV_FILE", str(Path.cwd() / ".missing-test.env"))
