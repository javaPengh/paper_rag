"""Answer generation and citation formatting."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from paper_rag.exceptions import AnswerGenerationError
from paper_rag.schemas import Answer, Citation, SearchResult

INSUFFICIENT_ANSWER = "不足以回答：当前检索到的证据不足以支持可靠答案。"


class ChatClient(Protocol):
    """Minimal chat completion interface for answer generation."""

    model_name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return one answer string."""


@dataclass
class OpenAIChatClient:
    """OpenAI-compatible chat client."""

    model_name: str
    api_key: str | None = None
    base_url: str | None = None

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
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
    """Generate citation-backed answers with an OpenAI-compatible chat model."""

    chat_client: ChatClient
    min_score: float = 0.05

    def generate(self, question: str, results: Sequence[SearchResult]) -> Answer:
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
    """Deterministic local answer generator for offline CLI verification."""

    model_name: str = "extractive-local-v1"
    min_score: float = 0.05
    max_evidence_items: int = 3

    def generate(self, question: str, results: Sequence[SearchResult]) -> Answer:
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
    return (
        "You answer questions using only the provided evidence. "
        "If the evidence is insufficient, answer exactly in Chinese: "
        f"{INSUFFICIENT_ANSWER} "
        "When answering, include source citations in the form [file.pdf, p.1] "
        "or [file.pdf, pp.1-2]. Do not cite sources that are not in the evidence."
    )


def build_user_prompt(question: str, context: str) -> str:
    return f"Question:\n{question}\n\nEvidence:\n{context}\n\nAnswer:"


def build_answer_context(results: Sequence[SearchResult]) -> str:
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        citation = citation_from_result(result)
        lines.append(
            f"[Evidence {index}] {citation.label} score={result.score:.3f}\n"
            f"{result.chunk.text.strip()}"
        )
    return "\n\n".join(lines)


def citations_from_results(results: Sequence[SearchResult]) -> list[Citation]:
    citations: list[Citation] = []
    seen_chunk_ids: set[str] = set()
    for result in results:
        if result.chunk.id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(result.chunk.id)
        citations.append(citation_from_result(result))
    return citations


def citation_from_result(result: SearchResult) -> Citation:
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
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


def ensure_answer_has_citation(answer_text: str, citations: Sequence[Citation]) -> str:
    if not citations:
        return answer_text
    if any(citation.label in answer_text for citation in citations):
        return answer_text
    return f"{answer_text.rstrip()} {citations[0].label}"


def insufficient_answer(question: str, model_name: str, *, context: str | None = None) -> Answer:
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
    lines = ["Answer:", answer.answer]
    if answer.citations:
        lines.extend(["", "Citations:"])
        for citation in answer.citations:
            snippet = f" - {citation.snippet}" if citation.snippet else ""
            lines.append(f"- {citation.label} chunk={citation.chunk_id}{snippet}")
    return "\n".join(lines)
