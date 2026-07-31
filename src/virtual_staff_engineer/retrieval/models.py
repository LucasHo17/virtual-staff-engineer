from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticSearchResult:
    """One citable playbook chunk returned by semantic retrieval."""

    playbook_chunk_id: str
    playbook_version_id: str
    document_id: str
    filename: str
    category: str
    version: int
    rule_key: str
    chunk_index: int
    section: str
    content: str
    embedding_model: str
    similarity_score: float
