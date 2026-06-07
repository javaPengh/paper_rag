"""答案生成和引用格式化。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from paper_rag.exceptions import AnswerGenerationError
from paper_rag.schemas import Answer, Citation, SearchResult

# 本地和 LLM 驱动的答案生成器共用的标准拒答文本。
INSUFFICIENT_ANSWER = "不足以回答：当前检索到的证据不足以支持可靠答案。"


class ChatClient(Protocol):
    """用于答案生成的最小聊天补全接口。"""

    # 该提供方/模型标识会复制到 Answer.model_name 里，便于追踪。
    model_name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """返回一个答案字符串。"""


@dataclass
class OpenAIChatClient:
    """OpenAI 兼容的聊天客户端。"""

    model_name: str = field(
        metadata={"description": "用于答案生成的 OpenAI 兼容聊天模型。"},
    )
    api_key: str | None = field(
        default=None,
        metadata={"description": "聊天提供方的 API 密钥。"},
    )
    base_url: str | None = field(
        default=None,
        metadata={"description": "可选的 OpenAI 兼容聊天端点覆盖。"},
    )

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """调用聊天提供方并返回非空答案字符串。"""
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise AnswerGenerationError(
                "OpenAI SDK is required for QA. Install dependencies with "
                'pip install -e ".[dev]".'
            ) from exc

        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
        except Exception as exc:
            raise AnswerGenerationError(f"Answer generation failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise AnswerGenerationError("Answer generation returned empty content.")
        return content.strip()


@dataclass
class OpenAIAnswerGenerator:
    """使用 OpenAI 兼容聊天模型生成带引用的答案。"""

    chat_client: ChatClient = field(
        metadata={"description": "用于生成最终答案的聊天补全边界。"},
    )
    min_score: float = field(
        default=0.05,
        metadata={"description": "允许证据进入提示词的最低检索分数。"},
    )

    def generate(self, question: str, results: Sequence[SearchResult]) -> Answer:
        """根据检索到的证据生成一个有依据的答案，或者返回拒答。"""
        usable_results = filter_usable_results(question, results, min_score=self.min_score)
        citations = citations_from_results(usable_results)
        context = build_answer_context(usable_results)
        if not usable_results:
            return insufficient_answer(question, self.chat_client.model_name, context=context)

        raw_answer = self.chat_client.complete(
            system_prompt=build_system_prompt(),
            user_prompt=build_user_prompt(question, context),
        )
        insufficient = "不足以回答" in raw_answer
        if insufficient:
            return Answer(
                question=question,
                answer=raw_answer,
                citations=[],
                evidence_chunk_ids=[],
                model_name=self.chat_client.model_name,
                insufficient_evidence=True,
                context=context,
            )

        answer_text = ensure_answer_has_citation(raw_answer, citations)
        return Answer(
            question=question,
            answer=answer_text,
            citations=citations,
            evidence_chunk_ids=[result.chunk.id for result in usable_results],
            model_name=self.chat_client.model_name,
            insufficient_evidence=False,
            context=context,
        )


@dataclass
class ExtractiveAnswerGenerator:
    """用于离线 CLI 验证的确定性本地答案生成器。"""

    model_name: str = field(
        default="extractive-local-v1",
        metadata={"description": "本地答案生成器标识。"},
    )
    min_score: float = field(
        default=0.05,
        metadata={"description": "抽取式证据的最低检索分数。"},
    )
    max_evidence_items: int = field(
        default=3,
        metadata={"description": "本地答案中包含的最大证据 chunk 数量。"},
    )

    def generate(self, question: str, results: Sequence[SearchResult]) -> Answer:
        """通过总结检索到的 chunk 并附上引用来构造确定性答案。"""
        usable_results = filter_usable_results(question, results, min_score=self.min_score)
        context = build_answer_context(usable_results)
        if not usable_results:
            return insufficient_answer(question, self.model_name, context=context)

        selected_results = list(usable_results[: self.max_evidence_items])
        citations = citations_from_results(selected_results)
        evidence_parts = [
            f"{summarize_chunk(result.chunk.text)} {citation.label}"
            for result, citation in zip(selected_results, citations, strict=False)
        ]
        answer_text = "基于检索到的证据：" + " ".join(evidence_parts)
        return Answer(
            question=question,
            answer=answer_text,
            citations=citations,
            evidence_chunk_ids=[result.chunk.id for result in selected_results],
            model_name=self.model_name,
            insufficient_evidence=False,
            context=context,
        )


def build_system_prompt() -> str:
    """创建用于 LLM 答案生成的依据约束说明。"""
    return (
        "You answer questions using only the provided evidence. "
        "If the evidence is insufficient, answer exactly in Chinese: "
        f"{INSUFFICIENT_ANSWER} "
        "When answering, include source citations in the form [file.pdf, p.1] "
        "or [file.pdf, pp.1-2]. Do not cite sources that are not in the evidence."
    )


def build_user_prompt(question: str, context: str) -> str:
    """把用户问题和证据上下文合并成一个模型提示词。"""
    return f"Question:\n{question}\n\nEvidence:\n{context}\n\nAnswer:"


def build_answer_context(results: Sequence[SearchResult]) -> str:
    """把检索到的 chunk 序列化为编号证据块，供答案提示词使用。"""
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        citation = citation_from_result(result)
        lines.append(
            f"[Evidence {index}] {citation.label} score={result.score:.3f}\n"
            f"{result.chunk.text.strip()}"
        )
    return "\n\n".join(lines)


def citations_from_results(results: Sequence[SearchResult]) -> list[Citation]:
    """按检索顺序创建去重后的引用。"""
    citations: list[Citation] = []
    seen_chunk_ids: set[str] = set()
    for result in results:
        if result.chunk.id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(result.chunk.id)
        citations.append(citation_from_result(result))
    return citations


def citation_from_result(result: SearchResult) -> Citation:
    """把一个检索结果转换为带文件和页码来源信息的引用。"""
    document = result.document
    file_name = document.file_name if document is not None else result.chunk.document_id
    return Citation(
        document_id=result.chunk.document_id,
        document_version_id=result.chunk.document_version_id,
        chunk_id=result.chunk.id,
        file_name=file_name,
        page_start=result.chunk.page_start,
        page_end=result.chunk.page_end,
        snippet=summarize_chunk(result.chunk.text),
    )


def filter_usable_results(
    question: str,
    results: Sequence[SearchResult],
    *,
    min_score: float,
) -> list[SearchResult]:
    """按分数和轻量词汇重叠过滤检索到的 chunk，以保证 MVP 安全性。"""
    question_terms = content_terms(question)
    usable: list[SearchResult] = []
    for result in results:
        if result.score < min_score:
            continue
        if question_terms and not question_terms.intersection(content_terms(result.chunk.text)):
            continue
        usable.append(result)
    return usable


def content_terms(text: str) -> set[str]:
    """提取用于 MVP 证据充分性过滤的粗粒度词汇锚点。"""
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "do",
        "does",
        "for",
        "in",
        "is",
        "of",
        "the",
        "to",
        "what",
        "with",
    }
    return {
        token
        for token in re.findall(r"[\w-]+", text.lower())
        if len(token) > 2 and token not in stop_words
    }


def summarize_chunk(text: str, *, max_length: int = 260) -> str:
    """在不改变源 chunk 文本的情况下创建紧凑的引用片段。"""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


def ensure_answer_has_citation(answer_text: str, citations: Sequence[Citation]) -> str:
    """当模型忘记包含允许的引用标签时，附加第一个引用。"""
    if not citations:
        return answer_text
    if any(citation.label in answer_text for citation in citations):
        return answer_text
    return f"{answer_text.rstrip()} {citations[0].label}"


def insufficient_answer(question: str, model_name: str, *, context: str | None = None) -> Answer:
    """创建标准的有依据拒答答案。"""
    return Answer(
        question=question,
        answer=INSUFFICIENT_ANSWER,
        citations=[],
        evidence_chunk_ids=[],
        model_name=model_name,
        insufficient_evidence=True,
        context=context,
    )


def format_answer(answer: Answer) -> str:
    """把 Answer 渲染成 CLI 输出，同时保留结构化数据。"""
    lines = ["Answer:", answer.answer]
    if answer.citations:
        lines.extend(["", "Citations:"])
        for citation in answer.citations:
            snippet = f" - {citation.snippet}" if citation.snippet else ""
            lines.append(f"- {citation.label} chunk={citation.chunk_id}{snippet}")
    return "\n".join(lines)
