"""评测证据匹配工具。

本模块沉淀 retrieval 与 citation 指标都会使用的低层匹配规则：文档短键如何
对应到实际索引文档，以及两个页码区间是否重叠。统一这些规则可以避免不同
指标对同一组人工 evidence 产生互相矛盾的判断。
"""

from __future__ import annotations

from pathlib import Path

from paper_rag.evaluation.dataset import EvalDataset
from paper_rag.schemas import Document


def document_matches(dataset: EvalDataset, doc_key: str, document: Document | None) -> bool:
    """判断一个索引文档是否对应评测集中的文档短键。"""
    if document is None:
        return False

    if file_name_matches_source(dataset, doc_key, document.file_name):
        return True

    source_uri = document.source_uri.strip()
    if not source_uri:
        return False
    return source_uri_matches_source(dataset, doc_key, source_uri)


def file_name_matches_source(dataset: EvalDataset, doc_key: str, file_name: str) -> bool:
    """判断显示文件名是否与评测文档短键指向的 source_path 文件名一致。"""
    expected_source_path = dataset.resolve_source_path(doc_key)
    return file_name.casefold() == expected_source_path.name.casefold()


def source_uri_matches_source(dataset: EvalDataset, doc_key: str, source_uri: str) -> bool:
    """判断文档 source_uri 是否指向评测文档短键对应的固定语料路径。"""
    expected_source_path = dataset.resolve_source_path(doc_key)
    try:
        actual_path = Path(source_uri)
        return actual_path.resolve() == expected_source_path.resolve()
    except (OSError, RuntimeError, ValueError):
        return source_uri.casefold() == str(expected_source_path).casefold()


def page_ranges_overlap(
    actual_start: int,
    actual_end: int,
    expected_start: int,
    expected_end: int,
) -> bool:
    """判断实际页码区间与 expected evidence 页码区间是否有交集。"""
    return actual_start <= expected_end and expected_start <= actual_end
