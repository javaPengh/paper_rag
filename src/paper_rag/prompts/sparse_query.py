"""英文 BM25 稀疏检索词提示词。

本模块只维护将用户原始问题转换为英文词法检索词的提示词。输出仅用于 BM25，
不得作为答案，也不得改变向量检索和答案生成使用的原始问题。
"""

from __future__ import annotations

SPARSE_QUERY_PROMPT_VERSION = "sparse_query_v1_english_keywords"
"""英文稀疏检索词提示词版本。"""


def build_sparse_query_system_prompt() -> str:
    """返回将原始问题转换为英文 BM25 检索词的系统提示词。"""
    return (
        "Convert the user's question into a concise English keyword query for BM25 search "
        "over English academic papers. Preserve dataset names, model names, abbreviations, "
        "numbers, and constraints from the original question. Do not answer the question, "
        "do not invent facts or unseen section names, and do not explain your output. "
        "Return only the English keyword query."
    )


def build_sparse_query_user_prompt(question: str) -> str:
    """将原始问题组装为稀疏检索词生成的用户提示词。"""
    return f"Original question:\n{question}\n\nEnglish BM25 keyword query:"
