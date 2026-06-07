"""文档、chunk、引用、答案和索引状态的共享数据模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def utc_now() -> datetime:
    """返回一个带时区信息的 UTC 时间戳。"""
    return datetime.now(UTC)


class Document(BaseModel):
    """租户知识库中的一个逻辑文档。"""

    id: str = Field(description="稳定的内部文档 ID，不依赖本地文件路径。")
    tenant_id: str = Field(
        default="default",
        description="用于隔离文档和 chunk 的租户或工作区命名空间。",
    )
    source_uri: str = Field(description="该文档的原始或受管源 URI。")
    file_name: str = Field(description="保留用于引用和调试的显示文件名。")
    page_count: int = Field(ge=0, description="解析器报告的总页数。")
    title: str | None = Field(
        default=None,
        description="可选的 PDF 元数据标题（如可用）。",
    )
    source_id: str | None = Field(
        default=None,
        description="为未来连接器或对象存储预留的可选外部系统 ID。",
    )
    current_version_id: str | None = Field(
        default=None,
        description="当前用于检索和引用的 DocumentVersion ID。",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="逻辑文档首次注册时的 UTC 时间戳。",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="文档元数据最后刷新的 UTC 时间戳。",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="不应影响核心身份的解析器或连接器元数据。",
    )


class DocumentVersion(BaseModel):
    """逻辑文档的一个具体内容版本。"""

    id: str = Field(description="该具体解析内容版本的稳定 ID。")
    tenant_id: str = Field(
        default="default",
        description="继承自逻辑文档的租户命名空间。",
    )
    document_id: str = Field(description="拥有该版本的逻辑文档 ID。")
    content_hash: str = Field(description="规范化解析页面文本的 SHA-256 哈希。")
    source_uri: str = Field(description="解析该版本时使用的源 URI。")
    file_name: str = Field(description="与该内容版本相关的文件名。")
    page_count: int = Field(ge=0, description="该解析版本的页数。")
    source_id: str | None = Field(
        default=None,
        description="随该版本记录的可选外部源 ID。",
    )
    title: str | None = Field(
        default=None,
        description="解析时记录的可选 PDF 标题。",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="该内容版本创建时的 UTC 时间戳。",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="该版本的原始解析器或连接器元数据。",
    )


class Page(BaseModel):
    """从一个 PDF 页面提取出的文本。"""

    document_id: str = Field(description="该页面所属的逻辑文档 ID。")
    document_version_id: str | None = Field(
        default=None,
        description="生成该页面文本的内容版本 ID。",
    )
    page_number: int = Field(ge=1, description="源 PDF 中从 1 开始的页码。")
    text: str = Field(description="从该页面提取并规范化后的文本。")


class SkippedFile(BaseModel):
    """目录导入时被跳过的非 PDF 或不受支持文件。"""

    source_path: Path = Field(description="在源扫描期间被跳过的路径。")
    reason: str = Field(description="文件未被导入的人类可读原因。")


class ParseIssue(BaseModel):
    """可恢复的解析警告或错误。"""

    source_path: Path = Field(description="与解析问题相关的 PDF 路径。")
    message: str = Field(description="人类可读的解析警告或错误消息。")
    page_number: int | None = Field(
        default=None,
        ge=1,
        description="问题与某一页面相关时的页码（从 1 开始）。",
    )


class ParsedPdf(BaseModel):
    """解析后的 PDF 内容以及可恢复警告。"""

    document: Document = Field(description="解析产生的逻辑文档元数据。")
    version: DocumentVersion = Field(description="解析产生的具体内容版本。")
    pages: list[Page] = Field(
        default_factory=list,
        description="可用于分块的非空解析页面。",
    )
    warnings: list[ParseIssue] = Field(
        default_factory=list,
        description="未阻止文档导入的可恢复解析问题。",
    )


class DirectoryParseResult(BaseModel):
    """导入源文件目录的结果。"""

    documents: list[Document] = Field(
        default_factory=list,
        description="从源目录成功解析出的逻辑文档。",
    )
    versions: list[DocumentVersion] = Field(
        default_factory=list,
        description="从源目录成功解析出的内容版本。",
    )
    pages: list[Page] = Field(
        default_factory=list,
        description="所有成功导入 PDF 的解析页面。",
    )
    skipped_files: list[SkippedFile] = Field(
        default_factory=list,
        description="扫描时被忽略的非 PDF 或不支持文件。",
    )
    errors: list[ParseIssue] = Field(
        default_factory=list,
        description="阻止导入的每个文件致命解析错误。",
    )
    warnings: list[ParseIssue] = Field(
        default_factory=list,
        description="从已导入 PDF 中收集到的可恢复解析警告。",
    )


class Chunk(BaseModel):
    """带有源页面来源信息的可检索文本 chunk。"""

    id: str = Field(description="由来源信息和文本派生的稳定 chunk ID。")
    document_id: str = Field(description="拥有该 chunk 的逻辑文档 ID。")
    document_version_id: str = Field(description="生成该 chunk 的内容版本 ID。")
    text: str = Field(description="用于 embedding、检索和引用的 chunk 文本。")
    page_start: int = Field(ge=1, description="chunk 覆盖的首个源页码（从 1 开始）。")
    page_end: int = Field(ge=1, description="chunk 覆盖的最后一个源页码（从 1 开始）。")
    chunk_index: int = Field(ge=0, description="文档内从 0 开始的 chunk 顺序。")
    token_count: int | None = Field(
        default=None,
        ge=0,
        description="已知时 chunk 中的 tokenizer 单元数。",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="镜像到向量存储的轻量元数据。",
    )

    @model_validator(mode="after")
    def validate_page_range(self) -> Chunk:
        """确保 chunk 来源始终使用正向页码区间。"""
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class Citation(BaseModel):
    """指向答案所用证据的人类可读引用。"""

    document_id: str = Field(description="答案所引用的逻辑文档 ID。")
    document_version_id: str | None = Field(
        default=None,
        description="答案所引用的内容版本 ID（如有）。",
    )
    chunk_id: str = Field(description="支撑该引用的证据 chunk ID。")
    file_name: str = Field(description="在引用标签中显示的文件名。")
    page_start: int = Field(ge=1, description="引用的首个源页码（从 1 开始）。")
    page_end: int = Field(ge=1, description="引用的最后一个源页码（从 1 开始）。")
    snippet: str | None = Field(
        default=None,
        description="随引用详情显示的简短证据预览。",
    )

    @model_validator(mode="after")
    def validate_page_range(self) -> Citation:
        """确保引用标签不会描述反向页码区间。"""
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self

    @property
    def label(self) -> str:
        """返回 CLI 和 API 响应使用的紧凑引用标签。"""
        if self.page_start == self.page_end:
            return f"[{self.file_name}, p.{self.page_start}]"
        return f"[{self.file_name}, pp.{self.page_start}-{self.page_end}]"


class Answer(BaseModel):
    """生成的答案以及引用和证据元数据。"""

    question: str = Field(description="RAG 流水线回答的用户问题。")
    answer: str = Field(description="返回给调用方的最终答案文本。")
    citations: list[Citation] = Field(
        default_factory=list,
        description="答案明确依赖的引用。",
    )
    evidence_chunk_ids: list[str] = Field(
        default_factory=list,
        description="被选为答案可用证据的 chunk ID。",
    )
    model_name: str | None = Field(
        default=None,
        description="生成该答案的 LLM 或本地答案生成器名称。",
    )
    insufficient_evidence: bool = Field(
        default=False,
        description="检索证据是否不足以支撑有依据的答案。",
    )
    context: str | None = Field(
        default=None,
        description="由检索证据组装的提示词上下文，便于调试。",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="答案对象创建时的 UTC 时间戳。",
    )


class IndexedSource(BaseModel):
    """构建索引时记录的源文件详情。"""

    tenant_id: str = Field(
        default="default",
        description="被索引源快照的租户命名空间。",
    )
    document_id: str = Field(description="索引中存在的逻辑文档 ID。")
    document_version_id: str = Field(description="索引中存在的内容版本 ID。")
    source_uri: str = Field(description="用于构建该索引条目的源 URI。")
    file_name: str = Field(description="被索引源的显示文件名。")
    content_hash: str = Field(description="用于去重检查的已索引内容哈希。")
    indexed_at: datetime = Field(
        default_factory=utc_now,
        description="记录该源快照时的 UTC 时间戳。",
    )


class SearchResult(BaseModel):
    """一个检索结果 chunk，包含相似度分数和源文档。"""

    chunk: Chunk = Field(description="向量搜索返回的检索 chunk。")
    score: float = Field(description="用于答案过滤的归一化相似度分数。")
    document: Document | None = Field(
        default=None,
        description="向量搜索后从 SQLite 关联得到的逻辑文档元数据。",
    )
    distance: float | None = Field(
        default=None,
        description="后端提供时的原始向量库距离。",
    )


class IndexBuildResult(BaseModel):
    """一次索引运行的摘要。"""

    status: IndexStatus = Field(description="构建运行完成后的索引状态。")
    indexed_documents: list[Document] = Field(
        default_factory=list,
        description="本次运行中新解析并索引的逻辑文档。",
    )
    reused_documents: list[Document] = Field(
        default_factory=list,
        description="无需新的 chunk embedding 工作而复用的所有文档。",
    )
    reused_source_documents: list[Document] = Field(
        default_factory=list,
        description="因相同源路径和内容仍然有效而跳过的文档。",
    )
    reused_content_documents: list[Document] = Field(
        default_factory=list,
        description="因相同内容已存在向量而跳过的文档。",
    )
    reindexed_documents: list[Document] = Field(
        default_factory=list,
        description="源内容发生变化并被重新索引的已有文档。",
    )
    indexed_chunk_count: int = Field(
        default=0,
        ge=0,
        description="本次运行中新生成 embedding 并写入的 chunk 数。",
    )
    skipped_files: list[SkippedFile] = Field(
        default_factory=list,
        description="因不受支持而在解析前被忽略的文件。",
    )
    errors: list[ParseIssue] = Field(
        default_factory=list,
        description="在不中止整个构建的情况下捕获到的逐文件失败。",
    )
    warnings: list[ParseIssue] = Field(
        default_factory=list,
        description="构建过程中捕获到的可恢复解析问题。",
    )


class IndexStatus(BaseModel):
    """本地论文索引的当前状态。"""

    status: Literal["empty", "building", "ready", "stale", "error"] = Field(
        default="empty",
        description="本地租户索引的生命周期状态。",
    )
    tenant_id: str = Field(default="default", description="此处汇总的租户命名空间。")
    index_dir: Path = Field(description="包含 SQLite 和 Chroma 数据的根目录。")
    document_count: int = Field(
        default=0,
        ge=0,
        description="该租户已索引的逻辑文档数量。",
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="可用于检索的已索引 chunk 数量。",
    )
    embedding_model: str | None = Field(
        default=None,
        description="用于创建当前向量索引的 embedding 模型。",
    )
    built_at: datetime | None = Field(
        default=None,
        description="索引首次构建时的 UTC 时间戳。",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="状态最后写入时的 UTC 时间戳。",
    )
    sources: list[IndexedSource] = Field(
        default_factory=list,
        description="当前索引状态中包含的源快照。",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="保留用于状态检查的构建错误。",
    )

    @field_validator("errors")
    @classmethod
    def drop_empty_errors(cls, value: list[str]) -> list[str]:
        """在调用方传入空白错误字符串时保持持久化状态整洁。"""
        return [item for item in value if item.strip()]
