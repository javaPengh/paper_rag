"""PDF Reader 组件 provider。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paper_rag.documents.parser import parse_pdf, parse_pdf_directory, scan_source_directory
from paper_rag.domain import DirectoryParseResult, ParsedPdf, SkippedFile


@dataclass(frozen=True)
class PdfReader:
    """把现有 PyMuPDF 解析器包装成 Reader 组件。"""

    def scan_directory(
        self,
        directory: Path,
        *,
        recursive: bool = True,
    ) -> tuple[list[Path], list[SkippedFile]]:
        """发现目录中的 PDF 文件，并保留非 PDF 跳过记录。"""
        return scan_source_directory(directory, recursive=recursive)

    def read_directory(self, directory: Path, *, recursive: bool = True) -> DirectoryParseResult:
        """解析目录中的 PDF 文件，行为保持与旧 parse_pdf_directory 一致。"""
        return parse_pdf_directory(directory, recursive=recursive)

    def read_pdf(
        self,
        path: Path,
        *,
        tenant_id: str = "default",
        document_id: str | None = None,
        document_version_id: str | None = None,
        source_id: str | None = None,
        source_uri: str | None = None,
        content_hash: str | None = None,
    ) -> ParsedPdf:
        """解析单个 PDF，并把可选身份参数传给旧解析函数。"""
        return parse_pdf(
            path,
            tenant_id=tenant_id,
            document_id=document_id,
            document_version_id=document_version_id,
            source_id=source_id,
            source_uri=source_uri,
            content_hash=content_hash,
        )
