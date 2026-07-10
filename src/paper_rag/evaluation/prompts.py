"""评测提示词集中定义。

本模块管理只影响评测判分的提示词版本。它与 `paper_rag.qa.prompts`
刻意分开：问答提示词影响系统如何回答，judge 提示词影响评测如何判定答案质量。
"""

from __future__ import annotations

JUDGE_PROMPT_VERSION = "judge_v1_requirements"
"""语义评估 judge 提示词版本。

v1 要求 judge 只返回 JSON，并逐条判断 `evaluation_requirements` 是否满足。
"""


def build_judge_system_prompt() -> str:
    """返回 judge 使用的系统提示词。"""
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
