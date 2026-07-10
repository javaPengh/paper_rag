"""评测运行器与 `paper-rag eval` 命令测试。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from paper_rag.cli import app
from paper_rag.embeddings import HashEmbeddingClient
from paper_rag.evaluation import (
    EvalJudgeConfig,
    EvalRunConfig,
    JudgeOnlyConfig,
    build_eval_json_report,
    run_evaluation,
    run_judge_only,
)
from paper_rag.qa import ExtractiveAnswerGenerator

PDF_TEXT = (
    "Paper RAG indexes local PDF papers, splits pages into chunks, "
    "creates embeddings, and stores vectors in a local Chroma index. "
    "The workflow returns citation-backed answers for retrieved evidence."
)


class _FakeJudgeGenerator:
    """带 chat_client 的假生成器，用于 CLI judge-only 测试。"""

    def __init__(self) -> None:
        """提供 eval-judge 需要复用的聊天客户端。"""
        self.chat_client = _FakeJudgeClient()


class _FakeJudgeClient:
    """返回固定 judge JSON 的测试客户端，避免 runner 测试调用真实模型。"""

    model_name = "fake-judge"
    source_name = "fake"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """返回通过 judge 的最小结构化响应。"""
        assert "JSON" in system_prompt
        assert "evaluation_requirements" in user_prompt
        return json.dumps(
            {
                "passed": True,
                "score": 1.0,
                "requirement_results": [
                    {
                        "requirement": "Answer states that Paper RAG indexes local PDF papers.",
                        "passed": True,
                        "reason": "The answer covers the expected point.",
                    }
                ],
                "hallucination_risk": "low",
                "overall_reason": "The answer satisfies the requirement.",
            }
        )


def test_run_evaluation_keeps_rag_config_for_legacy_local_components(tmp_path: Path) -> None:
    """确认评测报告仍能记录遗留本地组件的配置快照。"""
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
    assert result.case_count == 2
    assert result.error_count == 0
    assert result.rag_config.embedder.id == "hash_embedder"
    assert result.rag_config.embedder.source == "local"
    assert result.rag_config.generator.id == "extractive_generator"
    assert result.rag_config.generator.source == "local"


def test_run_evaluation_filters_case_ids(tmp_path: Path) -> None:
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
            case_ids=["case_answerable"],
        ),
        embedding_client=HashEmbeddingClient(),
        answer_generator=ExtractiveAnswerGenerator(),
    )

    assert result.case_count == 1
    assert result.dataset.case_ids == ["case_answerable"]
    assert [case.case_id for case in result.case_results] == ["case_answerable"]
    assert result.retrieval_summary.answerable_case_count == 1


def test_run_evaluation_records_judge_metrics_and_report(tmp_path: Path) -> None:
    """启用 judge 时，runner 应单独汇总语义指标并写入 schema v3 report。"""
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
            case_ids=["case_answerable"],
            judge_config=EvalJudgeConfig(enabled=True, source="fake", model="fake-judge"),
        ),
        embedding_client=HashEmbeddingClient(),
        answer_generator=ExtractiveAnswerGenerator(),
        judge_client=_FakeJudgeClient(),
    )

    report = build_eval_json_report(result)

    assert result.judge_summary.enabled is True
    assert result.judge_summary.case_count == 1
    assert result.judge_summary.passed_count == 1
    assert result.case_results[0].judge_metrics is not None
    assert report["schema_version"] == 3
    assert report["run"]["judge"]["source"] == "fake"
    assert report["summary"]["judge"]["passed_count"] == 1
    assert report["cases"][0]["judge_metrics"]["passed"] is True


def test_run_judge_only_uses_existing_report_answer(tmp_path: Path) -> None:
    """judge-only 应读取已有 report 的答案文本，而不是重新执行 RAG 链路。"""
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
            case_ids=["case_answerable"],
        ),
        embedding_client=HashEmbeddingClient(),
        answer_generator=ExtractiveAnswerGenerator(),
    )
    report_path = tmp_path / "base_report.json"
    report_path.write_text(
        json.dumps(build_eval_json_report(result), ensure_ascii=False),
        encoding="utf-8",
    )

    judge_result = run_judge_only(
        JudgeOnlyConfig(
            input_report_path=report_path,
            dataset_path=dataset_path,
            case_ids=["case_answerable"],
            judge_source="fake",
            judge_model="fake-judge",
        ),
        judge_client=_FakeJudgeClient(),
    )

    assert judge_result.report["run"]["judge"]["mode"] == "judge_only"
    assert judge_result.report["summary"]["judge"]["passed_count"] == 1
    assert judge_result.report["cases"][0]["judge_metrics"]["passed"] is True


def test_cli_eval_judge_writes_judge_only_report(tmp_path: Path, monkeypatch) -> None:
    """eval-judge 命令应只 judge 既有 report，并写出 judge-only report。"""
    source_dir, dataset_path, index_dir = _write_eval_fixture(tmp_path)
    base_result = run_evaluation(
        EvalRunConfig(
            dataset_path=dataset_path,
            source_dir=source_dir,
            index_dir=index_dir,
            tenant_id="eval_test",
            top_k=2,
            chunk_size=120,
            chunk_overlap=20,
            case_ids=["case_answerable"],
        ),
        embedding_client=HashEmbeddingClient(),
        answer_generator=ExtractiveAnswerGenerator(),
    )
    input_report = tmp_path / "base_report.json"
    output_report = tmp_path / "judge_only_report.json"
    input_report.write_text(
        json.dumps(build_eval_json_report(base_result), ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr("paper_rag.cli._make_answer_generator", lambda **_: _FakeJudgeGenerator())

    result = CliRunner().invoke(
        app,
        [
            "eval-judge",
            str(input_report),
            "--dataset",
            str(dataset_path),
            "--case-id",
            "case_answerable",
            "--chat-source",
            "fake",
            "--chat-model",
            "fake-judge",
            "--report-json",
            str(output_report),
        ],
    )

    assert result.exit_code == 0
    assert "Judge-only 运行" in result.output
    written = json.loads(output_report.read_text(encoding="utf-8"))
    assert written["run"]["judge"]["mode"] == "judge_only"
    assert written["summary"]["judge"]["passed_count"] == 1


def test_cli_eval_accepts_judge_and_case_id_options(tmp_path: Path) -> None:
    """CLI 应接受 --judge 与 --case-id；缺模型配置时仍在组件配置阶段明确失败。"""
    source_dir, dataset_path, index_dir = _write_eval_fixture(tmp_path)

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
            "--judge",
            "--case-id",
            "case_answerable",
        ],
        env=_empty_model_env(),
    )

    assert result.exit_code != 0
    assert "No such option" not in result.output
    assert "缺少 embedding 模型来源" in result.output


def test_cli_eval_requires_external_model_config(tmp_path: Path) -> None:
    """确认 CLI 评测不会再提供本地模式兜底。"""
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
            "--top-k",
            "2",
            "--chunk-size",
            "120",
            "--chunk-overlap",
            "20",
            "--report-json",
            str(report_path),
        ],
        env=_empty_model_env(),
    )

    assert result.exit_code != 0
    assert "缺少 embedding 模型来源" in result.output
    assert not report_path.exists()


def _write_eval_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """写入本地评测需要的 PDF、dataset 与索引目录。"""
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
                    "evaluation_requirements": [
                        "Answer states that Paper RAG indexes local PDF papers."
                    ],
                    "reference_answer": "Paper RAG indexes local PDF papers.",
                    "notes": "",
                },
                {
                    "id": "case_unanswerable",
                    "question": "What is the capital of France?",
                    "answerable": False,
                    "evidence": [],
                    "answer_terms": ["refuse"],
                    "reference_answer": "",
                    "notes": "",
                },
            ]
        ),
        encoding="utf-8",
    )

    return source_dir, dataset_path, index_dir


def _write_test_pdf(path: Path) -> Path:
    """创建一个极小 PDF 夹具，供评测测试使用。"""
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 520, 240), PDF_TEXT, fontsize=11)
    document.save(path)
    document.close()
    return path


def _empty_model_env() -> dict[str, str]:
    """构造不包含模型配置的最小评测命令环境变量集合。"""
    env = dict(os.environ)
    for key in [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_EMBEDDING_MODELS",
        "OPENAI_CHAT_MODELS",
        "SILICONFLOW_API_KEY",
        "SILICONFLOW_BASE_URL",
        "SILICONFLOW_EMBEDDING_MODELS",
        "SILICONFLOW_CHAT_MODELS",
        "EMBEDDING_SOURCE",
        "EMBEDDING_MODEL",
        "CHAT_SOURCE",
        "CHAT_MODEL",
        "PAPER_RAG_EMBEDDING_MODEL",
        "PAPER_RAG_LLM_MODEL",
    ]:
        env.pop(key, None)
    env["PAPER_RAG_ENV_FILE"] = str(Path.cwd() / ".missing-test.env")
    return env
