"""Managed local storage for uploaded source documents."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from paper_rag.exceptions import DocumentUploadError

PDF_HEADER = b"%PDF-"
PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/octet-stream",
    "application/x-pdf",
}
SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredUpload:
    """A PDF saved into managed tenant-scoped source storage."""

    tenant_id: str
    storage_tenant: str
    original_file_name: str
    safe_file_name: str
    stored_path: Path
    source_uri: str
    content_hash: str
    size_bytes: int


class LocalUploadStorage:
    """Store validated uploaded PDFs under a controlled local root directory."""

    def __init__(self, root_dir: Path, *, max_size_bytes: int | None = None) -> None:
        self.root_dir = Path(root_dir)
        self.max_size_bytes = max_size_bytes

    def save_pdf(
        self,
        *,
        tenant_id: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> StoredUpload:
        """Validate and save one PDF upload, returning its stable source URI."""
        normalized_file_name = _extract_file_name(file_name)
        _validate_pdf_upload(
            file_name=normalized_file_name,
            content=content,
            content_type=content_type,
            max_size_bytes=self.max_size_bytes,
        )

        content_hash = hashlib.sha256(content).hexdigest()
        storage_tenant = safe_path_segment(tenant_id, default="default")
        safe_file_name = safe_pdf_file_name(normalized_file_name)
        stored_file_name = f"{content_hash[:16]}-{safe_file_name}"
        tenant_dir = self.root_dir / storage_tenant
        tenant_dir.mkdir(parents=True, exist_ok=True)
        stored_path = (tenant_dir / stored_file_name).resolve()
        storage_root = self.root_dir.resolve()
        if not stored_path.is_relative_to(storage_root):
            raise DocumentUploadError("Upload target escaped the configured storage root.")

        stored_path.write_bytes(content)
        return StoredUpload(
            tenant_id=tenant_id,
            storage_tenant=storage_tenant,
            original_file_name=normalized_file_name,
            safe_file_name=safe_file_name,
            stored_path=stored_path,
            source_uri=str(stored_path),
            content_hash=content_hash,
            size_bytes=len(content),
        )


def safe_pdf_file_name(file_name: str) -> str:
    """Return a safe local file name with a `.pdf` suffix."""
    base_name = _extract_file_name(file_name)
    path = Path(base_name)
    stem = safe_path_segment(path.stem, default="document")
    suffix = path.suffix.lower()
    if suffix != ".pdf":
        raise DocumentUploadError("Only PDF uploads are supported.")
    return f"{stem}.pdf"


def safe_path_segment(value: str, *, default: str) -> str:
    """Sanitize one directory or file-name segment."""
    sanitized = SAFE_NAME_PATTERN.sub("_", value.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("._-")
    return sanitized or default


def _validate_pdf_upload(
    *,
    file_name: str,
    content: bytes,
    content_type: str | None,
    max_size_bytes: int | None,
) -> None:
    if not content:
        raise DocumentUploadError("Uploaded PDF is empty.")
    if max_size_bytes is not None and len(content) > max_size_bytes:
        raise DocumentUploadError(
            f"Uploaded PDF is too large: {len(content)} bytes exceeds "
            f"the limit of {max_size_bytes} bytes."
        )
    if Path(file_name).suffix.lower() != ".pdf":
        raise DocumentUploadError("Only PDF uploads are supported.")
    if content_type and content_type.lower().split(";")[0].strip() not in PDF_CONTENT_TYPES:
        raise DocumentUploadError(f"Unsupported PDF content type: {content_type}")
    if not content.startswith(PDF_HEADER):
        raise DocumentUploadError("Uploaded file does not look like a PDF.")


def _extract_file_name(file_name: str) -> str:
    normalized = file_name.replace("\\", "/").split("/")[-1].strip()
    if not normalized:
        raise DocumentUploadError("Uploaded file name cannot be empty.")
    return normalized
