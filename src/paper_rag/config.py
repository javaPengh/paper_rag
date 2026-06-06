"""从环境变量加载的应用配置。"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """供 CLI 命令共享的运行时设置。"""

    index_dir: Path = field(
        default=Path(".paper_rag/index"),
        metadata={"description": "Default local index root containing SQLite and Chroma data."},
    )
    upload_dir: Path = field(
        default=Path(".paper_rag/uploads"),
        metadata={"description": "Managed local storage root for uploaded PDF sources."},
    )
    upload_max_bytes: int = field(
        default=50 * 1024 * 1024,
        metadata={"description": "Maximum accepted upload size in bytes."},
    )
    llm_model: str = field(
        default="gpt-4.1-mini",
        metadata={"description": "Default OpenAI-compatible model for answer generation."},
    )
    embedding_model: str = field(
        default="text-embedding-3-small",
        metadata={"description": "Default OpenAI-compatible model for document/query embeddings."},
    )
    openai_api_key: str | None = field(
        default=None,
        metadata={"description": "API key passed to OpenAI-compatible clients."},
    )
    openai_base_url: str | None = field(
        default=None,
        metadata={"description": "Optional OpenAI-compatible base URL override."},
    )
    top_k: int = field(
        default=5,
        metadata={"description": "Default number of chunks retrieved for a question."},
    )
    log_level: str = field(
        default="INFO",
        metadata={"description": "Process logging threshold used by CLI commands."},
    )


def load_settings() -> Settings:
    """从环境变量加载设置，并提供适合 MVP 的默认值。"""
    return Settings(
        index_dir=Path(os.getenv("PAPER_RAG_INDEX_DIR", ".paper_rag/index")),
        upload_dir=Path(os.getenv("PAPER_RAG_UPLOAD_DIR", ".paper_rag/uploads")),
        upload_max_bytes=int(os.getenv("PAPER_RAG_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024))),
        llm_model=os.getenv("PAPER_RAG_LLM_MODEL", "gpt-4.1-mini"),
        embedding_model=os.getenv("PAPER_RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        top_k=int(os.getenv("PAPER_RAG_TOP_K", "5")),
        log_level=os.getenv("PAPER_RAG_LOG_LEVEL", "INFO").upper(),
    )
