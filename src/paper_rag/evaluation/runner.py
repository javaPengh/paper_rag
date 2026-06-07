"""评测运行器。

本模块负责把 golden dataset 接入现有本地 RAG 链路：先构建或复用评测索引，
再对每条 eval case 执行 retrieval 和 answer generation，并汇总检索命中指标。
answer、citation 和 refusal 指标用于衡量生成结果是否符合人工标注预期。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from paper_rag.embeddings import EmbeddingClient
from paper_rag.evaluation.answer_metrics import (
    AnswerCaseMetrics,
    AnswerMetricSummary,
    evaluate_answer_case,
    summarize_answer_metrics,
)
from paper_rag.evaluation.dataset import EvalCase, EvalDataset, load_eval_dataset
from paper_rag.evaluation.retrieval_metrics import (
    RetrievalCaseMetrics,
    RetrievalMetricSummary,
    evaluate_retrieval_case,
    summarize_retrieval_metrics,
)
from paper_rag.exceptions import EvaluationDatasetError, PaperRagError
from paper_rag.indexing import ChunkingConfig, LocalPaperIndex, build_index_from_directory
from paper_rag.retrieval import Retriever
from paper_rag.schemas import Answer, IndexBuildResult, SearchResult


class AnswerGenerator(Protocol):
    """评测运行器需要的最小答案生成接口。"""

    def generate(self, question: str, results: Sequence[SearchResult]) -> Answer:
        """根据一个问题和检索结果生成答案。"""
        ...


class EvalRunConfig(BaseModel):
    """一次评测运行的输入配置。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataset_path: Path = Field(description="JSONL golden dataset 的路径。")
    index_dir: Path = Field(description="评测运行使用或复用的本地索引目录。")
    source_dir: Path | None = Field(
        default=None,
        description="固定评测 PDF 所在目录；为空时从评测集文档映射中推导。",
    )
    project_root: Path | None = Field(
        default=None,
        description="解析评测集相对 source_path 和相对 index/source 路径时使用的根目录。",
    )
    tenant_id: str = Field(
        default="default",
        description="评测索引和检索使用的租户命名空间。",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        description="每条 eval case 检索的最大 chunk 数。",
    )
    chunk_size: int = Field(
        default=800,
        ge=1,
        description="构建评测索引时使用的 chunk token 窗口大小。",
    )
    chunk_overlap: int = Field(
        default=120,
        ge=0,
        description="构建评测索引时相邻 chunk 之间重复的 token 数。",
    )
    recursive: bool = Field(
        default=True,
        description="扫描评测 source_dir 时是否递归查找 PDF。",
    )


class EvalCaseRunResult(BaseModel):
    """单条 eval case 的实际运行结果。"""

    case_id: str = Field(description="对应 golden dataset 中的稳定 case ID。")
    question: str = Field(description="实际提交给 RAG 链路的问题。")
    answerable: bool = Field(description="人工标注中该问题是否应当可回答。")
    retrieved_chunk_ids: list[str] = Field(
        default_factory=list,
        description="retrieval 阶段返回的 chunk ID，按排名顺序保存。",
    )
    answer_text: str = Field(
        default="",
        description="答案生成器返回的最终答案文本。",
    )
    insufficient_evidence: bool = Field(
        default=False,
        description="答案生成器是否认为检索证据不足。",
    )
    citation_labels: list[str] = Field(
        default_factory=list,
        description="答案中使用的 citation 标签，便于后续 citation 指标复用。",
    )
    used_chunk_ids: list[str] = Field(
        default_factory=list,
        description="答案生成器实际选用为证据的 chunk ID。",
    )
    retrieval_metrics: RetrievalCaseMetrics | None = Field(
        default=None,
        description="该 case 的 retrieval hit@k 和 evidence 命中明细。",
    )
    answer_metrics: AnswerCaseMetrics | None = Field(
        default=None,
        description="该 case 的 answer、citation 和 refusal 指标明细。",
    )
    error: str | None = Field(
        default=None,
        description="该 case 在检索或答案生成阶段发生的可预期错误。",
    )

    @property
    def ok(self) -> bool:
        """返回该 case 是否完成了 retrieval 和 answer generation。"""
        return self.error is None


class EvalRunResult(BaseModel):
    """一次评测运行的整体结果。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataset: EvalDataset = Field(description="本次运行加载并校验后的评测集。")
    source_dir: Path = Field(description="本次运行实际用于构建或复用索引的 PDF 目录。")
    index_dir: Path = Field(description="本次运行实际使用的本地索引目录。")
    tenant_id: str = Field(description="本次运行使用的租户命名空间。")
    top_k: int = Field(description="本次运行对每条 case 使用的检索数量。")
    index_result: IndexBuildResult = Field(description="索引构建或复用步骤返回的摘要。")
    retrieval_summary: RetrievalMetricSummary = Field(
        description="本次运行的 retrieval hit@k 汇总。",
    )
    answer_summary: AnswerMetricSummary = Field(
        description="本次运行的 answer、citation 和 refusal 指标汇总。",
    )
    case_results: list[EvalCaseRunResult] = Field(
        default_factory=list,
        description="每条 eval case 的 retrieval 与 answer generation 运行结果。",
    )

    @property
    def case_count(self) -> int:
        """返回本次运行覆盖的 eval case 数量。"""
        return len(self.case_results)

    @property
    def error_count(self) -> int:
        """返回运行中发生检索或答案生成错误的 case 数量。"""
        return sum(1 for result in self.case_results if result.error is not None)


def run_evaluation(
    config: EvalRunConfig,
    *,
    embedding_client: EmbeddingClient,
    answer_generator: AnswerGenerator,
) -> EvalRunResult:
    """执行一次 MVP 评测运行。

    该函数会先加载评测集并构建或复用本地评测索引，再逐条执行检索和答案生成。
    指标计算保持分层：retrieval 指标看证据是否被找回，answer 指标看生成结果是否可用。
    """
    project_root = config.project_root or Path.cwd()
    dataset_path = _resolve_path(config.dataset_path, project_root)
    dataset = load_eval_dataset(dataset_path, project_root=project_root)
    source_dir = _resolve_source_dir(dataset, config.source_dir)
    index_dir = _resolve_path(config.index_dir, project_root)

    index_result = build_index_from_directory(
        source_dir,
        index_dir=index_dir,
        embedding_client=embedding_client,
        tenant_id=config.tenant_id,
        chunking_config=ChunkingConfig(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        ),
        recursive=config.recursive,
    )

    local_index = LocalPaperIndex(index_dir)
    retriever = Retriever(
        local_index=local_index,
        embedding_client=embedding_client,
        tenant_id=config.tenant_id,
    )
    case_results = [
        _run_case(
            case=case,
            dataset=dataset,
            config=config,
            retriever=retriever,
            answer_generator=answer_generator,
        )
        for case in dataset.cases
    ]
    retrieval_summary = summarize_retrieval_metrics(
        [
            case_result.retrieval_metrics
            for case_result in case_results
            if case_result.retrieval_metrics is not None
        ],
        top_k=config.top_k,
    )
    answer_summary = summarize_answer_metrics(
        [
            case_result.answer_metrics
            for case_result in case_results
            if case_result.answer_metrics is not None
        ]
    )

    return EvalRunResult(
        dataset=dataset,
        source_dir=source_dir,
        index_dir=index_dir,
        tenant_id=config.tenant_id,
        top_k=config.top_k,
        index_result=index_result,
        retrieval_summary=retrieval_summary,
        answer_summary=answer_summary,
        case_results=case_results,
    )


def format_eval_run_result(result: EvalRunResult) -> str:
    """把 MVP 评测运行结果渲染成 CLI 可读文本。"""
    lines = [
        "评测运行:",
        f"数据集: {result.dataset.path}",
        f"语料目录: {result.source_dir}",
        f"索引目录: {result.index_dir}",
        f"租户: {result.tenant_id}",
        f"Top-k: {result.top_k}",
        (
            "索引: "
            f"status={result.index_result.status.status} "
            f"documents={result.index_result.status.document_count} "
            f"chunks={result.index_result.status.chunk_count} "
            f"indexed_chunks={result.index_result.indexed_chunk_count}"
        ),
        f"样本数: {result.case_count}",
        f"样本错误数: {result.error_count}",
        (
            f"检索 hit@{result.retrieval_summary.top_k}: "
            f"{result.retrieval_summary.answerable_hit_count}/"
            f"{result.retrieval_summary.answerable_case_count} "
            f"({result.retrieval_summary.retrieval_hit_rate:.2%})"
        ),
        f"检索不可回答诊断样本数: {result.retrieval_summary.unanswerable_case_count}",
        (
            f"回答成功率: {result.answer_summary.answer_success_count}/"
            f"{result.answer_summary.answerable_case_count} "
            f"({result.answer_summary.answer_success_rate:.2%})"
        ),
        (
            f"拒答成功率: {result.answer_summary.refusal_success_count}/"
            f"{result.answer_summary.unanswerable_case_count} "
            f"({result.answer_summary.refusal_success_rate:.2%})"
        ),
        (
            f"引用命中率: {result.answer_summary.citation_hit_count}/"
            f"{result.answer_summary.citation_case_count} "
            f"({result.answer_summary.citation_hit_rate:.2%})"
        ),
        (
            f"答案词命中率: {result.answer_summary.answer_terms_hit_count}/"
            f"{result.answer_summary.answer_terms_case_count} "
            f"({result.answer_summary.answer_terms_hit_rate:.2%})"
        ),
        "",
        "未命中检索样本:",
    ]
    if result.retrieval_summary.missed_case_ids:
        case_results_by_id = {
            case_result.case_id: case_result for case_result in result.case_results
        }
        for case_id in result.retrieval_summary.missed_case_ids:
            case_result = case_results_by_id[case_id]
            reasons = (
                case_result.retrieval_metrics.missed_reasons
                if case_result.retrieval_metrics is not None
                else ["未生成 retrieval 指标"]
            )
            lines.append(f"- {case_id}: {'; '.join(reasons)}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("失败答案样本:")
    if result.answer_summary.failed_case_ids:
        case_results_by_id = {
            case_result.case_id: case_result for case_result in result.case_results
        }
        for case_id in result.answer_summary.failed_case_ids:
            case_result = case_results_by_id[case_id]
            reasons = (
                case_result.answer_metrics.failed_reasons
                if case_result.answer_metrics is not None
                else ["未生成 answer 指标"]
            )
            lines.append(f"- {case_id}: {'; '.join(reasons)}")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "样本结果:",
        ]
    )

    for case_result in result.case_results:
        state = "error" if case_result.error else "ok"
        retrieval_state = _format_retrieval_state(case_result.retrieval_metrics)
        answer_state = _format_answer_state(case_result.answer_metrics)
        lines.append(
            f"- {case_result.case_id} 状态={state} "
            f"retrieval={retrieval_state} "
            f"answer={answer_state} "
            f"answerable={case_result.answerable} "
            f"retrieved={len(case_result.retrieved_chunk_ids)} "
            f"used={len(case_result.used_chunk_ids)} "
            f"citations={len(case_result.citation_labels)} "
            f"insufficient={case_result.insufficient_evidence}"
        )
        if case_result.error:
            lines.append(f"  错误: {case_result.error}")
        else:
            preview = " ".join(case_result.answer_text.split())
            if len(preview) > 180:
                preview = preview[:177].rstrip() + "..."
            lines.append(f"  答案: {preview}")

    return "\n".join(lines)


def _run_case(
    *,
    case: EvalCase,
    dataset: EvalDataset,
    config: EvalRunConfig,
    retriever: Retriever,
    answer_generator: AnswerGenerator,
) -> EvalCaseRunResult:
    """执行单个 case，并把可预期错误保留为 case-level 结果。"""
    try:
        results = retriever.retrieve(case.question, top_k=config.top_k)
    except (PaperRagError, ValueError) as exc:
        retrieval_metrics = evaluate_retrieval_case(
            dataset=dataset,
            case=case,
            results=[],
            top_k=config.top_k,
        )
        answer_metrics = evaluate_answer_case(
            dataset=dataset,
            case=case,
            answer=None,
            results=[],
        )
        return EvalCaseRunResult(
            case_id=case.id,
            question=case.question,
            answerable=case.answerable,
            retrieval_metrics=retrieval_metrics,
            answer_metrics=answer_metrics,
            error=str(exc),
        )

    retrieval_metrics = evaluate_retrieval_case(
        dataset=dataset,
        case=case,
        results=results,
        top_k=config.top_k,
    )
    try:
        answer = answer_generator.generate(case.question, results)
    except (PaperRagError, ValueError) as exc:
        answer_metrics = evaluate_answer_case(
            dataset=dataset,
            case=case,
            answer=None,
            results=results,
        )
        return EvalCaseRunResult(
            case_id=case.id,
            question=case.question,
            answerable=case.answerable,
            retrieved_chunk_ids=[result.chunk.id for result in results],
            retrieval_metrics=retrieval_metrics,
            answer_metrics=answer_metrics,
            error=str(exc),
        )

    answer_metrics = evaluate_answer_case(
        dataset=dataset,
        case=case,
        answer=answer,
        results=results,
    )
    return EvalCaseRunResult(
        case_id=case.id,
        question=case.question,
        answerable=case.answerable,
        retrieved_chunk_ids=[result.chunk.id for result in results],
        answer_text=answer.answer,
        insufficient_evidence=answer.insufficient_evidence,
        citation_labels=[citation.label for citation in answer.citations],
        used_chunk_ids=answer.evidence_chunk_ids,
        retrieval_metrics=retrieval_metrics,
        answer_metrics=answer_metrics,
    )


def _format_retrieval_state(metrics: RetrievalCaseMetrics | None) -> str:
    """把单条 case 的 retrieval 状态压缩成 CLI 行内文本。"""
    if metrics is None:
        return "unknown"
    if metrics.hit_at_k is None:
        return metrics.expectation
    return "hit" if metrics.hit_at_k else "miss"


def _format_answer_state(metrics: AnswerCaseMetrics | None) -> str:
    """把单条 case 的 answer 指标状态压缩成 CLI 行内文本。"""
    if metrics is None:
        return "unknown"
    return "pass" if metrics.passed else "fail"


def _resolve_source_dir(dataset: EvalDataset, source_dir: Path | None) -> Path:
    """解析评测语料目录；未指定时从文档映射中的 source_path 推导。"""
    if source_dir is not None:
        return _resolve_path(source_dir, dataset.project_root)

    source_parents = {dataset.resolve_source_path(key).parent for key in dataset.documents}
    if len(source_parents) == 1:
        return next(iter(source_parents))

    parents = ", ".join(sorted(str(path) for path in source_parents))
    raise EvaluationDatasetError(
        "Eval dataset references multiple source directories; "
        f"please pass --source-dir explicitly. Directories: {parents}"
    )


def _resolve_path(path: Path, project_root: Path) -> Path:
    """把相对路径解析到 project_root 下，绝对路径保持不变。"""
    resolved = Path(path)
    return resolved if resolved.is_absolute() else project_root / resolved
