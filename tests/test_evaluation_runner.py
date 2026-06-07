"""评测运行器和 `paper-rag eval` 命令的测试。

这些测试使用临时 PDF、临时 golden dataset 和本地 hash embedding，验证第 4 阶段
runner 能够构建或复用索引，并对每个 eval case 执行检索、检索指标和答案生成。
同时验证第 6 阶段的 answer、citation 与 refusal 指标会进入整体评测结果。
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from paper_rag.cli import app
from paper_rag.embeddings import HashEmbeddingClient
from paper_rag.evaluation import EvalRunConfig, run_evaluation
from paper_rag.qa import ExtractiveAnswerGenerator

PDF_TEXT = (
    "Paper RAG indexes local PDF papers, splits pages into chunks, "
    "creates embeddings, and stores vectors in a local Chroma index. "
    "The workflow returns citation-backed answers for retrieved evidence."
)


def test_run_evaluation_local_builds_index_and_runs_cases(tmp_path: Path) -> None:
    source_dir, dataset_path, index_dir = _write_eval_fixture(tmp_path)

    result = run_evaluation(
        EvalRunConfig(
            dataset_path=dataset_path,
            source_dir=source_dir,
            index_dir=index_dir,
            tenant_id="eval_test",
            top_k=2,
            chunk_size=120,
            chunk_overlap=20,
        ),
        embedding_client=HashEmbeddingClient(),
        answer_generator=ExtractiveAnswerGenerator(),
    )

    assert result.index_result.status.status == "ready"
    assert result.index_result.status.document_count == 1
    assert result.case_count == 2
    assert result.error_count == 0
    assert result.retrieval_summary.answerable_case_count == 1
    assert result.retrieval_summary.answerable_hit_count == 1
    assert result.retrieval_summary.unanswerable_case_count == 1
    assert result.retrieval_summary.missed_case_ids == []
    assert result.answer_summary.answerable_case_count == 1
    assert result.answer_summary.answer_success_count == 1
    assert result.answer_summary.unanswerable_case_count == 1
    assert result.answer_summary.refusal_success_count == 1
    assert result.answer_summary.citation_hit_count == 1
    assert result.answer_summary.failed_case_ids == []

    answerable_result = result.case_results[0]
    assert answerable_result.case_id == "case_answerable"
    assert answerable_result.retrieval_metrics is not None
    assert answerable_result.retrieval_metrics.hit_at_k is True
    assert answerable_result.answer_metrics is not None
    assert answerable_result.answer_metrics.passed
    assert answerable_result.answer_metrics.citation_evidence_hit is True
    assert answerable_result.retrieved_chunk_ids
    assert answerable_result.citation_labels
    assert not answerable_result.insufficient_evidence

    unanswerable_result = result.case_results[1]
    assert unanswerable_result.case_id == "case_unanswerable"
    assert unanswerable_result.retrieval_metrics is not None
    assert unanswerable_result.retrieval_metrics.hit_at_k is None
    assert unanswerable_result.answer_metrics is not None
    assert unanswerable_result.answer_metrics.passed
    assert unanswerable_result.answer_metrics.refused
    assert unanswerable_result.insufficient_evidence


def test_cli_eval_runs_local_evaluation(tmp_path: Path) -> None:
    source_dir, dataset_path, index_dir = _write_eval_fixture(tmp_path)
    report_path = tmp_path / "reports" / "eval_report.json"

    result = CliRunner().invoke(
        app,
        [
            "eval",
            str(dataset_path),
            "--source-dir",
            str(source_dir),
            "--index-dir",
            str(index_dir),
            "--tenant-id",
            "eval_test",
            "--local",
            "--top-k",
            "2",
            "--chunk-size",
            "120",
            "--chunk-overlap",
            "20",
            "--report-json",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "评测运行:" in result.output
    assert "样本数: 2" in result.output
    assert "样本错误数: 0" in result.output
    assert "检索 hit@2: 1/1 (100.00%)" in result.output
    assert "回答成功率: 1/1 (100.00%)" in result.output
    assert "拒答成功率: 1/1 (100.00%)" in result.output
    assert "引用命中率: 1/1 (100.00%)" in result.output
    assert "失败答案样本:\n- 无" in result.output
    assert "未命中检索样本:\n- 无" in result.output
    assert f"JSON report: {report_path}" in result.output
    assert "case_answerable 状态=ok retrieval=hit answer=pass" in result.output
    assert "case_unanswerable 状态=ok retrieval=diagnostic answer=pass" in result.output

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert report["summary"]["retrieval"]["answerable_hit_count"] == 1
    assert report["summary"]["answer"]["success_count"] == 1
    assert report["summary"]["citation"]["hit_count"] == 1
    assert report["summary"]["refusal"]["success_count"] == 1
    assert report["summary"]["failed_case_ids"] == {"retrieval": [], "answer": []}
    assert report["run"]["rag_config"]["reader"]["id"] == "pdf_reader"
    assert report["run"]["rag_config"]["chunker"]["id"] == "token_window_chunker"
    assert report["run"]["rag_config"]["embedder"]["id"] == "hash_embedder"
    assert report["run"]["rag_config"]["retriever"]["id"] == "vector_retriever"
    assert report["run"]["rag_config"]["generator"]["id"] == "extractive_generator"
    assert report["run"]["rag_config"]["chunker"]["parameters"]["chunk_size"] == 120
    assert report["cases"][0]["id"] == "case_answerable"
    assert report["cases"][0]["retrieval_state"] == "hit"
    assert report["cases"][0]["answer_state"] == "pass"
    assert report["cases"][0]["failures"] == {"retrieval": [], "answer": []}


def _write_eval_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """写入本地评测需要的 PDF、dataset、documents mapping 和 index 目录。"""
    source_dir = tmp_path / "papers"
    dataset_dir = tmp_path / "datasets"
    index_dir = tmp_path / "eval_index"
    source_pdf = _write_test_pdf(source_dir / "paper_rag_eval.pdf")
    dataset_dir.mkdir(parents=True, exist_ok=True)

    documents_path = dataset_dir / "golden.documents.json"
    documents_path.write_text(
        json.dumps(
            {
                "paper": {
                    "source_path": source_pdf.as_posix(),
                    "notes": "临时评测 PDF",
                }
            }
        ),
        encoding="utf-8",
    )

    dataset_path = dataset_dir / "golden.jsonl"
    dataset_path.write_text(
        "\n".join(
            json.dumps(case, ensure_ascii=False)
            for case in [
                {
                    "id": "case_answerable",
                    "question": "What does Paper RAG index?",
                    "answerable": True,
                    "evidence": [
                        {
                            "doc_key": "paper",
                            "page_start": 1,
                            "page_end": 1,
                            "terms": ["Paper RAG", "local PDF papers"],
                        }
                    ],
                    "answer_terms": ["PDF", "index"],
                    "reference_answer": "Paper RAG indexes local PDF papers.",
                    "notes": "",
                },
                {
                    "id": "case_unanswerable",
                    "question": "What is the capital of France?",
                    "answerable": False,
                    "evidence": [],
                    "answer_terms": ["不足以回答"],
                    "reference_answer": "不足以回答。",
                    "notes": "",
                },
            ]
        ),
        encoding="utf-8",
    )
    return source_dir, dataset_path, index_dir


def _write_test_pdf(path: Path) -> Path:
    """创建一个只包含一页文本的临时 PDF，用于本地 eval 流程测试。"""
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 520, 260), PDF_TEXT, fontsize=11)
    document.save(path)
    document.close()
    return path
