import os

from virtual_staff_engineer.database.connection import connect
from virtual_staff_engineer.ingestion.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    generate_embeddings,
    get_embedding_client,
)
from virtual_staff_engineer.ingestion.markdown import (
    compute_checksum,
    parse_markdown,
)


def ingest_playbook(
    file_path,
    category="general",
    database_url=None,
    ai_client=None,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimension=EMBEDDING_DIMENSION,
    embedding_generator=None,
):
    """Create an immutable, embedded playbook version when content changes."""
    filename = os.path.basename(file_path)
    current_checksum = compute_checksum(file_path)
    parsed_chunks = parse_markdown(file_path)

    print(f"📄 Processing playbook: {filename}...")

    if not parsed_chunks:
        raise ValueError(f"No non-empty Markdown sections found in {file_path}.")

    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pd.document_id,
                    pd.archived_at,
                    pv.playbook_version_id
                FROM playbook_documents AS pd
                JOIN playbook_versions AS pv
                    ON pv.document_id = pd.document_id
                WHERE pd.filename = %s
                  AND pv.checksum = %s
                  AND pv.embedding_model = %s
                  AND pv.embedding_dimension = %s;
                """,
                (
                    filename,
                    current_checksum,
                    embedding_model,
                    embedding_dimension,
                ),
            )
            existing_version = cur.fetchone()
            if existing_version:
                document_id, archived_at, _ = existing_version
                if archived_at is not None:
                    cur.execute(
                        """
                        UPDATE playbook_documents
                        SET archived_at = NULL,
                            category = %s
                        WHERE document_id = %s;
                        """,
                        (category, document_id),
                    )
                print(f"⏩ No changes detected for {filename}. Skipping ingestion.")
                return {
                    "status": "skipped",
                    "filename": filename,
                    "chunk_count": 0,
                }

    print(f"✂️ Parsed {len(parsed_chunks)} non-empty playbook chunks.")
    resolved_client = ai_client or get_embedding_client()
    resolved_generator = embedding_generator or generate_embeddings
    embedded_chunks = resolved_generator(
        parsed_chunks,
        resolved_client,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
    )

    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO playbook_documents (filename, category)
                VALUES (%s, %s)
                ON CONFLICT (filename) DO UPDATE
                SET category = EXCLUDED.category,
                    archived_at = NULL
                RETURNING document_id;
                """,
                (filename, category),
            )
            document_id = cur.fetchone()[0]

            # Serialize version allocation for concurrent ingestion of one document.
            cur.execute(
                """
                SELECT document_id
                FROM playbook_documents
                WHERE document_id = %s
                FOR UPDATE;
                """,
                (document_id,),
            )

            # Recheck after locking in case another worker completed first.
            cur.execute(
                """
                SELECT playbook_version_id
                FROM playbook_versions
                WHERE document_id = %s
                  AND checksum = %s
                  AND embedding_model = %s
                  AND embedding_dimension = %s;
                """,
                (
                    document_id,
                    current_checksum,
                    embedding_model,
                    embedding_dimension,
                ),
            )
            concurrent_version = cur.fetchone()
            if concurrent_version:
                print(
                    f"⏩ Version was ingested concurrently for {filename}. "
                    "Skipping duplicate write."
                )
                return {
                    "status": "skipped",
                    "filename": filename,
                    "chunk_count": 0,
                }

            cur.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM playbook_versions
                WHERE document_id = %s;
                """,
                (document_id,),
            )
            version_number = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO playbook_versions (
                    document_id,
                    version,
                    checksum,
                    embedding_model,
                    embedding_dimension
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING playbook_version_id;
                """,
                (
                    document_id,
                    version_number,
                    current_checksum,
                    embedding_model,
                    embedding_dimension,
                ),
            )
            playbook_version_id = cur.fetchone()[0]

            for chunk in embedded_chunks:
                cur.execute(
                    """
                    INSERT INTO playbook_chunks (
                        playbook_version_id,
                        rule_key,
                        chunk_index,
                        section,
                        content,
                        embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (
                        playbook_version_id,
                        chunk["rule_key"],
                        chunk["chunk_index"],
                        chunk["section"],
                        chunk["content"],
                        chunk["embedding"],
                    ),
                )

        conn.commit()

    print(
        f"✅ Ingested {filename} version {version_number} "
        f"with {len(embedded_chunks)} chunks."
    )
    return {
        "status": "ingested",
        "filename": filename,
        "version": version_number,
        "chunk_count": len(embedded_chunks),
    }
