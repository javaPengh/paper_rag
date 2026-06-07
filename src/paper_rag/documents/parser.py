"""PDF 发现与解析。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from paper_rag.domain import (
    DirectoryParseResult,
    Document,
    DocumentVersion,
    Page,
    ParsedPdf,
    ParseIssue,
    SkippedFile,
)
from paper_rag.exceptions import ConfigurationError, DocumentParseError


def scan_source_directory(
    directory: Path,
    *,
    recursive: bool = True,
) -> tuple[list[Path], list[SkippedFile]]:
    """返回目录下的 PDF 文件，并记录被跳过的非 PDF 文件。"""
    source_dir = Path(directory)
    if not source_dir.exists():
        raise DocumentParseError(f"Source directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise DocumentParseError(f"Source path is not a directory: {source_dir}")

    pattern = "**/*" if recursive else "*"
    pdf_paths: list[Path] = []
    skipped_files: list[SkippedFile] = []

    for path in sorted(source_dir.glob(pattern)):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".pdf":
            pdf_paths.append(path)
        else:
            skipped_files.append(SkippedFile(source_path=path, reason="not a PDF file"))

    return pdf_paths, skipped_files


def parse_pdf_directory(directory: Path, *, recursive: bool = True) -> DirectoryParseResult:
    """解析目录中的每个 PDF，但不会因为单个文件失败而中止。"""
    pdf_paths, skipped_files = scan_source_directory(directory, recursive=recursive)
    result = DirectoryParseResult(skipped_files=skipped_files)

    for pdf_path in pdf_paths:
        try:
            parsed_pdf = parse_pdf(pdf_path)
        except DocumentParseError as exc:
            result.errors.append(ParseIssue(source_path=pdf_path, message=str(exc)))
            continue

        result.documents.append(parsed_pdf.document)
        result.versions.append(parsed_pdf.version)
        result.pages.extend(parsed_pdf.pages)
        result.warnings.extend(parsed_pdf.warnings)

    return result


def parse_pdf(
    path: Path,
    *,
    tenant_id: str = "default",
    document_id: str | None = None,
    document_version_id: str | None = None,
    source_id: str | None = None,
    source_uri: str | None = None,
    content_hash: str | None = None,
) -> ParsedPdf:
    """把一个 PDF 解析为文档元数据和非空页面文本。"""
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise DocumentParseError(f"PDF file does not exist: {pdf_path}")
    if not pdf_path.is_file():
        raise DocumentParseError(f"PDF path is not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise DocumentParseError(f"Source file is not a PDF: {pdf_path}")

    fitz = _load_pymupdf()
    resolved_source_uri = source_uri or str(pdf_path.resolve())

    try:
        pdf = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF uses several exception classes across versions.
        raise DocumentParseError(f"Could not open PDF {pdf_path}: {exc}") from exc

    try:
        metadata = dict(pdf.metadata or {})
        extracted_pages: list[tuple[int, str]] = []
        warnings: list[ParseIssue] = []

        for page_index in range(pdf.page_count):
            page_number = page_index + 1
            try:
                text = normalize_page_text(pdf.load_page(page_index).get_text("text"))
            except Exception as exc:
                warnings.append(
                    ParseIssue(
                        source_path=pdf_path,
                        page_number=page_number,
                        message=f"Could not extract text from page {page_number}: {exc}",
                    )
                )
                continue

            if not text.strip():
                warnings.append(
                    ParseIssue(
                        source_path=pdf_path,
                        page_number=page_number,
                        message=f"Skipped empty text page {page_number}",
                    )
                )
                continue

            extracted_pages.append((page_number, text))

        resolved_content_hash = content_hash or hash_page_texts(extracted_pages)
        resolved_document_id = document_id or new_document_id()
        resolved_version_id = document_version_id or make_document_version_id(
            resolved_document_id,
            resolved_content_hash,
        )
        document = Document(
            id=resolved_document_id,
            tenant_id=tenant_id,
            source_id=source_id,
            source_uri=resolved_source_uri,
            file_name=pdf_path.name,
            page_count=pdf.page_count,
            title=_clean_optional_text(metadata.get("title")),
            current_version_id=resolved_version_id,
            metadata=metadata,
        )
        version = DocumentVersion(
            id=resolved_version_id,
            tenant_id=tenant_id,
            document_id=resolved_document_id,
            source_id=source_id,
            source_uri=resolved_source_uri,
            file_name=pdf_path.name,
            page_count=pdf.page_count,
            title=document.title,
            content_hash=resolved_content_hash,
            metadata=metadata,
        )

        pages = [
            Page(
                document_id=resolved_document_id,
                document_version_id=resolved_version_id,
                page_number=page_number,
                text=text,
            )
            for page_number, text in extracted_pages
        ]

        return ParsedPdf(document=document, version=version, pages=pages, warnings=warnings)
    finally:
        pdf.close()


def normalize_page_text(text: str) -> str:
    """规范化 PDF 文本提取结果，同时不破坏段落边界。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def hash_page_texts(page_texts: Iterable[tuple[int, str]]) -> str:
    """为解析后并规范化的 PDF 页面文本计算 SHA-256 哈希。"""
    digest = hashlib.sha256()
    for page_number, text in page_texts:
        digest.update(f"\f{page_number}\n{text.strip()}".encode())
    return digest.hexdigest()


def hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """为源文件计算 SHA-256 哈希。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def new_document_id() -> str:
    """创建不依赖本地路径的稳定内部文档 ID。"""
    return uuid4().hex[:24]


def make_document_version_id(document_id: str, content_hash: str) -> str:
    """为一个逻辑文档创建稳定的内容版本 ID。"""
    material = f"{document_id}:{content_hash}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _clean_optional_text(value: object) -> str | None:
    """规范化可选的 PDF 元数据字段，并将空白字符串视为缺失。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_pymupdf():
    """延迟导入 PyMuPDF，使配置错误能指向预期的项目安装方式。"""
    try:
        import fitz  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise ConfigurationError(
            "PyMuPDF is required for PDF parsing. Install dependencies with "
            'pip install -e ".[dev]" inside the paper_rag conda environment.'
        ) from exc
    return fitz


def iter_pages_by_document(pages: Iterable[Page]) -> dict[str, list[Page]]:
    """按文档 ID 分组页面，同时保留页面顺序。"""
    grouped: dict[str, list[Page]] = {}
    for page in sorted(pages, key=lambda item: (item.document_id, item.page_number)):
        grouped.setdefault(page.document_id, []).append(page)
    return grouped
