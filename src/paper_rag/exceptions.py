"""项目内可预期异常类型。

这些异常用于区分配置、解析、索引、检索、回答生成和评测集加载等业务阶段的
可解释失败，方便 CLI、API 和测试按错误类型处理。
"""


class PaperRagError(Exception):
    """Paper RAG 可预期失败的基础异常类型。"""


class ConfigurationError(PaperRagError):
    """运行时配置缺失或取值非法时抛出的异常。"""


class DocumentParseError(PaperRagError):
    """文档无法解析为可索引文本时抛出的异常。"""


class DocumentUploadError(PaperRagError):
    """上传文档无法被接受或保存时抛出的异常。"""


class EmbeddingError(PaperRagError):
    """向量生成失败时抛出的异常。"""


class IndexOperationError(PaperRagError):
    """本地索引读写或构建失败时抛出的异常。"""


class RetrievalError(PaperRagError):
    """检索阶段无法产出可用证据时抛出的异常。"""


class AnswerGenerationError(PaperRagError):
    """答案生成阶段失败时抛出的异常。"""


class EvaluationDatasetError(PaperRagError):
    """评测集文件缺失、格式错误或人工标注不一致时抛出的可预期异常。"""
