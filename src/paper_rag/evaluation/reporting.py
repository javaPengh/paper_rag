"""评测报告输出工具。

本模块把一次 eval 运行结果转换成稳定的 JSON report。报告结构刻意按业务指标
分层，而不是直接暴露内部 Pydantic 对象，方便后续用同一份报告做回归对比、
脚本分析或人工排查失败样本。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paper_rag.evaluation.runner import EvalCaseRunResult, EvalRunResult

REPORT_SCHEMA_VERSION = 1


def build_eval_json_report(result: EvalRunResult) -> dict[str, Any]:
    """把评测运行结果转换为可持久化的 JSON report 字典。"""
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset": {
            "path": str(result.dataset.path),
            "documents_path": str(result.dataset.documents_path),
            "case_count": result.case_count,
        },
        "run": {
            "source_dir": str(result.source_dir),
            "index_dir": str(result.index_dir),
            "tenant_id": result.tenant_id,
            "top_k": result.top_k,
            "rag_config": result.rag_config.model_dump(mode="json"),
            "index": {
                "status": result.index_result.status.status,
                "document_count": result.index_result.status.document_count,
                "chunk_count": result.index_result.status.chunk_count,
                "indexed_chunk_count": result.index_result.indexed_chunk_count,
            },
        },
        "summary": {
            "case_count": result.case_count,
            "error_count": result.error_count,
            "retrieval": result.retrieval_summary.model_dump(mode="json"),
            "answer": {
                "case_count": result.answer_summary.answerable_case_count,
                "success_count": result.answer_summary.answer_success_count,
                "success_rate": result.answer_summary.answer_success_rate,
                "answer_terms_case_count": result.answer_summary.answer_terms_case_count,
                "answer_terms_hit_count": result.answer_summary.answer_terms_hit_count,
                "answer_terms_hit_rate": result.answer_summary.answer_terms_hit_rate,
            },
            "citation": {
                "case_count": result.answer_summary.citation_case_count,
                "hit_count": result.answer_summary.citation_hit_count,
                "hit_rate": result.answer_summary.citation_hit_rate,
            },
            "refusal": {
                "case_count": result.answer_summary.unanswerable_case_count,
                "success_count": result.answer_summary.refusal_success_count,
                "success_rate": result.answer_summary.refusal_success_rate,
            },
            "failed_case_ids": {
                "retrieval": result.retrieval_summary.missed_case_ids,
                "answer": result.answer_summary.failed_case_ids,
            },
        },
        "cases": [_case_report(case_result) for case_result in result.case_results],
    }


def write_eval_json_report(result: EvalRunResult, report_path: Path) -> Path:
    """把评测 JSON report 写入指定路径，并返回实际写入路径。"""
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = build_eval_json_report(result)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _case_report(case_result: EvalCaseRunResult) -> dict[str, Any]:
    """把单条 case 结果转换成报告中的 case-level 明细。"""
    return {
        "id": case_result.case_id,
        "question": case_result.question,
        "answerable": case_result.answerable,
        "status": "error" if case_result.error else "ok",
        "error": case_result.error,
        "retrieval_state": _retrieval_state(case_result),
        "answer_state": _answer_state(case_result),
        "retrieved_chunk_ids": case_result.retrieved_chunk_ids,
        "used_chunk_ids": case_result.used_chunk_ids,
        "citation_labels": case_result.citation_labels,
        "insufficient_evidence": case_result.insufficient_evidence,
        "answer_text": case_result.answer_text,
        "retrieval_metrics": (
            case_result.retrieval_metrics.model_dump(mode="json")
            if case_result.retrieval_metrics is not None
            else None
        ),
        "answer_metrics": (
            case_result.answer_metrics.model_dump(mode="json")
            if case_result.answer_metrics is not None
            else None
        ),
        "failures": {
            "retrieval": (
                case_result.retrieval_metrics.missed_reasons
                if case_result.retrieval_metrics is not None
                else []
            ),
            "answer": (
                case_result.answer_metrics.failed_reasons
                if case_result.answer_metrics is not None
                else []
            ),
        },
    }


def _retrieval_state(case_result: EvalCaseRunResult) -> str:
    """返回报告中使用的单条 case retrieval 状态。"""
    metrics = case_result.retrieval_metrics
    if metrics is None:
        return "unknown"
    if metrics.hit_at_k is None:
        return metrics.expectation
    return "hit" if metrics.hit_at_k else "miss"


def _answer_state(case_result: EvalCaseRunResult) -> str:
    """返回报告中使用的单条 case answer 状态。"""
    metrics = case_result.answer_metrics
    if metrics is None:
        return "unknown"
    return "pass" if metrics.passed else "fail"
