from psycopg.rows import dict_row

from virtual_staff_engineer.database.connection import connect


class CorpusValidationError(RuntimeError):
    """Raised when PostgreSQL does not match the frozen dataset corpus."""


def verify_corpus(dataset, database_url=None):
    """Verify retrieval will search exactly the frozen active playbook."""
    with connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH latest_versions AS (
                    SELECT DISTINCT ON (pd.document_id)
                        pd.document_id,
                        pd.filename,
                        pd.category,
                        pv.playbook_version_id,
                        pv.version,
                        pv.embedding_model,
                        pv.embedding_dimension
                    FROM playbook_documents AS pd
                    JOIN playbook_versions AS pv
                      ON pv.document_id = pd.document_id
                    WHERE pd.archived_at IS NULL
                      AND pd.category = %s
                    ORDER BY pd.document_id, pv.version DESC
                )
                SELECT
                    lv.document_id,
                    lv.filename,
                    lv.category,
                    lv.playbook_version_id,
                    lv.version,
                    lv.embedding_model,
                    lv.embedding_dimension,
                    COUNT(pc.playbook_chunk_id) AS chunk_count,
                    ARRAY_AGG(pc.rule_key ORDER BY pc.rule_key) AS rule_keys
                FROM latest_versions AS lv
                JOIN playbook_chunks AS pc
                  ON pc.playbook_version_id = lv.playbook_version_id
                GROUP BY
                    lv.document_id,
                    lv.filename,
                    lv.category,
                    lv.playbook_version_id,
                    lv.version,
                    lv.embedding_model,
                    lv.embedding_dimension
                ORDER BY lv.filename;
                """,
                (dataset.playbook.category,),
            )
            rows = cur.fetchall()

    if len(rows) != 1:
        filenames = [row["filename"] for row in rows]
        raise CorpusValidationError(
            f"Category {dataset.playbook.category!r} must contain exactly one "
            f"active latest playbook, found {filenames}."
        )

    row = rows[0]
    mismatches = []
    if row["filename"] != dataset.playbook.filename:
        mismatches.append(
            f"filename={row['filename']!r}, expected "
            f"{dataset.playbook.filename!r}"
        )
    if row["version"] != dataset.playbook.version:
        mismatches.append(
            f"version={row['version']}, expected {dataset.playbook.version}"
        )
    if row["chunk_count"] != dataset.playbook.rule_count:
        mismatches.append(
            f"chunks={row['chunk_count']}, expected "
            f"{dataset.playbook.rule_count}"
        )

    expected_keys = {
        key for case in dataset.cases for key in case.expected_rule_keys
    }
    database_keys = set(row["rule_keys"])
    missing_keys = sorted(expected_keys - database_keys)
    if missing_keys:
        mismatches.append(f"missing expected rule keys={missing_keys}")

    if mismatches:
        raise CorpusValidationError(
            "Frozen dataset does not match PostgreSQL: " + "; ".join(mismatches)
        )

    return {
        "document_id": str(row["document_id"]),
        "playbook_version_id": str(row["playbook_version_id"]),
        "filename": row["filename"],
        "category": row["category"],
        "version": row["version"],
        "embedding_model": row["embedding_model"],
        "embedding_dimension": row["embedding_dimension"],
        "chunk_count": row["chunk_count"],
        "rule_keys": row["rule_keys"],
    }
