"""检索前英文查询翻译边界。

本模块把原始问题翻译与实际 Retriever 调用集中到同一处，确保 CLI、API 和评测
使用一致的检索输入，同时保留原始问题供答案生成、前端回显和评测使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from paper_rag.components.interfaces import Retriever
from paper_rag.domain import SearchResult
from paper_rag.exceptions import QueryTranslationError
from paper_rag.prompts.translation import (
    QUERY_TRANSLATION_PROMPT_VERSION,
    build_query_translation_system_prompt,
    build_query_translation_user_prompt,
)


class QueryTranslationClient(Protocol):
    """执行查询翻译所需的最小聊天补全接口。"""

    model_name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """返回模型生成的英文检索问题。"""


@dataclass(frozen=True)
class QueryTranslation:
    """一次原始问题到检索问题的转换记录。"""

    original_question: str
    """用户或评测集提交的原始问题。"""

    retrieval_question: str
    """实际传给 Retriever 的英文问题。"""


@dataclass(frozen=True)
class QueryRetrievalResult:
    """一次检索的原始问题、实际检索问题和召回结果。"""

    translation: QueryTranslation
    """原始问题与实际检索问题的对应关系。"""

    results: list[SearchResult]
    """Retriever 按实际检索问题返回的候选证据。"""


class EnglishQueryTranslator:
    """使用答案生成器同一聊天模型生成英文检索问题。"""

    def __init__(self, chat_client: QueryTranslationClient) -> None:
        """保存已配置的聊天模型，供查询翻译调用复用。"""
        self.chat_client = chat_client
        self.prompt_version = QUERY_TRANSLATION_PROMPT_VERSION

    @property
    def model_name(self) -> str:
        """返回翻译复用的答案生成模型名称。"""
        return self.chat_client.model_name

    @property
    def source_name(self) -> str | None:
        """返回翻译复用的答案生成模型来源；客户端未声明时为空。"""
        source_name = getattr(self.chat_client, "source_name", None)
        return source_name if isinstance(source_name, str) and source_name else None

    def translate(self, question: str) -> QueryTranslation:
        """将非空原始问题翻译为非空英文检索问题。"""
        if not question.strip():
            raise QueryTranslationError("查询翻译需要非空原始问题。")
        try:
            translated_question = self.chat_client.complete(
                system_prompt=build_query_translation_system_prompt(),
                user_prompt=build_query_translation_user_prompt(question),
            ).strip()
        except Exception as exc:
            raise QueryTranslationError(f"英文查询翻译失败: {exc}") from exc
        if not translated_question:
            raise QueryTranslationError("英文查询翻译返回了空结果。")
        return QueryTranslation(
            original_question=question,
            retrieval_question=translated_question,
        )


def retrieve_for_question(
    *,
    question: str,
    retriever: Retriever,
    top_k: int,
    query_translator: EnglishQueryTranslator | None = None,
) -> QueryRetrievalResult:
    """按可选英文翻译策略执行一次检索，并保留实际检索问题。"""
    translation = (
        query_translator.translate(question)
        if query_translator is not None
        else QueryTranslation(original_question=question, retrieval_question=question)
    )
    return QueryRetrievalResult(
        translation=translation,
        results=retriever.retrieve(translation.retrieval_question, top_k=top_k),
    )


def build_query_translator(answer_generator: object) -> EnglishQueryTranslator:
    """从答案生成器提取聊天模型，构造使用同一模型的查询翻译器。"""
    chat_client = getattr(answer_generator, "chat_client", None)
    if chat_client is None or not hasattr(chat_client, "complete"):
        raise QueryTranslationError(
            "启用英文查询翻译时，答案生成器必须提供可调用的外部聊天模型。"
        )
    model_name = getattr(chat_client, "model_name", None)
    if not isinstance(model_name, str) or not model_name:
        raise QueryTranslationError("启用英文查询翻译时，答案生成器缺少聊天模型名称。")
    return EnglishQueryTranslator(chat_client=chat_client)
