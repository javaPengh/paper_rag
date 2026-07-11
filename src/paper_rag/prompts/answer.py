"""答案生成提示词。

本模块集中维护答案生成器使用的提示词和标准拒答文本。修改提示词时必须同步更新
版本标识，使评测报告能够区分提示词改动与检索、切分或模型配置改动。
"""

from __future__ import annotations

# 本地和 LLM 驱动的答案生成器共用的标准拒答文本。
INSUFFICIENT_ANSWER = "不足以回答：当前检索到的证据不足以支持可靠答案。"

ANSWER_PROMPT_VERSION = "answer_v4_corrective_mapping"
"""答案生成系统提示词版本。

v4 在 v3 的纠错边界基础上，要求模型解释错误前提可能混淆了哪些相邻实体、
动作或数值，避免只纠正用户显式提到的对象而遗漏证据中的正确对应关系。
"""


def build_answer_system_prompt() -> str:
    """返回当前答案生成系统提示词。"""
    return (
        "You answer questions using only the provided evidence.\n"
        "Follow this decision order strictly:\n"
        "1. If none of the provided evidence is relevant to the question, "
        "answer exactly in Chinese: "
        f"{INSUFFICIENT_ANSWER}\n"
        "2. If any provided evidence is relevant, do not use the exact refusal "
        "sentence above. Relevant evidence must be answered with citations, "
        "even when it only supports correcting the user.\n"
        "3. If the evidence contradicts a premise in the question, the answer "
        "must start in Chinese with '问题前提不成立：'. Then state what the "
        "evidence actually says, correct the premise, and cite the evidence. "
        "If the false premise appears to mix up nearby entities, actions, "
        "or numbers from the evidence, explicitly contrast the correct "
        "entity-action-number mappings for each related item. "
        "Do not answer a 'why' question that is based on a false premise; "
        "correct the false premise instead.\n"
        "4. If the evidence is relevant but lacks a requested detail, do not "
        "invent the detail and do not use the exact refusal sentence. State "
        "that the paper does not provide that detail, summarize what it does "
        "say, and cite evidence.\n"
        "5. For direct factual questions, answer concisely from the evidence "
        "and cite evidence.\n"
        "Use Chinese for the final answer unless the question explicitly asks "
        "for another language. Include source citations in the form "
        "[file.pdf, p.1] or [file.pdf, pp.1-2]. Do not cite sources that are "
        "not in the evidence."
    )


def build_answer_user_prompt(question: str, context: str) -> str:
    """将用户问题和检索证据组装为答案生成用户提示词。"""
    return f"Question:\n{question}\n\nEvidence:\n{context}\n\nAnswer:"
