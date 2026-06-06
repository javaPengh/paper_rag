"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings shared by CLI commands."""

    index_dir: Path = Path(".paper_rag/index")
    upload_dir: Path = Path(".paper_rag/uploads")
    upload_max_bytes: int = 50 * 1024 * 1024
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    top_k: int = 5
    log_level: str = "INFO"


def load_settings() -> Settings:
    """Load settings from environment variables with MVP-friendly defaults."""
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
