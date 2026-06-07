"""RAG 组件 registry 与默认配置工厂。"""

from __future__ import annotations

from collections.abc import Mapping

from paper_rag.components.chunking.token_window_chunker import TokenWindowChunker
from paper_rag.components.embedding.hash_embedder import HashEmbedder
from paper_rag.components.embedding.openai_embedder import OpenAIEmbedder
from paper_rag.components.generation.extractive_generator import ExtractiveGenerator
from paper_rag.components.generation.openai_generator import OpenAIGenerator
from paper_rag.components.interfaces import Chunker, Embedder, Generator, Reader, Retriever
from paper_rag.components.reading.pdf_reader import PdfReader
from paper_rag.components.retrieval.vector_retriever import VectorRetriever
from paper_rag.components.types import (
    ComponentConfigField,
    ComponentDescriptor,
    ComponentKind,
    ComponentSelection,
    ConfigFieldType,
    ConfigValue,
    ModelOption,
    RagPipelineConfig,
)
from paper_rag.config import Settings, load_settings
from paper_rag.indexing.chunking import ChunkingConfig
from paper_rag.indexing.local_index import LocalPaperIndex
from paper_rag.qa.answering import OpenAIChatClient

DEFAULT_READER_ID = "pdf_reader"
DEFAULT_CHUNKER_ID = "token_window_chunker"
DEFAULT_HASH_EMBEDDER_ID = "hash_embedder"
DEFAULT_OPENAI_EMBEDDER_ID = "openai_embedder"
DEFAULT_RETRIEVER_ID = "vector_retriever"
DEFAULT_EXTRACTIVE_GENERATOR_ID = "extractive_generator"
DEFAULT_OPENAI_GENERATOR_ID = "openai_generator"
DEFAULT_HASH_EMBEDDING_MODEL = "hash-embedding-v1"
DEFAULT_EXTRACTIVE_MODEL = "extractive-local-v1"


class ComponentRegistry:
    """集中注册当前可用 RAG 组件，并负责按配置创建实例。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """绑定运行时设置，以便工厂读取默认模型和 OpenAI 兼容端点。"""
        self.settings = settings or load_settings()
        self._descriptors = _build_descriptors(self.settings)

    def list_descriptors(self, kind: ComponentKind | None = None) -> list[ComponentDescriptor]:
        """列出 registry 中的组件描述，可按组件类别过滤。"""
        descriptors = list(self._descriptors.values())
        if kind is None:
            return descriptors
        return [descriptor for descriptor in descriptors if descriptor.kind == kind]

    def grouped_descriptors(self) -> dict[ComponentKind, list[ComponentDescriptor]]:
        """按 Reader/Chunker/Embedder/Retriever/Generator 分组返回组件 catalog。"""
        return {
            kind: self.list_descriptors(kind)
            for kind in (
                ComponentKind.READER,
                ComponentKind.CHUNKER,
                ComponentKind.EMBEDDER,
                ComponentKind.RETRIEVER,
                ComponentKind.GENERATOR,
            )
        }

    def get_descriptor(self, component_id: str) -> ComponentDescriptor:
        """按 ID 返回组件描述；未知 ID 会抛出 ValueError 以暴露配置错误。"""
        try:
            return self._descriptors[component_id]
        except KeyError as exc:
            raise ValueError(f"Unknown RAG component: {component_id}") from exc

    def resolve_embedder_id(self, *, local: bool, model_name: str | None = None) -> str:
        """根据本地模式和模型名推导应该使用的 Embedder 组件 ID。"""
        if local or (model_name is not None and model_name.startswith("hash-")):
            return DEFAULT_HASH_EMBEDDER_ID
        return DEFAULT_OPENAI_EMBEDDER_ID

    def resolve_generator_id(self, *, local: bool) -> str:
        """根据本地模式推导应该使用的 Generator 组件 ID。"""
        return DEFAULT_EXTRACTIVE_GENERATOR_ID if local else DEFAULT_OPENAI_GENERATOR_ID

    def create_reader(
        self,
        component_id: str = DEFAULT_READER_ID,
        *,
        parameters: Mapping[str, ConfigValue] | None = None,
    ) -> Reader:
        """创建 Reader 组件；当前只注册 PDF reader。"""
        _ = parameters
        self._ensure_kind(component_id, ComponentKind.READER)
        if component_id == DEFAULT_READER_ID:
            return PdfReader()
        raise ValueError(f"Unsupported Reader component: {component_id}")

    def create_chunker(
        self,
        component_id: str = DEFAULT_CHUNKER_ID,
        *,
        parameters: Mapping[str, ConfigValue] | None = None,
    ) -> Chunker:
        """创建 Chunker 组件，并把公开参数转换成 ChunkingConfig。"""
        self._ensure_kind(component_id, ComponentKind.CHUNKER)
        params = dict(parameters or {})
        if component_id == DEFAULT_CHUNKER_ID:
            return TokenWindowChunker(
                config=ChunkingConfig(
                    chunk_size=int(params.get("chunk_size", 800)),
                    chunk_overlap=int(params.get("chunk_overlap", 120)),
                    encoding_name=str(params.get("encoding_name", "cl100k_base")),
                )
            )
        raise ValueError(f"Unsupported Chunker component: {component_id}")

    def create_embedder(
        self,
        component_id: str,
        *,
        model_name: str | None = None,
        parameters: Mapping[str, ConfigValue] | None = None,
    ) -> Embedder:
        """创建 Embedder 组件；不会把 API 密钥暴露到 descriptor 或报告中。"""
        self._ensure_kind(component_id, ComponentKind.EMBEDDER)
        params = dict(parameters or {})
        if component_id == DEFAULT_HASH_EMBEDDER_ID:
            return HashEmbedder(
                model_name=model_name or DEFAULT_HASH_EMBEDDING_MODEL,
                dimensions=int(params.get("dimensions", 64)),
            )
        if component_id == DEFAULT_OPENAI_EMBEDDER_ID:
            return OpenAIEmbedder(
                model_name=model_name or self.settings.embedding_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                max_retries=int(params.get("max_retries", 2)),
                retry_delay_seconds=float(params.get("retry_delay_seconds", 1.0)),
            )
        raise ValueError(f"Unsupported Embedder component: {component_id}")

    def create_retriever(
        self,
        component_id: str = DEFAULT_RETRIEVER_ID,
        *,
        local_index: LocalPaperIndex,
        embedding_client: Embedder,
        tenant_id: str = "default",
        parameters: Mapping[str, ConfigValue] | None = None,
    ) -> Retriever:
        """创建 Retriever 组件，并绑定检索所需的索引和 embedding 组件。"""
        _ = parameters
        self._ensure_kind(component_id, ComponentKind.RETRIEVER)
        if component_id == DEFAULT_RETRIEVER_ID:
            return VectorRetriever(
                local_index=local_index,
                embedding_client=embedding_client,
                tenant_id=tenant_id,
            )
        raise ValueError(f"Unsupported Retriever component: {component_id}")

    def create_generator(
        self,
        component_id: str,
        *,
        model_name: str | None = None,
        parameters: Mapping[str, ConfigValue] | None = None,
    ) -> Generator:
        """创建 Generator 组件；OpenAI 兼容密钥只在工厂内部注入。"""
        self._ensure_kind(component_id, ComponentKind.GENERATOR)
        params = dict(parameters or {})
        min_score = float(params.get("min_score", 0.05))
        if component_id == DEFAULT_EXTRACTIVE_GENERATOR_ID:
            return ExtractiveGenerator(
                model_name=model_name or DEFAULT_EXTRACTIVE_MODEL,
                min_score=min_score,
                max_evidence_items=int(params.get("max_evidence_items", 3)),
            )
        if component_id == DEFAULT_OPENAI_GENERATOR_ID:
            return OpenAIGenerator(
                chat_client=OpenAIChatClient(
                    model_name=model_name or self.settings.llm_model,
                    api_key=self.settings.openai_api_key,
                    base_url=self.settings.openai_base_url,
                ),
                min_score=min_score,
            )
        raise ValueError(f"Unsupported Generator component: {component_id}")

    def build_pipeline_config(
        self,
        *,
        local: bool,
        embedding_model: str | None = None,
        llm_model: str | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        recursive: bool = True,
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> RagPipelineConfig:
        """构建可写入日志或评测报告的五类组件配置快照。"""
        embedder_id = self.resolve_embedder_id(local=local, model_name=embedding_model)
        generator_id = self.resolve_generator_id(local=local)
        embedder_model = (
            embedding_model
            or (
                DEFAULT_HASH_EMBEDDING_MODEL
                if embedder_id == DEFAULT_HASH_EMBEDDER_ID
                else self.settings.embedding_model
            )
        )
        generator_model = (
            DEFAULT_EXTRACTIVE_MODEL
            if generator_id == DEFAULT_EXTRACTIVE_GENERATOR_ID
            else (llm_model or self.settings.llm_model)
        )
        return RagPipelineConfig(
            reader=ComponentSelection(
                id=DEFAULT_READER_ID,
                parameters={"recursive": recursive},
            ),
            chunker=ComponentSelection(
                id=DEFAULT_CHUNKER_ID,
                parameters={
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "encoding_name": "cl100k_base",
                },
            ),
            embedder=ComponentSelection(id=embedder_id, model=embedder_model),
            retriever=ComponentSelection(
                id=DEFAULT_RETRIEVER_ID,
                parameters={"top_k": top_k},
            ),
            generator=ComponentSelection(
                id=generator_id,
                model=generator_model,
                parameters={"min_score": min_score},
            ),
        )

    def _ensure_kind(self, component_id: str, kind: ComponentKind) -> None:
        """校验调用方请求的组件 ID 与所需能力类别一致。"""
        descriptor = self.get_descriptor(component_id)
        if descriptor.kind != kind:
            raise ValueError(
                f"Component {component_id} is {descriptor.kind.value}, expected {kind.value}."
            )


def get_component_registry(settings: Settings | None = None) -> ComponentRegistry:
    """创建绑定当前运行时设置的默认组件 registry。"""
    return ComponentRegistry(settings=settings)


def _build_descriptors(settings: Settings) -> dict[str, ComponentDescriptor]:
    """构建当前版本内置组件的 catalog 元数据。"""
    descriptors = [
        ComponentDescriptor(
            id=DEFAULT_READER_ID,
            kind=ComponentKind.READER,
            label="PDF Reader",
            description="使用 PyMuPDF 读取本地 PDF，并产出文档、版本和页面领域模型。",
            config_fields=[
                ComponentConfigField(
                    name="recursive",
                    label="递归扫描",
                    description="目录索引时是否递归发现子目录中的 PDF 文件。",
                    field_type=ConfigFieldType.BOOLEAN,
                    default=True,
                )
            ],
        ),
        ComponentDescriptor(
            id=DEFAULT_CHUNKER_ID,
            kind=ComponentKind.CHUNKER,
            label="Token Window Chunker",
            description="按 tokenizer 窗口切分页面文本，保留页面来源和稳定 chunk ID。",
            config_fields=[
                ComponentConfigField(
                    name="chunk_size",
                    label="Chunk 大小",
                    description="单个 chunk 允许的最大 tokenizer 单元数。",
                    field_type=ConfigFieldType.INTEGER,
                    default=800,
                    minimum=1,
                ),
                ComponentConfigField(
                    name="chunk_overlap",
                    label="Chunk 重叠",
                    description="相邻 chunk 之间重复的 tokenizer 单元数。",
                    field_type=ConfigFieldType.INTEGER,
                    default=120,
                    minimum=0,
                ),
                ComponentConfigField(
                    name="encoding_name",
                    label="Tokenizer 编码",
                    description="用于估算模型感知边界的 tiktoken 编码名。",
                    field_type=ConfigFieldType.STRING,
                    default="cl100k_base",
                ),
            ],
        ),
        ComponentDescriptor(
            id=DEFAULT_HASH_EMBEDDER_ID,
            kind=ComponentKind.EMBEDDER,
            label="Hash Embedder",
            description="确定性本地 embedding，适合离线测试、CI 和无密钥验收。",
            models=[
                ModelOption(
                    id=DEFAULT_HASH_EMBEDDING_MODEL,
                    label=DEFAULT_HASH_EMBEDDING_MODEL,
                    description="基于词项哈希的本地确定性向量模型。",
                )
            ],
            default_model=DEFAULT_HASH_EMBEDDING_MODEL,
            config_fields=[
                ComponentConfigField(
                    name="dimensions",
                    label="向量维度",
                    description="hash embedding 输出向量的固定维度。",
                    field_type=ConfigFieldType.INTEGER,
                    default=64,
                    minimum=1,
                )
            ],
        ),
        ComponentDescriptor(
            id=DEFAULT_OPENAI_EMBEDDER_ID,
            kind=ComponentKind.EMBEDDER,
            label="OpenAI Embedder",
            description="OpenAI 兼容 embedding provider，密钥和 base URL 只在后端读取。",
            models=_model_options(
                settings.embedding_model,
                "text-embedding-3-small",
                "text-embedding-3-large",
                description="OpenAI 兼容 embedding 模型。",
            ),
            default_model=settings.embedding_model,
            config_fields=[
                ComponentConfigField(
                    name="max_retries",
                    label="最大重试",
                    description="临时 provider 失败时的 embedding 调用重试次数。",
                    field_type=ConfigFieldType.INTEGER,
                    default=2,
                    minimum=0,
                ),
                ComponentConfigField(
                    name="retry_delay_seconds",
                    label="重试延迟",
                    description="embedding 重试之间的基础延迟秒数。",
                    field_type=ConfigFieldType.NUMBER,
                    default=1.0,
                    minimum=0,
                ),
            ],
        ),
        ComponentDescriptor(
            id=DEFAULT_RETRIEVER_ID,
            kind=ComponentKind.RETRIEVER,
            label="Vector Retriever",
            description="使用本地 Chroma 向量索引和 SQLite 元数据召回证据 chunk。",
            config_fields=[
                ComponentConfigField(
                    name="top_k",
                    label="Top K",
                    description="每个问题最多召回的候选证据 chunk 数。",
                    field_type=ConfigFieldType.INTEGER,
                    default=5,
                    minimum=1,
                )
            ],
        ),
        ComponentDescriptor(
            id=DEFAULT_EXTRACTIVE_GENERATOR_ID,
            kind=ComponentKind.GENERATOR,
            label="Extractive Generator",
            description="确定性本地抽取式答案生成器，适合离线测试和评测基线。",
            models=[
                ModelOption(
                    id=DEFAULT_EXTRACTIVE_MODEL,
                    label=DEFAULT_EXTRACTIVE_MODEL,
                    description="从检索 chunk 中抽取证据并拼接引用的本地生成器。",
                )
            ],
            default_model=DEFAULT_EXTRACTIVE_MODEL,
            config_fields=[
                ComponentConfigField(
                    name="min_score",
                    label="最低证据分数",
                    description="低于该分数的检索结果不会进入答案证据。",
                    field_type=ConfigFieldType.NUMBER,
                    default=0.05,
                    minimum=0,
                ),
                ComponentConfigField(
                    name="max_evidence_items",
                    label="最大证据数",
                    description="本地抽取式答案最多引用的证据 chunk 数。",
                    field_type=ConfigFieldType.INTEGER,
                    default=3,
                    minimum=1,
                ),
            ],
        ),
        ComponentDescriptor(
            id=DEFAULT_OPENAI_GENERATOR_ID,
            kind=ComponentKind.GENERATOR,
            label="OpenAI Generator",
            description="OpenAI 兼容聊天生成器，使用检索证据生成带引用答案。",
            models=_model_options(
                settings.llm_model,
                "gpt-4.1-mini",
                "gpt-4.1",
                description="OpenAI 兼容聊天生成模型。",
            ),
            default_model=settings.llm_model,
            config_fields=[
                ComponentConfigField(
                    name="min_score",
                    label="最低证据分数",
                    description="低于该分数的检索结果不会进入答案提示词。",
                    field_type=ConfigFieldType.NUMBER,
                    default=0.05,
                    minimum=0,
                )
            ],
        ),
    ]
    return {descriptor.id: descriptor for descriptor in descriptors}


def _model_options(*model_names: str, description: str) -> list[ModelOption]:
    """按顺序去重模型名，并生成 catalog 中使用的模型选项。"""
    seen: set[str] = set()
    options: list[ModelOption] = []
    for model_name in model_names:
        if model_name in seen:
            continue
        seen.add(model_name)
        options.append(
            ModelOption(
                id=model_name,
                label=model_name,
                description=description,
            )
        )
    return options
