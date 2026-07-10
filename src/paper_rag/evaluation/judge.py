"""LLM judge 语义评估指标。

本模块只负责可选的语义质量评估，不替代 retrieval、citation 和 answer_terms
这些确定性指标。judge 结果作为并行指标写入报告，便于判断复杂答案是否满足人工
列出的评估要求。
"""

from __future__ import annotations

import json
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from paper_rag.domain import Answer
from paper_rag.evaluation.dataset import EvalCase
from paper_rag.evaluation.prompts import build_judge_system_prompt


class JudgeClient(Protocol):
    """用于 judge 的最小聊天补全接口。"""

    model_name: str
    source_name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """返回 judge 模型输出的 JSON 字符串。"""


class JudgeRequirementResult(BaseModel):
    """单条语义评估要求的 judge 判断。"""

    requirement: str = Field(description="被评估的人工要求。")
    passed: bool = Field(description="答案是否满足该要求。")
    reason: str = Field(description="judge 给出的人类可读判断理由。")


class JudgeCaseMetrics(BaseModel):
    """单条 eval case 的 LLM judge 语义评估结果。"""

    case_id: str = Field(description="对应 golden dataset 中的稳定 case ID。")
    expectation: str = Field(description="该 case 的评测期望类型。")
    passed: bool = Field(description="judge 是否判定答案整体满足语义要求。")
    score: float = Field(ge=0.0, le=1.0, description="judge 给出的 0 到 1 语义质量分。")
    requirement_results: list[JudgeRequirementResult] = Field(
        default_factory=list,
        description="逐条 evaluation_requirements 的判断结果。",
    )
    hallucination_risk: Literal["low", "medium", "high"] = Field(
        description="judge 判断答案存在无依据扩展或幻觉的风险等级。",
    )
    overall_reason: str = Field(description="judge 对整体判断的简短说明。")
    error: str | None = Field(default=None, description="judge 调用或解析失败时的错误说明。")


class JudgeMetricSummary(BaseModel):
    """一组 judge case 指标的汇总。"""

    enabled: bool = Field(description="本次评测是否启用了 judge。")
    case_count: int = Field(
        ge=0,
        description="配置了 evaluation_requirements 并实际进入 judge 的 case 数。",
    )
    passed_count: int = Field(ge=0, description="judge 判定通过的 case 数。")
    pass_rate: float = Field(description="passed_count / case_count。")
    average_score: float = Field(description="已评估 case 的平均 judge 分数。")
    error_count: int = Field(ge=0, description="judge 调用或解析失败的 case 数。")
    failed_case_ids: list[str] = Field(
        default_factory=list,
        description="judge 未通过或出错的 case ID。",
    )


def build_judge_user_prompt(
    *,
    case: EvalCase,
    answer_text: str,
    citation_labels: list[str],
    insufficient_evidence: bool,
) -> str:
    """把单条 case、答案文本和评估要求组装成 judge 用户提示词。"""
    payload = {
        "case_id": case.id,
        "question": case.question,
        "expectation": case.expectation,
        "reference_answer": case.reference_answer,
        "evaluation_requirements": case.evaluation_requirements,
        "answer_text": answer_text,
        "citation_labels": citation_labels,
        "insufficient_evidence": insufficient_evidence,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_judge_response(case: EvalCase, raw_response: str) -> JudgeCaseMetrics:
    """解析 judge JSON 输出，并校验字段和取值范围。"""
    try:
        payload = json.loads(_strip_json_fence(raw_response))
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge 输出不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("judge 输出必须是 JSON object。")
    payload["case_id"] = case.id
    payload["expectation"] = case.expectation
    try:
        return JudgeCaseMetrics.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"judge 输出结构不合法: {exc}") from exc


def evaluate_judge_case(
    *,
    case: EvalCase,
    answer: Answer | None,
    judge_client: JudgeClient,
) -> JudgeCaseMetrics | None:
    """对配置了 evaluation_requirements 的 case 运行 LLM judge。"""
    if answer is None:
        return evaluate_judge_answer_text(
            case=case,
            answer_text="",
            citation_labels=[],
            insufficient_evidence=False,
            judge_client=judge_client,
        )
    return evaluate_judge_answer_text(
        case=case,
        answer_text=answer.answer,
        citation_labels=[citation.label for citation in answer.citations],
        insufficient_evidence=answer.insufficient_evidence,
        judge_client=judge_client,
    )


def evaluate_judge_answer_text(
    *,
    case: EvalCase,
    answer_text: str,
    citation_labels: list[str],
    insufficient_evidence: bool,
    judge_client: JudgeClient,
) -> JudgeCaseMetrics | None:
    """对已有答案文本运行 LLM judge，用于完整 eval 和 judge-only 复用。"""
    if not case.evaluation_requirements:
        return None
    if not answer_text.strip():
        return _judge_error_metrics(case, "没有可供 judge 评估的答案。")
    try:
        raw_response = judge_client.complete(
            system_prompt=build_judge_system_prompt(),
            user_prompt=build_judge_user_prompt(
                case=case,
                answer_text=answer_text,
                citation_labels=citation_labels,
                insufficient_evidence=insufficient_evidence,
            ),
        )
        metrics = parse_judge_response(case, raw_response)
    except Exception as exc:
        return _judge_error_metrics(case, str(exc))
    return metrics


def summarize_judge_metrics(
    case_metrics: list[JudgeCaseMetrics],
    *,
    enabled: bool,
) -> JudgeMetricSummary:
    """汇总 judge 指标。"""
    case_count = len(case_metrics)
    passed_count = sum(1 for item in case_metrics if item.passed and item.error is None)
    error_count = sum(1 for item in case_metrics if item.error is not None)
    score_sum = sum(item.score for item in case_metrics)
    failed_case_ids = [item.case_id for item in case_metrics if not item.passed or item.error]
    return JudgeMetricSummary(
        enabled=enabled,
        case_count=case_count,
        passed_count=passed_count,
        pass_rate=_safe_rate(passed_count, case_count),
        average_score=_safe_rate(score_sum, case_count),
        error_count=error_count,
        failed_case_ids=failed_case_ids,
    )


def _strip_json_fence(raw_response: str) -> str:
    """兼容模型把 JSON 包在 Markdown code fence 中的情况。"""
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _judge_error_metrics(case: EvalCase, error: str) -> JudgeCaseMetrics:
    """创建 judge 失败时的结构化指标，避免单个 case 中断整次评测。"""
    return JudgeCaseMetrics(
        case_id=case.id,
        expectation=case.expectation,
        passed=False,
        score=0.0,
        requirement_results=[],
        hallucination_risk="high",
        overall_reason="judge 调用或解析失败。",
        error=error,
    )


def _safe_rate(numerator: float, denominator: int) -> float:
    """安全计算比例，避免空数据集除零。"""
    if denominator == 0:
        return 0.0
    return numerator / denominator
