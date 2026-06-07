"""Extractive Generator 组件 provider。"""

from __future__ import annotations

from dataclasses import dataclass

from paper_rag.qa.answering import ExtractiveAnswerGenerator


@dataclass
class ExtractiveGenerator(ExtractiveAnswerGenerator):
    """把确定性本地抽取式回答器包装成 Generator 组件。"""
