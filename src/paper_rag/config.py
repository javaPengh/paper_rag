"""从 `.env` 文件和环境变量加载应用配置。"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ApiModelSourceConfig:
    """一个 OpenAI 兼容模型来源的运行时配置。"""

    id: str = field(metadata={"description": "前端、CLI 和 registry 共同使用的模型来源 ID。"})
    label: str = field(metadata={"description": "前端下拉框展示的模型来源名称。"})
    description: str = field(metadata={"description": "说明该来源的用途和调用协议。"})
    api_key: str | None = field(metadata={"description": "调用该来源时使用的 API 密钥。"})
    base_url: str | None = field(
        metadata={"description": "调用该来源时使用的 OpenAI 兼容基础 URL。"}
    )
    api_key_env: str = field(metadata={"description": "该来源 API 密钥对应的环境变量名。"})
    base_url_env: str = field(metadata={"description": "该来源基础 URL 对应的环境变量名。"})
    requires_base_url: bool = field(
        metadata={"description": "调用该来源时是否必须显式配置基础 URL。"}
    )
    embedding_models: list[str] = field(
        metadata={"description": "该来源下可供前端选择的 embedding 模型列表。"}
    )
    chat_models: list[str] = field(
        metadata={"description": "该来源下可供前端选择的对话模型列表。"}
    )


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
    llm_model: str | None = field(
        default=None,
        metadata={"description": "用于答案生成的当前对话模型；未配置时外部调用会报错。"},
    )
    embedding_model: str | None = field(
        default=None,
        metadata={"description": "用于文档/查询 embedding 的当前模型；未配置时外部调用会报错。"},
    )
    embedding_source: str | None = field(
        default=None,
        metadata={"description": "当前 embedding 模型来源；未配置时外部调用会报错。"},
    )
    chat_source: str | None = field(
        default=None,
        metadata={"description": "当前对话模型来源；未配置时外部调用会报错。"},
    )
    openai_api_key: str | None = field(
        default=None,
        metadata={"description": "传给 OpenAI 兼容客户端的 API 密钥。"},
    )
    openai_base_url: str | None = field(
        default=None,
        metadata={"description": "可选的 OpenAI 兼容基础 URL 覆盖。"},
    )
    openai_embedding_models: list[str] = field(
        default_factory=list,
        metadata={"description": "OpenAI 来源下可供前端选择的 embedding 模型列表。"},
    )
    openai_chat_models: list[str] = field(
        default_factory=list,
        metadata={"description": "OpenAI 来源下可供前端选择的对话模型列表。"},
    )
    siliconflow_api_key: str | None = field(
        default=None,
        metadata={"description": "传给硅基流动 OpenAI 兼容接口的 API 密钥。"},
    )
    siliconflow_base_url: str | None = field(
        default=None,
        metadata={"description": "硅基流动 OpenAI 兼容接口基础 URL，必须显式配置。"},
    )
    siliconflow_embedding_models: list[str] = field(
        default_factory=list,
        metadata={"description": "硅基流动来源下可供前端选择的 embedding 模型列表。"},
    )
    siliconflow_chat_models: list[str] = field(
        default_factory=list,
        metadata={"description": "硅基流动来源下可供前端选择的对话模型列表。"},
    )
    top_k: int = field(
        default=5,
        metadata={"description": "每个问题默认检索的 chunk 数量。"},
    )
    log_level: str = field(
        default="INFO",
        metadata={"description": "CLI 命令使用的进程日志级别。"},
    )

    @property
    def chat_model(self) -> str | None:
        """返回对话模型的语义化别名，兼容内部旧字段 `llm_model`。"""
        return self.llm_model

    def api_model_sources(self) -> tuple[ApiModelSourceConfig, ...]:
        """返回当前支持的外部模型来源配置，不包含本地 hash 或抽取式实现。"""
        return (
            ApiModelSourceConfig(
                id="openai",
                label="OpenAI",
                description="OpenAI 官方或兼容 OpenAI 协议的模型来源。",
                api_key=self.openai_api_key,
                base_url=self.openai_base_url,
                api_key_env="OPENAI_API_KEY",
                base_url_env="OPENAI_BASE_URL",
                requires_base_url=False,
                embedding_models=self.openai_embedding_models,
                chat_models=self.openai_chat_models,
            ),
            ApiModelSourceConfig(
                id="siliconflow",
                label="硅基流动",
                description="硅基流动 OpenAI 兼容模型来源。",
                api_key=self.siliconflow_api_key,
                base_url=self.siliconflow_base_url,
                api_key_env="SILICONFLOW_API_KEY",
                base_url_env="SILICONFLOW_BASE_URL",
                requires_base_url=True,
                embedding_models=self.siliconflow_embedding_models,
                chat_models=self.siliconflow_chat_models,
            ),
        )

    def api_model_source(self, source_id: str) -> ApiModelSourceConfig:
        """按来源 ID 读取外部模型来源配置，未知来源抛出清晰错误。"""
        normalized_source_id = _normalize_source_id(source_id)
        for source in self.api_model_sources():
            if source.id == normalized_source_id:
                return source
        raise ValueError(f"Unknown model source: {source_id}")


def load_settings() -> Settings:
    """从 `.env` 与环境变量加载设置。

    Shell 中已经存在的环境变量优先级高于 `.env`，这样临时覆盖配置时不需要修改文件。
    本函数只为本地路径、上传大小和 top-k 这类系统参数提供工程默认值，不为外部模型、
    密钥或连接信息编造默认值。
    """
    dotenv_values = _load_dotenv_values(_resolve_dotenv_path())
    embedding_source = _optional_source_id(_optional_setting("EMBEDDING_SOURCE", dotenv_values))
    chat_source = _optional_source_id(_optional_setting("CHAT_SOURCE", dotenv_values))
    embedding_model = _first_optional_setting(
        ("EMBEDDING_MODEL", "PAPER_RAG_EMBEDDING_MODEL"),
        dotenv_values,
    )
    llm_model = _first_optional_setting(
        ("CHAT_MODEL", "PAPER_RAG_LLM_MODEL"),
        dotenv_values,
    )
    openai_embedding_models = _model_list_setting(
        "OPENAI_EMBEDDING_MODELS",
        dotenv_values,
    )
    openai_chat_models = _model_list_setting(
        "OPENAI_CHAT_MODELS",
        dotenv_values,
    )
    siliconflow_embedding_models = _model_list_setting(
        "SILICONFLOW_EMBEDDING_MODELS",
        dotenv_values,
    )
    siliconflow_chat_models = _model_list_setting(
        "SILICONFLOW_CHAT_MODELS",
        dotenv_values,
    )
    return Settings(
        index_dir=Path(_setting("PAPER_RAG_INDEX_DIR", ".paper_rag/index", dotenv_values)),
        upload_dir=Path(_setting("PAPER_RAG_UPLOAD_DIR", ".paper_rag/uploads", dotenv_values)),
        upload_max_bytes=int(
            _setting("PAPER_RAG_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024), dotenv_values)
        ),
        llm_model=llm_model,
        embedding_model=embedding_model,
        embedding_source=embedding_source,
        chat_source=chat_source,
        openai_api_key=_optional_setting("OPENAI_API_KEY", dotenv_values),
        openai_base_url=_optional_setting("OPENAI_BASE_URL", dotenv_values),
        openai_embedding_models=_ensure_selected_model(
            openai_embedding_models,
            embedding_model if embedding_source == "openai" else None,
        ),
        openai_chat_models=_ensure_selected_model(
            openai_chat_models,
            llm_model if chat_source == "openai" else None,
        ),
        siliconflow_api_key=_optional_setting("SILICONFLOW_API_KEY", dotenv_values),
        siliconflow_base_url=_optional_setting("SILICONFLOW_BASE_URL", dotenv_values),
        siliconflow_embedding_models=_ensure_selected_model(
            siliconflow_embedding_models,
            embedding_model if embedding_source == "siliconflow" else None,
        ),
        siliconflow_chat_models=_ensure_selected_model(
            siliconflow_chat_models,
            llm_model if chat_source == "siliconflow" else None,
        ),
        top_k=int(_setting("PAPER_RAG_TOP_K", "5", dotenv_values)),
        log_level=_setting("PAPER_RAG_LOG_LEVEL", "INFO", dotenv_values).upper(),
    )


def _first_optional_setting(
    keys: tuple[str, ...],
    dotenv_values: Mapping[str, str],
) -> str | None:
    """按顺序读取多个兼容配置键，全部缺失或为空时返回 None。"""
    for key in keys:
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    for key in keys:
        value = dotenv_values.get(key)
        if value is not None and value.strip():
            return value.strip()
    return None


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


def _model_list_setting(
    key: str,
    dotenv_values: Mapping[str, str],
) -> list[str]:
    """读取逗号分隔的模型列表，空配置表示该来源没有可展示模型。"""
    if key in os.environ:
        return _dedupe_non_empty(item.strip() for item in os.environ[key].split(","))
    if key in dotenv_values:
        return _dedupe_non_empty(item.strip() for item in dotenv_values[key].split(","))
    return []


def _ensure_selected_model(models: list[str], selected_model: str | None) -> list[str]:
    """确保显式选中的模型即使不在列表变量中也会出现在前端候选项里。"""
    if selected_model is None or not selected_model.strip():
        return models
    return _dedupe_non_empty((selected_model, *models))


def _dedupe_non_empty(values) -> list[str]:
    """按出现顺序去重字符串，并丢弃空白项。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_source_id(source_id: str) -> str:
    """把模型来源 ID 规整成前端和后端约定的小写形式。"""
    return source_id.strip().lower().replace("-", "_")


def _optional_source_id(source_id: str | None) -> str | None:
    """规整可选模型来源 ID；未配置时保持 None。"""
    return _normalize_source_id(source_id) if source_id else None


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
