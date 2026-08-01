import math

from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)
from virtual_staff_engineer.retrieval.lexical import (
    DEFAULT_FUZZY_THRESHOLD,
    lexical_search,
    validate_fuzzy_threshold,
)
from virtual_staff_engineer.retrieval.models import HybridSearchResult
from virtual_staff_engineer.retrieval.semantic import semantic_search
from virtual_staff_engineer.retrieval.validation import (
    validate_category,
    validate_query,
    validate_top_k,
)


DEFAULT_CANDIDATE_K = 20
DEFAULT_RRF_K = 60
DEFAULT_SEMANTIC_WEIGHT = 1.0
DEFAULT_LEXICAL_WEIGHT = 1.0


def hybrid_search(
    query,
    top_k=5,
    candidate_k=DEFAULT_CANDIDATE_K,
    category=None,
    fuzzy_threshold=DEFAULT_FUZZY_THRESHOLD,
    rrf_k=DEFAULT_RRF_K,
    semantic_weight=DEFAULT_SEMANTIC_WEIGHT,
    lexical_weight=DEFAULT_LEXICAL_WEIGHT,
    database_url=None,
    ai_client=None,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimension=EMBEDDING_DIMENSION,
):
    """Retrieve semantic and lexical candidates and fuse their ranks."""
    normalized_query = validate_query(query)
    normalized_category = validate_category(category)
    validate_top_k(top_k)
    validate_top_k(candidate_k)
    if candidate_k < top_k:
        raise ValueError("candidate_k must be greater than or equal to top_k.")
    validate_fuzzy_threshold(fuzzy_threshold)

    _validate_fusion_parameters(
        rrf_k,
        semantic_weight,
        lexical_weight,
    )

    semantic_results = semantic_search(
        normalized_query,
        top_k=candidate_k,
        category=normalized_category,
        database_url=database_url,
        ai_client=ai_client,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
    )
    lexical_results = lexical_search(
        normalized_query,
        top_k=candidate_k,
        category=normalized_category,
        fuzzy_threshold=fuzzy_threshold,
        database_url=database_url,
    )

    return reciprocal_rank_fusion(
        semantic_results,
        lexical_results,
        top_k=top_k,
        rrf_k=rrf_k,
        semantic_weight=semantic_weight,
        lexical_weight=lexical_weight,
    )


def reciprocal_rank_fusion(
    semantic_results,
    lexical_results,
    top_k=5,
    rrf_k=DEFAULT_RRF_K,
    semantic_weight=DEFAULT_SEMANTIC_WEIGHT,
    lexical_weight=DEFAULT_LEXICAL_WEIGHT,
):
    """Combine ranked lists without comparing their incompatible raw scores."""
    validate_top_k(top_k)
    _validate_fusion_parameters(
        rrf_k,
        semantic_weight,
        lexical_weight,
    )

    semantic_by_chunk = _index_first_rank(semantic_results)
    lexical_by_chunk = _index_first_rank(lexical_results)
    chunk_ids = set(semantic_by_chunk) | set(lexical_by_chunk)
    fused_results = []

    for chunk_id in chunk_ids:
        semantic_entry = semantic_by_chunk.get(chunk_id)
        lexical_entry = lexical_by_chunk.get(chunk_id)
        semantic_rank = semantic_entry[0] if semantic_entry else None
        lexical_rank = lexical_entry[0] if lexical_entry else None
        semantic_result = semantic_entry[1] if semantic_entry else None
        lexical_result = lexical_entry[1] if lexical_entry else None
        source_result = semantic_result or lexical_result

        rrf_score = 0.0
        if semantic_rank is not None:
            rrf_score += semantic_weight / (rrf_k + semantic_rank)
        if lexical_rank is not None:
            rrf_score += lexical_weight / (rrf_k + lexical_rank)

        # A zero weight disables that retrieval channel and its one-sided items.
        if rrf_score == 0:
            continue

        fused_results.append(
            HybridSearchResult(
                playbook_chunk_id=source_result.playbook_chunk_id,
                playbook_version_id=source_result.playbook_version_id,
                document_id=source_result.document_id,
                filename=source_result.filename,
                category=source_result.category,
                version=source_result.version,
                rule_key=source_result.rule_key,
                chunk_index=source_result.chunk_index,
                section=source_result.section,
                content=source_result.content,
                embedding_model=source_result.embedding_model,
                semantic_rank=semantic_rank,
                lexical_rank=lexical_rank,
                similarity_score=(
                    semantic_result.similarity_score
                    if semantic_result is not None
                    else None
                ),
                lexical_score=(
                    lexical_result.lexical_score
                    if lexical_result is not None
                    else None
                ),
                rrf_score=rrf_score,
            )
        )

    fused_results.sort(key=_hybrid_sort_key)
    return fused_results[:top_k]


def _index_first_rank(results):
    indexed_results = {}
    for rank, result in enumerate(results, start=1):
        indexed_results.setdefault(result.playbook_chunk_id, (rank, result))
    return indexed_results


def _hybrid_sort_key(result):
    appears_in_both = (
        result.semantic_rank is not None and result.lexical_rank is not None
    )
    available_ranks = [
        rank
        for rank in (result.semantic_rank, result.lexical_rank)
        if rank is not None
    ]
    best_rank = min(available_ranks)
    return (
        -result.rrf_score,
        -int(appears_in_both),
        best_rank,
        result.playbook_chunk_id,
    )


def _validate_fusion_parameters(rrf_k, semantic_weight, lexical_weight):
    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int) or rrf_k < 1:
        raise ValueError("rrf_k must be a positive integer.")

    for name, weight in (
        ("semantic_weight", semantic_weight),
        ("lexical_weight", lexical_weight),
    ):
        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not math.isfinite(weight)
            or weight < 0
        ):
            raise ValueError(f"{name} must be a finite, non-negative number.")

    if semantic_weight == 0 and lexical_weight == 0:
        raise ValueError("At least one retrieval weight must be greater than zero.")
