"""SQLite metadata store for local indexes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from paper_rag.schemas import Chunk, Document, DocumentVersion, IndexStatus

SCHEMA_VERSION = 2


class MetadataStore:
    """Persist tenant-aware document, version, chunk, and status metadata."""

    def __init__(self, index_dir: Path) -> None:
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.index_dir / "metadata.sqlite3"
        self._init_schema()

    def upsert_documents(self, documents: list[Document]) -> None:
        if not documents:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO documents (
                    id, tenant_id, source_id, source_uri, current_version_id, data
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    source_id = excluded.source_id,
                    source_uri = excluded.source_uri,
                    current_version_id = excluded.current_version_id,
                    data = excluded.data
                """,
                [
                    (
                        document.id,
                        document.tenant_id,
                        document.source_id,
                        document.source_uri,
                        document.current_version_id,
                        document.model_dump_json(),
                    )
                    for document in documents
                ],
            )

    def upsert_versions(self, versions: list[DocumentVersion]) -> None:
        if not versions:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO document_versions (
                    id, tenant_id, document_id, content_hash, source_uri, data
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    document_id = excluded.document_id,
                    content_hash = excluded.content_hash,
                    source_uri = excluded.source_uri,
                    data = excluded.data
                """,
                [
                    (
                        version.id,
                        version.tenant_id,
                        version.document_id,
                        version.content_hash,
                        version.source_uri,
                        version.model_dump_json(),
                    )
                    for version in versions
                ],
            )

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO chunks (id, tenant_id, document_id, document_version_id, data)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    document_id = excluded.document_id,
                    document_version_id = excluded.document_version_id,
                    data = excluded.data
                """,
                [
                    (
                        chunk.id,
                        chunk.metadata.get("tenant_id", "default"),
                        chunk.document_id,
                        chunk.document_version_id,
                        chunk.model_dump_json(),
                    )
                    for chunk in chunks
                ],
            )

    def delete_document_ids(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM chunks WHERE document_id IN ({placeholders})",
                document_ids,
            )
            connection.execute(
                f"DELETE FROM document_versions WHERE document_id IN ({placeholders})",
                document_ids,
            )
            connection.execute(f"DELETE FROM documents WHERE id IN ({placeholders})", document_ids)

    def delete_document_version_ids(self, document_version_ids: list[str]) -> None:
        if not document_version_ids:
            return
        placeholders = ",".join("?" for _ in document_version_ids)
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM chunks WHERE document_version_id IN ({placeholders})",
                document_version_ids,
            )

    def get_document_by_source(
        self,
        *,
        tenant_id: str,
        source_uri: str,
        source_id: str | None = None,
    ) -> Document | None:
        with self._connect() as connection:
            if source_id is not None:
                row = connection.execute(
                    "SELECT data FROM documents WHERE tenant_id = ? AND source_id = ?",
                    (tenant_id, source_id),
                ).fetchone()
                if row:
                    return Document.model_validate_json(row["data"])
            row = connection.execute(
                "SELECT data FROM documents WHERE tenant_id = ? AND source_uri = ?",
                (tenant_id, source_uri),
            ).fetchone()
        return Document.model_validate_json(row["data"]) if row else None

    def get_version_by_content_hash(
        self,
        *,
        tenant_id: str,
        content_hash: str,
    ) -> DocumentVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT data FROM document_versions
                WHERE tenant_id = ? AND content_hash = ?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (tenant_id, content_hash),
            ).fetchone()
        return DocumentVersion.model_validate_json(row["data"]) if row else None

    def get_version(self, version_id: str) -> DocumentVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM document_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        return DocumentVersion.model_validate_json(row["data"]) if row else None

    def get_document(self, document_id: str) -> Document | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        return Document.model_validate_json(row["data"]) if row else None

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        with self._connect() as connection:
            row = connection.execute("SELECT data FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
        return Chunk.model_validate_json(row["data"]) if row else None

    def list_chunks(
        self,
        *,
        tenant_id: str | None = None,
        document_id: str | None = None,
        document_version_id: str | None = None,
        limit: int | None = None,
    ) -> list[Chunk]:
        query = "SELECT data FROM chunks"
        clauses: list[str] = []
        params: list[object] = []
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if document_id is not None:
            clauses.append("document_id = ?")
            params.append(document_id)
        if document_version_id is not None:
            clauses.append("document_version_id = ?")
            params.append(document_version_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY document_id, document_version_id, json_extract(data, '$.chunk_index')"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Chunk.model_validate_json(row["data"]) for row in rows]

    def list_documents(self, *, tenant_id: str | None = None) -> list[Document]:
        query = "SELECT data FROM documents"
        params: tuple[object, ...] = ()
        if tenant_id is not None:
            query += " WHERE tenant_id = ?"
            params = (tenant_id,)
        query += " ORDER BY tenant_id, json_extract(data, '$.file_name')"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Document.model_validate_json(row["data"]) for row in rows]

    def count_chunks(
        self,
        *,
        tenant_id: str | None = None,
        document_id: str | None = None,
        document_version_id: str | None = None,
    ) -> int:
        query = "SELECT COUNT(*) AS count FROM chunks"
        clauses: list[str] = []
        params: list[object] = []
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if document_id is not None:
            clauses.append("document_id = ?")
            params.append(document_id)
        if document_version_id is not None:
            clauses.append("document_version_id = ?")
            params.append(document_version_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["count"])

    def write_status(self, status: IndexStatus) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO index_status (id, data)
                VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET data = excluded.data
                """,
                (status.model_dump_json(),),
            )

    def load_status(self) -> IndexStatus | None:
        with self._connect() as connection:
            row = connection.execute("SELECT data FROM index_status WHERE id = 1").fetchone()
        return IndexStatus.model_validate_json(row["data"]) if row else None

    def _init_schema(self) -> None:
        with self._connect() as connection:
            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version != SCHEMA_VERSION:
                self._reset_schema(connection)
            self._create_schema(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _reset_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute("DROP TABLE IF EXISTS chunks")
        connection.execute("DROP TABLE IF EXISTS document_versions")
        connection.execute("DROP TABLE IF EXISTS documents")
        connection.execute("DROP TABLE IF EXISTS index_status")

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source_id TEXT,
                source_uri TEXT NOT NULL,
                current_version_id TEXT,
                data TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                document_version_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS index_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_tenant_source_uri "
            "ON documents(tenant_id, source_uri)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_tenant_source_id "
            "ON documents(tenant_id, source_id) WHERE source_id IS NOT NULL"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_versions_tenant_content_hash "
            "ON document_versions(tenant_id, content_hash)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON chunks(tenant_id)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_document_version_id "
            "ON chunks(document_version_id)"
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection
