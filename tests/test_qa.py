from pathlib import Path

from paper_rag.qa import ExtractiveAnswerGenerator, format_answer
from paper_rag.schemas import Chunk, Document, SearchResult


def test_extractive_answer_includes_citation() -> None:
    document = Document(
        id="doc-1",
        source_uri=str(Path("paper.pdf")),
        file_name="paper.pdf",
        page_count=1,
        current_version_id="version-1",
    )
    result = SearchResult(
        chunk=Chunk(
            id="chunk-1",
            document_id=document.id,
            document_version_id="version-1",
            text="Paper RAG indexes local PDF papers and stores vectors.",
            page_start=1,
            page_end=1,
            chunk_index=0,
        ),
        document=document,
        score=0.8,
    )

    answer = ExtractiveAnswerGenerator().generate("What does Paper RAG index?", [result])

    assert not answer.insufficient_evidence
    assert "[paper.pdf, p.1]" in answer.answer
    assert answer.citations[0].label == "[paper.pdf, p.1]"
    assert "Citations:" in format_answer(answer)


def test_extractive_answer_reports_insufficient_evidence() -> None:
    document = Document(
        id="doc-1",
        source_uri=str(Path("paper.pdf")),
        file_name="paper.pdf",
        page_count=1,
        current_version_id="version-1",
    )
    result = SearchResult(
        chunk=Chunk(
            id="chunk-1",
            document_id=document.id,
            document_version_id="version-1",
            text="Paper RAG indexes local PDF papers and stores vectors.",
            page_start=1,
            page_end=1,
            chunk_index=0,
        ),
        document=document,
        score=0.8,
    )

    answer = ExtractiveAnswerGenerator().generate("What is the capital of France?", [result])

    assert answer.insufficient_evidence
    assert "不足以回答" in answer.answer
    assert answer.citations == []
