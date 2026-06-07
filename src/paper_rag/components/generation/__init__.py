"""Generator 组件 provider 导出。"""

from paper_rag.components.generation.extractive_generator import ExtractiveGenerator
from paper_rag.components.generation.openai_generator import OpenAIGenerator

__all__ = ["ExtractiveGenerator", "OpenAIGenerator"]
