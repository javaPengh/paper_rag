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
                "EMBEDDING_SOURCE=siliconflow",
                "EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B",
                "CHAT_SOURCE=siliconflow",
                "CHAT_MODEL=deepseek-ai/DeepSeek-V4-Pro",
                "SILICONFLOW_API_KEY=siliconflow-key",
                "SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1",
                "SILICONFLOW_EMBEDDING_MODELS=Qwen/Qwen3-Embedding-0.6B,Qwen/Qwen3-Embedding-4B",
                "SILICONFLOW_CHAT_MODELS=deepseek-ai/DeepSeek-V4-Pro,deepseek-ai/DeepSeek-V4-Flash",
                "OPENAI_EMBEDDING_MODELS=",
                "OPENAI_CHAT_MODELS=",
                "PAPER_RAG_INDEX_DIR=.paper_rag/dotenv_index",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.openai_api_key == "dotenv-key"
    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.embedding_source == "siliconflow"
    assert settings.embedding_model == "Qwen/Qwen3-Embedding-4B"
    assert settings.chat_source == "siliconflow"
    assert settings.llm_model == "deepseek-ai/DeepSeek-V4-Pro"
    assert settings.siliconflow_api_key == "siliconflow-key"
    assert settings.siliconflow_embedding_models == [
        "Qwen/Qwen3-Embedding-4B",
        "Qwen/Qwen3-Embedding-0.6B",
    ]
    assert settings.siliconflow_chat_models == [
        "deepseek-ai/DeepSeek-V4-Pro",
        "deepseek-ai/DeepSeek-V4-Flash",
    ]
    assert settings.openai_embedding_models == []
    assert settings.openai_chat_models == []
    assert settings.index_dir == Path(".paper_rag/dotenv_index")


def test_load_settings_keeps_legacy_model_env_names(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """确认旧 PAPER_RAG 模型变量仍可作为兼容入口。"""
    monkeypatch.chdir(tmp_path)
    _clear_config_env(monkeypatch)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "PAPER_RAG_EMBEDDING_MODEL=embedding-from-dotenv",
                "PAPER_RAG_LLM_MODEL=llm-from-dotenv",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.embedding_model == "embedding-from-dotenv"
    assert settings.llm_model == "llm-from-dotenv"


def test_load_settings_does_not_invent_external_model_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """确认未显式配置外部来源和模型时，配置层保持空值而不是补占位默认值。"""
    monkeypatch.chdir(tmp_path)
    _clear_config_env(monkeypatch)
    (tmp_path / ".env").write_text("", encoding="utf-8")

    settings = load_settings()

    assert settings.embedding_source is None
    assert settings.embedding_model is None
    assert settings.chat_source is None
    assert settings.llm_model is None
    assert settings.openai_embedding_models == []
    assert settings.openai_chat_models == []
    assert settings.siliconflow_embedding_models == []
    assert settings.siliconflow_chat_models == []


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
        "PAPER_RAG_INDEX_DIR",
        "PAPER_RAG_UPLOAD_DIR",
        "PAPER_RAG_UPLOAD_MAX_BYTES",
        "PAPER_RAG_TOP_K",
        "PAPER_RAG_LOG_LEVEL",
        "PAPER_RAG_ENV_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)
