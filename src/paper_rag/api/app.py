"""FastAPI application for the local Paper RAG Web Inspector."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from paper_rag import __version__
from paper_rag.api.schemas import (
    AskRequest,
    AskResponse,
    ChunkResponse,
    CitationResponse,
    DocumentSummaryResponse,
    ErrorDetailResponse,
    EvidenceResponse,
    FileIssueResponse,
    HealthResponse,
    IndexingSummaryResponse,
    IndexStatusResponse,
    StoredUploadResponse,
    UploadIndexResponse,
)
from paper_rag.config import load_settings
from paper_rag.embeddings import HashEmbeddingClient, OpenAIEmbeddingClient
from paper_rag.exceptions import DocumentUploadError, PaperRagError
from paper_rag.indexing import ChunkingConfig, LocalPaperIndex, build_index_from_directory
from paper_rag.qa import ExtractiveAnswerGenerator, OpenAIAnswerGenerator
from paper_rag.qa.answering import OpenAIChatClient
from paper_rag.retrieval import Retriever
from paper_rag.schemas import (
    Chunk,
    Citation,
    Document,
    IndexBuildResult,
    ParseIssue,
    SearchResult,
    SkippedFile,
)
from paper_rag.storage import LocalUploadStorage, StoredUpload


def create_app() -> FastAPI:
    """Create the FastAPI app used by the local Web Inspector."""
    app = FastAPI(
        title="Paper RAG Inspector",
        version=__version__,
        description="Development inspector for local Paper RAG indexes.",
    )

    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index_page() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.get("/api/index/status", response_model=IndexStatusResponse)
    def index_status(
        tenant_id: Annotated[str, Query(description="Tenant/workspace ID.")] = "default",
        index_dir: Annotated[
            str | None,
            Query(description="Local index directory. Defaults to PAPER_RAG_INDEX_DIR."),
        ] = None,
    ) -> IndexStatusResponse:
        local_index = _make_local_index(index_dir)
        status = local_index.store.load_status()
        return _index_status_response(local_index, tenant_id=tenant_id, status=status)

    @app.get("/api/documents", response_model=list[DocumentSummaryResponse])
    def list_documents(
        tenant_id: Annotated[str, Query(description="Tenant/workspace ID.")] = "default",
        index_dir: Annotated[
            str | None,
            Query(description="Local index directory. Defaults to PAPER_RAG_INDEX_DIR."),
        ] = None,
    ) -> list[DocumentSummaryResponse]:
        local_index = _make_local_index(index_dir)
        documents = local_index.store.list_documents(tenant_id=tenant_id)
        return [_document_summary(local_index, document) for document in documents]

    @app.get("/api/documents/{document_id}/chunks", response_model=list[ChunkResponse])
    def list_chunks(
        document_id: str,
        tenant_id: Annotated[str, Query(description="Tenant/workspace ID.")] = "default",
        index_dir: Annotated[
            str | None,
            Query(description="Local index directory. Defaults to PAPER_RAG_INDEX_DIR."),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> list[ChunkResponse]:
        local_index = _make_local_index(index_dir)
        document = local_index.store.get_document(document_id)
        if document is None or document.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Document not found for tenant.")

        chunks = local_index.store.list_chunks(
            tenant_id=tenant_id,
            document_id=document_id,
            limit=limit,
        )
        return [_chunk_response(chunk, document) for chunk in chunks]

    @app.post("/api/documents/upload", response_model=UploadIndexResponse)
    async def upload_document(
        file: Annotated[UploadFile, File(description="Single PDF file to store and index.")],
        tenant_id: Annotated[
            str,
            Form(description="Tenant/workspace ID for data isolation."),
        ] = "default",
        index_dir: Annotated[
            str | None,
            Form(description="Local index directory. Defaults to PAPER_RAG_INDEX_DIR."),
        ] = None,
        local: Annotated[
            bool,
            Form(description="Use deterministic local hash embeddings for offline checks."),
        ] = False,
        chunk_size: Annotated[
            int,
            Form(ge=1, description="Maximum chunk size in tokens."),
        ] = 800,
        chunk_overlap: Annotated[
            int,
            Form(ge=0, description="Chunk overlap in tokens."),
        ] = 120,
        embedding_model: Annotated[
            str | None,
            Form(description="Embedding model name."),
        ] = None,
    ) -> UploadIndexResponse:
        settings = load_settings()
        file_name = file.filename or ""
        content = await file.read()
        try:
            stored_upload = LocalUploadStorage(
                settings.upload_dir,
                max_size_bytes=settings.upload_max_bytes,
            ).save_pdf(
                tenant_id=tenant_id,
                file_name=file_name,
                content=content,
                content_type=file.content_type,
            )
            indexing_result = build_index_from_directory(
                stored_upload.stored_path.parent,
                index_dir=Path(index_dir) if index_dir else settings.index_dir,
                embedding_client=_make_embedding_client(
                    embedding_model=embedding_model,
                    local=local,
                ),
                tenant_id=tenant_id,
                chunking_config=ChunkingConfig(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                ),
                recursive=False,
            )
        except DocumentUploadError as exc:
            raise _bad_request(stage="upload", exc=exc) from exc
        except (PaperRagError, ValueError) as exc:
            raise _bad_request(stage="indexing", exc=exc) from exc

        return UploadIndexResponse(
            upload=_stored_upload_response(stored_upload),
            index=_indexing_summary_response(indexing_result),
            status=_index_status_response(
                LocalPaperIndex(Path(index_dir) if index_dir else settings.index_dir),
                tenant_id=tenant_id,
                status=indexing_result.status,
            ),
        )

    @app.post("/api/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        settings = load_settings()
        local_index = LocalPaperIndex(request.index_dir or settings.index_dir)
        status = local_index.store.load_status()
        local_mode = request.local
        if status and status.embedding_model and status.embedding_model.startswith("hash-"):
            local_mode = True

        embedding_client = _make_embedding_client(
            embedding_model=request.embedding_model or (status.embedding_model if status else None),
            local=local_mode,
        )
        retriever = Retriever(
            local_index=local_index,
            embedding_client=embedding_client,
            tenant_id=request.tenant_id,
        )
        try:
            results = retriever.retrieve(
                request.question,
                top_k=request.top_k if request.top_k is not None else settings.top_k,
            )
            answer = _make_answer_generator(
                llm_model=request.llm_model or settings.llm_model,
                local=local_mode,
                min_score=request.min_score,
            ).generate(request.question, results)
        except PaperRagError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        used_chunk_ids = set(answer.evidence_chunk_ids)
        return AskResponse(
            question=answer.question,
            answer=answer.answer,
            insufficient_evidence=answer.insufficient_evidence,
            model_name=answer.model_name,
            citations=[_citation_response(citation) for citation in answer.citations],
            evidence=[
                _evidence_response(result, used=result.chunk.id in used_chunk_ids)
                for result in results
            ],
            context=answer.context,
        )

    return app


def _make_local_index(index_dir: str | None) -> LocalPaperIndex:
    settings = load_settings()
    return LocalPaperIndex(Path(index_dir) if index_dir else settings.index_dir)


def _bad_request(*, stage: str, exc: Exception) -> HTTPException:
    detail = ErrorDetailResponse(
        stage=stage,
        error_type=exc.__class__.__name__,
        message=str(exc),
    )
    return HTTPException(status_code=400, detail=detail.model_dump())


def _index_status_response(
    local_index: LocalPaperIndex,
    *,
    tenant_id: str,
    status,
) -> IndexStatusResponse:
    if status is None:
        return IndexStatusResponse(
            status="missing",
            tenant_id=tenant_id,
            index_dir=local_index.index_dir,
            document_count=len(local_index.store.list_documents(tenant_id=tenant_id)),
            chunk_count=local_index.store.count_chunks(tenant_id=tenant_id),
        )

    return IndexStatusResponse(
        status=status.status,
        tenant_id=tenant_id,
        index_dir=local_index.index_dir,
        document_count=len(local_index.store.list_documents(tenant_id=tenant_id)),
        chunk_count=local_index.store.count_chunks(tenant_id=tenant_id),
        embedding_model=status.embedding_model,
        built_at=status.built_at,
        updated_at=status.updated_at,
        errors=status.errors,
    )


def _make_embedding_client(*, embedding_model: str | None, local: bool):
    settings = load_settings()
    model_name = embedding_model or ("hash-embedding-v1" if local else settings.embedding_model)
    if local or model_name.startswith("hash-"):
        return HashEmbeddingClient(model_name=model_name)
    return OpenAIEmbeddingClient(
        model_name=model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def _make_answer_generator(*, llm_model: str, local: bool, min_score: float):
    settings = load_settings()
    if local:
        return ExtractiveAnswerGenerator(min_score=min_score)
    return OpenAIAnswerGenerator(
        chat_client=OpenAIChatClient(
            model_name=llm_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        ),
        min_score=min_score,
    )


def _document_summary(
    local_index: LocalPaperIndex,
    document: Document,
) -> DocumentSummaryResponse:
    current_version = (
        local_index.store.get_version(document.current_version_id)
        if document.current_version_id
        else None
    )
    return DocumentSummaryResponse(
        id=document.id,
        tenant_id=document.tenant_id,
        source_id=document.source_id,
        source_uri=document.source_uri,
        file_name=document.file_name,
        title=document.title,
        page_count=document.page_count,
        current_version_id=document.current_version_id,
        content_hash=current_version.content_hash if current_version else None,
        chunk_count=local_index.store.count_chunks(
            tenant_id=document.tenant_id,
            document_id=document.id,
        ),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _chunk_response(chunk: Chunk, document: Document | None) -> ChunkResponse:
    return ChunkResponse(
        id=chunk.id,
        document_id=chunk.document_id,
        document_version_id=chunk.document_version_id,
        file_name=document.file_name if document is not None else None,
        text=chunk.text,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        chunk_index=chunk.chunk_index,
        token_count=chunk.token_count,
    )


def _stored_upload_response(upload: StoredUpload) -> StoredUploadResponse:
    return StoredUploadResponse(
        tenant_id=upload.tenant_id,
        storage_tenant=upload.storage_tenant,
        original_file_name=upload.original_file_name,
        safe_file_name=upload.safe_file_name,
        stored_path=upload.stored_path,
        source_uri=upload.source_uri,
        content_hash=upload.content_hash,
        size_bytes=upload.size_bytes,
    )


def _indexing_summary_response(result: IndexBuildResult) -> IndexingSummaryResponse:
    return IndexingSummaryResponse(
        indexed=len(result.indexed_documents),
        reused_source=len(result.reused_source_documents),
        reused_content=len(result.reused_content_documents),
        reindexed=len(result.reindexed_documents),
        indexed_chunks=result.indexed_chunk_count,
        total_documents=result.status.document_count,
        total_chunks=result.status.chunk_count,
        skipped_files=[_skipped_file_response(item) for item in result.skipped_files],
        warnings=[_parse_issue_response(item) for item in result.warnings],
        errors=[_parse_issue_response(item) for item in result.errors],
    )


def _skipped_file_response(skipped_file: SkippedFile) -> FileIssueResponse:
    return FileIssueResponse(
        source_path=skipped_file.source_path,
        reason=skipped_file.reason,
    )


def _parse_issue_response(issue: ParseIssue) -> FileIssueResponse:
    return FileIssueResponse(
        source_path=issue.source_path,
        message=issue.message,
        page_number=issue.page_number,
    )


def _citation_response(citation: Citation) -> CitationResponse:
    return CitationResponse(
        label=citation.label,
        document_id=citation.document_id,
        document_version_id=citation.document_version_id,
        chunk_id=citation.chunk_id,
        file_name=citation.file_name,
        page_start=citation.page_start,
        page_end=citation.page_end,
        snippet=citation.snippet,
    )


def _evidence_response(result: SearchResult, *, used: bool) -> EvidenceResponse:
    return EvidenceResponse(
        chunk=_chunk_response(result.chunk, result.document),
        score=result.score,
        distance=result.distance,
        used=used,
    )


app = create_app()
