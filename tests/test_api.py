"""FastAPI and Web Inspector integration tests."""

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


def test_api_inspector_local_flow(tmp_path: Path) -> None:
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
            "local": True,
            "top_k": 3,
        },
    )
    assert answer.status_code == 200
    answer_payload = answer.json()
    assert answer_payload["insufficient_evidence"] is False
    assert answer_payload["citations"]
    assert answer_payload["evidence"]


def test_api_serves_inspector_upload_ui() -> None:
    client = TestClient(create_app())

    page = client.get("/")
    assert page.status_code == 200
    assert 'id="index-dir"' in page.text
    assert 'id="upload-form"' in page.text
    assert 'id="upload-file"' in page.text
    assert 'id="upload-mode"' in page.text
    assert 'id="upload-chunk-size"' in page.text
    assert 'id="ask-mode"' in page.text
    assert 'src="/static/inspector.js"' in page.text


def test_api_config_exposes_model_names_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PAPER_RAG_EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("PAPER_RAG_LLM_MODEL", "llm-model")

    client = TestClient(create_app())
    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_model"] == "embedding-model"
    assert payload["llm_model"] == "llm-model"
    assert payload["api_key_configured"] is True
    assert payload["base_url_configured"] is True
    assert payload["recommended_local_index_dir"] == ".paper_rag/manual_index"
    assert payload["recommended_api_index_dir"] == ".paper_rag/api_index"
    assert "secret-key" not in response.text


def test_api_components_exposes_catalog_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认组件 catalog 覆盖五类组件，且不会暴露 OpenAI 密钥。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("PAPER_RAG_EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("PAPER_RAG_LLM_MODEL", "llm-model")

    client = TestClient(create_app())
    response = client.get("/api/components")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"reader", "chunker", "embedder", "retriever", "generator"}
    assert {item["id"] for item in payload["embedder"]} == {
        "hash_embedder",
        "openai_embedder",
    }
    assert {item["id"] for item in payload["generator"]} == {
        "extractive_generator",
        "openai_generator",
    }
    openai_embedder = next(item for item in payload["embedder"] if item["id"] == "openai_embedder")
    assert openai_embedder["default_model"] == "embedding-model"
    assert "secret-key" not in response.text


def test_api_uploads_pdf_and_triggers_local_indexing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    source_dir = run_dir / "source"
    index_dir = run_dir / "index"
    upload_dir = run_dir / "uploads"
    pdf_path = _write_test_pdf(source_dir / "paper_rag_test.pdf")
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(upload_dir))

    client = TestClient(create_app())
    initial_status = client.get(
        "/api/index/status",
        params={"index_dir": str(index_dir), "tenant_id": "default"},
    )
    assert initial_status.status_code == 200
    assert initial_status.json()["status"] == "missing"
    assert initial_status.json()["document_count"] == 0

    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(index_dir),
            "local": "true",
            "chunk_size": "120",
            "chunk_overlap": "20",
        },
        files={"file": ("paper_rag_test.pdf", pdf_path.read_bytes(), "application/pdf")},
    )

    assert upload.status_code == 200, upload.text
    upload_payload = upload.json()
    assert upload_payload["upload"]["safe_file_name"] == "paper_rag_test.pdf"
    assert upload_payload["upload"]["source_uri"]
    assert upload_payload["index"]["indexed"] == 1
    assert upload_payload["index"]["indexed_chunks"] >= 1
    assert upload_payload["status"]["status"] == "ready"

    params = {"index_dir": str(index_dir), "tenant_id": "default"}
    documents = client.get("/api/documents", params=params)
    assert documents.status_code == 200
    document_payload = documents.json()
    assert len(document_payload) == 1
    assert "paper_rag_test" in document_payload[0]["file_name"]

    chunks = client.get(
        f"/api/documents/{document_payload[0]['id']}/chunks",
        params={**params, "limit": 2},
    )
    assert chunks.status_code == 200
    chunk_payload = chunks.json()
    assert chunk_payload
    assert chunk_payload[0]["page_start"] == 1

    answer = client.post(
        "/api/ask",
        json={
            "question": "What does Paper RAG index?",
            "index_dir": str(index_dir),
            "tenant_id": "default",
            "local": True,
            "top_k": 3,
        },
    )
    assert answer.status_code == 200
    answer_payload = answer.json()
    assert answer_payload["insufficient_evidence"] is False
    assert answer_payload["citations"]
    assert answer_payload["evidence"]
    citation = answer_payload["citations"][0]
    evidence_chunk_ids = {item["chunk"]["id"] for item in answer_payload["evidence"]}
    assert citation["chunk_id"] in evidence_chunk_ids
    assert citation["page_start"] == 1
    assert "paper_rag_test.pdf" in citation["label"]

    insufficient = client.post(
        "/api/ask",
        json={
            "question": "What is the capital of France?",
            "index_dir": str(index_dir),
            "tenant_id": "default",
            "local": True,
            "top_k": 3,
        },
    )
    assert insufficient.status_code == 200
    insufficient_payload = insufficient.json()
    assert insufficient_payload["insufficient_evidence"] is True
    assert insufficient_payload["citations"] == []


def test_api_upload_rejects_non_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
            "local": "true",
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
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
            "local": "true",
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
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))
    monkeypatch.setenv("PAPER_RAG_UPLOAD_MAX_BYTES", "5")

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
            "local": "true",
        },
        files={"file": ("paper.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "upload"
    assert "too large" in detail["message"]


def test_api_upload_returns_structured_errors_for_unparseable_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(run_dir / "uploads"))

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(run_dir / "index"),
            "local": "true",
        },
        files={"file": ("broken.pdf", b"%PDF-this is not parseable", "application/pdf")},
    )

    assert upload.status_code == 200, upload.text
    payload = upload.json()
    assert payload["status"]["status"] == "error"
    assert payload["index"]["errors"]
    assert "Could not open PDF" in payload["index"]["errors"][0]["message"]


def test_api_upload_returns_structured_indexing_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "test_api_upload" / uuid4().hex
    source_dir = run_dir / "source"
    index_dir = run_dir / "index"
    upload_dir = run_dir / "uploads"
    pdf_path = _write_test_pdf(source_dir / "paper_rag_test.pdf")
    monkeypatch.setenv("PAPER_RAG_UPLOAD_DIR", str(upload_dir))

    client = TestClient(create_app())
    upload = client.post(
        "/api/documents/upload",
        data={
            "tenant_id": "default",
            "index_dir": str(index_dir),
            "local": "true",
            "chunk_size": "10",
            "chunk_overlap": "10",
        },
        files={"file": ("paper.pdf", pdf_path.read_bytes(), "application/pdf")},
    )

    assert upload.status_code == 400
    detail = upload.json()["detail"]
    assert detail["stage"] == "indexing"
    assert detail["error_type"] == "ValueError"
    assert "chunk_overlap" in detail["message"]


def _write_test_pdf(path: Path, text: str = TEST_PDF_TEXT) -> Path:
    """Create a tiny PDF fixture for API tests without production sample helpers."""
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
