"""Project-specific exception types."""


class PaperRagError(Exception):
    """Base exception for expected Paper RAG failures."""


class ConfigurationError(PaperRagError):
    """Raised when runtime configuration is invalid."""


class DocumentParseError(PaperRagError):
    """Raised when a document cannot be parsed."""


class DocumentUploadError(PaperRagError):
    """Raised when an uploaded document cannot be accepted or stored."""


class EmbeddingError(PaperRagError):
    """Raised when embedding generation fails."""


class IndexOperationError(PaperRagError):
    """Raised when local index operations fail."""


class RetrievalError(PaperRagError):
    """Raised when retrieval cannot produce usable evidence."""


class AnswerGenerationError(PaperRagError):
    """Raised when answer generation fails."""
