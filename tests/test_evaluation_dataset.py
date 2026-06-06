"""评测集解析器的单元测试。

这些测试覆盖 golden dataset 的正常加载，以及重复 ID、非法 JSON、证据字段
和文档短键映射等常见人工标注错误，确保评测运行前能尽早失败。
"""

import json
from pathlib import Path

import pytest

from paper_rag.evaluation import load_eval_dataset
from paper_rag.exceptions import EvaluationDatasetError


def test_load_eval_dataset_parses_project_golden_dataset() -> None:
    dataset = load_eval_dataset(Path("eval/datasets/golden.jsonl"))

    assert len(dataset.cases) == 13
    assert dataset.cases[0].id == "golden_001"
    assert dataset.cases[0].evidence[0].doc_key == "think_in_space"
    assert dataset.documents["SIBE-LM"].source_path == Path("eval/papers/SIBE-LM.pdf")


def test_load_eval_dataset_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    dataset_path = tmp_path / "golden.jsonl"
    documents_path = tmp_path / "golden.documents.json"
    source_path = tmp_path / "paper.pdf"
    source_path.write_bytes(b"%PDF-1.7\n%%EOF\n")
    documents_path.write_text(
        json.dumps({"paper": {"source_path": "paper.pdf", "notes": "fixture"}}),
        encoding="utf-8",
    )
    dataset_path.write_text(
        "\n".join(
            [
                "# comment",
                "",
                json.dumps(_case("case_001")),
            ]
        ),
        encoding="utf-8",
    )

    dataset = load_eval_dataset(dataset_path, project_root=tmp_path)

    assert dataset.case_ids == ["case_001"]
    assert dataset.resolve_source_path("paper") == tmp_path / "paper.pdf"


def test_load_eval_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    dataset_path, _ = _write_dataset(
        tmp_path,
        [
            _case("case_001"),
            _case("case_001"),
        ],
    )

    with pytest.raises(EvaluationDatasetError, match="Duplicate eval case id"):
        load_eval_dataset(dataset_path, project_root=tmp_path)


def test_load_eval_dataset_rejects_invalid_json_with_line_number(tmp_path: Path) -> None:
    dataset_path, _ = _write_dataset(tmp_path, [])
    dataset_path.write_text('{"id": "ok"}\n{"id": ', encoding="utf-8")

    with pytest.raises(EvaluationDatasetError, match="line 2"):
        load_eval_dataset(dataset_path, project_root=tmp_path)


def test_load_eval_dataset_rejects_answerable_case_without_evidence(tmp_path: Path) -> None:
    dataset_path, _ = _write_dataset(
        tmp_path,
        [
            {
                "id": "case_001",
                "question": "What is answered?",
                "answerable": True,
                "evidence": [],
                "answer_terms": ["answer"],
                "notes": "",
            }
        ],
    )

    with pytest.raises(EvaluationDatasetError, match="answerable cases"):
        load_eval_dataset(dataset_path, project_root=tmp_path)


def test_load_eval_dataset_rejects_unknown_doc_key(tmp_path: Path) -> None:
    dataset_path, _ = _write_dataset(
        tmp_path,
        [
            _case("case_001", doc_key="missing"),
        ],
    )

    with pytest.raises(EvaluationDatasetError, match="unknown document key"):
        load_eval_dataset(dataset_path, project_root=tmp_path)


def test_load_eval_dataset_rejects_invalid_page_range(tmp_path: Path) -> None:
    dataset_path, _ = _write_dataset(
        tmp_path,
        [
            _case("case_001", page_start=3, page_end=2),
        ],
    )

    with pytest.raises(EvaluationDatasetError, match="page_end"):
        load_eval_dataset(dataset_path, project_root=tmp_path)


def test_load_eval_dataset_rejects_missing_source_path(tmp_path: Path) -> None:
    dataset_path = tmp_path / "golden.jsonl"
    documents_path = tmp_path / "golden.documents.json"
    documents_path.write_text(
        json.dumps({"paper": {"source_path": "missing.pdf", "notes": "fixture"}}),
        encoding="utf-8",
    )
    dataset_path.write_text(json.dumps(_case("case_001")), encoding="utf-8")

    with pytest.raises(EvaluationDatasetError, match="missing source path"):
        load_eval_dataset(dataset_path, project_root=tmp_path)


def _case(
    case_id: str,
    *,
    doc_key: str = "paper",
    page_start: int = 1,
    page_end: int = 1,
) -> dict:
    """构造最小可用的 eval case，减少各个错误场景测试的重复样板。"""
    return {
        "id": case_id,
        "question": "What does this paper say?",
        "answerable": True,
        "evidence": [
            {
                "doc_key": doc_key,
                "page_start": page_start,
                "page_end": page_end,
                "terms": ["paper"],
            }
        ],
        "answer_terms": ["paper"],
        "reference_answer": "The paper says paper.",
        "notes": "",
    }


def _write_dataset(tmp_path: Path, cases: list[dict]) -> tuple[Path, Path]:
    """写入一组临时评测文件，用于验证 parser 对文件系统路径的处理。"""
    dataset_path = tmp_path / "golden.jsonl"
    documents_path = tmp_path / "golden.documents.json"
    source_path = tmp_path / "paper.pdf"
    source_path.write_bytes(b"%PDF-1.7\n%%EOF\n")
    documents_path.write_text(
        json.dumps({"paper": {"source_path": "paper.pdf", "notes": "fixture"}}),
        encoding="utf-8",
    )
    dataset_path.write_text(
        "\n".join(json.dumps(case) for case in cases),
        encoding="utf-8",
    )
    return dataset_path, documents_path
