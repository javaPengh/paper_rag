"""Shared data models for documents, chunks, citations, answers, and index state."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class Document(BaseModel):
    """A logical document in a tenant knowledge base."""

    id: str
    tenant_id: str = "default"
    source_uri: str
    file_name: str
    page_count: int = Field(ge=0)
    title: str | None = None
    source_id: str | None = None
    current_version_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentVersion(BaseModel):
    """A concrete content version of a logical document."""

    id: str
    tenant_id: str = "default"
    document_id: str
    content_hash: str
    source_uri: str
    file_name: str
    page_count: int = Field(ge=0)
    source_id: str | None = None
    title: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Page(BaseModel):
    """Text extracted from one PDF page."""

    document_id: str
    document_version_id: str | None = None
    page_number: int = Field(ge=1)
    text: str


class SkippedFile(BaseModel):
    """A non-PDF or unsupported file skipped during directory import."""

    source_path: Path
    reason: str


class ParseIssue(BaseModel):
    """A recoverable parsing warning or error."""

    source_path: Path
    message: str
    page_number: int | None = Field(default=None, ge=1)


class ParsedPdf(BaseModel):
    """Parsed PDF content plus recoverable warnings."""

    document: Document
    version: DocumentVersion
    pages: list[Page] = Field(default_factory=list)
    warnings: list[ParseIssue] = Field(default_factory=list)


class DirectoryParseResult(BaseModel):
    """Result of importing a directory of source files."""

    documents: list[Document] = Field(default_factory=list)
    versions: list[DocumentVersion] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)
    skipped_files: list[SkippedFile] = Field(default_factory=list)
    errors: list[ParseIssue] = Field(default_factory=list)
    warnings: list[ParseIssue] = Field(default_factory=list)


class Chunk(BaseModel):
    """A retrievable text chunk with source-page provenance."""

    id: str
    document_id: str
    document_version_id: str
    text: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    token_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_page_range(self) -> Chunk:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class Citation(BaseModel):
    """A human-readable pointer back to evidence used in an answer."""

    document_id: str
    document_version_id: str | None = None
    chunk_id: str
    file_name: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    snippet: str | None = None

    @model_validator(mode="after")
    def validate_page_range(self) -> Citation:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self

    @property
    def label(self) -> str:
        if self.page_start == self.page_end:
            return f"[{self.file_name}, p.{self.page_start}]"
        return f"[{self.file_name}, pp.{self.page_start}-{self.page_end}]"


class Answer(BaseModel):
    """A generated answer plus citations and evidence metadata."""

    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    model_name: str | None = None
    insufficient_evidence: bool = False
    context: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class IndexedSource(BaseModel):
    """Source file details captured when building an index."""

    tenant_id: str = "default"
    document_id: str
    document_version_id: str
    source_uri: str
    file_name: str
    content_hash: str
    indexed_at: datetime = Field(default_factory=utc_now)


class SearchResult(BaseModel):
    """One retrieved chunk with similarity score and source document."""

    chunk: Chunk
    score: float
    document: Document | None = None
    distance: float | None = None


class IndexBuildResult(BaseModel):
    """Summary of one indexing run."""

    status: IndexStatus
    indexed_documents: list[Document] = Field(default_factory=list)
    reused_documents: list[Document] = Field(default_factory=list)
    reused_source_documents: list[Document] = Field(default_factory=list)
    reused_content_documents: list[Document] = Field(default_factory=list)
    reindexed_documents: list[Document] = Field(default_factory=list)
    indexed_chunk_count: int = Field(default=0, ge=0)
    skipped_files: list[SkippedFile] = Field(default_factory=list)
    errors: list[ParseIssue] = Field(default_factory=list)
    warnings: list[ParseIssue] = Field(default_factory=list)


class IndexStatus(BaseModel):
    """Current state of the local paper index."""

    status: Literal["empty", "building", "ready", "stale", "error"] = "empty"
    tenant_id: str = "default"
    index_dir: Path
    document_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)
    embedding_model: str | None = None
    built_at: datetime | None = None
    updated_at: datetime | None = None
    sources: list[IndexedSource] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @field_validator("errors")
    @classmethod
    def drop_empty_errors(cls, value: list[str]) -> list[str]:
        return [item for item in value if item.strip()]
