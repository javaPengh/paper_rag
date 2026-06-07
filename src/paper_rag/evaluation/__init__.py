"""评测集相关模型与解析入口。

该包向外暴露 golden dataset 的结构化模型和加载函数，供后续 eval CLI、
指标计算和报告输出复用同一套数据入口。
"""

from paper_rag.evaluation.answer_metrics import (
    AnswerCaseMetrics,
    AnswerMetricSummary,
    CitationEvidenceMatch,
    evaluate_answer_case,
    summarize_answer_metrics,
)
from paper_rag.evaluation.dataset import (
    EvalCase,
    EvalDataset,
    EvalDocument,
    EvalEvidence,
    load_eval_dataset,
)
from paper_rag.evaluation.reporting import build_eval_json_report, write_eval_json_report
from paper_rag.evaluation.retrieval_metrics import (
    RetrievalCaseMetrics,
    RetrievalEvidenceMatch,
    RetrievalMetricSummary,
    evaluate_retrieval_case,
    summarize_retrieval_metrics,
)
from paper_rag.evaluation.runner import (
    EvalCaseRunResult,
    EvalRunConfig,
    EvalRunResult,
    format_eval_run_result,
    run_evaluation,
)

__all__ = [
    "AnswerCaseMetrics",
    "AnswerMetricSummary",
    "CitationEvidenceMatch",
    "EvalCase",
    "EvalCaseRunResult",
    "EvalDataset",
    "EvalDocument",
    "EvalEvidence",
    "EvalRunConfig",
    "EvalRunResult",
    "RetrievalCaseMetrics",
    "RetrievalEvidenceMatch",
    "RetrievalMetricSummary",
    "build_eval_json_report",
    "evaluate_answer_case",
    "evaluate_retrieval_case",
    "format_eval_run_result",
    "load_eval_dataset",
    "run_evaluation",
    "summarize_answer_metrics",
    "summarize_retrieval_metrics",
    "write_eval_json_report",
]
