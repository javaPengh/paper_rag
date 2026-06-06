"""PDF discovery and parsing."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from paper_rag.exceptions import ConfigurationError, DocumentParseError
from paper_rag.schemas import (
    DirectoryParseResult,
    Document,
    DocumentVersion,
    Page,
    ParsedPdf,
    ParseIssue,
    SkippedFile,
)


def scan_source_directory(
    directory: Path,
    *,
    recursive: bool = True,
) -> tuple[list[Path], list[SkippedFile]]:
    """Return PDF files under a directory and record skipped non-PDF files."""
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
    """Parse every PDF in a directory without aborting on individual file failures."""
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
    """Parse one PDF into document metadata and non-empty page text."""
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
    """Normalize PDF text extraction output without destroying paragraph boundaries."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def hash_page_texts(page_texts: Iterable[tuple[int, str]]) -> str:
    """Compute a SHA-256 hash for parsed, normalized PDF page text."""
    digest = hashlib.sha256()
    for page_number, text in page_texts:
        digest.update(f"\f{page_number}\n{text.strip()}".encode())
    return digest.hexdigest()


def hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute a SHA-256 hash for a source file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def new_document_id() -> str:
    """Create a stable internal document ID that is not derived from local paths."""
    return uuid4().hex[:24]


def make_document_version_id(document_id: str, content_hash: str) -> str:
    """Create a stable content-version ID for one logical document."""
    material = f"{document_id}:{content_hash}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_pymupdf():
    try:
        import fitz  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise ConfigurationError(
            "PyMuPDF is required for PDF parsing. Install dependencies with "
            'pip install -e ".[dev]" inside the paper_rag conda environment.'
        ) from exc
    return fitz


def iter_pages_by_document(pages: Iterable[Page]) -> dict[str, list[Page]]:
    """Group pages by document ID while preserving page order."""
    grouped: dict[str, list[Page]] = {}
    for page in sorted(pages, key=lambda item: (item.document_id, item.page_number)):
        grouped.setdefault(page.document_id, []).append(page)
    return grouped
