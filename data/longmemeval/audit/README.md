# LongMemEval-S Knowledge Update Audit

This directory preserves the final audit artifacts used to define the
LongMemEval-S Knowledge Update subset for external validation.

## Source dataset

File:

`longmemeval_s_cleaned.json`

SHA-256:

`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`

The raw dataset is stored locally under `data/longmemeval/raw/` and is excluded
from version control.

## Candidate selection

Knowledge Update candidates were identified using:

```python
instance["question_type"] == "knowledge-update" \
and not instance["question_id"].endswith("_abs")
