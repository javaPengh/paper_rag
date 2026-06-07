"""兼容旧导入路径的向量检索器。"""

from __future__ import annotations

from paper_rag.components.retrieval.vector_retriever import VectorRetriever


class Retriever(VectorRetriever):
    """旧 `paper_rag.retrieval.Retriever` 路径的兼容包装。"""
