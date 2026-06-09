"""RAG 组件接口、类型和默认 registry。"""

from paper_rag.components.registry import ComponentRegistry, get_component_registry
from paper_rag.components.types import (
    ComponentConfigField,
    ComponentDescriptor,
    ComponentKind,
    ComponentSelection,
    ConfigFieldType,
    ModelCatalog,
    ModelOption,
    ModelSelectionCatalog,
    ModelSourceOption,
    RagPipelineConfig,
)

__all__ = [
    "ComponentConfigField",
    "ComponentDescriptor",
    "ComponentKind",
    "ComponentRegistry",
    "ComponentSelection",
    "ConfigFieldType",
    "ModelCatalog",
    "ModelOption",
    "ModelSelectionCatalog",
    "ModelSourceOption",
    "RagPipelineConfig",
    "get_component_registry",
]
