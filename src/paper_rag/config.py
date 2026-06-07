"""从环境变量加载的应用配置。"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """供 CLI 命令共享的运行时设置。"""

    index_dir: Path = field(
        default=Path(".paper_rag/index"),
        metadata={"description": "默认本地索引根目录，包含 SQLite 和 Chroma 数据。"},
    )
    upload_dir: Path = field(
        default=Path(".paper_rag/uploads"),
        metadata={"description": "上传 PDF 源文件的受管本地存储根目录。"},
    )
    upload_max_bytes: int = field(
        default=50 * 1024 * 1024,
        metadata={"description": "允许的最大上传大小（字节）。"},
    )
    llm_model: str = field(
        default="gpt-4.1-mini",
        metadata={"description": "用于答案生成的默认 OpenAI 兼容模型。"},
    )
    embedding_model: str = field(
        default="text-embedding-3-small",
        metadata={"description": "用于文档/查询 embedding 的默认 OpenAI 兼容模型。"},
    )
    openai_api_key: str | None = field(
        default=None,
        metadata={"description": "传给 OpenAI 兼容客户端的 API 密钥。"},
    )
    openai_base_url: str | None = field(
        default=None,
        metadata={"description": "可选的 OpenAI 兼容基础 URL 覆盖。"},
    )
    top_k: int = field(
        default=5,
        metadata={"description": "每个问题默认检索的 chunk 数量。"},
    )
    log_level: str = field(
        default="INFO",
        metadata={"description": "CLI 命令使用的进程日志级别。"},
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
