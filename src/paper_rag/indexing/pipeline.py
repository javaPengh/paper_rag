"""Directory-to-index pipeline."""

from __future__ import annotations

from pathlib import Path

from paper_rag.documents.parser import (
    new_document_id,
    parse_pdf,
    scan_source_directory,
)
from paper_rag.embeddings import EmbeddingClient
from paper_rag.indexing.chunking import ChunkingConfig, chunk_pages
from paper_rag.indexing.local_index import LocalPaperIndex
from paper_rag.schemas import (
    Chunk,
    Document,
    DocumentVersion,
    IndexBuildResult,
    IndexedSource,
    IndexStatus,
    ParseIssue,
    utc_now,
)


def build_index_from_directory(
    source_dir: Path,
    *,
    index_dir: Path,
    embedding_client: EmbeddingClient,
    tenant_id: str = "default",
    chunking_config: ChunkingConfig | None = None,
    batch_size: int = 64,
    recursive: bool = True,
) -> IndexBuildResult:
    """Parse changed PDFs, embed their chunks, and persist them in the local index."""
    local_index = LocalPaperIndex(index_dir)
    pdf_paths, skipped_files = scan_source_directory(source_dir, recursive=recursive)

    indexed_documents: list[Document] = []
    reindexed_documents: list[Document] = []
    reused_source_documents: list[Document] = []
    reused_content_documents: list[Document] = []
    versions_to_index: list[DocumentVersion] = []
    chunks_to_index: list[Chunk] = []
    warnings: list[ParseIssue] = []
    errors: list[ParseIssue] = []

    for pdf_path in pdf_paths:
        resolved_pdf_path = pdf_path.resolve()
        source_uri = str(resolved_pdf_path)
        try:
            existing_source_document = local_index.store.get_document_by_source(
                tenant_id=tenant_id,
                source_uri=source_uri,
            )

            if existing_source_document is not None:
                parsed_pdf = parse_pdf(
                    resolved_pdf_path,
                    tenant_id=tenant_id,
                    document_id=existing_source_document.id,
                    source_uri=source_uri,
                )
                content_hash = parsed_pdf.version.content_hash
                current_version = _current_version(local_index, existing_source_document)
                if (
                    current_version is not None
                    and current_version.content_hash == content_hash
                    and local_index.store.count_chunks(
                        document_version_id=current_version.id,
                        tenant_id=tenant_id,
                    )
                    > 0
                ):
                    reused_source_documents.append(existing_source_document)
                    warnings.extend(parsed_pdf.warnings)
                    continue

                if existing_source_document.current_version_id is not None:
                    local_index.delete_document_version_ids(
                        [existing_source_document.current_version_id]
                    )

                reindexed_documents.append(parsed_pdf.document)
            else:
                document_id = new_document_id()
                parsed_pdf = parse_pdf(
                    resolved_pdf_path,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    source_uri=source_uri,
                )
                content_hash = parsed_pdf.version.content_hash
                existing_content_version = local_index.store.get_version_by_content_hash(
                    tenant_id=tenant_id,
                    content_hash=content_hash,
                )
                if (
                    existing_content_version is not None
                    and local_index.store.count_chunks(
                        document_version_id=existing_content_version.id,
                        tenant_id=tenant_id,
                    )
                    > 0
                ):
                    existing_content_document = local_index.store.get_document(
                        existing_content_version.document_id
                    )
                    if existing_content_document is not None:
                        reused_content_documents.append(existing_content_document)
                        warnings.extend(parsed_pdf.warnings)
                        continue

                indexed_documents.append(parsed_pdf.document)

            document_chunks = chunk_pages(
                parsed_pdf.pages,
                config=chunking_config or ChunkingConfig(),
            )
        except Exception as exc:
            errors.append(ParseIssue(source_path=resolved_pdf_path, message=str(exc)))
            continue

        versions_to_index.append(parsed_pdf.version)
        chunks_to_index.extend(_stamp_chunk_tenant(document_chunks, tenant_id))
        warnings.extend(parsed_pdf.warnings)

    embeddings = _embed_chunks(chunks_to_index, embedding_client, batch_size=batch_size)
    documents_to_upsert = indexed_documents + reindexed_documents
    if documents_to_upsert or versions_to_index or chunks_to_index:
        local_index.upsert(
            documents_to_upsert,
            chunks_to_index,
            embeddings,
            versions=versions_to_index,
        )

    status = _write_status(
        local_index=local_index,
        embedding_model=embedding_client.model_name,
        tenant_id=tenant_id,
        errors=errors,
    )
    reused_documents = reused_source_documents + reused_content_documents
    return IndexBuildResult(
        status=status,
        indexed_documents=indexed_documents,
        reused_documents=reused_documents,
        reused_source_documents=reused_source_documents,
        reused_content_documents=reused_content_documents,
        reindexed_documents=reindexed_documents,
        indexed_chunk_count=len(chunks_to_index),
        skipped_files=skipped_files,
        errors=errors,
        warnings=warnings,
    )


def _current_version(
    local_index: LocalPaperIndex,
    document: Document,
) -> DocumentVersion | None:
    if document.current_version_id is None:
        return None
    return local_index.store.get_version(document.current_version_id)


def _stamp_chunk_tenant(chunks: list[Chunk], tenant_id: str) -> list[Chunk]:
    stamped: list[Chunk] = []
    for chunk in chunks:
        metadata = dict(chunk.metadata)
        metadata["tenant_id"] = tenant_id
        stamped.append(chunk.model_copy(update={"metadata": metadata}))
    return stamped


def _embed_chunks(
    chunks: list[Chunk],
    embedding_client: EmbeddingClient,
    *,
    batch_size: int,
) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings.extend(embedding_client.embed_texts([chunk.text for chunk in batch]))
    return embeddings


def _write_status(
    *,
    local_index: LocalPaperIndex,
    embedding_model: str,
    tenant_id: str,
    errors: list[ParseIssue],
) -> IndexStatus:
    documents = local_index.store.list_documents(tenant_id=tenant_id)
    chunk_count = local_index.store.count_chunks(tenant_id=tenant_id)
    now = utc_now()
    status_value = "ready" if documents else "empty"
    if errors and not documents:
        status_value = "error"

    existing_status = local_index.store.load_status()
    built_at = existing_status.built_at if existing_status and existing_status.built_at else now
    sources: list[IndexedSource] = []
    for document in documents:
        if document.current_version_id is None:
            continue
        version = local_index.store.get_version(document.current_version_id)
        if version is None:
            continue
        sources.append(
            IndexedSource(
                tenant_id=document.tenant_id,
                document_id=document.id,
                document_version_id=version.id,
                source_uri=version.source_uri,
                file_name=document.file_name,
                content_hash=version.content_hash,
            )
        )

    status = IndexStatus(
        status=status_value,
        tenant_id=tenant_id,
        index_dir=local_index.index_dir,
        document_count=len(documents),
        chunk_count=chunk_count,
        embedding_model=embedding_model,
        built_at=built_at,
        updated_at=now,
        sources=sources,
        errors=[error.message for error in errors],
    )
    local_index.store.write_status(status)
    return status
