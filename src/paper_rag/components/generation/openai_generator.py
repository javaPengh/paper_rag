"""OpenAI 兼容 Generator 组件 provider。"""

from __future__ import annotations

from dataclasses import dataclass

from paper_rag.qa.answering import OpenAIAnswerGenerator


@dataclass
class OpenAIGenerator(OpenAIAnswerGenerator):
    """把 OpenAI 兼容聊天回答器包装成 Generator 组件。"""
