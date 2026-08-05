# Offline Retrieval Optimization

Source dataset: `phase1-retrieval-v1` (65 cases)

This replay uses saved candidate rankings. It makes no database or embedding API calls.

## Semantic threshold sweep

| Threshold | Recall@5 | Hit@1 | Negative FP@5 | Changed cases |
|---:|---:|---:|---:|---:|
| 0.50 | 1.000 | 0.967 | 1.000 | 0 |
| 0.51 | 1.000 | 0.967 | 1.000 | 1 |
| 0.52 | 1.000 | 0.967 | 1.000 | 1 |
| 0.53 | 1.000 | 0.967 | 1.000 | 1 |
| 0.54 | 1.000 | 0.967 | 1.000 | 1 |
| 0.55 | 1.000 | 0.967 | 1.000 | 3 |
| 0.56 | 1.000 | 0.967 | 0.800 | 4 |
| 0.57 | 1.000 | 0.967 | 0.800 | 5 |
| 0.58 | 1.000 | 0.967 | 0.600 | 7 |
| 0.59 | 1.000 | 0.967 | 0.600 | 13 |
| 0.60 | 0.983 | 0.967 | 0.400 | 16 |
| 0.61 | 0.983 | 0.967 | 0.200 | 18 |
| 0.62 | 0.942 | 0.933 | 0.200 | 23 |
| 0.63 | 0.933 | 0.933 | 0.200 | 32 |
| 0.64 | 0.933 | 0.933 | 0.000 | 41 |
| 0.65 | 0.911 | 0.933 | 0.000 | 44 |
| 0.66 | 0.861 | 0.900 | 0.000 | 48 |
| 0.67 | 0.797 | 0.833 | 0.000 | 54 |
| 0.68 | 0.747 | 0.800 | 0.000 | 57 |
| 0.69 | 0.739 | 0.783 | 0.000 | 59 |
| 0.70 | 0.717 | 0.783 | 0.000 | 60 |
| 0.71 | 0.700 | 0.767 | 0.000 | 63 |
| 0.72 | 0.619 | 0.700 | 0.000 | 64 |
| 0.73 | 0.544 | 0.633 | 0.000 | 65 |
| 0.74 | 0.472 | 0.550 | 0.000 | 65 |
| 0.75 | 0.358 | 0.433 | 0.000 | 65 |

## Fusion sweep

| Lexical policy | Lexical weight | Recall@5 | Hit@1 | MRR | Changed cases |
|---|---:|---:|---:|---:|---:|
| all | 0.00 | 1.000 | 0.967 | 0.979 | 0 |
| all | 0.10 | 1.000 | 0.950 | 0.971 | 7 |
| all | 0.25 | 1.000 | 0.950 | 0.971 | 7 |
| all | 0.50 | 1.000 | 0.950 | 0.971 | 7 |
| all | 0.75 | 1.000 | 0.950 | 0.971 | 7 |
| all | 1.00 | 1.000 | 0.950 | 0.971 | 8 |
| confident | 0.00 | 1.000 | 0.967 | 0.979 | 0 |
| confident | 0.10 | 1.000 | 0.967 | 0.979 | 0 |
| confident | 0.25 | 1.000 | 0.967 | 0.979 | 0 |
| confident | 0.50 | 1.000 | 0.967 | 0.979 | 0 |
| confident | 0.75 | 1.000 | 0.967 | 0.979 | 0 |
| confident | 1.00 | 1.000 | 0.967 | 0.979 | 0 |
| explicit_only | 0.00 | 1.000 | 0.967 | 0.979 | 0 |
| explicit_only | 0.10 | 1.000 | 0.967 | 0.979 | 0 |
| explicit_only | 0.25 | 1.000 | 0.967 | 0.979 | 0 |
| explicit_only | 0.50 | 1.000 | 0.967 | 0.979 | 0 |
| explicit_only | 0.75 | 1.000 | 0.967 | 0.979 | 0 |
| explicit_only | 1.00 | 1.000 | 0.967 | 0.979 | 0 |

## Evidence-preserving recommendations

- Threshold `0.59` is the strongest tested cutoff that preserves baseline Recall@5.
- Fusion policy `confident` with lexical weight `1.00` does not regress baseline Hit@1 or Recall@5.
- Combined development policy: Recall@5 `1.000`, Hit@1 `0.967`, negative FP@5 `0.600`.

These are development-set recommendations, not production thresholds. Validate them on a separately reviewed holdout before adoption.
