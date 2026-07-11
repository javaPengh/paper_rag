"""评测 Judge 提示词。

本模块集中维护只影响语义评测判分的提示词。修改提示词时必须同步更新版本标识，
以便将 Judge 口径变化与被测 RAG 链路的变化区分开。
"""

from __future__ import annotations

import json

JUDGE_PROMPT_VERSION = "judge_v1_requirements"
"""语义评估 Judge 提示词版本。

v1 要求 Judge 只返回 JSON，并逐条判断 `evaluation_requirements` 是否满足。
"""


def build_judge_system_prompt() -> str:
    """返回 Judge 使用的系统提示词。"""
    return (
        "You are an evaluation judge for a paper RAG system. "
        "Evaluate whether the answer satisfies the listed requirements using "
        "only the question, reference answer, cited evidence labels, and the "
        "answer text. "
        "Do not fail an answer only because it uses different wording from a "
        "requirement. "
        "Focus on semantic coverage, correction of false premises, refusal "
        "boundaries, and unsupported claims. "
        "Return only valid JSON with this shape: "
        "{\"passed\": boolean, \"score\": number, "
        "\"requirement_results\": ["
        "{\"requirement\": string, \"passed\": boolean, \"reason\": string}], "
        "\"hallucination_risk\": \"low\"|\"medium\"|\"high\", "
        "\"overall_reason\": string}. "
        "The score must be between 0 and 1."
    )


def build_judge_user_prompt(
    *,
    case_id: str,
    question: str,
    expectation: str,
    reference_answer: str,
    evaluation_requirements: list[str],
    answer_text: str,
    citation_labels: list[str],
    insufficient_evidence: bool,
) -> str:
    """将评测 case 与待判答案组装为 Judge 用户提示词。"""
    payload = {
        "case_id": case_id,
        "question": question,
        "expectation": expectation,
        "reference_answer": reference_answer,
        "evaluation_requirements": evaluation_requirements,
        "answer_text": answer_text,
        "citation_labels": citation_labels,
        "insufficient_evidence": insufficient_evidence,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
