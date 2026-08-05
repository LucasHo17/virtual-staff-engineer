# Offline Retrieval Optimization

Source dataset: `phase1-retrieval-holdout-v1` (20 cases)

This replay uses saved candidate rankings. It makes no database or embedding API calls.

## Semantic threshold sweep

| Threshold | Recall@5 | Hit@1 | Negative FP@5 | Changed cases |
|---:|---:|---:|---:|---:|
| 0.50 | 1.000 | 1.000 | 1.000 | 0 |
| 0.51 | 1.000 | 1.000 | 1.000 | 0 |
| 0.52 | 1.000 | 1.000 | 1.000 | 0 |
| 0.53 | 1.000 | 1.000 | 1.000 | 0 |
| 0.54 | 1.000 | 1.000 | 1.000 | 0 |
| 0.55 | 1.000 | 1.000 | 1.000 | 0 |
| 0.56 | 1.000 | 1.000 | 1.000 | 0 |
| 0.57 | 1.000 | 1.000 | 1.000 | 2 |
| 0.58 | 1.000 | 1.000 | 1.000 | 3 |
| 0.59 | 1.000 | 1.000 | 1.000 | 4 |
| 0.60 | 1.000 | 1.000 | 1.000 | 6 |
| 0.61 | 1.000 | 1.000 | 0.900 | 8 |
| 0.62 | 1.000 | 1.000 | 0.800 | 9 |
| 0.63 | 1.000 | 1.000 | 0.800 | 13 |
| 0.64 | 1.000 | 1.000 | 0.500 | 19 |
| 0.65 | 1.000 | 1.000 | 0.400 | 20 |
| 0.66 | 1.000 | 1.000 | 0.400 | 20 |
| 0.67 | 0.900 | 0.900 | 0.200 | 20 |
| 0.68 | 0.900 | 0.900 | 0.200 | 20 |
| 0.69 | 0.700 | 0.700 | 0.100 | 20 |
| 0.70 | 0.600 | 0.600 | 0.100 | 20 |
| 0.71 | 0.600 | 0.600 | 0.000 | 20 |
| 0.72 | 0.500 | 0.500 | 0.000 | 20 |
| 0.73 | 0.300 | 0.300 | 0.000 | 20 |
| 0.74 | 0.100 | 0.100 | 0.000 | 20 |
| 0.75 | 0.100 | 0.100 | 0.000 | 20 |

## Fusion sweep

| Lexical policy | Lexical weight | Recall@5 | Hit@1 | MRR | Changed cases |
|---|---:|---:|---:|---:|---:|
| all | 0.00 | 1.000 | 1.000 | 1.000 | 0 |
| all | 0.10 | 1.000 | 1.000 | 1.000 | 1 |
| all | 0.25 | 1.000 | 0.900 | 0.950 | 2 |
| all | 0.50 | 1.000 | 0.900 | 0.950 | 2 |
| all | 0.75 | 1.000 | 0.900 | 0.950 | 2 |
| all | 1.00 | 1.000 | 0.900 | 0.950 | 2 |
| confident | 0.00 | 1.000 | 1.000 | 1.000 | 0 |
| confident | 0.10 | 1.000 | 1.000 | 1.000 | 1 |
| confident | 0.25 | 1.000 | 1.000 | 1.000 | 1 |
| confident | 0.50 | 1.000 | 1.000 | 1.000 | 1 |
| confident | 0.75 | 1.000 | 1.000 | 1.000 | 1 |
| confident | 1.00 | 1.000 | 1.000 | 1.000 | 1 |
| explicit_only | 0.00 | 1.000 | 1.000 | 1.000 | 0 |
| explicit_only | 0.10 | 1.000 | 1.000 | 1.000 | 0 |
| explicit_only | 0.25 | 1.000 | 1.000 | 1.000 | 0 |
| explicit_only | 0.50 | 1.000 | 1.000 | 1.000 | 0 |
| explicit_only | 0.75 | 1.000 | 1.000 | 1.000 | 0 |
| explicit_only | 1.00 | 1.000 | 1.000 | 1.000 | 0 |

## Locked holdout policy

- Semantic threshold: `0.59`
- Lexical policy: `confident`
- Lexical weight: `1.00`
- Recall@5: `1.000`
- Hit@1: `1.000`
- Negative FP@5: `1.000`

The sweep tables above are diagnostic only. Selecting a new threshold from this holdout would leak evaluation data into tuning.
