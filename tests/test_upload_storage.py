from pathlib import Path
from uuid import uuid4

import pytest

from paper_rag.exceptions import DocumentUploadError
from paper_rag.storage import LocalUploadStorage
from paper_rag.storage.uploads import safe_pdf_file_name

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def test_local_upload_storage_saves_pdf_under_tenant_root() -> None:
    root_dir = Path(".paper_rag") / "test_uploads" / uuid4().hex
    storage = LocalUploadStorage(root_dir)

    stored = storage.save_pdf(
        tenant_id="tenant-a",
        file_name=r"..\unsafe/My Paper?.PDF",
        content=PDF_BYTES,
        content_type="application/pdf",
    )

    assert stored.tenant_id == "tenant-a"
    assert stored.storage_tenant == "tenant-a"
    assert stored.safe_file_name == "My_Paper.pdf"
    assert stored.stored_path.exists()
    assert stored.stored_path.read_bytes() == PDF_BYTES
    assert stored.source_uri == str(stored.stored_path)
    assert stored.stored_path.is_relative_to(root_dir.resolve())
    assert stored.stored_path.parent == (root_dir / "tenant-a").resolve()
    assert stored.stored_path.name.startswith(stored.content_hash[:16])


def test_local_upload_storage_sanitizes_tenant_path_segment() -> None:
    root_dir = Path(".paper_rag") / "test_uploads" / uuid4().hex
    storage = LocalUploadStorage(root_dir)

    stored = storage.save_pdf(
        tenant_id="../tenant b",
        file_name="paper.pdf",
        content=PDF_BYTES,
    )

    assert stored.storage_tenant == "tenant_b"
    assert stored.stored_path.is_relative_to(root_dir.resolve())
    assert stored.stored_path.parent == (root_dir / "tenant_b").resolve()


def test_local_upload_storage_rejects_non_pdf_extension() -> None:
    storage = LocalUploadStorage(Path(".paper_rag") / "test_uploads" / uuid4().hex)

    with pytest.raises(DocumentUploadError, match="Only PDF"):
        storage.save_pdf(
            tenant_id="default",
            file_name="notes.txt",
            content=PDF_BYTES,
        )


def test_local_upload_storage_rejects_non_pdf_header() -> None:
    storage = LocalUploadStorage(Path(".paper_rag") / "test_uploads" / uuid4().hex)

    with pytest.raises(DocumentUploadError, match="does not look like a PDF"):
        storage.save_pdf(
            tenant_id="default",
            file_name="paper.pdf",
            content=b"not a pdf",
            content_type="application/pdf",
        )


def test_local_upload_storage_rejects_empty_upload() -> None:
    storage = LocalUploadStorage(Path(".paper_rag") / "test_uploads" / uuid4().hex)

    with pytest.raises(DocumentUploadError, match="empty"):
        storage.save_pdf(
            tenant_id="default",
            file_name="paper.pdf",
            content=b"",
            content_type="application/pdf",
        )


def test_local_upload_storage_rejects_uploads_over_size_limit() -> None:
    storage = LocalUploadStorage(
        Path(".paper_rag") / "test_uploads" / uuid4().hex,
        max_size_bytes=len(PDF_BYTES) - 1,
    )

    with pytest.raises(DocumentUploadError, match="too large"):
        storage.save_pdf(
            tenant_id="default",
            file_name="paper.pdf",
            content=PDF_BYTES,
            content_type="application/pdf",
        )


def test_local_upload_storage_rejects_unexpected_content_type() -> None:
    storage = LocalUploadStorage(Path(".paper_rag") / "test_uploads" / uuid4().hex)

    with pytest.raises(DocumentUploadError, match="Unsupported PDF content type"):
        storage.save_pdf(
            tenant_id="default",
            file_name="paper.pdf",
            content=PDF_BYTES,
            content_type="text/plain",
        )


def test_safe_pdf_file_name_rejects_pathless_empty_names() -> None:
    with pytest.raises(DocumentUploadError, match="file name cannot be empty"):
        safe_pdf_file_name("../")
