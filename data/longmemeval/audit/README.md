# LongMemEval-S Knowledge Update Audit

This directory preserves the final artifacts of the audit that defined the
LongMemEval-S Knowledge Update subset for external validation (checkpoint
`LongMemEvalAudit v1.0`).

## Source dataset

The source file is `data/longmemeval/raw/longmemeval_s_cleaned.json`
(277383467 bytes, SHA-256
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`). The raw
dataset is stored locally and is excluded from version control.

## Candidate selection

Knowledge Update candidates were identified using:

```python
instance["question_type"] == "knowledge-update" \
and not instance["question_id"].endswith("_abs")
```

The source contains 500 instances, of which 78 are Knowledge Update instances.
Removing the 6 abstention variants leaves 72 candidates.

## Audit result

Stage A verified the source identity and checked the structure of each
candidate: 68 passed, 4 were flagged and none failed. Stage B assessed each
candidate against criteria C1–C7. It classified 54 candidates as clean and 18 as
material or uncertain. The Stage B semantic judgments were produced by a
language model, not by human adjudication.

The 18 exceptions went to human review. The first review included 2 and
excluded 16, and an independent blinded second review agreed with all 16
exclusions. The usable set therefore contains 56 instances (54 clean and 2
included by human review), with none pending. It was frozen at
2026-09-12T16:24:03.604794+00:00, before any M1, M2 or M3 policy output was
accessed.

| Exclusion code | Count |
| --- | ---: |
| `E01_WRONG_OR_INVALID_KU_SEMANTICS` | 8 |
| `E03_SUPERSEDED_EVIDENCE_UNTRACEABLE` | 4 |
| `E05_CURRENT_STATE_AMBIGUOUS` | 1 |
| `E06_GOLD_INCONSISTENT_WITH_CURRENT_STATE` | 2 |
| `E07_ANNOTATION_CONFLICT` | 1 |

Reviewer identities, actual review dates and a per-unit second-review rationale
were not recorded. These fields are null in the artifacts.

## Artifacts

| File | Content |
| --- | --- |
| `frozen_usable_ids.json` | The 56 usable question IDs in canonical candidate order, with the selection rule. |
| `exclusions.json` | The 16 excluded units with exclusion code, rationale and review record. |
| `human_adjudication.jsonl` | One record for each of the 18 human-reviewed units, with first- and second-review decisions. |
| `source_verification.json` | Stage A source verification and structural findings. |
| `aggregate_summary.json` | Stage A and Stage B counts, criterion counts, the human review queue, provenance and freeze status. |
| `validation_set_freeze_manifest.json` | Freeze record with final counts, freeze checks and SHA-256 hashes of the audit and methodology files. |

The first five files match the SHA-256 values recorded in
`validation_set_freeze_manifest.json`. The remaining Stage A and Stage B
artifacts listed in the manifest, such as `analysis_packets.jsonl` and
`semantic_assessments.jsonl`, are not part of this directory and are recorded
by hash only.

## Notes on the preserved artifacts

**Stage A snapshot.** `source_verification.json` records the state at the end
of Stage A. Its values `"N_KU_usable": "OPEN"`, `"conformance_analysis":
"NOT_RUN"` and `"validation_set_frozen": false` describe that point. The final
state is recorded in `validation_set_freeze_manifest.json`, with 56 usable
instances and status `FROZEN`.

**Paths outside this repository.** The provenance in `aggregate_summary.json`
names inputs under `data/longmemeval/audit_v1_0/` and `docs/methodology/`, and
`source_verification.json` names the Stage A tool
`scripts/longmemeval/audit_stage_a.py`. None of these paths exist in this
repository. The artifacts were produced under `data/longmemeval/audit_v1_0/` and
later moved to this directory. The methodology files and the Stage A tool were
not migrated. Their recorded hashes refer to the historical bytes. The
methodology files and the recorded version of the Stage A tool are kept in the
researcher's archive and are available on request; their SHA-256 values match
those recorded in the freeze manifest.

**Wording in hash-bound artifacts.** Several fields in the JSON and JSONL
artifacts use vocabulary from the audit process. Examples are "User confirms",
"not supplied" and "authorized by user", where "user" refers to the researcher.
`aggregate_summary.json` describes the Stage B analysis in the same working
vocabulary. The artifacts are kept as they are because their hashes are
recorded in the freeze manifest.
