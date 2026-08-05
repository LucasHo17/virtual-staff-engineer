import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    get_embedding_client,
)
from virtual_staff_engineer.evaluation.corpus import verify_corpus
from virtual_staff_engineer.evaluation.metrics import (
    aggregate_metrics,
    evaluate_ranking,
    validate_cutoffs,
)
from virtual_staff_engineer.retrieval.hybrid import (
    DEFAULT_LEXICAL_POLICY,
    DEFAULT_LEXICAL_WEIGHT,
    DEFAULT_RRF_K,
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_STRONG_TRIGRAM_THRESHOLD,
    filter_lexical_results,
    reciprocal_rank_fusion,
    validate_lexical_policy,
)
from virtual_staff_engineer.retrieval.lexical import (
    DEFAULT_FUZZY_THRESHOLD,
    lexical_search,
    validate_fuzzy_threshold,
)
from virtual_staff_engineer.retrieval.semantic import (
    generate_query_embedding,
    search_by_embedding,
    validate_similarity_threshold,
)
from virtual_staff_engineer.retrieval.validation import validate_top_k


METHODS = ("semantic", "lexical", "hybrid")


@dataclass(frozen=True)
class BenchmarkConfig:
    cutoffs: tuple = (1, 3, 5)
    candidate_k: int = 20
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD
    rrf_k: int = DEFAULT_RRF_K
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = EMBEDDING_DIMENSION
    min_similarity: Optional[float] = None
    lexical_policy: str = DEFAULT_LEXICAL_POLICY
    strong_trigram_threshold: float = DEFAULT_STRONG_TRIGRAM_THRESHOLD

    def validated(self):
        cutoffs = validate_cutoffs(self.cutoffs)
        validate_top_k(self.candidate_k)
        if self.candidate_k < max(cutoffs):
            raise ValueError(
                "candidate_k must be greater than or equal to every cutoff."
            )
        validate_fuzzy_threshold(self.fuzzy_threshold)
        validate_similarity_threshold(self.min_similarity)
        validate_lexical_policy(self.lexical_policy)
        validate_fuzzy_threshold(self.strong_trigram_threshold)
        _validate_fusion_config(
            self.rrf_k,
            self.semantic_weight,
            self.lexical_weight,
        )
        if not isinstance(self.embedding_model, str) or not self.embedding_model:
            raise ValueError("embedding_model must be a non-empty string.")
        if (
            isinstance(self.embedding_dimension, bool)
            or not isinstance(self.embedding_dimension, int)
            or self.embedding_dimension < 1
        ):
            raise ValueError("embedding_dimension must be a positive integer.")
        return BenchmarkConfig(
            cutoffs=cutoffs,
            candidate_k=self.candidate_k,
            fuzzy_threshold=self.fuzzy_threshold,
            rrf_k=self.rrf_k,
            semantic_weight=self.semantic_weight,
            lexical_weight=self.lexical_weight,
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            min_similarity=self.min_similarity,
            lexical_policy=self.lexical_policy,
            strong_trigram_threshold=self.strong_trigram_threshold,
        )


def run_benchmark(
    dataset,
    cases=None,
    config=None,
    database_url=None,
    ai_client=None,
    corpus_verifier=verify_corpus,
    query_embedder=generate_query_embedding,
    semantic_retriever=search_by_embedding,
    lexical_retriever=lexical_search,
    fusion=reciprocal_rank_fusion,
):
    """Evaluate semantic, lexical, and hybrid retrieval over labeled cases."""
    resolved_config = (config or BenchmarkConfig()).validated()
    selected_cases = tuple(cases if cases is not None else dataset.cases)
    if not selected_cases:
        raise ValueError("At least one evaluation case is required.")

    corpus = corpus_verifier(dataset, database_url=database_url)
    if corpus["embedding_model"] != resolved_config.embedding_model:
        raise ValueError(
            "Benchmark embedding model does not match the frozen corpus: "
            f"{resolved_config.embedding_model!r} != "
            f"{corpus['embedding_model']!r}."
        )
    if corpus["embedding_dimension"] != resolved_config.embedding_dimension:
        raise ValueError(
            "Benchmark embedding dimension does not match the frozen corpus: "
            f"{resolved_config.embedding_dimension} != "
            f"{corpus['embedding_dimension']}."
        )

    resolved_client = ai_client
    if resolved_client is None and query_embedder is generate_query_embedding:
        resolved_client = get_embedding_client()

    case_results = []
    for case in selected_cases:
        try:
            case_results.append(
                _evaluate_case(
                    case,
                    dataset.playbook.category,
                    resolved_config,
                    database_url,
                    resolved_client,
                    query_embedder,
                    semantic_retriever,
                    lexical_retriever,
                    fusion,
                )
            )
        except Exception as error:
            raise RuntimeError(
                f"Retrieval benchmark failed for case {case.case_id}: {error}"
            ) from error

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_status": (
            "complete"
            if len(selected_cases) == len(dataset.cases)
            else "partial"
        ),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "status": dataset.status,
            "source_path": dataset.source_path,
            "total_case_count": len(dataset.cases),
            "selected_case_count": len(selected_cases),
            "review": dataset.review,
        },
        "corpus": corpus,
        "config": _config_dict(resolved_config),
        "usage": {"embedding_requests": len(selected_cases)},
        "summary": _summarize(case_results, resolved_config.cutoffs),
        "cases": case_results,
    }


def _evaluate_case(
    case,
    category,
    config,
    database_url,
    ai_client,
    query_embedder,
    semantic_retriever,
    lexical_retriever,
    fusion,
):
    embedding_started = time.perf_counter()
    query_embedding = query_embedder(
        case.query,
        ai_client=ai_client,
        embedding_model=config.embedding_model,
        embedding_dimension=config.embedding_dimension,
    )
    embedding_ms = _elapsed_ms(embedding_started)

    semantic_started = time.perf_counter()
    semantic_results = semantic_retriever(
        query_embedding,
        top_k=config.candidate_k,
        category=category,
        database_url=database_url,
        embedding_model=config.embedding_model,
        embedding_dimension=config.embedding_dimension,
        min_similarity=config.min_similarity,
    )
    semantic_database_ms = _elapsed_ms(semantic_started)

    lexical_started = time.perf_counter()
    lexical_results = lexical_retriever(
        case.query,
        top_k=config.candidate_k,
        category=category,
        fuzzy_threshold=config.fuzzy_threshold,
        database_url=database_url,
    )
    lexical_ms = _elapsed_ms(lexical_started)

    fusion_started = time.perf_counter()
    fusion_lexical_results = filter_lexical_results(
        case.query,
        lexical_results,
        policy=config.lexical_policy,
        strong_trigram_threshold=config.strong_trigram_threshold,
    )
    hybrid_results = fusion(
        semantic_results,
        fusion_lexical_results,
        top_k=config.candidate_k,
        rrf_k=config.rrf_k,
        semantic_weight=config.semantic_weight,
        lexical_weight=config.lexical_weight,
    )
    fusion_ms = _elapsed_ms(fusion_started)

    method_results = {
        "semantic": _method_result(
            semantic_results,
            embedding_ms + semantic_database_ms,
            case.expected_rule_keys,
            config.cutoffs,
        ),
        "lexical": _method_result(
            lexical_results,
            lexical_ms,
            case.expected_rule_keys,
            config.cutoffs,
        ),
        "hybrid": _method_result(
            hybrid_results,
            embedding_ms + semantic_database_ms + lexical_ms + fusion_ms,
            case.expected_rule_keys,
            config.cutoffs,
        ),
    }

    return {
        "case_id": case.case_id,
        "query_type": case.query_type,
        "query": case.query,
        "expected_rule_keys": list(case.expected_rule_keys),
        "notes": case.notes,
        "timing_breakdown_ms": {
            "embedding": embedding_ms,
            "semantic_database": semantic_database_ms,
            "lexical_database": lexical_ms,
            "fusion": fusion_ms,
        },
        "methods": method_results,
    }


def _method_result(results, latency_ms, expected_rule_keys, cutoffs):
    ranked_rule_keys = list(dict.fromkeys(result.rule_key for result in results))
    return {
        "latency_ms": latency_ms,
        "ranked_rule_keys": ranked_rule_keys,
        "metrics": evaluate_ranking(
            expected_rule_keys,
            ranked_rule_keys,
            cutoffs,
        ),
        "candidates": [
            _serialize_candidate(result, rank)
            for rank, result in enumerate(results, start=1)
        ],
    }


def _serialize_candidate(result, rank):
    candidate = {
        "rank": rank,
        "rule_key": result.rule_key,
        "playbook_chunk_id": result.playbook_chunk_id,
        "playbook_version_id": result.playbook_version_id,
        "document_id": result.document_id,
        "filename": result.filename,
        "version": result.version,
        "section": result.section,
    }
    for field_name in (
        "similarity_score",
        "exact_rule_key_match",
        "full_text_rank",
        "trigram_score",
        "lexical_score",
        "semantic_rank",
        "lexical_rank",
        "rrf_score",
    ):
        if hasattr(result, field_name):
            candidate[field_name] = getattr(result, field_name)
    return candidate


def _summarize(case_results, cutoffs):
    overall = {}
    by_query_type = {}
    query_types = sorted({case["query_type"] for case in case_results})
    for method in METHODS:
        overall[method] = aggregate_metrics(
            [case["methods"][method] for case in case_results],
            cutoffs,
        )
        by_query_type[method] = {}
        for query_type in query_types:
            matching = [
                case["methods"][method]
                for case in case_results
                if case["query_type"] == query_type
            ]
            by_query_type[method][query_type] = aggregate_metrics(
                matching,
                cutoffs,
            )
    return {"overall": overall, "by_query_type": by_query_type}


def _config_dict(config):
    return {
        "cutoffs": list(config.cutoffs),
        "candidate_k": config.candidate_k,
        "fuzzy_threshold": config.fuzzy_threshold,
        "rrf_k": config.rrf_k,
        "semantic_weight": config.semantic_weight,
        "lexical_weight": config.lexical_weight,
        "embedding_model": config.embedding_model,
        "embedding_dimension": config.embedding_dimension,
        "min_similarity": config.min_similarity,
        "lexical_policy": config.lexical_policy,
        "strong_trigram_threshold": config.strong_trigram_threshold,
    }


def _validate_fusion_config(rrf_k, semantic_weight, lexical_weight):
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


def _elapsed_ms(started_at):
    return (time.perf_counter() - started_at) * 1000
