"""评测集数据模型与 JSONL 解析器。

本模块负责把人工维护的 golden dataset 解析成结构化对象，并在评测运行前
提前发现格式、文档短键和本地语料路径问题。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from paper_rag.exceptions import EvaluationDatasetError


class EvalDocument(BaseModel):
    """评测集引用的一篇固定评测文档。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        min_length=1,
        description="评测文档的稳定短键，用于让 eval case 避免直接依赖较长或会变化的文件路径。",
    )
    source_path: Path = Field(
        description="固定评测 PDF 的路径，可填写项目根目录相对路径或绝对路径。",
    )
    notes: str = Field(
        default="",
        description="人工维护的文档备注，用于说明文档版本、用途或标注时需要注意的上下文。",
    )

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        """规整文档短键，避免空白 key 进入后续评测流程。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("document key cannot be empty")
        return normalized


class EvalEvidence(BaseModel):
    """一组用于检索和引用评测的期望证据。"""

    model_config = ConfigDict(extra="forbid")

    doc_key: str = Field(
        min_length=1,
        description="证据所在文档短键，必须存在于评测文档映射表中。",
    )
    page_start: int = Field(
        ge=1,
        description="期望包含支持证据的起始页码，使用从 1 开始的闭区间。",
    )
    page_end: int = Field(
        ge=1,
        description="期望包含支持证据的结束页码，使用从 1 开始的闭区间。",
    )
    terms: list[str] = Field(
        min_length=1,
        description="期望出现在检索证据文本中的锚点词或短语，用于判断检索内容是否真正命中原文。",
    )

    @field_validator("doc_key")
    @classmethod
    def validate_doc_key(cls, value: str) -> str:
        """在校验映射表前规整文档短键，避免空白字符影响匹配。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("doc_key cannot be empty")
        return normalized

    @field_validator("terms")
    @classmethod
    def validate_terms(cls, value: list[str]) -> list[str]:
        """移除误填的空白锚点词，同时保留人工标注的词序。"""
        terms = [item.strip() for item in value if item.strip()]
        if not terms:
            raise ValueError("terms must contain at least one non-empty term")
        return terms

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        """确保页码区间可被后续 overlap 类指标直接比较。"""
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class EvalCase(BaseModel):
    """一条人工标注的 golden evaluation case。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        description="单个数据集内稳定唯一的 case ID，用于报告输出和回归对比。",
    )
    question: str = Field(
        min_length=1,
        description="提交给 RAG 系统的自然语言问题。",
    )
    answerable: bool = Field(
        description="固定本地 PDF 语料是否包含足够证据回答该问题。",
    )
    evidence: list[EvalEvidence] = Field(
        default_factory=list,
        description="检索和 citation 评测时应命中的证据组；完全不可回答题可以为空。",
    )
    answer_terms: list[str] = Field(
        min_length=1,
        description="期望出现在最终答案或有依据拒答文本中的关键词或短语。",
    )
    reference_answer: str = Field(
        default="",
        description="可选的人工参考答案，用于人工复核或后续引入 answer quality 指标。",
    )
    notes: str = Field(
        default="",
        description="人工标注备注，用于说明问题维度、注意事项或审核状态。",
    )

    @field_validator("id", "question")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """规整必填文本字段，避免只有空白字符的 case 进入评测集。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be empty")
        return normalized

    @field_validator("answer_terms")
    @classmethod
    def validate_answer_terms(cls, value: list[str]) -> list[str]:
        """规整答案锚点词，同时保留标注者选择的词序。"""
        terms = [item.strip() for item in value if item.strip()]
        if not terms:
            raise ValueError("answer_terms must contain at least one non-empty term")
        return terms

    @model_validator(mode="after")
    def validate_answerable_contract(self) -> Self:
        """要求可回答问题至少包含一组证据，保证后续检索指标有可对照目标。"""
        if self.answerable and not self.evidence:
            raise ValueError("answerable cases must include at least one evidence group")
        return self


class EvalDataset(BaseModel):
    """已解析的评测集，以及与之配套的文档短键映射。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path = Field(description="提供 eval cases 的 JSONL 数据集路径。")
    documents_path: Path = Field(description="该评测集使用的文档短键映射 JSON 路径。")
    project_root: Path = Field(description="用于解析相对 source_path 的项目根目录。")
    cases: list[EvalCase] = Field(description="按文件顺序保存的已校验 eval cases。")
    documents: dict[str, EvalDocument] = Field(
        description="已校验的文档短键到固定评测 PDF 元数据的映射。",
    )

    @property
    def case_ids(self) -> list[str]:
        """按数据集顺序返回 case ID，供报告和测试快速引用。"""
        return [case.id for case in self.cases]

    def document_for_key(self, doc_key: str) -> EvalDocument:
        """根据文档短键返回映射文档；短键不存在时抛出清晰的评测集错误。"""
        try:
            return self.documents[doc_key]
        except KeyError as exc:
            raise EvaluationDatasetError(f"Unknown eval document key: {doc_key}") from exc

    def resolve_source_path(self, doc_key: str) -> Path:
        """把文档 source_path 解析成可直接读取的本地路径。"""
        document = self.document_for_key(doc_key)
        if document.source_path.is_absolute():
            return document.source_path
        return self.project_root / document.source_path


def load_eval_dataset(
    dataset_path: Path,
    *,
    documents_path: Path | None = None,
    project_root: Path | None = None,
    require_source_paths: bool = True,
) -> EvalDataset:
    """加载并校验 JSONL golden dataset。

    `documents_path` 默认使用与数据集同名的 `.documents.json` 旁路文件；
    `project_root` 用于解析文档映射中的相对路径；`require_source_paths`
    控制是否在解析阶段检查固定评测 PDF 必须存在。
    """
    resolved_dataset_path = Path(dataset_path)
    if not resolved_dataset_path.exists():
        raise EvaluationDatasetError(f"Eval dataset does not exist: {resolved_dataset_path}")
    if not resolved_dataset_path.is_file():
        raise EvaluationDatasetError(f"Eval dataset path is not a file: {resolved_dataset_path}")

    resolved_documents_path = documents_path or _default_documents_path(resolved_dataset_path)
    documents = _load_documents(resolved_documents_path)
    cases = _load_cases(resolved_dataset_path)
    _validate_unique_case_ids(cases, resolved_dataset_path)
    resolved_project_root = Path(project_root) if project_root is not None else Path.cwd()
    _validate_case_document_keys(cases, documents, resolved_dataset_path)
    if require_source_paths:
        _validate_source_paths(documents, resolved_project_root, resolved_documents_path)

    return EvalDataset(
        path=resolved_dataset_path,
        documents_path=resolved_documents_path,
        project_root=resolved_project_root,
        cases=cases,
        documents=documents,
    )


def _default_documents_path(dataset_path: Path) -> Path:
    """根据 JSONL 数据集路径推导旁路文档映射文件路径。"""
    return dataset_path.with_name(f"{dataset_path.stem}.documents.json")


def _load_documents(documents_path: Path) -> dict[str, EvalDocument]:
    """加载文档短键映射，以便后续校验 evidence 引用是否有效。"""
    path = Path(documents_path)
    if not path.exists():
        raise EvaluationDatasetError(f"Eval document mapping does not exist: {path}")
    if not path.is_file():
        raise EvaluationDatasetError(f"Eval document mapping path is not a file: {path}")

    try:
        raw_documents = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise EvaluationDatasetError(
            f"Invalid JSON in eval document mapping {path}: {exc.msg} "
            f"at line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(raw_documents, dict):
        raise EvaluationDatasetError(f"Eval document mapping must be a JSON object: {path}")

    documents: dict[str, EvalDocument] = {}
    for key, value in raw_documents.items():
        if not isinstance(value, dict):
            raise EvaluationDatasetError(
                f"Invalid eval document mapping {path}: key {key!r} must map to an object"
            )
        try:
            documents[key] = EvalDocument.model_validate({"key": key, **value})
        except ValidationError as exc:
            raise EvaluationDatasetError(
                f"Invalid eval document mapping {path}: key {key!r}: "
                f"{_format_validation_error(exc)}"
            ) from exc

    return documents


def _load_cases(dataset_path: Path) -> list[EvalCase]:
    """加载 JSONL cases，并让 JSON 语法错误能报告真实行号。"""
    raw_cases: list[tuple[int, dict[str, Any]]] = []
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8-sig").splitlines(),
        1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            raw_case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationDatasetError(
                f"Invalid JSON in eval dataset {dataset_path} at line {line_number}: "
                f"{exc.msg} at column {exc.colno}"
            ) from exc

        if not isinstance(raw_case, dict):
            raise EvaluationDatasetError(
                f"Invalid eval case in {dataset_path} at line {line_number}: "
                "case must be a JSON object"
            )

        raw_cases.append((line_number, raw_case))

    cases: list[EvalCase] = []
    for line_number, raw_case in raw_cases:
        try:
            cases.append(EvalCase.model_validate(raw_case))
        except ValidationError as exc:
            case_hint = _case_hint(raw_case)
            raise EvaluationDatasetError(
                f"Invalid eval case in {dataset_path} at line {line_number}{case_hint}: "
                f"{_format_validation_error(exc)}"
            ) from exc

    return cases


def _validate_unique_case_ids(cases: list[EvalCase], dataset_path: Path) -> None:
    """拒绝重复 case ID，因为评测报告会把它作为稳定主键。"""
    seen: set[str] = set()
    duplicates: list[str] = []
    for case in cases:
        if case.id in seen:
            duplicates.append(case.id)
        seen.add(case.id)
    if duplicates:
        duplicate_list = ", ".join(sorted(set(duplicates)))
        raise EvaluationDatasetError(
            f"Duplicate eval case id(s) in {dataset_path}: {duplicate_list}"
        )


def _validate_case_document_keys(
    cases: list[EvalCase],
    documents: dict[str, EvalDocument],
    dataset_path: Path,
) -> None:
    """确保每组 evidence 都指向一个已知的文档短键。"""
    document_keys = set(documents)
    missing: list[str] = []
    for case in cases:
        for evidence in case.evidence:
            if evidence.doc_key not in document_keys:
                missing.append(f"{case.id}:{evidence.doc_key}")
    if missing:
        missing_list = ", ".join(missing)
        raise EvaluationDatasetError(
            f"Eval dataset {dataset_path} references unknown document key(s): {missing_list}"
        )


def _validate_source_paths(
    documents: dict[str, EvalDocument],
    project_root: Path,
    documents_path: Path,
) -> None:
    """在固定评测 PDF 缺失时提前失败，避免评测运行到一半才暴露语料问题。"""
    missing: list[str] = []
    for key, document in documents.items():
        source_path = (
            document.source_path
            if document.source_path.is_absolute()
            else project_root / document.source_path
        )
        if not source_path.exists():
            missing.append(f"{key}:{document.source_path}")
    if missing:
        missing_list = ", ".join(missing)
        raise EvaluationDatasetError(
            f"Eval document mapping {documents_path} references missing source path(s): "
            f"{missing_list}"
        )


def _format_validation_error(exc: ValidationError) -> str:
    """把 Pydantic 校验结果压缩成人类可读的单行错误信息。"""
    messages: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<case>"
        messages.append(f"{location}: {error['msg']}")
    return "; ".join(messages)


def _case_hint(raw_case: dict[str, Any]) -> str:
    """当原始 JSON 中存在 case ID 时，为解析错误补充短提示。"""
    case_id = raw_case.get("id")
    return f" (id={case_id})" if isinstance(case_id, str) and case_id else ""
