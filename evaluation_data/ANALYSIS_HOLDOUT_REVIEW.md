# Phase 2 holdout review

Review `analysis_holdout_v1.json` without running it through the agent. The
file intentionally remains `draft`, and the benchmark loader will reject it by
default until review is complete.

For every case:

1. Read the input without looking at any model output.
2. Compare it directly with `playbooks/evaluation_playbook.md` version 1.
3. Confirm the case type and terminal status.
4. Check every playbook rule, not only `candidate_rule_keys`, for another rule
   that directly governs the same behavior.
5. For a violating case, include every independently applicable rule in both
   `candidate_rule_keys` and `expected_rule_keys`.
6. For clean, ambiguous, and irrelevant cases, keep `expected_rule_keys` empty.
7. Record disputed or changed labels before freezing.

Pay special attention to overlapping rules. For example, a retrying financial
request may implicate both API idempotency and retry safety. Prefer explicit
multi-rule ground truth when both rules independently require the behavior;
do not force the evaluator to guess which valid rule the dataset author meant.

After all 20 cases are approved:

- set `status` to `frozen`;
- set `review.reviewed_on` to the review date;
- set `review.reviewed_case_count` to `20`;
- replace the pending review text with the actual review method and resolution;
- commit the frozen file before making any live model call.

Then validate without API calls:

```bash
python scripts/evaluate_analysis.py \
  --dataset evaluation_data/analysis_holdout_v1.json \
  --model gemini-3.5-flash-lite \
  --dry-run
```

Only after that dry run succeeds should the holdout be evaluated once and
reported without prompt tuning against its results.
