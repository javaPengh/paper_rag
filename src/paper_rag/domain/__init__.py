"""Paper RAG 的核心领域模型边界。

该包只承载文档、页面、chunk、引用、答案和索引状态等稳定业务类型，
避免 API DTO、评测数据结构和组件配置类型混在同一个巨大模块里。
"""

from paper_rag.domain.models import (
    Answer,
    Chunk,
    Citation,
    DirectoryParseResult,
    Document,
    DocumentVersion,
    IndexBuildResult,
    IndexedSource,
    IndexStatus,
    Page,
    ParsedPdf,
    ParseIssue,
    SearchResult,
    SkippedFile,
    utc_now,
)

__all__ = [
    "Answer",
    "Chunk",
    "Citation",
    "DirectoryParseResult",
    "Document",
    "DocumentVersion",
    "IndexBuildResult",
    "IndexedSource",
    "IndexStatus",
    "Page",
    "ParsedPdf",
    "ParseIssue",
    "SearchResult",
    "SkippedFile",
    "utc_now",
]
