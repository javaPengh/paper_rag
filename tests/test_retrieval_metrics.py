"""Retrieval 指标的单元测试。

这些测试只验证检索阶段的确定性判断：文档短键、页码范围、证据锚点词、
answerable 与 unanswerable 的不同统计口径，以及 missed case 汇总。
"""

from pathlib import Path

from paper_rag.evaluation import (
    EvalCase,
    EvalDataset,
    EvalDocument,
    EvalEvidence,
    evaluate_retrieval_case,
    summarize_retrieval_metrics,
)
from paper_rag.schemas import Chunk, Document, SearchResult


def test_evaluate_retrieval_case_hits_doc_page_and_terms(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path, [_answerable_case()])
    result = _search_result(tmp_path, text="alpha evidence beta", page_start=2, page_end=2)

    metrics = evaluate_retrieval_case(
        dataset=dataset,
        case=dataset.cases[0],
        results=[result],
        top_k=3,
    )

    assert metrics.hit_at_k is True
    assert metrics.evidence_matches[0].doc_hit
    assert metrics.evidence_matches[0].page_hit
    assert metrics.evidence_matches[0].terms_hit
    assert metrics.evidence_matches[0].matched_chunk_ids == ["chunk_1"]


def test_evaluate_retrieval_case_reports_page_miss(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path, [_answerable_case()])
    result = _search_result(tmp_path, text="alpha evidence beta", page_start=5, page_end=5)

    metrics = evaluate_retrieval_case(
        dataset=dataset,
        case=dataset.cases[0],
        results=[result],
        top_k=3,
    )

    assert metrics.hit_at_k is False
    assert metrics.evidence_matches[0].doc_hit
    assert not metrics.evidence_matches[0].page_hit
    assert metrics.missed_reasons == ["paper pp.2-2: 未命中页码范围"]


def test_evaluate_retrieval_case_reports_missing_terms(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path, [_answerable_case()])
    result = _search_result(tmp_path, text="alpha evidence only", page_start=2, page_end=2)

    metrics = evaluate_retrieval_case(
        dataset=dataset,
        case=dataset.cases[0],
        results=[result],
        top_k=3,
    )

    assert metrics.hit_at_k is False
    assert metrics.evidence_matches[0].page_hit
    assert not metrics.evidence_matches[0].terms_hit
    assert metrics.evidence_matches[0].missing_terms == ["beta"]
    assert metrics.missed_reasons == ["paper pp.2-2: 缺少证据词 beta"]


def test_summarize_retrieval_metrics_excludes_unanswerable_cases(tmp_path: Path) -> None:
    answerable_case = _answerable_case()
    unanswerable_case = EvalCase(
        id="case_unanswerable",
        question="What is outside the corpus?",
        answerable=False,
        evidence=[],
        answer_terms=["不足以回答"],
    )
    dataset = _dataset(tmp_path, [answerable_case, unanswerable_case])
    hit_result = _search_result(tmp_path, text="alpha evidence beta", page_start=2, page_end=2)

    answerable_metrics = evaluate_retrieval_case(
        dataset=dataset,
        case=answerable_case,
        results=[hit_result],
        top_k=3,
    )
    unanswerable_metrics = evaluate_retrieval_case(
        dataset=dataset,
        case=unanswerable_case,
        results=[],
        top_k=3,
    )
    summary = summarize_retrieval_metrics(
        [answerable_metrics, unanswerable_metrics],
        top_k=3,
    )

    assert unanswerable_metrics.expectation == "diagnostic"
    assert unanswerable_metrics.hit_at_k is None
    assert summary.answerable_case_count == 1
    assert summary.answerable_hit_count == 1
    assert summary.retrieval_hit_rate == 1.0
    assert summary.unanswerable_case_count == 1
    assert summary.missed_case_ids == []


def test_summarize_retrieval_metrics_outputs_missed_case_ids(tmp_path: Path) -> None:
    answerable_case = _answerable_case()
    dataset = _dataset(tmp_path, [answerable_case])
    missed_result = _search_result(tmp_path, text="wrong page", page_start=9, page_end=9)
    metrics = evaluate_retrieval_case(
        dataset=dataset,
        case=answerable_case,
        results=[missed_result],
        top_k=3,
    )

    summary = summarize_retrieval_metrics([metrics], top_k=3)

    assert summary.answerable_case_count == 1
    assert summary.answerable_hit_count == 0
    assert summary.retrieval_hit_rate == 0.0
    assert summary.missed_case_ids == ["case_answerable"]


def _answerable_case() -> EvalCase:
    """创建一个需要命中文档、页码和两个证据词的可回答 case。"""
    return EvalCase(
        id="case_answerable",
        question="What evidence is present?",
        answerable=True,
        evidence=[
            EvalEvidence(
                doc_key="paper",
                page_start=2,
                page_end=2,
                terms=["alpha", "beta"],
            )
        ],
        answer_terms=["alpha"],
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
    text: str,
    page_start: int,
    page_end: int,
) -> SearchResult:
    """创建一个可被 retrieval 指标消费的检索结果。"""
    document = Document(
        id="doc_1",
        tenant_id="eval",
        source_uri=str(tmp_path / "paper.pdf"),
        file_name="paper.pdf",
        page_count=10,
    )
    chunk = Chunk(
        id="chunk_1",
        document_id=document.id,
        document_version_id="version_1",
        text=text,
        page_start=page_start,
        page_end=page_end,
        chunk_index=0,
        metadata={"tenant_id": "eval"},
    )
    return SearchResult(chunk=chunk, document=document, score=0.9)
