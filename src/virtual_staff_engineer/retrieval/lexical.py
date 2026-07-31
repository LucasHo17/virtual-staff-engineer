from psycopg.rows import dict_row

from virtual_staff_engineer.database.connection import connect
from virtual_staff_engineer.retrieval.models import LexicalSearchResult
from virtual_staff_engineer.retrieval.validation import (
    validate_category,
    validate_query,
    validate_top_k,
)


DEFAULT_FUZZY_THRESHOLD = 0.2
EXACT_RULE_KEY_WEIGHT = 2.0
FULL_TEXT_WEIGHT = 1.0
TRIGRAM_WEIGHT = 0.25


def lexical_search(
    query,
    top_k=5,
    category=None,
    fuzzy_threshold=DEFAULT_FUZZY_THRESHOLD,
    database_url=None,
):
    """Rank active, latest playbook chunks using PostgreSQL lexical signals."""
    normalized_query = validate_query(query)
    normalized_category = validate_category(category)
    validate_top_k(top_k)
    _validate_fuzzy_threshold(fuzzy_threshold)

    with connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH search_input AS (
                    SELECT
                        websearch_to_tsquery('english', %(query)s) AS ts_query,
                        lower(%(query)s) AS normalized_query
                ),
                latest_versions AS (
                    SELECT DISTINCT ON (pv.document_id)
                        pv.playbook_version_id,
                        pv.document_id,
                        pv.version,
                        pv.embedding_model
                    FROM playbook_versions AS pv
                    ORDER BY pv.document_id, pv.version DESC
                ),
                scored_chunks AS (
                    SELECT
                        pc.playbook_chunk_id,
                        pc.playbook_version_id,
                        pd.document_id,
                        pd.filename,
                        pd.category,
                        lv.version,
                        pc.rule_key,
                        pc.chunk_index,
                        pc.section,
                        pc.content,
                        lv.embedding_model,
                        lower(pc.rule_key) = si.normalized_query
                            AS exact_rule_key_match,
                        ts_rank_cd(
                            to_tsvector(
                                'english',
                                pc.rule_key || ' ' || pc.section || ' ' || pc.content
                            ),
                            si.ts_query,
                            32
                        ) AS full_text_rank,
                        GREATEST(
                            similarity(lower(pc.rule_key), si.normalized_query),
                            similarity(lower(pc.section), si.normalized_query),
                            similarity(lower(pc.content), si.normalized_query)
                        ) AS trigram_score
                    FROM playbook_chunks AS pc
                    JOIN latest_versions AS lv
                      ON lv.playbook_version_id = pc.playbook_version_id
                    JOIN playbook_documents AS pd
                      ON pd.document_id = lv.document_id
                    CROSS JOIN search_input AS si
                    WHERE pd.archived_at IS NULL
                      AND (
                          %(category)s::text IS NULL
                          OR pd.category = %(category)s
                      )
                ),
                eligible_chunks AS (
                    SELECT
                        *,
                        (%(exact_weight)s * exact_rule_key_match::integer)
                        + (%(full_text_weight)s * full_text_rank)
                        + (%(trigram_weight)s * trigram_score)
                            AS lexical_score
                    FROM scored_chunks
                    WHERE exact_rule_key_match
                       OR full_text_rank > 0
                       OR trigram_score >= %(fuzzy_threshold)s
                )
                SELECT
                    playbook_chunk_id,
                    playbook_version_id,
                    document_id,
                    filename,
                    category,
                    version,
                    rule_key,
                    chunk_index,
                    section,
                    content,
                    embedding_model,
                    exact_rule_key_match,
                    full_text_rank,
                    trigram_score,
                    lexical_score
                FROM eligible_chunks
                ORDER BY
                    lexical_score DESC,
                    exact_rule_key_match DESC,
                    full_text_rank DESC,
                    trigram_score DESC,
                    playbook_chunk_id ASC
                LIMIT %(top_k)s;
                """,
                {
                    "query": normalized_query,
                    "category": normalized_category,
                    "fuzzy_threshold": fuzzy_threshold,
                    "exact_weight": EXACT_RULE_KEY_WEIGHT,
                    "full_text_weight": FULL_TEXT_WEIGHT,
                    "trigram_weight": TRIGRAM_WEIGHT,
                    "top_k": top_k,
                },
            )
            rows = cur.fetchall()

    return [
        LexicalSearchResult(
            playbook_chunk_id=str(row["playbook_chunk_id"]),
            playbook_version_id=str(row["playbook_version_id"]),
            document_id=str(row["document_id"]),
            filename=row["filename"],
            category=row["category"],
            version=row["version"],
            rule_key=row["rule_key"],
            chunk_index=row["chunk_index"],
            section=row["section"],
            content=row["content"],
            embedding_model=row["embedding_model"],
            exact_rule_key_match=row["exact_rule_key_match"],
            full_text_rank=float(row["full_text_rank"]),
            trigram_score=float(row["trigram_score"]),
            lexical_score=float(row["lexical_score"]),
        )
        for row in rows
    ]


def _validate_fuzzy_threshold(fuzzy_threshold):
    if isinstance(fuzzy_threshold, bool) or not isinstance(
        fuzzy_threshold,
        (int, float),
    ):
        raise ValueError("fuzzy_threshold must be a number.")
    if fuzzy_threshold < 0 or fuzzy_threshold > 1:
        raise ValueError("fuzzy_threshold must be between 0 and 1.")
