"""Semantic, lexical, and hybrid retrieval (Phase 1)."""

from virtual_staff_engineer.retrieval.lexical import lexical_search
from virtual_staff_engineer.retrieval.models import (
    LexicalSearchResult,
    SemanticSearchResult,
)
from virtual_staff_engineer.retrieval.semantic import semantic_search

__all__ = [
    "LexicalSearchResult",
    "SemanticSearchResult",
    "lexical_search",
    "semantic_search",
]
