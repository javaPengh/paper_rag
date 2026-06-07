"""RAG 组件元数据与运行配置类型。

本模块只描述组件 catalog、可选模型和一次 RAG 流水线使用的组件配置；
真实 Reader、Chunker、Embedder、Retriever、Generator 行为放在 interfaces
和具体 provider 模块中。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypeAlias

from pydantic import BaseModel, Field

ConfigValue: TypeAlias = str | int | float | bool | None


class ComponentKind(StrEnum):
    """RAG 流水线中的组件能力类别。"""

    READER = "reader"  # 负责把源文件读取为领域文档和页面。
    CHUNKER = "chunker"  # 负责把页面文本切分成可检索 chunk。
    EMBEDDER = "embedder"  # 负责把文本转换为向量表示。
    RETRIEVER = "retriever"  # 负责按问题召回候选证据 chunk。
    GENERATOR = "generator"  # 负责基于证据生成最终答案。


class ConfigFieldType(StrEnum):
    """组件参数字段在 API catalog 中暴露的基础类型。"""

    STRING = "string"  # 文本配置，例如编码名或外部模型名。
    INTEGER = "integer"  # 整数配置，例如 chunk 大小或 top-k。
    NUMBER = "number"  # 浮点配置，例如最低相似度分数。
    BOOLEAN = "boolean"  # 布尔开关配置，例如是否递归读取。


class ModelOption(BaseModel):
    """组件支持的一个模型或本地实现标识。"""

    id: str = Field(description="传给组件工厂或 provider 的稳定模型标识。")
    label: str = Field(description="前端下拉框展示的人类可读名称。")
    description: str = Field(description="说明该模型适用场景、来源或限制。")


class ComponentConfigField(BaseModel):
    """组件在 catalog 中公开的可配置字段。"""

    name: str = Field(description="传给组件工厂的参数键名。")
    label: str = Field(description="前端表单或报告中显示的参数名称。")
    description: str = Field(description="解释该参数为什么存在以及如何影响组件行为。")
    field_type: ConfigFieldType = Field(description="前端渲染控件时使用的基础字段类型。")
    required: bool = Field(default=False, description="调用组件工厂时该字段是否必须提供。")
    default: ConfigValue = Field(default=None, description="未显式配置时使用的默认值。")
    minimum: float | None = Field(default=None, description="数值字段允许的最小值。")
    maximum: float | None = Field(default=None, description="数值字段允许的最大值。")


class ComponentDescriptor(BaseModel):
    """一个可注册 RAG 组件的后端 catalog 描述。"""

    id: str = Field(description="组件在 registry 中使用的稳定 ID。")
    kind: ComponentKind = Field(description="组件所属的 RAG 能力类别。")
    label: str = Field(description="供 CLI、API 和前端展示的组件名称。")
    description: str = Field(description="说明组件使用的实现、边界和适用场景。")
    models: list[ModelOption] = Field(
        default_factory=list,
        description="该组件可选择的模型或本地实现标识列表。",
    )
    default_model: str | None = Field(
        default=None,
        description="未显式指定 model 时 registry 使用的默认模型。",
    )
    config_fields: list[ComponentConfigField] = Field(
        default_factory=list,
        description="该组件对调用方公开的非密钥配置字段。",
    )


class ComponentSelection(BaseModel):
    """一次运行中某个组件的实际选择。"""

    id: str = Field(description="实际使用的组件 ID。")
    model: str | None = Field(default=None, description="实际传给组件的模型名或本地模型标识。")
    parameters: dict[str, ConfigValue] = Field(
        default_factory=dict,
        description="影响运行结果且可安全记录到报告中的关键参数。",
    )


class RagPipelineConfig(BaseModel):
    """一次 RAG 运行使用的五类组件配置快照。"""

    reader: ComponentSelection = Field(description="读取源文档时使用的 Reader 配置。")
    chunker: ComponentSelection = Field(description="切分页面文本时使用的 Chunker 配置。")
    embedder: ComponentSelection = Field(description="生成文档和问题向量时使用的 Embedder 配置。")
    retriever: ComponentSelection = Field(description="召回证据 chunk 时使用的 Retriever 配置。")
    generator: ComponentSelection = Field(description="基于证据生成答案时使用的 Generator 配置。")
