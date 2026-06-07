"""答案、引用和拒答的确定性评测指标。

本模块评估 answer generation 之后的结构化结果，不判断检索排序本身是否足够好。
可回答题要求生成有效答案并引用人工 evidence；不可回答题要求返回有依据拒答且
不携带 citation。这样可以把“找没找到证据”和“拿到证据后是否正确作答”拆开看。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from paper_rag.evaluation.dataset import EvalCase, EvalDataset, EvalEvidence
from paper_rag.evaluation.matching import (
    document_matches,
    file_name_matches_source,
    page_ranges_overlap,
)
from paper_rag.schemas import Answer, Citation, SearchResult


class CitationEvidenceMatch(BaseModel):
    """一组 expected evidence 在答案 citation 中的命中情况。"""

    doc_key: str = Field(description="当前 evidence 标注的评测文档短键。")
    page_start: int = Field(description="当前 evidence 标注的起始页。")
    page_end: int = Field(description="当前 evidence 标注的结束页。")
    doc_hit: bool = Field(description="答案 citation 是否命中对应文档。")
    page_hit: bool = Field(description="答案 citation 是否命中对应文档中的期望页码范围。")
    hit: bool = Field(description="答案 citation 是否同时命中文档和页码范围。")
    matched_citation_labels: list[str] = Field(
        default_factory=list,
        description="命中该 evidence 页码范围的 citation 标签。",
    )
    matched_chunk_ids: list[str] = Field(
        default_factory=list,
        description="命中该 evidence 页码范围的 citation chunk ID。",
    )


class AnswerCaseMetrics(BaseModel):
    """单条 eval case 的 answer、citation 与 refusal 指标结果。"""

    case_id: str = Field(description="对应 golden dataset 中的稳定 case ID。")
    answerable: bool = Field(description="该 case 是否应当可回答。")
    expectation: str = Field(
        description="answer 期望类型；可回答题为 answer_required，不可回答题为 refusal_required。",
    )
    answer_generated: bool = Field(description="答案生成阶段是否返回了 Answer 对象。")
    answered: bool = Field(description="可回答题是否生成了非拒答答案。")
    refused: bool = Field(description="答案生成器是否返回有依据拒答。")
    citation_present: bool = Field(description="答案结构化结果中是否包含 citation。")
    citation_absent: bool = Field(description="答案结构化结果中是否没有 citation。")
    citation_evidence_hit: bool | None = Field(
        default=None,
        description="可回答题的 citation 是否覆盖全部 expected evidence；不可回答题不计入。",
    )
    citation_matches: list[CitationEvidenceMatch] = Field(
        default_factory=list,
        description="每组 expected evidence 的 citation 命中明细。",
    )
    answer_terms_hit: bool = Field(description="答案文本是否覆盖全部 answer_terms。")
    missing_answer_terms: list[str] = Field(
        default_factory=list,
        description="答案文本中未覆盖的 answer_terms。",
    )
    passed: bool = Field(description="该 case 是否满足当前 answer/citation/refusal 评测口径。")
    failed_reasons: list[str] = Field(
        default_factory=list,
        description="未通过时的人类可读失败原因。",
    )


class AnswerMetricSummary(BaseModel):
    """一组 eval cases 的 answer、citation 与 refusal 指标汇总。"""

    answerable_case_count: int = Field(ge=0, description="应当回答的 case 数量。")
    answer_success_count: int = Field(ge=0, description="可回答 case 中成功回答的数量。")
    answer_success_rate: float = Field(
        description="answer_success_count / answerable_case_count。",
    )
    unanswerable_case_count: int = Field(ge=0, description="应当拒答的 case 数量。")
    refusal_success_count: int = Field(ge=0, description="不可回答 case 中正确拒答的数量。")
    refusal_success_rate: float = Field(
        description="refusal_success_count / unanswerable_case_count。",
    )
    citation_case_count: int = Field(ge=0, description="需要 citation 覆盖证据的 case 数量。")
    citation_hit_count: int = Field(ge=0, description="citation 命中全部 evidence 的数量。")
    citation_hit_rate: float = Field(description="citation_hit_count / citation_case_count。")
    answer_terms_case_count: int = Field(ge=0, description="检查 answer_terms 的 case 数量。")
    answer_terms_hit_count: int = Field(ge=0, description="答案覆盖全部 answer_terms 的数量。")
    answer_terms_hit_rate: float = Field(
        description="answer_terms_hit_count / answer_terms_case_count。",
    )
    failed_case_ids: list[str] = Field(
        default_factory=list,
        description="answer/citation/refusal 指标未通过的 case ID 列表。",
    )


def evaluate_answer_case(
    *,
    dataset: EvalDataset,
    case: EvalCase,
    answer: Answer | None,
    results: list[SearchResult],
) -> AnswerCaseMetrics:
    """评估单条 case 的答案、引用和拒答是否满足 golden dataset 预期。"""
    answer_text = answer.answer if answer is not None else ""
    citations = answer.citations if answer is not None else []
    refused = answer.insufficient_evidence if answer is not None else False
    answer_generated = answer is not None
    answered = answer_generated and bool(answer_text.strip()) and not refused
    citation_present = bool(citations)
    missing_answer_terms = _missing_terms(answer_text, case.answer_terms)
    citation_matches = [
        _evaluate_citation_evidence(
            dataset=dataset,
            evidence=evidence,
            citations=citations,
            results=results,
        )
        for evidence in case.evidence
    ]
    citation_evidence_hit = None
    if case.answerable:
        citation_evidence_hit = bool(citation_matches) and all(
            match.hit for match in citation_matches
        )

    metrics = AnswerCaseMetrics(
        case_id=case.id,
        answerable=case.answerable,
        expectation="answer_required" if case.answerable else "refusal_required",
        answer_generated=answer_generated,
        answered=answered,
        refused=refused,
        citation_present=citation_present,
        citation_absent=not citation_present,
        citation_evidence_hit=citation_evidence_hit,
        citation_matches=citation_matches,
        answer_terms_hit=not missing_answer_terms,
        missing_answer_terms=missing_answer_terms,
        passed=False,
        failed_reasons=[],
    )
    failed_reasons = _failed_reasons(metrics)
    return metrics.model_copy(
        update={
            "passed": not failed_reasons,
            "failed_reasons": failed_reasons,
        }
    )


def summarize_answer_metrics(case_metrics: list[AnswerCaseMetrics]) -> AnswerMetricSummary:
    """汇总 answer、citation 与 refusal 指标。"""
    answerable_metrics = [item for item in case_metrics if item.answerable]
    unanswerable_metrics = [item for item in case_metrics if not item.answerable]
    answerable_case_count = len(answerable_metrics)
    unanswerable_case_count = len(unanswerable_metrics)
    answer_success_count = sum(1 for item in answerable_metrics if item.passed)
    refusal_success_count = sum(1 for item in unanswerable_metrics if item.passed)
    citation_hit_count = sum(1 for item in answerable_metrics if item.citation_evidence_hit)
    answer_terms_hit_count = sum(1 for item in case_metrics if item.answer_terms_hit)

    return AnswerMetricSummary(
        answerable_case_count=answerable_case_count,
        answer_success_count=answer_success_count,
        answer_success_rate=_safe_rate(answer_success_count, answerable_case_count),
        unanswerable_case_count=unanswerable_case_count,
        refusal_success_count=refusal_success_count,
        refusal_success_rate=_safe_rate(refusal_success_count, unanswerable_case_count),
        citation_case_count=answerable_case_count,
        citation_hit_count=citation_hit_count,
        citation_hit_rate=_safe_rate(citation_hit_count, answerable_case_count),
        answer_terms_case_count=len(case_metrics),
        answer_terms_hit_count=answer_terms_hit_count,
        answer_terms_hit_rate=_safe_rate(answer_terms_hit_count, len(case_metrics)),
        failed_case_ids=[item.case_id for item in case_metrics if not item.passed],
    )


def _evaluate_citation_evidence(
    *,
    dataset: EvalDataset,
    evidence: EvalEvidence,
    citations: list[Citation],
    results: list[SearchResult],
) -> CitationEvidenceMatch:
    """评估一组 expected evidence 是否被答案 citation 命中。"""
    doc_citations = [
        citation
        for citation in citations
        if _citation_matches_doc(dataset, evidence.doc_key, citation, results)
    ]
    page_citations = [
        citation
        for citation in doc_citations
        if page_ranges_overlap(
            citation.page_start,
            citation.page_end,
            evidence.page_start,
            evidence.page_end,
        )
    ]

    return CitationEvidenceMatch(
        doc_key=evidence.doc_key,
        page_start=evidence.page_start,
        page_end=evidence.page_end,
        doc_hit=bool(doc_citations),
        page_hit=bool(page_citations),
        hit=bool(page_citations),
        matched_citation_labels=[citation.label for citation in page_citations],
        matched_chunk_ids=[citation.chunk_id for citation in page_citations],
    )


def _citation_matches_doc(
    dataset: EvalDataset,
    doc_key: str,
    citation: Citation,
    results: list[SearchResult],
) -> bool:
    """判断 citation 是否对应某个 expected evidence 的文档短键。"""
    result = _result_for_citation(citation, results)
    if result is not None and document_matches(dataset, doc_key, result.document):
        return True
    return file_name_matches_source(dataset, doc_key, citation.file_name)


def _result_for_citation(
    citation: Citation,
    results: list[SearchResult],
) -> SearchResult | None:
    """从检索结果中找到生成该 citation 的来源 chunk。"""
    for result in results:
        if result.chunk.id == citation.chunk_id:
            return result
    for result in results:
        if result.chunk.document_id != citation.document_id:
            continue
        if page_ranges_overlap(
            result.chunk.page_start,
            result.chunk.page_end,
            citation.page_start,
            citation.page_end,
        ):
            return result
    return None


def _missing_terms(answer_text: str, expected_terms: list[str]) -> list[str]:
    """返回答案文本中未覆盖的 answer_terms。"""
    normalized_answer = answer_text.casefold()
    return [term for term in expected_terms if term.casefold() not in normalized_answer]


def _failed_reasons(metrics: AnswerCaseMetrics) -> list[str]:
    """把指标未通过的原因压缩成 case-level 可读说明。"""
    if not metrics.answer_generated:
        return ["未生成答案"]

    reasons: list[str] = []
    if metrics.answerable:
        if not metrics.answered:
            reasons.append("可回答问题被拒答或答案为空")
        if not metrics.citation_present:
            reasons.append("缺少 citation")
        if not metrics.answer_terms_hit:
            reasons.append(f"缺少答案词 {', '.join(metrics.missing_answer_terms)}")
        if metrics.citation_evidence_hit is False:
            reasons.extend(_citation_missed_reasons(metrics.citation_matches))
        return reasons

    if not metrics.refused:
        reasons.append("不可回答问题未拒答")
    if not metrics.citation_absent:
        reasons.append("不可回答问题不应返回 citation")
    if not metrics.answer_terms_hit:
        reasons.append(f"缺少拒答词 {', '.join(metrics.missing_answer_terms)}")
    return reasons


def _citation_missed_reasons(citation_matches: list[CitationEvidenceMatch]) -> list[str]:
    """把 citation 未命中 evidence 的原因压缩成可输出文本。"""
    reasons: list[str] = []
    for match in citation_matches:
        prefix = f"{match.doc_key} pp.{match.page_start}-{match.page_end}"
        if not match.doc_hit:
            reasons.append(f"{prefix}: citation 未命中文档")
            continue
        if not match.page_hit:
            reasons.append(f"{prefix}: citation 未命中页码范围")
    if not reasons:
        reasons.append("没有可匹配的 expected evidence")
    return reasons


def _safe_rate(numerator: int, denominator: int) -> float:
    """在分母为零时返回 0，避免汇总输出出现除零错误。"""
    return numerator / denominator if denominator > 0 else 0.0
