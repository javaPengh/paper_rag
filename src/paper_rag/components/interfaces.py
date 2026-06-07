"""RAG 五类组件的协议边界。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from paper_rag.domain import (
    Answer,
    Chunk,
    DirectoryParseResult,
    Page,
    ParsedPdf,
    SearchResult,
    SkippedFile,
)


class Reader(Protocol):
    """把源文件读取为 Paper RAG 领域文档、版本和页面的组件。"""

    def scan_directory(
        self,
        directory: Path,
        *,
        recursive: bool = True,
    ) -> tuple[list[Path], list[SkippedFile]]:
        """发现目录中的可读取源文件，并记录被跳过的文件。"""
        ...

    def read_directory(self, directory: Path, *, recursive: bool = True) -> DirectoryParseResult:
        """读取一个目录中的源文件并返回统一解析结果。"""
        ...

    def read_pdf(
        self,
        path: Path,
        *,
        tenant_id: str = "default",
        document_id: str | None = None,
        document_version_id: str | None = None,
        source_id: str | None = None,
        source_uri: str | None = None,
        content_hash: str | None = None,
    ) -> ParsedPdf:
        """读取单个 PDF，并允许索引流水线复用已有文档身份。"""
        ...


class Chunker(Protocol):
    """把解析页面切分成可索引 chunk 的组件。"""

    def chunk(self, pages: Sequence[Page]) -> list[Chunk]:
        """根据组件配置把页面序列切分为 chunk。"""
        ...


class Embedder(Protocol):
    """把文本转换为向量的组件。"""

    model_name: str

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """对一批文本生成 embedding 向量。"""
        ...


class Retriever(Protocol):
    """根据问题召回候选证据 chunk 的组件。"""

    def retrieve(self, question: str, *, top_k: int = 5) -> list[SearchResult]:
        """返回按相关性排序的检索结果。"""
        ...


class Generator(Protocol):
    """基于问题和检索证据生成最终答案的组件。"""

    def generate(self, question: str, results: Sequence[SearchResult]) -> Answer:
        """根据检索结果生成有引用的答案或有依据拒答。"""
        ...
