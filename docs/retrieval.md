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

## Current limitations

- Category matching is exact.
- The database vector column currently requires 1,536 dimensions.
- Semantic similarity alone may miss exact identifiers or uncommon keywords.
- Retrieval quality has not yet been measured against an evaluation dataset.

Lexical retrieval and hybrid fusion will address complementary recall failure
modes in the next Phase 1 steps.
