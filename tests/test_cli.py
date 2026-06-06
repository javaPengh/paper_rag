"""CLI integration tests for the local RAG workflow."""

from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from paper_rag.cli import app

TEST_PDF_TEXT = (
    "Paper RAG is a learning project for citation-backed retrieval augmented generation. "
    "It indexes local PDF papers, splits pages into chunks, embeds each chunk, and stores "
    "the vectors in a local index. The command line workflow can answer questions with "
    "file names and page citations."
)


def test_cli_local_mvp_flow() -> None:
    run_dir = Path(".paper_rag") / "test_cli" / uuid4().hex
    source_dir = run_dir / "papers"
    index_dir = run_dir / "index"
    _write_test_pdf(source_dir / "paper_rag_test.pdf")

    runner = CliRunner()
    index_result = runner.invoke(
        app,
        [
            "index",
            str(source_dir),
            "--index-dir",
            str(index_dir),
            "--tenant-id",
            "default",
            "--local",
            "--chunk-size",
            "120",
            "--chunk-overlap",
            "20",
        ],
    )
    assert index_result.exit_code == 0, index_result.output
    assert "Status: ready" in index_result.output
    assert "Tenant: default" in index_result.output
    assert "Total chunks:" in index_result.output

    docs_result = runner.invoke(
        app,
        ["list-docs", "--index-dir", str(index_dir), "--tenant-id", "default"],
    )
    assert docs_result.exit_code == 0, docs_result.output
    assert "paper_rag_test.pdf" in docs_result.output
    assert "tenant=default" in docs_result.output
    assert "version=" in docs_result.output

    chunks_result = runner.invoke(
        app,
        [
            "show-chunks",
            "paper_rag_test.pdf",
            "--index-dir",
            str(index_dir),
            "--tenant-id",
            "default",
            "--limit",
            "1",
        ],
    )
    assert chunks_result.exit_code == 0, chunks_result.output
    assert "chunk_index=0" in chunks_result.output
    assert "version=" in chunks_result.output

    answer_result = runner.invoke(
        app,
        [
            "ask",
            "What does Paper RAG index?",
            "--index-dir",
            str(index_dir),
            "--tenant-id",
            "default",
            "--local",
            "--top-k",
            "3",
        ],
    )
    assert answer_result.exit_code == 0, answer_result.output
    assert "Answer:" in answer_result.output
    assert "[paper_rag_test.pdf, p.1]" in answer_result.output

    insufficient_result = runner.invoke(
        app,
        [
            "ask",
            "What is the capital of France?",
            "--index-dir",
            str(index_dir),
            "--tenant-id",
            "default",
            "--local",
            "--top-k",
            "3",
        ],
    )
    assert insufficient_result.exit_code == 0, insufficient_result.output
    assert "不足以回答" in insufficient_result.output


def _write_test_pdf(path: Path, text: str = TEST_PDF_TEXT) -> Path:
    """Create a tiny PDF fixture for CLI tests without production sample helpers."""
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
