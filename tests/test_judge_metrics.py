"""LLM judge 语义评估指标的单元测试。

这些测试只覆盖 judge 的结构化解析、错误归因和汇总逻辑，不调用真实外部模型，
确保可选 judge 能作为并行指标稳定接入评测报告。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paper_rag.evaluation import EvalCase, EvalDataset, EvalDocument, EvalEvidence
from paper_rag.evaluation.judge import (
    evaluate_judge_case,
    parse_judge_response,
    summarize_judge_metrics,
)
from paper_rag.evaluation.prompts import JUDGE_PROMPT_VERSION, build_judge_system_prompt
from paper_rag.schemas import Answer, Citation


class _FakeJudgeClient:
    """返回固定 JSON 的假 judge 客户端，用于隔离真实 LLM 调用。"""

    model_name = "fake-judge"
    source_name = "fake"

    def __init__(self, payload: dict) -> None:
        """保存待返回的 judge JSON 载荷。"""
        self.payload = payload

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """模拟聊天模型响应，并确认提示词包含 JSON 约束。"""
        assert "JSON" in system_prompt
        assert "evaluation_requirements" in user_prompt
        return json.dumps(self.payload, ensure_ascii=False)


def test_parse_judge_response_accepts_valid_json() -> None:
    """合法 JSON 会被解析为带 case_id 和 expectation 的结构化指标。"""
    case = _case()
    metrics = parse_judge_response(
        case,
        json.dumps(
            {
                "passed": True,
                "score": 0.9,
                "requirement_results": [
                    {"requirement": "指出前提错误", "passed": True, "reason": "答案已纠正。"}
                ],
                "hallucination_risk": "low",
                "overall_reason": "满足要求。",
            },
            ensure_ascii=False,
        ),
    )

    assert metrics.case_id == "case_judge"
    assert metrics.expectation == "corrective_answer"
    assert metrics.passed is True
    assert metrics.score == 0.9
    assert metrics.requirement_results[0].passed is True



def test_judge_prompt_is_versioned_in_evaluation_prompts() -> None:
    """确认 judge 提示词由 evaluation.prompts 统一管理。"""
    prompt = build_judge_system_prompt()

    assert JUDGE_PROMPT_VERSION == "judge_v1_requirements"
    assert "Return only valid JSON" in prompt
    assert "evaluation judge" in prompt
def test_parse_judge_response_accepts_fenced_json() -> None:
    """部分模型会误加代码块围栏，解析器应去掉围栏后再校验 JSON。"""
    case = _case()

    metrics = parse_judge_response(
        case,
        "```json\n"
        + json.dumps(
            {
                "passed": False,
                "score": 0.4,
                "requirement_results": [],
                "hallucination_risk": "medium",
                "overall_reason": "没有满足关键要求。",
            },
            ensure_ascii=False,
        )
        + "\n```",
    )

    assert metrics.passed is False
    assert metrics.hallucination_risk == "medium"


def test_parse_judge_response_reports_invalid_json() -> None:
    """非 JSON 响应应产生清晰的 case-level 解析错误。"""
    with pytest.raises(ValueError, match="合法 JSON"):
        parse_judge_response(_case(), "not json")


def test_parse_judge_response_reports_invalid_score() -> None:
    """score 越界会被 Pydantic 校验拦住，避免脏指标进入报告。"""
    with pytest.raises(ValueError, match="judge 输出结构不合法"):
        parse_judge_response(
            _case(),
            json.dumps(
                {
                    "passed": True,
                    "score": 1.2,
                    "requirement_results": [],
                    "hallucination_risk": "low",
                    "overall_reason": "分数越界。",
                },
                ensure_ascii=False,
            ),
        )


def test_evaluate_judge_case_skips_cases_without_requirements() -> None:
    """未配置 evaluation_requirements 的样本不会进入 judge，保持旧数据兼容。"""
    case = _case(requirements=[])
    answer = _answer()

    assert evaluate_judge_case(case=case, answer=answer, judge_client=_FakeJudgeClient({})) is None


def test_evaluate_judge_case_returns_case_level_error_for_missing_answer() -> None:
    """答案生成失败时 judge 不调用模型，而是产出清晰的 case-level error。"""
    metrics = evaluate_judge_case(
        case=_case(),
        answer=None,
        judge_client=_FakeJudgeClient({}),
    )

    assert metrics is not None
    assert metrics.passed is False
    assert metrics.error == "没有可供 judge 评估的答案。"


def test_evaluate_judge_case_uses_client_response() -> None:
    """配置了 requirements 的样本会把模型 JSON 响应转换为 judge 指标。"""
    payload = {
        "passed": True,
        "score": 1.0,
        "requirement_results": [
            {"requirement": "指出前提错误", "passed": True, "reason": "已指出。"}
        ],
        "hallucination_risk": "low",
        "overall_reason": "全部满足。",
    }

    metrics = evaluate_judge_case(
        case=_case(),
        answer=_answer(),
        judge_client=_FakeJudgeClient(payload),
    )

    assert metrics is not None
    assert metrics.passed is True
    assert metrics.score == 1.0
    assert metrics.overall_reason == "全部满足。"


def test_summarize_judge_metrics_counts_pass_and_errors() -> None:
    """judge 汇总独立统计通过率、平均分、错误数和失败 case。"""
    passed = parse_judge_response(
        _case(case_id="case_pass"),
        json.dumps(
            {
                "passed": True,
                "score": 1.0,
                "requirement_results": [],
                "hallucination_risk": "low",
                "overall_reason": "ok",
            }
        ),
    )
    failed = parse_judge_response(
        _case(case_id="case_fail"),
        json.dumps(
            {
                "passed": False,
                "score": 0.0,
                "requirement_results": [],
                "hallucination_risk": "high",
                "overall_reason": "bad",
            }
        ),
    )
    failed.error = "judge 解析失败"

    summary = summarize_judge_metrics([passed, failed], enabled=True)

    assert summary.enabled is True
    assert summary.case_count == 2
    assert summary.passed_count == 1
    assert summary.pass_rate == 0.5
    assert summary.average_score == 0.5
    assert summary.error_count == 1
    assert summary.failed_case_ids == ["case_fail"]


def _case(case_id: str = "case_judge", requirements: list[str] | None = None) -> EvalCase:
    """构造带语义要求的纠错题样本。"""
    return EvalCase(
        id=case_id,
        question="为什么作者合成 30 FPS 视频？",
        answerable=True,
        expectation="corrective_answer",
        evidence=[
            EvalEvidence(
                doc_key="paper",
                page_start=13,
                page_end=13,
                terms=["24 FPS", "30 FPS"],
            )
        ],
        answer_terms=["24 FPS"],
        evaluation_requirements=(requirements if requirements is not None else ["指出前提错误"]),
        reference_answer="问题前提有误。",
        notes="",
    )


def _answer() -> Answer:
    """构造带引用的答案对象，供 judge 输入使用。"""
    return Answer(
        question="Why did the authors synthesize 30 FPS video?",
        answer="问题前提有误。论文是把 ScanNet 帧转换为 24 FPS，并将 ScanNet++ 降采样到 30 FPS。",
        citations=[
            Citation(
                document_id="paper",
                document_version_id="v1",
                chunk_id="chunk-1",
                file_name="paper.pdf",
                page_start=13,
                page_end=13,
                snippet="ScanNet frames 24 FPS and ScanNet++ 30 FPS",
            )
        ],
        evidence_chunk_ids=["chunk-1"],
        insufficient_evidence=False,
        model_name="fake-answer",
    )


def _dataset(tmp_path: Path, cases: list[EvalCase]) -> EvalDataset:
    """保留数据集构造器，便于后续扩展 judge 与 evidence 联合测试。"""
    return EvalDataset(
        path=tmp_path / "golden.jsonl",
        documents_path=tmp_path / "golden.documents.json",
        documents={"paper": EvalDocument(source_path=Path("paper.pdf"), notes="fixture")},
        cases=cases,
    )


