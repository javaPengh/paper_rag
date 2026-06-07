"""运行时配置加载测试。"""

from pathlib import Path

from paper_rag.config import load_settings


def test_load_settings_reads_dotenv_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """确认 `.env` 能作为本地开发的默认配置入口。"""
    monkeypatch.chdir(tmp_path)
    _clear_config_env(monkeypatch)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "OPENAI_BASE_URL=https://example.test/v1",
                "PAPER_RAG_EMBEDDING_MODEL=embedding-from-dotenv",
                "PAPER_RAG_LLM_MODEL=llm-from-dotenv",
                "PAPER_RAG_INDEX_DIR=.paper_rag/dotenv_index",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.openai_api_key == "dotenv-key"
    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.embedding_model == "embedding-from-dotenv"
    assert settings.llm_model == "llm-from-dotenv"
    assert settings.index_dir == Path(".paper_rag/dotenv_index")


def test_load_settings_prefers_shell_environment_over_dotenv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """确认临时 shell 配置可以覆盖 `.env`，方便一次性实验。"""
    monkeypatch.chdir(tmp_path)
    _clear_config_env(monkeypatch)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=dotenv-key", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "shell-key")

    settings = load_settings()

    assert settings.openai_api_key == "shell-key"


def _clear_config_env(monkeypatch) -> None:
    """清理会影响配置测试的环境变量。"""
    for key in [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "PAPER_RAG_EMBEDDING_MODEL",
        "PAPER_RAG_LLM_MODEL",
        "PAPER_RAG_INDEX_DIR",
        "PAPER_RAG_UPLOAD_DIR",
        "PAPER_RAG_UPLOAD_MAX_BYTES",
        "PAPER_RAG_TOP_K",
        "PAPER_RAG_LOG_LEVEL",
        "PAPER_RAG_ENV_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)
