"""本地 Web Inspector 的 API 请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """基础服务健康状态载荷。"""

    status: str = Field(description="服务健康状态，通常为 `ok`。")
    version: str = Field(description="已安装的 paper_rag 包版本。")


class ErrorDetailResponse(BaseModel):
    """用于 HTTP 错误响应的结构化 API 错误详情。"""

    stage: str = Field(description="API 错误发生的流水线阶段。")
    error_type: str = Field(description="异常类名或错误类别。")
    message: str = Field(description="可安全显示在检视器界面的可读错误信息。")


class IndexStatusResponse(BaseModel):
    """租户范围内的本地索引状态。"""

    status: str = Field(description="该租户当前的索引生命周期状态。")
    tenant_id: str = Field(description="本次查询使用的租户/工作区命名空间。")
    index_dir: Path = Field(description="API 检查的本地索引目录。")
    document_count: int = Field(ge=0, description="该租户已索引的文档数。")
    chunk_count: int = Field(ge=0, description="该租户已索引的 chunk 数。")
    embedding_model: str | None = Field(
        default=None,
        description="已索引向量使用的 embedding 模型（如已知）。",
    )
    built_at: datetime | None = Field(
        default=None,
        description="索引首次构建时的 UTC 时间戳。",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="索引状态最后更新时间的 UTC 时间戳。",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="展示给检视器用户的已持久化索引错误。",
    )


class DocumentSummaryResponse(BaseModel):
    """Inspector 文档列表所需的文档详情。"""

    id: str = Field(description="稳定的内部文档 ID。")
    tenant_id: str = Field(description="拥有该文档的租户/工作区命名空间。")
    source_id: str | None = Field(
        default=None,
        description="为未来连接器保留的可选外部源 ID。",
    )
    source_uri: str = Field(description="用于构建当前文档记录的源 URI。")
    file_name: str = Field(description="检视器和引用显示使用的文件名。")
    title: str | None = Field(default=None, description="可选的 PDF 元数据标题。")
    page_count: int = Field(ge=0, description="解析器报告的页数。")
    current_version_id: str | None = Field(
        default=None,
        description="该文档当前生效的内容版本 ID。",
    )
    content_hash: str | None = Field(
        default=None,
        description="当前版本的内容哈希（如有）。",
    )
    chunk_count: int = Field(ge=0, description="该文档已索引的 chunk 数。")
    created_at: datetime = Field(description="文档创建时的 UTC 时间戳。")
    updated_at: datetime = Field(description="文档最后更新时间的 UTC 时间戳。")


class ChunkResponse(BaseModel):
    """用于检查和引用追踪的 chunk 详情。"""

    id: str = Field(description="稳定的 chunk ID。")
    document_id: str = Field(description="拥有该 chunk 的逻辑文档 ID。")
    document_version_id: str = Field(description="生成该 chunk 的内容版本。")
    file_name: str | None = Field(
        default=None,
        description="可用时从文档元数据合并得到的显示文件名。",
    )
    text: str = Field(description="用于检查和证据追踪的 chunk 文本。")
    page_start: int = Field(ge=1, description="chunk 中的起始页码（从 1 开始）。")
    page_end: int = Field(ge=1, description="chunk 中的结束页码（从 1 开始）。")
    chunk_index: int = Field(ge=0, description="文档内从 0 开始的 chunk 顺序。")
    token_count: int | None = Field(
        default=None,
        ge=0,
        description="分块时记录的 tokenizer 单元数。",
    )


class StoredUploadResponse(BaseModel):
    """保存到受管本地源存储中的 PDF 详情。"""

    tenant_id: str = Field(description="上传者请求的租户 ID。")
    storage_tenant: str = Field(description="磁盘上使用的已清理租户路径片段。")
    original_file_name: str = Field(description="去掉路径后的原始上传文件名。")
    safe_file_name: str = Field(description="用于存储的已清理 PDF 文件名。")
    stored_path: Path = Field(description="受管存储的 PDF 本地绝对路径。")
    source_uri: str = Field(description="传给索引流水线的源 URI。")
    content_hash: str = Field(description="上传 PDF 字节的 SHA-256 哈希。")
    size_bytes: int = Field(ge=0, description="上传 PDF 的大小（字节）。")


class FileIssueResponse(BaseModel):
    """索引返回的跳过文件或解析问题。"""

    source_path: Path = Field(description="与该问题关联的源文件。")
    reason: str | None = Field(
        default=None,
        description="文件在解析前被跳过的原因。",
    )
    message: str | None = Field(
        default=None,
        description="用于警告和错误的解析或索引消息。",
    )
    page_number: int | None = Field(
        default=None,
        ge=1,
        description="问题与特定页面相关时的页码（从 1 开始）。",
    )


class IndexingSummaryResponse(BaseModel):
    """一次由上传触发的索引运行的结构化摘要。"""

    indexed: int = Field(ge=0, description="新索引的文档数。")
    reused_source: int = Field(ge=0, description="因源 URI 未变化而复用的文档数。")
    reused_content: int = Field(ge=0, description="因内容哈希重复而复用的文档数。")
    reindexed: int = Field(ge=0, description="内容变化后重新索引的已有文档数。")
    indexed_chunks: int = Field(ge=0, description="新生成 embedding 并写入的 chunk 数。")
    total_documents: int = Field(ge=0, description="本次运行后的总文档数。")
    total_chunks: int = Field(ge=0, description="本次运行后的总 chunk 数。")
    skipped_files: list[FileIssueResponse] = Field(
        default_factory=list,
        description="在解析/索引工作前跳过的文件。",
    )
    warnings: list[FileIssueResponse] = Field(
        default_factory=list,
        description="可恢复的解析/索引警告。",
    )
    errors: list[FileIssueResponse] = Field(
        default_factory=list,
        description="每个文件的致命解析/索引错误。",
    )


class UploadIndexResponse(BaseModel):
    """保存 PDF 并同步索引后返回的响应。"""

    upload: StoredUploadResponse = Field(description="受管上传存储结果。")
    index: IndexingSummaryResponse = Field(description="同步索引摘要。")
    status: IndexStatusResponse = Field(description="上传索引后的索引状态。")


class CitationResponse(BaseModel):
    """与 CLI 字符串格式解耦的引用载荷。"""

    label: str = Field(description="渲染后的引用标签，例如 `[paper.pdf, p.1]`。")
    document_id: str = Field(description="被引用的逻辑文档 ID。")
    document_version_id: str | None = Field(
        default=None,
        description="被引用的内容版本 ID（如有）。",
    )
    chunk_id: str = Field(description="支撑该引用的证据 chunk ID。")
    file_name: str = Field(description="在引用标签中显示的文件名。")
    page_start: int = Field(ge=1, description="引用的起始源页码。")
    page_end: int = Field(ge=1, description="引用的结束源页码。")
    snippet: str | None = Field(default=None, description="简短的引用证据预览。")


class EvidenceResponse(BaseModel):
    """检索到的证据及其排序元数据。"""

    chunk: ChunkResponse = Field(description="在 Evidence 面板中显示的检索 chunk。")
    score: float = Field(description="答案过滤使用的相似度分数。")
    distance: float | None = Field(
        default=None,
        description="可用时的向量库原始距离。",
    )
    used: bool = Field(default=False, description="答案生成器是否使用了该 chunk。")


class AskRequest(BaseModel):
    """本地 Inspector 的问题请求。"""

    question: str = Field(min_length=1, description="要回答的自然语言问题。")
    tenant_id: str = Field(default="default", description="要查询的租户/工作区命名空间。")
    index_dir: Path | None = Field(
        default=None,
        description="本次请求覆盖使用的本地索引目录。",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="答案生成前要检索的证据 chunk 数量。",
    )
    min_score: float = Field(
        default=0.05,
        ge=0,
        description="证据被视为可用的最低检索分数。",
    )
    embedding_model: str | None = Field(
        default=None,
        description="用于查询 embedding 的模型覆盖值。",
    )
    llm_model: str | None = Field(
        default=None,
        description="用于非本地答案生成的 LLM 模型覆盖值。",
    )
    local: bool = Field(
        default=False,
        description="使用确定性的本地 embedding 和抽取式答案生成。",
    )


class AskResponse(BaseModel):
    """带有引用和检索证据的答案载荷。"""

    question: str = Field(description="从请求中回显的问题。")
    answer: str = Field(description="答案生成器返回的答案文本。")
    insufficient_evidence: bool = Field(description="答案是否为有依据的拒答。")
    model_name: str | None = Field(
        default=None,
        description="产生该答案的模型或本地生成器名称。",
    )
    citations: list[CitationResponse] = Field(
        default_factory=list,
        description="答案中包含的引用。",
    )
    evidence: list[EvidenceResponse] = Field(
        default_factory=list,
        description="用于检查和调试的检索证据。",
    )
    context: str | None = Field(
        default=None,
        description="由证据组装的提示词上下文，便于本地调试。",
    )
