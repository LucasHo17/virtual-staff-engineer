# Retrieval Evaluation

Phase 1 compares semantic, lexical, and hybrid retrieval against the frozen
labels in `evaluation_data/retrieval_cases.json`.

The evaluator checks that PostgreSQL contains the exact referenced playbook
version before it runs. For every selected query it creates one Gemini
embedding, reuses that vector for semantic and hybrid retrieval, and runs the
lexical query independently. Hybrid ranking uses Reciprocal Rank Fusion over
the semantic and lexical candidate lists.

## Safe preflight

Validate the dataset, its labels, and the PostgreSQL corpus without making any
embedding API calls or writing reports:

```bash
python scripts/evaluate_retrieval.py --dry-run
```

## Small smoke benchmark

Run five cases before paying for the complete benchmark:

```bash
python scripts/evaluate_retrieval.py \
  --limit 5 \
  --output-dir evaluation_results/smoke
```

The command reports its embedding-request count before processing. Re-running
against an existing report directory requires the explicit `--overwrite` flag.

## Complete Phase 1 benchmark

```bash
python scripts/evaluate_retrieval.py \
  --output-dir evaluation_results/phase1_v1
```

This currently evaluates 65 cases and therefore makes 65 embedding requests.
It writes:

- `results.json`: configuration, corpus identity, per-case rankings, scores,
  latency, and aggregate metrics.
- `report.md`: overall and query-type summaries plus cases needing review.

You can isolate one or more query groups with repeated `--query-type` options:

```bash
python scripts/evaluate_retrieval.py \
  --query-type exact \
  --query-type fuzzy \
  --output-dir evaluation_results/exact_fuzzy
```

## Metrics

- Recall@K: fraction of expected rules retrieved in the first K unique rules.
- Precision@K: expected rules in the first K divided by K.
- Hit@K: whether at least one expected rule appears in the first K.
- MRR: reciprocal rank of the first expected rule.
- Negative false-positive rate: fraction of negative cases returning any result
  in the first K.
- Latency: mean, p50, and nearest-rank p95 in milliseconds.

Negative-query results are intentionally reported separately. A retriever that
always returns a nearest vector can have good positive recall and still fail to
abstain on unrelated questions; the negative metric makes that limitation
visible.

The report records semantic latency as embedding plus vector search. Hybrid
latency includes embedding, both database searches, and rank fusion. Because
the implementation currently runs those steps sequentially, these are measured
end-to-end baselines rather than hypothetical parallel latency.

## Offline optimization

Replay semantic thresholds and lexical-fusion policies over a completed result
file without querying PostgreSQL or calling the embedding API:

```bash
python scripts/analyze_retrieval_results.py \
  --results evaluation_results/phase1_v1/results.json \
  --output-dir evaluation_results/phase1_v1
```

This produces `optimization.json` and `optimization.md`. The current v1 replay
identifies `0.59` as the strongest tested semantic cutoff preserving development
Recall@5, but that value is deliberately not the default. It must first be
validated on a separately frozen holdout.

Semantic and hybrid search accept an experimental cutoff:

```bash
python scripts/search_semantic.py \
  "Should commit messages follow Conventional Commits?" \
  --category evaluation \
  --min-similarity 0.59
```

Hybrid retrieval defaults to the `confident` lexical policy. Explicit rule-key
mentions, non-zero full-text evidence, and strong trigram evidence may influence
RRF; barely eligible fuzzy matches cannot override semantic ranks. Use
`--lexical-policy all` only to reproduce the original baseline behavior.

## Holdout discipline

`evaluation_data/retrieval_holdout_v1.json` contains new positive paraphrases
and harder engineering-adjacent negative cases. It remains `draft` until the
manual process in `evaluation_data/HOLDOUT_REVIEW.md` is complete.

Do not tune parameters after inspecting holdout output. The original
`retrieval_cases.json` is the development benchmark; the holdout is an unbiased
check of the selected `0.59` threshold and guarded-fusion policy.
