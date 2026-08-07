from typing import Protocol, Tuple

from virtual_staff_engineer.analysis.contracts import RuleEvidence, SearchQuery
from virtual_staff_engineer.retrieval.hybrid import (
    DEFAULT_CANDIDATE_K,
    hybrid_search,
)


class RetrievalTool(Protocol):
    """Deterministic tool boundary consumed by the orchestrator."""

    def search(self, query: SearchQuery) -> Tuple[RuleEvidence, ...]:
        """Return versioned evidence for one planned query."""


class HybridRetrievalTool:
    """Adapter from the Phase 1 hybrid retriever to Phase 2 evidence."""

    def __init__(
        self,
        top_k=5,
        candidate_k=DEFAULT_CANDIDATE_K,
        category=None,
        database_url=None,
        ai_client=None,
        search_function=hybrid_search,
    ):
        self.top_k = top_k
        self.candidate_k = candidate_k
        self.category = category
        self.database_url = database_url
        self.ai_client = ai_client
        self.search_function = search_function

    def search(self, query):
        results = self.search_function(
            query.query,
            top_k=self.top_k,
            candidate_k=self.candidate_k,
            category=self.category,
            database_url=self.database_url,
            ai_client=self.ai_client,
        )
        return tuple(
            RuleEvidence(
                playbook_chunk_id=result.playbook_chunk_id,
                playbook_version_id=result.playbook_version_id,
                rule_key=result.rule_key,
                filename=result.filename,
                section=result.section,
                content=result.content,
                retrieval_query=query.query,
                rank_position=rank_position,
                retrieval_score=result.rrf_score,
                semantic_rank=result.semantic_rank,
                lexical_rank=result.lexical_rank,
            )
            for rank_position, result in enumerate(results, start=1)
        )
