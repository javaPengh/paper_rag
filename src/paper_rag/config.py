"""从 `.env` 文件和环境变量加载应用配置。"""

import os
from collections.abc import Mapping
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
    """从 `.env` 与环境变量加载设置，并提供适合 MVP 的默认值。

    Shell 中已经存在的环境变量优先级高于 `.env`，这样临时覆盖配置时不需要修改文件。
    """
    dotenv_values = _load_dotenv_values(_resolve_dotenv_path())
    return Settings(
        index_dir=Path(_setting("PAPER_RAG_INDEX_DIR", ".paper_rag/index", dotenv_values)),
        upload_dir=Path(_setting("PAPER_RAG_UPLOAD_DIR", ".paper_rag/uploads", dotenv_values)),
        upload_max_bytes=int(
            _setting("PAPER_RAG_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024), dotenv_values)
        ),
        llm_model=_setting("PAPER_RAG_LLM_MODEL", "gpt-4.1-mini", dotenv_values),
        embedding_model=_setting(
            "PAPER_RAG_EMBEDDING_MODEL",
            "text-embedding-3-small",
            dotenv_values,
        ),
        openai_api_key=_optional_setting("OPENAI_API_KEY", dotenv_values),
        openai_base_url=_optional_setting("OPENAI_BASE_URL", dotenv_values),
        top_k=int(_setting("PAPER_RAG_TOP_K", "5", dotenv_values)),
        log_level=_setting("PAPER_RAG_LOG_LEVEL", "INFO", dotenv_values).upper(),
    )


def _setting(key: str, default: str, dotenv_values: Mapping[str, str]) -> str:
    """读取单个配置值，保持 shell 环境变量高于 `.env` 的优先级。"""
    value = os.getenv(key)
    if value is not None:
        return value
    return dotenv_values.get(key, default)


def _optional_setting(key: str, dotenv_values: Mapping[str, str]) -> str | None:
    """读取可选配置值，并把空字符串视为未配置。"""
    value = _setting(key, "", dotenv_values).strip()
    return value or None


def _resolve_dotenv_path() -> Path | None:
    """解析要加载的 `.env` 路径；默认从当前目录向上查找。"""
    configured_path = os.getenv("PAPER_RAG_ENV_FILE")
    if configured_path:
        path = Path(configured_path)
        return path if path.is_absolute() else Path.cwd() / path

    current = Path.cwd()
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.exists():
            return candidate
    return None


def _load_dotenv_values(path: Path | None) -> dict[str, str]:
    """加载 `.env` 文件中的键值；文件不存在时返回空配置。"""
    if path is None or not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid .env line {line_number} in {path}: missing '='")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ValueError(f"Invalid .env key at line {line_number} in {path}: {key!r}")
        values[key] = _normalize_dotenv_value(value)
    return values


def _normalize_dotenv_value(value: str) -> str:
    """规整 `.env` 值，支持常见的单双引号写法。"""
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        return normalized[1:-1]
    if " #" in normalized:
        normalized = normalized.split(" #", 1)[0].rstrip()
    return normalized
