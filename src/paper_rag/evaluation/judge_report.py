"""基于已有 JSON report 的 judge-only 评估工具。

本模块不重新执行检索或答案生成，只读取历史 report 中的答案文本，结合 golden dataset
中的 `evaluation_requirements` 重新运行 LLM judge，便于隔离“答案是否变化”和“judge
如何判定”这两个变量。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from paper_rag.evaluation.dataset import EvalCase, load_eval_dataset
from paper_rag.evaluation.judge import (
    JudgeCaseMetrics,
    JudgeClient,
    evaluate_judge_answer_text,
    summarize_judge_metrics,
)
from paper_rag.evaluation.prompts import JUDGE_PROMPT_VERSION
from paper_rag.exceptions import EvaluationDatasetError


class JudgeOnlyConfig(BaseModel):
    """judge-only 运行所需的输入配置。"""

    input_report_path: Path = Field(description="已有 eval JSON report 路径。")
    dataset_path: Path = Field(
        description="用于查找 evaluation_requirements 的 golden dataset 路径。",
    )
    case_ids: list[str] = Field(
        default_factory=list,
        description="只重新 judge 指定 case；为空时处理 report 中全部可 judge case。",
    )
    judge_source: str | None = Field(default=None, description="judge 使用的模型来源。")
    judge_model: str | None = Field(default=None, description="judge 使用的模型名称。")


class JudgeOnlyResult(BaseModel):
    """judge-only 运行结果。"""

    report: dict[str, Any] = Field(description="写入磁盘或输出给调用方的新 JSON report。")
    judge_metrics: list[JudgeCaseMetrics] = Field(description="本次实际生成的 judge 指标。")


def run_judge_only(config: JudgeOnlyConfig, *, judge_client: JudgeClient) -> JudgeOnlyResult:
    """读取已有 report，对其中答案文本重新运行 judge。"""
    base_report = _load_report(config.input_report_path)
    dataset = load_eval_dataset(
        config.dataset_path,
        project_root=Path.cwd(),
        require_source_paths=False,
    )
    cases_by_id = {case.id: case for case in dataset.cases}
    report_cases = _select_report_cases(base_report, config.case_ids)
    judge_metrics_by_id: dict[str, JudgeCaseMetrics] = {}

    for report_case in report_cases:
        case_id = _case_id(report_case)
        try:
            eval_case = cases_by_id[case_id]
        except KeyError as exc:
            raise EvaluationDatasetError(
                f"judge-only report case not found in dataset: {case_id}"
            ) from exc
        metrics = _judge_report_case(
            eval_case=eval_case,
            report_case=report_case,
            judge_client=judge_client,
        )
        if metrics is not None:
            judge_metrics_by_id[case_id] = metrics

    output_report = _build_output_report(
        base_report=base_report,
        report_cases=report_cases,
        judge_metrics_by_id=judge_metrics_by_id,
        config=config,
    )
    return JudgeOnlyResult(
        report=output_report,
        judge_metrics=list(judge_metrics_by_id.values()),
    )


def write_judge_only_report(result: JudgeOnlyResult, report_path: Path) -> Path:
    """把 judge-only report 写入指定路径。"""
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_report(report_path: Path) -> dict[str, Any]:
    """读取已有 JSON report，并校验顶层结构。"""
    path = Path(report_path)
    if not path.exists():
        raise EvaluationDatasetError(f"eval report does not exist: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvaluationDatasetError(f"eval report is not valid JSON: {path}") from exc
    if not isinstance(report, dict) or not isinstance(report.get("cases"), list):
        raise EvaluationDatasetError("eval report must contain a top-level cases array")
    return report


def _select_report_cases(report: dict[str, Any], case_ids: list[str]) -> list[dict[str, Any]]:
    """按 case ID 选择 report 中的 case，保持用户输入顺序。"""
    cases = [_require_case_object(item) for item in report.get("cases", [])]
    if not case_ids:
        return cases
    cases_by_id = {_case_id(case): case for case in cases}
    missing = [case_id for case_id in case_ids if case_id not in cases_by_id]
    if missing:
        raise EvaluationDatasetError("eval report 中不存在指定 case ID: " + ", ".join(missing))
    return [cases_by_id[case_id] for case_id in dict.fromkeys(case_ids)]


def _judge_report_case(
    *,
    eval_case: EvalCase,
    report_case: dict[str, Any],
    judge_client: JudgeClient,
) -> JudgeCaseMetrics | None:
    """从 report case 中提取答案文本并运行 judge。"""
    answer_text = str(report_case.get("answer_text") or "")
    citation_labels = [str(item) for item in report_case.get("citation_labels") or []]
    insufficient_evidence = bool(report_case.get("insufficient_evidence", False))
    return evaluate_judge_answer_text(
        case=eval_case,
        answer_text=answer_text,
        citation_labels=citation_labels,
        insufficient_evidence=insufficient_evidence,
        judge_client=judge_client,
    )


def _build_output_report(
    *,
    base_report: dict[str, Any],
    report_cases: list[dict[str, Any]],
    judge_metrics_by_id: dict[str, JudgeCaseMetrics],
    config: JudgeOnlyConfig,
) -> dict[str, Any]:
    """基于旧 report 生成只包含本次 judge 结果的新 report。"""
    report = copy.deepcopy(base_report)
    output_cases = []
    for report_case in report_cases:
        case_copy = copy.deepcopy(report_case)
        metrics = judge_metrics_by_id.get(_case_id(case_copy))
        case_copy["judge_metrics"] = metrics.model_dump(mode="json") if metrics else None
        failures = dict(case_copy.get("failures") or {})
        failures["judge"] = _judge_failures(metrics)
        case_copy["failures"] = failures
        output_cases.append(case_copy)

    summary = dict(report.get("summary") or {})
    failed_case_ids = dict(summary.get("failed_case_ids") or {})
    judge_summary = summarize_judge_metrics(list(judge_metrics_by_id.values()), enabled=True)
    failed_case_ids["judge"] = judge_summary.failed_case_ids
    summary["case_count"] = len(output_cases)
    summary["judge"] = judge_summary.model_dump(mode="json")
    summary["failed_case_ids"] = failed_case_ids

    run = dict(report.get("run") or {})
    run["judge"] = {
        "enabled": True,
        "source": config.judge_source,
        "model": config.judge_model,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "mode": "judge_only",
        "input_report_path": str(config.input_report_path),
    }

    dataset = dict(report.get("dataset") or {})
    dataset["case_count"] = len(output_cases)
    dataset.setdefault("path", str(config.dataset_path))

    report["schema_version"] = max(int(report.get("schema_version", 0)), 3)
    report["dataset"] = dataset
    report["run"] = run
    report["summary"] = summary
    report["cases"] = output_cases
    return report


def _judge_failures(metrics: JudgeCaseMetrics | None) -> list[str]:
    """返回 report failures.judge 字段。"""
    if metrics is None or metrics.passed:
        return []
    if metrics.error:
        return [metrics.error]
    return [metrics.overall_reason]


def _require_case_object(value: Any) -> dict[str, Any]:
    """校验 report case 必须是 JSON object。"""
    if not isinstance(value, dict):
        raise EvaluationDatasetError("eval report cases[] must contain JSON objects")
    return value


def _case_id(report_case: dict[str, Any]) -> str:
    """读取 report case ID，并给出清晰错误。"""
    case_id = report_case.get("id")
    if not isinstance(case_id, str) or not case_id:
        raise EvaluationDatasetError("eval report case is missing string id")
    return case_id
