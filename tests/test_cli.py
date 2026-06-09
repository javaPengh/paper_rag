"""CLI 集成测试。"""

import os
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


def test_cli_requires_external_model_config_for_index(tmp_path: Path) -> None:
    """确认 CLI 建索引时不会再接受本地模式兜底。"""
    run_dir = tmp_path / "test_cli" / uuid4().hex
    source_dir = run_dir / "papers"
    index_dir = run_dir / "index"
    _write_test_pdf(source_dir / "paper_rag_test.pdf")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "index",
            str(source_dir),
            "--index-dir",
            str(index_dir),
            "--tenant-id",
            "default",
        ],
        env=_empty_model_env(),
    )

    assert result.exit_code != 0
    assert "缺少 embedding 模型来源" in result.output


def test_cli_requires_external_model_config_for_ask(tmp_path: Path) -> None:
    """确认 CLI 问答缺少模型配置时会直接报错。"""
    run_dir = tmp_path / "test_cli" / uuid4().hex
    index_dir = run_dir / "index"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ask",
            "What does Paper RAG index?",
            "--index-dir",
            str(index_dir),
            "--tenant-id",
            "default",
        ],
        env=_empty_model_env(),
    )

    assert result.exit_code != 0
    assert "缺少 embedding 模型来源" in result.output or "Build the index before retrieval." in result.output


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


def _empty_model_env() -> dict[str, str]:
    """构造不包含模型配置的最小 CLI 环境变量集合。"""
    env = dict(os.environ)
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
        env.pop(key, None)
    env["PAPER_RAG_ENV_FILE"] = str(Path.cwd() / ".missing-test.env")
    return env
