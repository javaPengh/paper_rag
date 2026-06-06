"""上传源文档的受管本地存储。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from paper_rag.exceptions import DocumentUploadError

# 用于在解析前拒绝明显非 PDF 上传文件的最小 PDF 魔术头。
PDF_HEADER = b"%PDF-"

# 浏览器和本地客户端可能会用这些常见 MIME 值来表示 PDF 上传。
PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/octet-stream",
    "application/x-pdf",
}

# 在把用户输入映射到本地存储时，只保留保守的路径字符。
SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredUpload:
    """保存到受管租户范围源存储中的 PDF。"""

    tenant_id: str = field(
        metadata={"description": "Tenant ID supplied by the upload caller."},
    )
    storage_tenant: str = field(
        metadata={"description": "Sanitized tenant path segment used under the storage root."},
    )
    original_file_name: str = field(
        metadata={"description": "Original upload file name after removing path components."},
    )
    safe_file_name: str = field(
        metadata={"description": "Sanitized PDF file name retained in the stored file name."},
    )
    stored_path: Path = field(
        metadata={"description": "Resolved local path where the upload bytes were written."},
    )
    source_uri: str = field(
        metadata={"description": "URI passed into document parsing and index metadata."},
    )
    content_hash: str = field(
        metadata={"description": "SHA-256 hash of uploaded bytes used for stored-name stability."},
    )
    size_bytes: int = field(metadata={"description": "Upload size in bytes."})


class LocalUploadStorage:
    """将已验证的 PDF 上传文件存到受控的本地根目录下。"""

    def __init__(self, root_dir: Path, *, max_size_bytes: int | None = None) -> None:
        """创建一个以受管本地目录为根的租户范围上传存储。"""
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
        """验证并保存一个 PDF 上传，并返回其稳定的源 URI。"""
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
    """返回带 `.pdf` 后缀的安全本地文件名。"""
    base_name = _extract_file_name(file_name)
    path = Path(base_name)
    stem = safe_path_segment(path.stem, default="document")
    suffix = path.suffix.lower()
    if suffix != ".pdf":
        raise DocumentUploadError("Only PDF uploads are supported.")
    return f"{stem}.pdf"


def safe_path_segment(value: str, *, default: str) -> str:
    """清理一个目录或文件名片段。"""
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
    """拒绝空文件、超大文件、非 PDF 文件或不在允许 MIME 范围内的上传。"""
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
    """去掉客户端提供的路径部分，只保留上传文件名的叶子部分。"""
    normalized = file_name.replace("\\", "/").split("/")[-1].strip()
    if not normalized:
        raise DocumentUploadError("Uploaded file name cannot be empty.")
    return normalized
