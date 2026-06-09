"""Paper RAG 学习项目的命令行界面。"""

from pathlib import Path
from typing import Annotated

import typer

from paper_rag import __version__
from paper_rag.components import ComponentRegistry, get_component_registry
from paper_rag.components.interfaces import Embedder, Generator
from paper_rag.config import load_settings
from paper_rag.domain import Document
from paper_rag.evaluation import (
    EvalRunConfig,
    format_eval_run_result,
    run_evaluation,
    write_eval_json_report,
)
from paper_rag.exceptions import PaperRagError
from paper_rag.indexing import LocalPaperIndex, build_index_from_directory
from paper_rag.logging import configure_logging
from paper_rag.qa import format_answer

app = typer.Typer(
    name="paper-rag",
    help="CLI MVP for asking citation-backed questions over local papers.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    """在 Typer 接收到全局版本标志时提前输出包版本。"""
    if value:
        typer.echo(f"paper-rag {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, help="Show the package version."),
    ] = False,
) -> None:
    """配置进程级 CLI 行为。"""
    _ = version
    settings = load_settings()
    configure_logging(settings.log_level)


@app.command()
def index(
    source_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, dir_okay=True, help="Directory of PDF files."),
    ],
    index_dir: Annotated[
        Path | None,
        typer.Option("--index-dir", help="Directory for the local index."),
    ] = None,
    embedding_model: Annotated[
        str | None,
        typer.Option("--embedding-model", help="Embedding model name."),
    ] = None,
    embedding_source: Annotated[
        str | None,
        typer.Option("--embedding-source", help="Embedding model source."),
    ] = None,
    tenant_id: Annotated[
        str,
        typer.Option("--tenant-id", help="Tenant/workspace ID for data isolation."),
    ] = "default",
    chunk_size: Annotated[
        int,
        typer.Option("--chunk-size", min=1, help="Maximum chunk size in tokens."),
    ] = 800,
    chunk_overlap: Annotated[
        int,
        typer.Option("--chunk-overlap", min=0, help="Chunk overlap in tokens."),
    ] = 120,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", min=1, help="Embedding batch size."),
    ] = 64,
    recursive: Annotated[
        bool,
        typer.Option("--recursive/--no-recursive", help="Scan PDF files recursively."),
    ] = True,
) -> None:
    """导入 PDF 目录并构建或更新本地索引。"""
    settings = load_settings()
    registry = get_component_registry(settings)
    target_index_dir = index_dir or settings.index_dir

    try:
        embedding_client = _make_embedding_client(
            embedding_source=embedding_source,
            embedding_model=embedding_model,
            registry=registry,
        )
        chunker = registry.create_chunker(
            parameters={
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            }
        )
        result = build_index_from_directory(
            source_dir,
            index_dir=target_index_dir,
            embedding_client=embedding_client,
            tenant_id=tenant_id,
            reader=registry.create_reader(parameters={"recursive": recursive}),
            chunker=chunker,
            batch_size=batch_size,
            recursive=recursive,
        )
    except (PaperRagError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"Index directory: {target_index_dir}")
    typer.echo(f"Tenant: {tenant_id}")
    typer.echo(f"Status: {result.status.status}")
    typer.echo(f"Documents indexed: {len(result.indexed_documents)}")
    typer.echo(f"Documents reused by source: {len(result.reused_source_documents)}")
    typer.echo(f"Documents reused by content: {len(result.reused_content_documents)}")
    typer.echo(f"Documents reindexed: {len(result.reindexed_documents)}")
    typer.echo(f"Chunks indexed: {result.indexed_chunk_count}")
    typer.echo(f"Total documents: {result.status.document_count}")
    typer.echo(f"Total chunks: {result.status.chunk_count}")

    for skipped_file in result.skipped_files:
        typer.echo(f"Skipped: {skipped_file.source_path} ({skipped_file.reason})")
    for warning in result.warnings:
        typer.echo(f"Warning: {warning.source_path} {warning.message}")
    for error in result.errors:
        typer.echo(f"Error: {error.source_path} {error.message}")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question to ask against the local index.")],
    index_dir: Annotated[
        Path | None,
        typer.Option("--index-dir", help="Directory containing the local index."),
    ] = None,
    embedding_model: Annotated[
        str | None,
        typer.Option("--embedding-model", help="Embedding model name."),
    ] = None,
    embedding_source: Annotated[
        str | None,
        typer.Option("--embedding-source", help="Embedding model source."),
    ] = None,
    tenant_id: Annotated[
        str,
        typer.Option("--tenant-id", help="Tenant/workspace ID for data isolation."),
    ] = "default",
    llm_model: Annotated[
        str | None,
        typer.Option("--chat-model", "--llm-model", help="Chat model name."),
    ] = None,
    chat_source: Annotated[
        str | None,
        typer.Option("--chat-source", help="Chat model source."),
    ] = None,
    top_k: Annotated[
        int | None,
        typer.Option("--top-k", min=1, help="Number of evidence chunks to retrieve."),
    ] = None,
    min_score: Annotated[
        float,
        typer.Option("--min-score", min=0.0, help="Minimum retrieval score for usable evidence."),
    ] = 0.05,
) -> None:
    """向现有本地索引提问。"""
    settings = load_settings()
    registry = get_component_registry(settings)
    target_index_dir = index_dir or settings.index_dir
    effective_top_k = top_k if top_k is not None else settings.top_k

    local_index = LocalPaperIndex(target_index_dir)
    try:
        embedding_client = _make_embedding_client(
            embedding_source=embedding_source,
            embedding_model=embedding_model,
            registry=registry,
        )
        retriever = registry.create_retriever(
            local_index=local_index,
            embedding_client=embedding_client,
            tenant_id=tenant_id,
            parameters={"top_k": effective_top_k},
        )
        results = retriever.retrieve(question, top_k=effective_top_k)
        answer = _make_answer_generator(
            chat_source=chat_source,
            llm_model=llm_model or settings.llm_model,
            min_score=min_score,
            registry=registry,
        ).generate(question, results)
    except (PaperRagError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(format_answer(answer))


@app.command("eval")
def eval_command(
    dataset_path: Annotated[
        Path,
        typer.Argument(
            help="JSONL golden dataset 路径。",
        ),
    ] = Path("eval/datasets/golden.jsonl"),
    source_dir: Annotated[
        Path | None,
        typer.Option(
            "--source-dir",
            file_okay=False,
            dir_okay=True,
            help="固定评测 PDF 所在目录。",
        ),
    ] = None,
    index_dir: Annotated[
        Path | None,
        typer.Option("--index-dir", help="本地评测索引目录。"),
    ] = None,
    tenant_id: Annotated[
        str,
        typer.Option("--tenant-id", help="评测隔离使用的租户或工作区 ID。"),
    ] = "eval",
    top_k: Annotated[
        int | None,
        typer.Option("--top-k", min=1, help="每条 case 检索的证据 chunk 数。"),
    ] = None,
    chunk_size: Annotated[
        int,
        typer.Option("--chunk-size", min=1, help="chunk 的最大 token 数。"),
    ] = 800,
    chunk_overlap: Annotated[
        int,
        typer.Option("--chunk-overlap", min=0, help="相邻 chunk 重叠的 token 数。"),
    ] = 120,
    embedding_model: Annotated[
        str | None,
        typer.Option("--embedding-model", help="embedding 模型名称。"),
    ] = None,
    embedding_source: Annotated[
        str | None,
        typer.Option("--embedding-source", help="embedding 模型来源。"),
    ] = None,
    llm_model: Annotated[
        str | None,
        typer.Option("--chat-model", "--llm-model", help="对话模型名称。"),
    ] = None,
    chat_source: Annotated[
        str | None,
        typer.Option("--chat-source", help="对话模型来源。"),
    ] = None,
    min_score: Annotated[
        float,
        typer.Option("--min-score", min=0.0, help="可用证据的最低检索分数。"),
    ] = 0.05,
    report_json: Annotated[
        Path | None,
        typer.Option("--report-json", help="可选的 JSON 评测报告输出路径。"),
    ] = None,
) -> None:
    """运行 MVP 评测集，执行本地索引、检索和答案生成。"""
    settings = load_settings()
    registry = get_component_registry(settings)
    target_index_dir = index_dir or Path(".paper_rag/eval_index")
    effective_top_k = top_k if top_k is not None else settings.top_k

    try:
        rag_config = registry.build_pipeline_config(
            embedding_source=embedding_source,
            embedding_model=embedding_model,
            chat_source=chat_source,
            llm_model=llm_model or settings.llm_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k=effective_top_k,
            min_score=min_score,
        )
        embedding_client = _make_embedding_client(
            embedding_source=embedding_source,
            embedding_model=embedding_model,
            registry=registry,
        )
        answer_generator = _make_answer_generator(
            chat_source=chat_source,
            llm_model=llm_model or settings.llm_model,
            min_score=min_score,
            registry=registry,
        )
        result = run_evaluation(
            EvalRunConfig(
                dataset_path=dataset_path,
                source_dir=source_dir,
                index_dir=target_index_dir,
                tenant_id=tenant_id,
                top_k=effective_top_k,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                rag_config=rag_config,
            ),
            embedding_client=embedding_client,
            answer_generator=answer_generator,
        )
    except (PaperRagError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(format_eval_run_result(result))
    if report_json is not None:
        try:
            written_path = write_eval_json_report(result, report_json)
        except OSError as exc:
            raise typer.BadParameter(f"JSON report 写入失败: {exc}") from exc
        typer.echo(f"JSON report: {written_path}")


@app.command("list-docs")
def list_docs(
    index_dir: Annotated[
        Path | None,
        typer.Option("--index-dir", help="Directory containing the local index."),
    ] = None,
    tenant_id: Annotated[
        str,
        typer.Option("--tenant-id", help="Tenant/workspace ID for data isolation."),
    ] = "default",
) -> None:
    """列出已索引的文档。"""
    settings = load_settings()
    local_index = LocalPaperIndex(index_dir or settings.index_dir)
    status = local_index.store.load_status()
    documents = local_index.store.list_documents(tenant_id=tenant_id)

    if status is None and not documents:
        typer.echo("No local index found.")
        return

    if status is not None:
        typer.echo(
            f"Status: {status.status} | tenant={status.tenant_id} | "
            f"documents={status.document_count} | "
            f"chunks={status.chunk_count} | embedding_model={status.embedding_model}"
        )
    for document in documents:
        current_version = (
            local_index.store.get_version(document.current_version_id)
            if document.current_version_id
            else None
        )
        chunk_count = local_index.store.count_chunks(
            document_id=document.id,
            tenant_id=tenant_id,
        )
        typer.echo(
            f"- {document.file_name} tenant={document.tenant_id} id={document.id} "
            f"version={document.current_version_id} pages={document.page_count} "
            f"chunks={chunk_count} "
            f"content_hash={(current_version.content_hash if current_version else '')} "
            f"source_uri={document.source_uri}"
        )


@app.command("show-chunks")
def show_chunks(
    document_ref: Annotated[
        str | None,
        typer.Argument(help="Document ID prefix or file name. Omit to show chunks from all docs."),
    ] = None,
    index_dir: Annotated[
        Path | None,
        typer.Option("--index-dir", help="Directory containing the local index."),
    ] = None,
    tenant_id: Annotated[
        str,
        typer.Option("--tenant-id", help="Tenant/workspace ID for data isolation."),
    ] = "default",
    limit: Annotated[int, typer.Option("--limit", min=1, help="Maximum chunks to show.")] = 5,
) -> None:
    """显示已索引文档的 chunk 调试输出。"""
    settings = load_settings()
    local_index = LocalPaperIndex(index_dir or settings.index_dir)
    document = _find_document(local_index.store.list_documents(tenant_id=tenant_id), document_ref)
    if document_ref is not None and document is None:
        raise typer.BadParameter(f"No indexed document matched: {document_ref}")

    chunks = local_index.store.list_chunks(
        tenant_id=tenant_id,
        document_id=document.id if document else None,
        limit=limit,
    )
    if not chunks:
        typer.echo("No chunks found.")
        return

    indexed_documents = local_index.store.list_documents(tenant_id=tenant_id)
    documents_by_id = {item.id: item for item in indexed_documents}
    for chunk in chunks:
        chunk_document = documents_by_id.get(chunk.document_id)
        file_name = chunk_document.file_name if chunk_document else chunk.document_id
        typer.echo(
            f"- {chunk.id} {file_name} pp.{chunk.page_start}-{chunk.page_end} "
            f"version={chunk.document_version_id} chunk_index={chunk.chunk_index} "
            f"tokens={chunk.token_count}"
        )
        typer.echo(f"  {chunk.text[:240].replace(chr(10), ' ')}")


@app.command()
def serve(
    host: Annotated[
        str,
        typer.Option("--host", help="Host interface for the local inspector server."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65535, help="Port for the local inspector server."),
    ] = 8000,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable auto-reload for local development."),
    ] = False,
) -> None:
    """运行用于本地验证的 FastAPI Web Inspector。"""
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise typer.BadParameter(
            'Uvicorn is required for the Web Inspector. Install with pip install -e ".[dev]".'
        ) from exc

    uvicorn.run(
        "paper_rag.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


def _make_embedding_client(
    *,
    embedding_source: str | None,
    embedding_model: str | None,
    registry: ComponentRegistry | None = None,
) -> Embedder:
    """根据 CLI 标志和环境设置创建 embedding 客户端。"""
    settings = load_settings()
    active_registry = registry or get_component_registry(settings)
    source_name = embedding_source or settings.embedding_source
    model_name = embedding_model or settings.embedding_model
    component_id = active_registry.resolve_embedder_id(
        source=source_name,
        model_name=model_name,
    )
    return active_registry.create_embedder(
        component_id,
        source=source_name,
        model_name=model_name,
    )


def _make_answer_generator(
    *,
    chat_source: str | None,
    llm_model: str | None,
    min_score: float,
    registry: ComponentRegistry | None = None,
) -> Generator:
    """根据 CLI 标志和环境设置创建答案生成器。"""
    settings = load_settings()
    active_registry = registry or get_component_registry(settings)
    source_name = chat_source or settings.chat_source
    component_id = active_registry.resolve_generator_id(source=source_name)
    return active_registry.create_generator(
        component_id,
        source=source_name,
        model_name=llm_model,
        parameters={"min_score": min_score},
    )


def _find_document(documents: list[Document], document_ref: str | None) -> Document | None:
    """按 ID 前缀或不区分大小写的文件名解析 CLI 文档引用。"""
    if document_ref is None:
        return None
    lowered_ref = document_ref.lower()
    for document in documents:
        if document.id.startswith(document_ref) or lowered_ref in document.file_name.lower():
            return document
    return None
