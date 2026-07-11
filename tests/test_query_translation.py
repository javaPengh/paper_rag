"""英文查询翻译与共享检索入口测试。"""

from __future__ import annotations

import pytest

from paper_rag.components.retrieval import (
    EnglishQueryTranslator,
    build_query_translator,
    retrieve_for_question,
)
from paper_rag.exceptions import QueryTranslationError
from paper_rag.prompts.translation import QUERY_TRANSLATION_PROMPT_VERSION


class _FakeTranslationClient:
    """记录提示词并返回固定英文检索问题的聊天客户端替身。"""

    model_name = "fake-answer-model"
    source_name = "fake"

    def __init__(self, translation: str = "What method does the paper use?") -> None:
        """保存测试需要返回的翻译文本。"""
        self.translation = translation
        self.system_prompt = ""
        self.user_prompt = ""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """记录输入提示词并返回预设翻译。"""
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.translation


class _FakeRetriever:
    """记录实际检索问题的最小 Retriever 替身。"""

    def __init__(self) -> None:
        """初始化空的检索调用记录。"""
        self.question = ""
        self.top_k = 0

    def retrieve(self, question: str, *, top_k: int = 5) -> list:
        """记录检索输入并返回空结果，隔离查询转换行为。"""
        self.question = question
        self.top_k = top_k
        return []


def test_query_translation_only_changes_retriever_input() -> None:
    """确认共享检索入口把英文翻译传给 Retriever，并保留原始问题。"""
    client = _FakeTranslationClient()
    translator = EnglishQueryTranslator(client)
    retriever = _FakeRetriever()

    result = retrieve_for_question(
        question="论文使用了什么方法？",
        retriever=retriever,
        top_k=3,
        query_translator=translator,
    )

    assert translator.prompt_version == QUERY_TRANSLATION_PROMPT_VERSION
    assert "Translate" in client.system_prompt
    assert "论文使用了什么方法？" in client.user_prompt
    assert result.translation.original_question == "论文使用了什么方法？"
    assert result.translation.retrieval_question == "What method does the paper use?"
    assert retriever.question == "What method does the paper use?"
    assert retriever.top_k == 3


def test_query_translation_rejects_empty_translation() -> None:
    """确认翻译模型返回空文本时不会回退为原始问题检索。"""
    translator = EnglishQueryTranslator(_FakeTranslationClient(translation="   "))

    with pytest.raises(QueryTranslationError, match="空结果"):
        translator.translate("论文使用了什么方法？")


def test_query_translator_reuses_answer_generator_chat_client() -> None:
    """确认翻译器复用答案生成器已经选择的聊天模型。"""
    chat_client = _FakeTranslationClient()
    answer_generator = type("AnswerGenerator", (), {"chat_client": chat_client})()

    translator = build_query_translator(answer_generator)

    assert translator.chat_client is chat_client
    assert translator.model_name == "fake-answer-model"
    assert translator.source_name == "fake"


def test_query_translator_rejects_generator_without_chat_client() -> None:
    """确认本地抽取式生成器不能被静默用作查询翻译模型。"""
    with pytest.raises(QueryTranslationError, match="外部聊天模型"):
        build_query_translator(object())
