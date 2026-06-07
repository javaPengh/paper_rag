"""索引工具的兼容导出。"""

from paper_rag.indexing.chunking import ChunkingConfig, chunk_pages
from paper_rag.indexing.local_index import LocalPaperIndex
from paper_rag.indexing.vector_store import ChromaVectorStore

__all__ = [
    "ChromaVectorStore",
    "ChunkingConfig",
    "LocalPaperIndex",
    "build_index_from_directory",
    "chunk_pages",
]


def __getattr__(name: str):
    """按需加载流水线入口，避免组件 provider 初始化时形成循环导入。"""
    if name == "build_index_from_directory":
        from paper_rag.indexing.pipeline import build_index_from_directory

        return build_index_from_directory
    raise AttributeError(f"module 'paper_rag.indexing' has no attribute {name!r}")
