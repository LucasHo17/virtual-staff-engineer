from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    """Source and version identity shared by every retrieval method."""

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


@dataclass(frozen=True)
class SemanticSearchResult(RetrievedChunk):
    """One playbook chunk ranked by vector similarity."""

    similarity_score: float


@dataclass(frozen=True)
class LexicalSearchResult(RetrievedChunk):
    """One playbook chunk ranked by exact, full-text, and fuzzy signals."""

    exact_rule_key_match: bool
    full_text_rank: float
    trigram_score: float
    lexical_score: float
