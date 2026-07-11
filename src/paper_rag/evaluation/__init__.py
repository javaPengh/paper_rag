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
    ANSWER_EXPECTATIONS,
    EvalCase,
    EvalDataset,
    EvalDocument,
    EvalEvidence,
    EvalExpectation,
    load_eval_dataset,
)
from paper_rag.evaluation.judge import (
    JudgeCaseMetrics,
    JudgeMetricSummary,
    JudgeRequirementResult,
    evaluate_judge_case,
    parse_judge_response,
    summarize_judge_metrics,
)
from paper_rag.evaluation.judge_report import (
    JudgeOnlyConfig,
    JudgeOnlyResult,
    run_judge_only,
    write_judge_only_report,
)
from paper_rag.prompts.judge import JUDGE_PROMPT_VERSION, build_judge_system_prompt
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
    EvalJudgeConfig,
    EvalRunConfig,
    EvalRunResult,
    format_eval_run_result,
    run_evaluation,
)

__all__ = [
    "ANSWER_EXPECTATIONS",
    "AnswerCaseMetrics",
    "AnswerMetricSummary",
    "CitationEvidenceMatch",
    "EvalCase",
    "EvalCaseRunResult",
    "EvalDataset",
    "EvalDocument",
    "EvalEvidence",
    "EvalExpectation",
    "EvalRunConfig",
    "EvalRunResult",
    "RetrievalCaseMetrics",
    "RetrievalEvidenceMatch",
    "RetrievalMetricSummary",
    "build_eval_json_report",
    "evaluate_answer_case",
    "evaluate_retrieval_case",
    "format_eval_run_result",
    "JUDGE_PROMPT_VERSION",
    "JudgeCaseMetrics",
    "JudgeMetricSummary",
    "JudgeRequirementResult",
    "write_judge_only_report",
    "run_judge_only",
    "JudgeOnlyResult",
    "JudgeOnlyConfig",
    "EvalJudgeConfig",
    "build_judge_system_prompt",
    "evaluate_judge_case",
    "parse_judge_response",
    "summarize_judge_metrics",
    "load_eval_dataset",
    "run_evaluation",
    "summarize_answer_metrics",
    "summarize_retrieval_metrics",
    "write_eval_json_report",
]
