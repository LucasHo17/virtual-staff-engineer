from psycopg.rows import dict_row

from virtual_staff_engineer.database.connection import connect
from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    embed_text,
    get_embedding_client,
    validate_embedding,
)
from virtual_staff_engineer.retrieval.models import SemanticSearchResult
from virtual_staff_engineer.retrieval.validation import (
    validate_category,
    validate_embedding_dimension,
    validate_query,
    validate_top_k,
)


def generate_query_embedding(
    query,
    ai_client=None,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimension=EMBEDDING_DIMENSION,
):
    """Validate and embed a natural-language retrieval query."""
    normalized_query = validate_query(query)
    validate_embedding_dimension(embedding_dimension)
    resolved_client = ai_client or get_embedding_client()
    return embed_text(
        normalized_query,
        resolved_client,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
    )


def semantic_search(
    query,
    top_k=5,
    category=None,
    database_url=None,
    ai_client=None,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimension=EMBEDDING_DIMENSION,
    min_similarity=None,
):
    """Embed a query and return ranked chunks from active, latest playbooks."""
    normalized_query = validate_query(query)
    normalized_category = validate_category(category)
    validate_top_k(top_k)
    validate_embedding_dimension(embedding_dimension)
    validate_similarity_threshold(min_similarity)

    query_embedding = generate_query_embedding(
        normalized_query,
        ai_client=ai_client,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
    )

    return search_by_embedding(
        query_embedding,
        top_k=top_k,
        category=normalized_category,
        database_url=database_url,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        min_similarity=min_similarity,
    )


def search_by_embedding(
    query_embedding,
    top_k=5,
    category=None,
    database_url=None,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimension=EMBEDDING_DIMENSION,
    min_similarity=None,
):
    """Search pgvector using a validated embedding without calling an API."""
    normalized_category = validate_category(category)
    validate_top_k(top_k)
    validate_embedding_dimension(embedding_dimension)
    validate_similarity_threshold(min_similarity)
    validate_embedding(query_embedding, embedding_dimension)
    vector_literal = _to_vector_literal(query_embedding)

    with connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH latest_versions AS (
                    SELECT DISTINCT ON (pv.document_id)
                        pv.playbook_version_id,
                        pv.document_id,
                        pv.version,
                        pv.embedding_model,
                        pv.embedding_dimension
                    FROM playbook_versions AS pv
                    ORDER BY pv.document_id, pv.version DESC
                ),
                ranked_chunks AS (
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
                        pc.embedding <=> %s::vector AS cosine_distance
                    FROM playbook_chunks AS pc
                    JOIN latest_versions AS lv
                      ON lv.playbook_version_id = pc.playbook_version_id
                    JOIN playbook_documents AS pd
                      ON pd.document_id = lv.document_id
                    WHERE pd.archived_at IS NULL
                      AND lv.embedding_model = %s
                      AND lv.embedding_dimension = %s
                      AND (%s::text IS NULL OR pd.category = %s)
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
                    1 - cosine_distance AS similarity_score
                FROM ranked_chunks
                WHERE (
                    %s::double precision IS NULL
                    OR 1 - cosine_distance >= %s
                )
                ORDER BY cosine_distance ASC, playbook_chunk_id ASC
                LIMIT %s;
                """,
                (
                    vector_literal,
                    embedding_model,
                    embedding_dimension,
                    normalized_category,
                    normalized_category,
                    min_similarity,
                    min_similarity,
                    top_k,
                ),
            )
            rows = cur.fetchall()

    return [
        SemanticSearchResult(
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
            similarity_score=float(row["similarity_score"]),
        )
        for row in rows
    ]


def validate_similarity_threshold(min_similarity):
    if min_similarity is None:
        return
    if isinstance(min_similarity, bool) or not isinstance(
        min_similarity,
        (int, float),
    ):
        raise ValueError("min_similarity must be a number or None.")
    if min_similarity < -1 or min_similarity > 1:
        raise ValueError("min_similarity must be between -1 and 1.")


def _to_vector_literal(embedding_vector):
    return "[" + ",".join(str(float(value)) for value in embedding_vector) + "]"
