# Retrieval

Phase 1 retrieval converts a natural-language question into citable engineering
playbook chunks.

## Semantic retrieval

```text
query
  ↓
Gemini embedding
  ↓
pgvector cosine distance
  ↓
active + latest + model-compatible playbook chunks
  ↓
ranked citation records
```

Semantic search returns the chunk, rule key, document, playbook version,
embedding model, and similarity score. This metadata lets later agent findings
cite the exact organizational rule used as evidence.

Only the latest version of each active document is eligible. If that version
was produced with a different embedding model, it is excluded instead of
falling back to stale content from an older version.

Run a search:

```bash
python scripts/search_semantic.py \
    "Can an application write authentication tokens to logs?" \
    --top-k 5 \
    --category standards
```

The result is JSON so the same entry point can be inspected manually or called
from shell-based evaluation tooling.

## Lexical retrieval

Lexical search combines three PostgreSQL signals:

1. Exact, case-insensitive rule-key matching
2. `ts_rank_cd` full-text ranking over rule key, section, and content
3. `pg_trgm` similarity for fuzzy wording and typographical errors

Exact rule identifiers receive the strongest baseline boost. Full-text and
trigram scores are then added with explicit weights. These weights are an
initial ranking policy, not a measured optimum; the Phase 1 evaluation dataset
will provide evidence for tuning them.

Run a lexical search:

```bash
python scripts/search_lexical.py "SEC-01" \
    --top-k 5 \
    --category standards
```

Lexical search does not call an embedding API. Its result exposes the exact
match flag, full-text rank, trigram score, combined lexical score, and the same
source/version citation metadata as semantic retrieval.

`pg_trgm` provides fuzzy string similarity. It is not BM25 and is not described
as BM25 in this project.

## Hybrid retrieval

Hybrid search requests a candidate list from both retrievers and combines the
lists with Reciprocal Rank Fusion (RRF):

```text
RRF(chunk) = semantic_weight / (rrf_k + semantic_rank)
           + lexical_weight  / (rrf_k + lexical_rank)
```

The default is equal weighting with `rrf_k = 60`. A chunk returned by both
retrievers receives both contributions, while a one-sided candidate remains
eligible with one contribution. The output preserves semantic rank, lexical
rank, cosine similarity, lexical score, and the fused RRF score.

RRF uses rank positions rather than directly combining cosine similarity and
lexical relevance. This avoids pretending that those raw scores share a common
scale or probability interpretation.

Run a hybrid search:

```bash
python scripts/search_hybrid.py \
    "Can an application write authentication tokens to logs?" \
    --top-k 5 \
    --candidate-k 20 \
    --category standards
```

`candidate_k` controls recall and cost: a larger pool gives fusion more
opportunities to recover relevant chunks but increases database work. It must
be at least as large as `top_k` and will be measured during evaluation.

## Current limitations

- Category matching is exact.
- The database vector column currently requires 1,536 dimensions.
- Lexical scoring weights have not yet been tuned against measured relevance.
- RRF weights and candidate-pool size are unoptimized baselines.
- Retrieval quality has not yet been measured against an evaluation dataset.

The remaining Phase 1 work is to build the evaluation dataset and compare
semantic-only, lexical-only, and hybrid quality and latency.
