"""Answer / Citation / Refusal 指标的单元测试。

这些测试验证答案阶段的确定性判断：可回答题是否真正回答、citation 是否覆盖
人工 evidence 的文档与页码、答案是否覆盖 answer_terms，以及不可回答题是否
以无 citation 的方式正确拒答。
"""

from pathlib import Path

from paper_rag.evaluation import (
    EvalCase,
    EvalDataset,
    EvalDocument,
    EvalEvidence,
    evaluate_answer_case,
    summarize_answer_metrics,
)
from paper_rag.schemas import Answer, Chunk, Citation, Document, SearchResult


def test_evaluate_answer_case_passes_answerable_with_citation_and_terms(
    tmp_path: Path,
) -> None:
    answerable_case = _answerable_case()
    dataset = _dataset(tmp_path, [answerable_case])
    result = _search_result(tmp_path, page_start=2, page_end=2)
    answer = _answer(
        question=answerable_case.question,
        text="alpha is supported by the cited evidence. [paper.pdf, p.2]",
        citations=[_citation_from_result(result)],
    )

    metrics = evaluate_answer_case(
        dataset=dataset,
        case=answerable_case,
        answer=answer,
        results=[result],
    )

    assert metrics.passed
    assert metrics.answered
    assert metrics.answer_terms_hit
    assert metrics.citation_evidence_hit is True
    assert metrics.citation_matches[0].doc_hit
    assert metrics.citation_matches[0].page_hit
    assert metrics.failed_reasons == []


def test_evaluate_answer_case_reports_citation_page_miss(tmp_path: Path) -> None:
    answerable_case = _answerable_case()
    dataset = _dataset(tmp_path, [answerable_case])
    result = _search_result(tmp_path, page_start=5, page_end=5)
    answer = _answer(
        question=answerable_case.question,
        text="alpha is supported by another page. [paper.pdf, p.5]",
        citations=[_citation_from_result(result)],
    )

    metrics = evaluate_answer_case(
        dataset=dataset,
        case=answerable_case,
        answer=answer,
        results=[result],
    )

    assert not metrics.passed
    assert metrics.citation_evidence_hit is False
    assert metrics.citation_matches[0].doc_hit
    assert not metrics.citation_matches[0].page_hit
    assert metrics.failed_reasons == ["paper pp.2-2: citation 未命中页码范围"]


def test_evaluate_answer_case_reports_missing_answer_terms(tmp_path: Path) -> None:
    answerable_case = _answerable_case()
    dataset = _dataset(tmp_path, [answerable_case])
    result = _search_result(tmp_path, page_start=2, page_end=2)
    answer = _answer(
        question=answerable_case.question,
        text="The cited evidence supports a different wording. [paper.pdf, p.2]",
        citations=[_citation_from_result(result)],
    )

    metrics = evaluate_answer_case(
        dataset=dataset,
        case=answerable_case,
        answer=answer,
        results=[result],
    )

    assert not metrics.passed
    assert not metrics.answer_terms_hit
    assert metrics.missing_answer_terms == ["alpha"]
    assert metrics.failed_reasons == ["缺少答案词 alpha"]


def test_evaluate_answer_case_passes_unanswerable_refusal(tmp_path: Path) -> None:
    unanswerable_case = _unanswerable_case()
    dataset = _dataset(tmp_path, [unanswerable_case])
    answer = _answer(
        question=unanswerable_case.question,
        text="不足以回答：当前检索到的证据不足以支持可靠答案。",
        citations=[],
        insufficient=True,
    )

    metrics = evaluate_answer_case(
        dataset=dataset,
        case=unanswerable_case,
        answer=answer,
        results=[],
    )

    assert metrics.passed
    assert metrics.refused
    assert metrics.citation_absent
    assert metrics.answer_terms_hit


def test_evaluate_answer_case_fails_unanswerable_with_citation(tmp_path: Path) -> None:
    unanswerable_case = _unanswerable_case()
    dataset = _dataset(tmp_path, [unanswerable_case])
    result = _search_result(tmp_path, page_start=2, page_end=2)
    answer = _answer(
        question=unanswerable_case.question,
        text="alpha is incorrectly answered. [paper.pdf, p.2]",
        citations=[_citation_from_result(result)],
    )

    metrics = evaluate_answer_case(
        dataset=dataset,
        case=unanswerable_case,
        answer=answer,
        results=[result],
    )

    assert not metrics.passed
    assert not metrics.refused
    assert metrics.citation_present
    assert metrics.failed_reasons == [
        "不可回答问题未拒答",
        "不可回答问题不应返回 citation",
        "缺少拒答词 不足以回答",
    ]


def test_summarize_answer_metrics_counts_answer_and_refusal_success(
    tmp_path: Path,
) -> None:
    passed_answerable = _answerable_case(case_id="case_answerable_pass")
    failed_answerable = _answerable_case(case_id="case_answerable_fail")
    unanswerable_case = _unanswerable_case()
    dataset = _dataset(tmp_path, [passed_answerable, failed_answerable, unanswerable_case])
    result = _search_result(tmp_path, page_start=2, page_end=2)
    passed_metrics = evaluate_answer_case(
        dataset=dataset,
        case=passed_answerable,
        answer=_answer(
            question=passed_answerable.question,
            text="alpha answer. [paper.pdf, p.2]",
            citations=[_citation_from_result(result)],
        ),
        results=[result],
    )
    failed_metrics = evaluate_answer_case(
        dataset=dataset,
        case=failed_answerable,
        answer=_answer(
            question=failed_answerable.question,
            text="wrong answer. [paper.pdf, p.2]",
            citations=[_citation_from_result(result)],
        ),
        results=[result],
    )
    refusal_metrics = evaluate_answer_case(
        dataset=dataset,
        case=unanswerable_case,
        answer=_answer(
            question=unanswerable_case.question,
            text="不足以回答：当前检索到的证据不足以支持可靠答案。",
            citations=[],
            insufficient=True,
        ),
        results=[],
    )

    summary = summarize_answer_metrics([passed_metrics, failed_metrics, refusal_metrics])

    assert summary.answerable_case_count == 2
    assert summary.answer_success_count == 1
    assert summary.answer_success_rate == 0.5
    assert summary.unanswerable_case_count == 1
    assert summary.refusal_success_count == 1
    assert summary.refusal_success_rate == 1.0
    assert summary.citation_case_count == 2
    assert summary.citation_hit_count == 2
    assert summary.answer_terms_hit_count == 2
    assert summary.failed_case_ids == ["case_answerable_fail"]


def _answerable_case(case_id: str = "case_answerable") -> EvalCase:
    """创建一个需要答案词和 citation 同时命中的可回答 case。"""
    return EvalCase(
        id=case_id,
        question="What evidence is present?",
        answerable=True,
        evidence=[
            EvalEvidence(
                doc_key="paper",
                page_start=2,
                page_end=2,
                terms=["alpha"],
            )
        ],
        answer_terms=["alpha"],
    )


def _unanswerable_case() -> EvalCase:
    """创建一个应当拒答且不应返回 citation 的不可回答 case。"""
    return EvalCase(
        id="case_unanswerable",
        question="What is outside the corpus?",
        answerable=False,
        evidence=[],
        answer_terms=["不足以回答"],
    )


def _dataset(tmp_path: Path, cases: list[EvalCase]) -> EvalDataset:
    """创建带有单个文档短键的内存评测集。"""
    return EvalDataset(
        path=tmp_path / "golden.jsonl",
        documents_path=tmp_path / "golden.documents.json",
        project_root=tmp_path,
        cases=cases,
        documents={
            "paper": EvalDocument(
                key="paper",
                source_path=tmp_path / "paper.pdf",
            )
        },
    )


def _search_result(
    tmp_path: Path,
    *,
    page_start: int,
    page_end: int,
) -> SearchResult:
    """创建一个可被 answer 指标用于 citation 溯源的检索结果。"""
    document = Document(
        id="doc_1",
        tenant_id="eval",
        source_uri=str(tmp_path / "paper.pdf"),
        file_name="paper.pdf",
        page_count=10,
    )
    chunk = Chunk(
        id=f"chunk_{page_start}_{page_end}",
        document_id=document.id,
        document_version_id="version_1",
        text="alpha evidence beta",
        page_start=page_start,
        page_end=page_end,
        chunk_index=0,
        metadata={"tenant_id": "eval"},
    )
    return SearchResult(chunk=chunk, document=document, score=0.9)


def _citation_from_result(result: SearchResult) -> Citation:
    """按生产代码的 citation 结构创建测试引用。"""
    document = result.document
    file_name = document.file_name if document is not None else result.chunk.document_id
    return Citation(
        document_id=result.chunk.document_id,
        document_version_id=result.chunk.document_version_id,
        chunk_id=result.chunk.id,
        file_name=file_name,
        page_start=result.chunk.page_start,
        page_end=result.chunk.page_end,
        snippet=result.chunk.text,
    )


def _answer(
    *,
    question: str,
    text: str,
    citations: list[Citation],
    insufficient: bool = False,
) -> Answer:
    """创建一个用于指标评测的结构化答案。"""
    return Answer(
        question=question,
        answer=text,
        citations=citations,
        evidence_chunk_ids=[citation.chunk_id for citation in citations],
        model_name="test-answer-generator",
        insufficient_evidence=insufficient,
    )
