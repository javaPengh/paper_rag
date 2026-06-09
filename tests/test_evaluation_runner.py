"""评测运行器与 `paper-rag eval` 命令测试。"""

from __future__ import annotations

import json
import os
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
