"""本地 Web Inspector 的 API 请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """基础服务健康状态载荷。"""

    status: str = Field(description="Service health state, normally `ok`.")
    version: str = Field(description="Installed paper_rag package version.")


class ErrorDetailResponse(BaseModel):
    """用于 HTTP 错误响应的结构化 API 错误详情。"""

    stage: str = Field(description="Pipeline stage where the API error occurred.")
    error_type: str = Field(description="Exception class name or error category.")
    message: str = Field(description="Human-readable error message safe for the inspector UI.")


class IndexStatusResponse(BaseModel):
    """租户范围内的本地索引状态。"""

    status: str = Field(description="Current index lifecycle state for the tenant.")
    tenant_id: str = Field(description="Tenant/workspace namespace used for this query.")
    index_dir: Path = Field(description="Local index directory inspected by the API.")
    document_count: int = Field(ge=0, description="Number of indexed documents for the tenant.")
    chunk_count: int = Field(ge=0, description="Number of indexed chunks for the tenant.")
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model used by the indexed vectors, if known.",
    )
    built_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the index was first built.",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when index status was last updated.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Persisted indexing errors shown to the inspector user.",
    )


class DocumentSummaryResponse(BaseModel):
    """Inspector 文档列表所需的文档详情。"""

    id: str = Field(description="Stable internal document ID.")
    tenant_id: str = Field(description="Tenant/workspace namespace that owns the document.")
    source_id: str | None = Field(
        default=None,
        description="Optional external source ID reserved for future connectors.",
    )
    source_uri: str = Field(description="Source URI used to build the current document record.")
    file_name: str = Field(description="Display file name used by the inspector and citations.")
    title: str | None = Field(default=None, description="Optional PDF metadata title.")
    page_count: int = Field(ge=0, description="Number of pages reported by the parser.")
    current_version_id: str | None = Field(
        default=None,
        description="Active content version ID for this document.",
    )
    content_hash: str | None = Field(
        default=None,
        description="Content hash for the active version, when available.",
    )
    chunk_count: int = Field(ge=0, description="Number of chunks indexed for this document.")
    created_at: datetime = Field(description="UTC timestamp when the document was created.")
    updated_at: datetime = Field(description="UTC timestamp when the document was last updated.")


class ChunkResponse(BaseModel):
    """用于检查和引用追踪的 chunk 详情。"""

    id: str = Field(description="Stable chunk ID.")
    document_id: str = Field(description="Logical document ID that owns this chunk.")
    document_version_id: str = Field(description="Content version that produced this chunk.")
    file_name: str | None = Field(
        default=None,
        description="Display file name joined from document metadata when available.",
    )
    text: str = Field(description="Chunk text shown for inspection and evidence tracing.")
    page_start: int = Field(ge=1, description="First one-based source page in the chunk.")
    page_end: int = Field(ge=1, description="Last one-based source page in the chunk.")
    chunk_index: int = Field(ge=0, description="Zero-based chunk order within the document.")
    token_count: int | None = Field(
        default=None,
        ge=0,
        description="Tokenizer unit count recorded at chunking time.",
    )


class StoredUploadResponse(BaseModel):
    """保存到受管本地源存储中的 PDF 详情。"""

    tenant_id: str = Field(description="Tenant ID requested by the uploader.")
    storage_tenant: str = Field(description="Sanitized tenant path segment used on disk.")
    original_file_name: str = Field(description="Original upload file name after path stripping.")
    safe_file_name: str = Field(description="Sanitized PDF file name retained for storage.")
    stored_path: Path = Field(description="Absolute local path of the managed stored PDF.")
    source_uri: str = Field(description="Source URI passed into the indexing pipeline.")
    content_hash: str = Field(description="SHA-256 hash of the uploaded PDF bytes.")
    size_bytes: int = Field(ge=0, description="Uploaded PDF size in bytes.")


class FileIssueResponse(BaseModel):
    """索引返回的跳过文件或解析问题。"""

    source_path: Path = Field(description="Source file associated with the issue.")
    reason: str | None = Field(
        default=None,
        description="Reason a file was skipped before parsing.",
    )
    message: str | None = Field(
        default=None,
        description="Parser or indexing message for warnings and errors.",
    )
    page_number: int | None = Field(
        default=None,
        ge=1,
        description="One-based source page when the issue is page-specific.",
    )


class IndexingSummaryResponse(BaseModel):
    """一次由上传触发的索引运行的结构化摘要。"""

    indexed: int = Field(ge=0, description="Number of new documents indexed.")
    reused_source: int = Field(ge=0, description="Documents reused by unchanged source URI.")
    reused_content: int = Field(ge=0, description="Documents reused by duplicate content hash.")
    reindexed: int = Field(ge=0, description="Existing documents reindexed after content changes.")
    indexed_chunks: int = Field(ge=0, description="Chunks newly embedded and written.")
    total_documents: int = Field(ge=0, description="Total indexed documents after the run.")
    total_chunks: int = Field(ge=0, description="Total indexed chunks after the run.")
    skipped_files: list[FileIssueResponse] = Field(
        default_factory=list,
        description="Files skipped before parse/index work.",
    )
    warnings: list[FileIssueResponse] = Field(
        default_factory=list,
        description="Recoverable parse/index warnings.",
    )
    errors: list[FileIssueResponse] = Field(
        default_factory=list,
        description="Fatal per-file parse/index errors.",
    )


class UploadIndexResponse(BaseModel):
    """保存 PDF 并同步索引后返回的响应。"""

    upload: StoredUploadResponse = Field(description="Managed upload storage result.")
    index: IndexingSummaryResponse = Field(description="Synchronous indexing summary.")
    status: IndexStatusResponse = Field(description="Index status after upload indexing.")


class CitationResponse(BaseModel):
    """与 CLI 字符串格式解耦的引用载荷。"""

    label: str = Field(description="Rendered citation label, e.g. `[paper.pdf, p.1]`.")
    document_id: str = Field(description="Cited logical document ID.")
    document_version_id: str | None = Field(
        default=None,
        description="Cited content version ID when available.",
    )
    chunk_id: str = Field(description="Evidence chunk ID backing this citation.")
    file_name: str = Field(description="File name displayed in the citation label.")
    page_start: int = Field(ge=1, description="First cited source page.")
    page_end: int = Field(ge=1, description="Last cited source page.")
    snippet: str | None = Field(default=None, description="Short cited evidence preview.")


class EvidenceResponse(BaseModel):
    """检索到的证据及其排序元数据。"""

    chunk: ChunkResponse = Field(description="Retrieved chunk shown in the Evidence panel.")
    score: float = Field(description="Similarity score used by answer filtering.")
    distance: float | None = Field(
        default=None,
        description="Raw vector-store distance when available.",
    )
    used: bool = Field(default=False, description="Whether the answer generator used this chunk.")


class AskRequest(BaseModel):
    """本地 Inspector 的问题请求。"""

    question: str = Field(min_length=1, description="Natural-language question to answer.")
    tenant_id: str = Field(default="default", description="Tenant/workspace namespace to query.")
    index_dir: Path | None = Field(
        default=None,
        description="Local index directory override for this request.",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="Number of evidence chunks to retrieve before answer generation.",
    )
    min_score: float = Field(
        default=0.05,
        ge=0,
        description="Minimum retrieval score for evidence to be considered usable.",
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model override for query embedding.",
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model override for non-local answer generation.",
    )
    local: bool = Field(
        default=False,
        description="Use deterministic local embeddings and extractive answer generation.",
    )


class AskResponse(BaseModel):
    """带有引用和检索证据的答案载荷。"""

    question: str = Field(description="Question echoed from the request.")
    answer: str = Field(description="Answer text returned by the answer generator.")
    insufficient_evidence: bool = Field(description="Whether the answer is a grounded refusal.")
    model_name: str | None = Field(
        default=None,
        description="Model or local generator name that produced the answer.",
    )
    citations: list[CitationResponse] = Field(
        default_factory=list,
        description="Citations included in the answer.",
    )
    evidence: list[EvidenceResponse] = Field(
        default_factory=list,
        description="Retrieved evidence shown for inspection and debugging.",
    )
    context: str | None = Field(
        default=None,
        description="Prompt context assembled from evidence, useful during local debugging.",
    )
