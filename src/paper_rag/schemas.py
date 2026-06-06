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

    id: str = Field(description="Stable internal document ID, independent of local file paths.")
    tenant_id: str = Field(
        default="default",
        description="Tenant or workspace namespace used to isolate documents and chunks.",
    )
    source_uri: str = Field(description="Original or managed source URI for this document.")
    file_name: str = Field(description="Display file name retained for citations and debugging.")
    page_count: int = Field(ge=0, description="Total number of pages reported by the parser.")
    title: str | None = Field(
        default=None,
        description="Optional title extracted from PDF metadata when available.",
    )
    source_id: str | None = Field(
        default=None,
        description="Optional external system ID for future connectors or object stores.",
    )
    current_version_id: str | None = Field(
        default=None,
        description="DocumentVersion ID currently active for retrieval and citation.",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when the logical document was first registered.",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when document metadata was last refreshed.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Parser or connector metadata that should not affect core identity.",
    )


class DocumentVersion(BaseModel):
    """逻辑文档的一个具体内容版本。"""

    id: str = Field(description="Stable ID for this exact parsed content version.")
    tenant_id: str = Field(
        default="default",
        description="Tenant namespace inherited from the logical document.",
    )
    document_id: str = Field(description="Logical document ID that owns this version.")
    content_hash: str = Field(description="SHA-256 hash of normalized parsed page text.")
    source_uri: str = Field(description="Source URI used when this version was parsed.")
    file_name: str = Field(description="File name associated with this content version.")
    page_count: int = Field(ge=0, description="Page count for this parsed version.")
    source_id: str | None = Field(
        default=None,
        description="Optional external source ID captured with this version.",
    )
    title: str | None = Field(
        default=None,
        description="Optional PDF title captured at parse time.",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this content version was created.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw parser or connector metadata for this version.",
    )


class Page(BaseModel):
    """从一个 PDF 页面提取出的文本。"""

    document_id: str = Field(description="Logical document ID this page belongs to.")
    document_version_id: str | None = Field(
        default=None,
        description="Content version ID that produced this page text.",
    )
    page_number: int = Field(ge=1, description="One-based page number in the source PDF.")
    text: str = Field(description="Normalized text extracted from this page.")


class SkippedFile(BaseModel):
    """目录导入时被跳过的非 PDF 或不受支持文件。"""

    source_path: Path = Field(description="Path that was skipped during source scanning.")
    reason: str = Field(description="Human-readable reason the file was not imported.")


class ParseIssue(BaseModel):
    """可恢复的解析警告或错误。"""

    source_path: Path = Field(description="PDF path associated with the parse issue.")
    message: str = Field(description="Human-readable parse warning or error message.")
    page_number: int | None = Field(
        default=None,
        ge=1,
        description="One-based page number when the issue is page-specific.",
    )


class ParsedPdf(BaseModel):
    """解析后的 PDF 内容以及可恢复警告。"""

    document: Document = Field(description="Logical document metadata produced by parsing.")
    version: DocumentVersion = Field(description="Concrete content version produced by parsing.")
    pages: list[Page] = Field(
        default_factory=list,
        description="Non-empty parsed pages available for chunking.",
    )
    warnings: list[ParseIssue] = Field(
        default_factory=list,
        description="Recoverable parse issues that did not stop document import.",
    )


class DirectoryParseResult(BaseModel):
    """导入源文件目录的结果。"""

    documents: list[Document] = Field(
        default_factory=list,
        description="Logical documents successfully parsed from the source directory.",
    )
    versions: list[DocumentVersion] = Field(
        default_factory=list,
        description="Content versions successfully parsed from the source directory.",
    )
    pages: list[Page] = Field(
        default_factory=list,
        description="All parsed pages across successfully imported PDFs.",
    )
    skipped_files: list[SkippedFile] = Field(
        default_factory=list,
        description="Non-PDF or unsupported files ignored during scanning.",
    )
    errors: list[ParseIssue] = Field(
        default_factory=list,
        description="Fatal per-file parse errors that prevented import.",
    )
    warnings: list[ParseIssue] = Field(
        default_factory=list,
        description="Recoverable parse warnings gathered across imported PDFs.",
    )


class Chunk(BaseModel):
    """带有源页面来源信息的可检索文本 chunk。"""

    id: str = Field(description="Stable chunk ID derived from provenance and text.")
    document_id: str = Field(description="Logical document ID that owns the chunk.")
    document_version_id: str = Field(description="Content version ID that produced the chunk.")
    text: str = Field(description="Chunk text used for embedding, retrieval, and citation.")
    page_start: int = Field(ge=1, description="First one-based source page covered by chunk.")
    page_end: int = Field(ge=1, description="Last one-based source page covered by chunk.")
    chunk_index: int = Field(ge=0, description="Zero-based chunk order within the document.")
    token_count: int | None = Field(
        default=None,
        ge=0,
        description="Number of tokenizer units in the chunk when known.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Lightweight metadata mirrored into vector storage.",
    )

    @model_validator(mode="after")
    def validate_page_range(self) -> Chunk:
        """确保 chunk 来源始终使用正向页码区间。"""
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class Citation(BaseModel):
    """指向答案所用证据的人类可读引用。"""

    document_id: str = Field(description="Logical document ID cited by the answer.")
    document_version_id: str | None = Field(
        default=None,
        description="Content version ID cited by the answer, when available.",
    )
    chunk_id: str = Field(description="Evidence chunk ID backing this citation.")
    file_name: str = Field(description="File name shown in the citation label.")
    page_start: int = Field(ge=1, description="First one-based cited source page.")
    page_end: int = Field(ge=1, description="Last one-based cited source page.")
    snippet: str | None = Field(
        default=None,
        description="Short evidence preview displayed with citation details.",
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

    question: str = Field(description="User question answered by the RAG pipeline.")
    answer: str = Field(description="Final answer text returned to the caller.")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Citations that the answer explicitly relies on.",
    )
    evidence_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk IDs selected as usable evidence for the answer.",
    )
    model_name: str | None = Field(
        default=None,
        description="LLM or local answer generator name that produced the answer.",
    )
    insufficient_evidence: bool = Field(
        default=False,
        description="Whether retrieval evidence was insufficient for a grounded answer.",
    )
    context: str | None = Field(
        default=None,
        description="Prompt context assembled from retrieved evidence for debugging.",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when the answer object was created.",
    )


class IndexedSource(BaseModel):
    """构建索引时记录的源文件详情。"""

    tenant_id: str = Field(
        default="default",
        description="Tenant namespace for the indexed source snapshot.",
    )
    document_id: str = Field(description="Logical document ID present in the index.")
    document_version_id: str = Field(description="Content version ID present in the index.")
    source_uri: str = Field(description="Source URI used to build this index entry.")
    file_name: str = Field(description="Display file name for the indexed source.")
    content_hash: str = Field(description="Content hash indexed for deduplication checks.")
    indexed_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this source snapshot was recorded.",
    )


class SearchResult(BaseModel):
    """一个检索结果 chunk，包含相似度分数和源文档。"""

    chunk: Chunk = Field(description="Retrieved chunk returned from vector search.")
    score: float = Field(description="Normalized similarity score used for answer filtering.")
    document: Document | None = Field(
        default=None,
        description="Logical document metadata joined from SQLite after vector search.",
    )
    distance: float | None = Field(
        default=None,
        description="Raw vector-store distance when provided by the backend.",
    )


class IndexBuildResult(BaseModel):
    """一次索引运行的摘要。"""

    status: IndexStatus = Field(description="Index status after the build run completed.")
    indexed_documents: list[Document] = Field(
        default_factory=list,
        description="New logical documents parsed and indexed in this run.",
    )
    reused_documents: list[Document] = Field(
        default_factory=list,
        description="All documents reused without new chunk embedding work.",
    )
    reused_source_documents: list[Document] = Field(
        default_factory=list,
        description="Documents skipped because the same source path and content were current.",
    )
    reused_content_documents: list[Document] = Field(
        default_factory=list,
        description="Documents skipped because identical content already had vectors.",
    )
    reindexed_documents: list[Document] = Field(
        default_factory=list,
        description="Existing documents whose source content changed and was reindexed.",
    )
    indexed_chunk_count: int = Field(
        default=0,
        ge=0,
        description="Number of chunks newly embedded and written in this run.",
    )
    skipped_files: list[SkippedFile] = Field(
        default_factory=list,
        description="Files ignored before parsing because they were unsupported.",
    )
    errors: list[ParseIssue] = Field(
        default_factory=list,
        description="Per-file failures captured without aborting the whole build.",
    )
    warnings: list[ParseIssue] = Field(
        default_factory=list,
        description="Recoverable parse issues captured during the build.",
    )


class IndexStatus(BaseModel):
    """本地论文索引的当前状态。"""

    status: Literal["empty", "building", "ready", "stale", "error"] = Field(
        default="empty",
        description="Lifecycle state of the local tenant index.",
    )
    tenant_id: str = Field(default="default", description="Tenant namespace summarized here.")
    index_dir: Path = Field(description="Root directory containing SQLite and Chroma data.")
    document_count: int = Field(
        default=0,
        ge=0,
        description="Number of indexed logical documents for the tenant.",
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Number of indexed chunks available for retrieval.",
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model used to create the current vector index.",
    )
    built_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the index was first built.",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when status was last written.",
    )
    sources: list[IndexedSource] = Field(
        default_factory=list,
        description="Source snapshots included in the current index status.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Build errors retained for status inspection.",
    )

    @field_validator("errors")
    @classmethod
    def drop_empty_errors(cls, value: list[str]) -> list[str]:
        """在调用方传入空白错误字符串时保持持久化状态整洁。"""
        return [item for item in value if item.strip()]
