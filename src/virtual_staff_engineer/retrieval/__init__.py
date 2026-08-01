"""Semantic, lexical, and hybrid retrieval (Phase 1)."""

from virtual_staff_engineer.retrieval.lexical import lexical_search
from virtual_staff_engineer.retrieval.hybrid import hybrid_search
from virtual_staff_engineer.retrieval.models import (
    HybridSearchResult,
    LexicalSearchResult,
    SemanticSearchResult,
)
from virtual_staff_engineer.retrieval.semantic import semantic_search

__all__ = [
    "HybridSearchResult",
    "LexicalSearchResult",
    "SemanticSearchResult",
    "hybrid_search",
    "lexical_search",
    "semantic_search",
]
