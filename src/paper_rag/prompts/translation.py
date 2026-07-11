"""英文检索查询翻译提示词。

本模块只维护将用户原始问题转换为英文检索问题的提示词。翻译结果只用于检索，
不得作为最终答案生成问题；修改模板时必须同步更新版本标识。
"""

from __future__ import annotations

QUERY_TRANSLATION_PROMPT_VERSION = "query_translation_v1_english_retrieval"
"""英文检索查询翻译提示词版本。"""


def build_query_translation_system_prompt() -> str:
    """返回将原始问题翻译为英文检索问题的系统提示词。"""
    return (
        "Translate the user's question into one concise English query for retrieving "
        "evidence from English academic papers. Preserve paper titles, method names, "
        "metrics, abbreviations, numbers, negations, constraints, and proper nouns. "
        "Do not answer the question, add facts, expand it with new search terms, or "
        "explain the translation. Return only the English retrieval query."
    )


def build_query_translation_user_prompt(question: str) -> str:
    """将原始问题组装为查询翻译模型的用户提示词。"""
    return f"Original question:\n{question}\n\nEnglish retrieval query:"
