"""英文 BM25 稀疏检索词生成边界。"""

from __future__ import annotations

from typing import Protocol

from paper_rag.exceptions import RetrievalError
from paper_rag.prompts.sparse_query import (
    SPARSE_QUERY_PROMPT_VERSION,
    build_sparse_query_system_prompt,
    build_sparse_query_user_prompt,
)


class SparseQueryClient(Protocol):
    """生成英文稀疏检索词所需的最小聊天补全接口。"""

    model_name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """返回模型生成的英文稀疏检索词。"""


class EnglishSparseQueryGenerator:
    """复用答案生成聊天模型生成英文 BM25 检索词。"""

    def __init__(self, chat_client: SparseQueryClient) -> None:
        """保存已配置的聊天模型，供每次稀疏检索词生成复用。"""
        self.chat_client = chat_client
        self.prompt_version = SPARSE_QUERY_PROMPT_VERSION

    @property
    def model_name(self) -> str:
        """返回生成稀疏检索词的聊天模型名称。"""
        return self.chat_client.model_name

    @property
    def source_name(self) -> str | None:
        """返回聊天模型来源；客户端未声明时为空。"""
        source_name = getattr(self.chat_client, "source_name", None)
        return source_name if isinstance(source_name, str) and source_name else None

    def generate(self, question: str) -> str:
        """将非空原始问题转换为非空英文 BM25 检索词。"""
        if not question.strip():
            raise RetrievalError("英文稀疏检索词生成需要非空原始问题。")
        try:
            sparse_query = self.chat_client.complete(
                system_prompt=build_sparse_query_system_prompt(),
                user_prompt=build_sparse_query_user_prompt(question),
            ).strip()
        except Exception as exc:
            raise RetrievalError(f"英文稀疏检索词生成失败: {exc}") from exc
        if not sparse_query:
            raise RetrievalError("英文稀疏检索词生成返回了空结果。")
        return sparse_query


def build_sparse_query_generator(answer_generator: object) -> EnglishSparseQueryGenerator:
    """从答案生成器提取聊天模型，构造复用同一模型的稀疏检索词生成器。"""
    chat_client = getattr(answer_generator, "chat_client", None)
    if chat_client is None or not hasattr(chat_client, "complete"):
        raise RetrievalError(
            "启用 Hybrid 检索时，答案生成器必须提供可调用的外部聊天模型。"
        )
    model_name = getattr(chat_client, "model_name", None)
    if not isinstance(model_name, str) or not model_name:
        raise RetrievalError("启用 Hybrid 检索时，答案生成器缺少聊天模型名称。")
    return EnglishSparseQueryGenerator(chat_client=chat_client)
