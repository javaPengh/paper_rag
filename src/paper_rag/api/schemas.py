"""API request and response models for the local Web Inspector."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Basic service health payload."""

    status: str
    version: str


class ErrorDetailResponse(BaseModel):
    """Structured API error detail used in HTTP error responses."""

    stage: str
    error_type: str
    message: str


class IndexStatusResponse(BaseModel):
    """Tenant-scoped local index status."""

    status: str
    tenant_id: str
    index_dir: Path
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    embedding_model: str | None = None
    built_at: datetime | None = None
    updated_at: datetime | None = None
    errors: list[str] = Field(default_factory=list)


class DocumentSummaryResponse(BaseModel):
    """Document details needed by the inspector document list."""

    id: str
    tenant_id: str
    source_id: str | None = None
    source_uri: str
    file_name: str
    title: str | None = None
    page_count: int = Field(ge=0)
    current_version_id: str | None = None
    content_hash: str | None = None
    chunk_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class ChunkResponse(BaseModel):
    """Chunk details for inspection and citation tracing."""

    id: str
    document_id: str
    document_version_id: str
    file_name: str | None = None
    text: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    token_count: int | None = Field(default=None, ge=0)


class StoredUploadResponse(BaseModel):
    """Details for a PDF saved into managed local source storage."""

    tenant_id: str
    storage_tenant: str
    original_file_name: str
    safe_file_name: str
    stored_path: Path
    source_uri: str
    content_hash: str
    size_bytes: int = Field(ge=0)


class FileIssueResponse(BaseModel):
    """Skipped file or parse issue returned from indexing."""

    source_path: Path
    reason: str | None = None
    message: str | None = None
    page_number: int | None = Field(default=None, ge=1)


class IndexingSummaryResponse(BaseModel):
    """Structured summary for one upload-triggered indexing run."""

    indexed: int = Field(ge=0)
    reused_source: int = Field(ge=0)
    reused_content: int = Field(ge=0)
    reindexed: int = Field(ge=0)
    indexed_chunks: int = Field(ge=0)
    total_documents: int = Field(ge=0)
    total_chunks: int = Field(ge=0)
    skipped_files: list[FileIssueResponse] = Field(default_factory=list)
    warnings: list[FileIssueResponse] = Field(default_factory=list)
    errors: list[FileIssueResponse] = Field(default_factory=list)


class UploadIndexResponse(BaseModel):
    """Response returned after storing a PDF and synchronously indexing it."""

    upload: StoredUploadResponse
    index: IndexingSummaryResponse
    status: IndexStatusResponse


class CitationResponse(BaseModel):
    """Citation payload detached from CLI string formatting."""

    label: str
    document_id: str
    document_version_id: str | None = None
    chunk_id: str
    file_name: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    snippet: str | None = None


class EvidenceResponse(BaseModel):
    """Retrieved evidence plus ranking metadata."""

    chunk: ChunkResponse
    score: float
    distance: float | None = None
    used: bool = False


class AskRequest(BaseModel):
    """Question request for the local inspector."""

    question: str = Field(min_length=1)
    tenant_id: str = "default"
    index_dir: Path | None = None
    top_k: int | None = Field(default=None, ge=1)
    min_score: float = Field(default=0.05, ge=0)
    embedding_model: str | None = None
    llm_model: str | None = None
    local: bool = False


class AskResponse(BaseModel):
    """Answer payload with citations and retrieved evidence."""

    question: str
    answer: str
    insufficient_evidence: bool
    model_name: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    evidence: list[EvidenceResponse] = Field(default_factory=list)
    context: str | None = None
