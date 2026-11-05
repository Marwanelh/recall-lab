# Retrieval evaluation

Generated 2026-11-05T09:18:57+00:00 · code `c1eea8d78a77`

38 cases · 33 indexed passages · chunk 800/150 · k1=1.2 b=0.75

| metric | value |
|---|---|
| Recall@1 | 0.724 |
| Recall@5 | 0.974 |
| Recall@10 | 1.000 |
| MRR | 0.873 |

## Cases that found nothing

None — every case found a relevant passage in its top results.

## Inputs

- dataset `evals/dataset.jsonl` sha256 `ee63926d9d82051e…`
- index sha256 `0d74513a0afe913b…`
- stale check: on

Reproduce with:

```
python -m recall_lab evaluate index.json evals/dataset.jsonl --report evals/REPORT.md
```
