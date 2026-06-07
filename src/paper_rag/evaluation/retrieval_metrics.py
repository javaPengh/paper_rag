"""Retrieval 确定性指标。

本模块只评估 retrieval 阶段：Top-k 结果是否命中文档短键、页码范围和证据锚点词。
答案质量、citation 和拒答判断留给后续阶段，避免不同链路问题混在同一个指标里。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from paper_rag.domain import SearchResult
from paper_rag.evaluation.dataset import EvalCase, EvalDataset, EvalEvidence
from paper_rag.evaluation.matching import document_matches, page_ranges_overlap


class RetrievalEvidenceMatch(BaseModel):
    """一组 expected evidence 在 Top-k 检索结果中的命中情况。"""

    doc_key: str = Field(description="当前 evidence 标注的评测文档短键。")
    page_start: int = Field(description="当前 evidence 标注的起始页。")
    page_end: int = Field(description="当前 evidence 标注的结束页。")
    expected_terms: list[str] = Field(description="当前 evidence 标注的期望证据锚点词。")
    doc_hit: bool = Field(description="Top-k 结果是否命中对应文档。")
    page_hit: bool = Field(description="Top-k 结果是否命中对应文档中的期望页码范围。")
    terms_hit: bool = Field(description="命中页码范围内的检索文本是否覆盖全部锚点词。")
    hit: bool = Field(description="文档、页码和锚点词是否全部命中。")
    matched_chunk_ids: list[str] = Field(
        default_factory=list,
        description="命中文档且页码重叠的 chunk ID 列表。",
    )
    missing_terms: list[str] = Field(
        default_factory=list,
        description="在命中页码文本中仍未覆盖的锚点词。",
    )


class RetrievalCaseMetrics(BaseModel):
    """单条 eval case 的 retrieval 指标结果。"""

    case_id: str = Field(description="对应 golden dataset 中的稳定 case ID。")
    answerable: bool = Field(description="该 case 是否应当可回答。")
    expectation: str = Field(
        description="retrieval 期望类型；可回答题为 must_hit，不可回答题为 diagnostic。",
    )
    top_k: int = Field(ge=1, description="本次评测使用的 Top-k 检索数量。")
    retrieved_count: int = Field(ge=0, description="实际返回的检索结果数量。")
    evidence_matches: list[RetrievalEvidenceMatch] = Field(
        default_factory=list,
        description="每组 expected evidence 的检索命中明细。",
    )
    hit_at_k: bool | None = Field(
        default=None,
        description="可回答题是否在 Top-k 中命中全部证据；不可回答题不计入该指标。",
    )
    missed_reasons: list[str] = Field(
        default_factory=list,
        description="可回答题未命中时的人类可读原因。",
    )


class RetrievalMetricSummary(BaseModel):
    """一组 eval cases 的 retrieval 指标汇总。"""

    top_k: int = Field(ge=1, description="汇总对应的 Top-k 设置。")
    answerable_case_count: int = Field(ge=0, description="计入 hit@k 的可回答 case 数量。")
    answerable_hit_count: int = Field(ge=0, description="可回答 case 中 retrieval 命中的数量。")
    retrieval_hit_rate: float = Field(description="answerable_hit_count / answerable_case_count。")
    missed_case_ids: list[str] = Field(
        default_factory=list,
        description="可回答但 retrieval 未命中的 case ID 列表。",
    )
    unanswerable_case_count: int = Field(
        ge=0,
        description="不计入 hit@k、仅保留诊断明细的不可回答 case 数量。",
    )


def evaluate_retrieval_case(
    *,
    dataset: EvalDataset,
    case: EvalCase,
    results: list[SearchResult],
    top_k: int,
) -> RetrievalCaseMetrics:
    """评估单条 case 的 Top-k retrieval 命中情况。"""
    evidence_matches = [
        _evaluate_evidence(dataset=dataset, evidence=evidence, results=results)
        for evidence in case.evidence
    ]
    expectation = "must_hit" if case.answerable else "diagnostic"
    hit_at_k = None
    missed_reasons: list[str] = []

    if case.answerable:
        hit_at_k = bool(evidence_matches) and all(match.hit for match in evidence_matches)
        if not hit_at_k:
            missed_reasons = _missed_reasons(evidence_matches)

    return RetrievalCaseMetrics(
        case_id=case.id,
        answerable=case.answerable,
        expectation=expectation,
        top_k=top_k,
        retrieved_count=len(results),
        evidence_matches=evidence_matches,
        hit_at_k=hit_at_k,
        missed_reasons=missed_reasons,
    )


def summarize_retrieval_metrics(
    case_metrics: list[RetrievalCaseMetrics],
    *,
    top_k: int,
) -> RetrievalMetricSummary:
    """汇总 retrieval hit@k，并把不可回答题从分母中分离出来。"""
    answerable_metrics = [item for item in case_metrics if item.answerable]
    answerable_hit_count = sum(1 for item in answerable_metrics if item.hit_at_k)
    answerable_case_count = len(answerable_metrics)
    hit_rate = (
        answerable_hit_count / answerable_case_count if answerable_case_count > 0 else 0.0
    )
    missed_case_ids = [
        item.case_id
        for item in answerable_metrics
        if item.hit_at_k is False
    ]
    unanswerable_case_count = sum(1 for item in case_metrics if not item.answerable)

    return RetrievalMetricSummary(
        top_k=top_k,
        answerable_case_count=answerable_case_count,
        answerable_hit_count=answerable_hit_count,
        retrieval_hit_rate=hit_rate,
        missed_case_ids=missed_case_ids,
        unanswerable_case_count=unanswerable_case_count,
    )


def _evaluate_evidence(
    *,
    dataset: EvalDataset,
    evidence: EvalEvidence,
    results: list[SearchResult],
) -> RetrievalEvidenceMatch:
    """评估一组 expected evidence 是否被 Top-k 结果命中。"""
    doc_results = [
        result
        for result in results
        if document_matches(dataset, evidence.doc_key, result.document)
    ]
    page_results = [
        result
        for result in doc_results
        if page_ranges_overlap(
            result.chunk.page_start,
            result.chunk.page_end,
            evidence.page_start,
            evidence.page_end,
        )
    ]
    page_text = "\n".join(result.chunk.text for result in page_results).casefold()
    missing_terms = [
        term
        for term in evidence.terms
        if term.casefold() not in page_text
    ]
    doc_hit = bool(doc_results)
    page_hit = bool(page_results)
    terms_hit = bool(page_results) and not missing_terms

    return RetrievalEvidenceMatch(
        doc_key=evidence.doc_key,
        page_start=evidence.page_start,
        page_end=evidence.page_end,
        expected_terms=evidence.terms,
        doc_hit=doc_hit,
        page_hit=page_hit,
        terms_hit=terms_hit,
        hit=doc_hit and page_hit and terms_hit,
        matched_chunk_ids=[result.chunk.id for result in page_results],
        missing_terms=missing_terms,
    )


def _missed_reasons(evidence_matches: list[RetrievalEvidenceMatch]) -> list[str]:
    """把未命中 evidence 的原因压缩成可输出的 case-level 说明。"""
    reasons: list[str] = []
    for match in evidence_matches:
        prefix = f"{match.doc_key} pp.{match.page_start}-{match.page_end}"
        if not match.doc_hit:
            reasons.append(f"{prefix}: 未命中文档")
            continue
        if not match.page_hit:
            reasons.append(f"{prefix}: 未命中页码范围")
            continue
        if not match.terms_hit:
            missing = ", ".join(match.missing_terms)
            reasons.append(f"{prefix}: 缺少证据词 {missing}")
    if not reasons:
        reasons.append("没有可匹配的 expected evidence")
    return reasons
