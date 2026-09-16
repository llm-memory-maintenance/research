# Retrieval and Context Calibration

## 1. Purpose

Retrieval / Context Calibration pre-specifies the engineering protocol for
qualifying an embedding implementation and selecting minimum adequate retrieval
and context parameters before calibration results are observed. It supports
subsequent calibration/pilot work, not inference about thesis hypotheses.

This specification uses [Research Design](research-design.md),
[Dataset Specification](dataset-specification.md),
[Research Decisions](decisions.md), and
[Model Qualification](model-qualification.md) as repository context. The proposal
manuscript source of truth remains
`PROPOSAL_REVISION__PreMicroPilot_v3__2026-09-12.pdf`; this work does not revise it.

## 2. Scope and Non-Goals

Dense active-memory retrieval calibration concerns the LongMemEval-S retrieval
setting. Maintenance retrieval applies to M2 and M3; answer retrieval applies to
M1, M2, and M3. The same embedding model serves both tasks. B0 historical-context
calibration is separate from active-memory retrieval.

CRST M1/M2/M3 retain complete active-memory context and must not be converted
into dense-retrieval experiments. This specification does not generate cases,
implement retrieval, install embeddings or tokenizers, run inference, compare
models in a tournament, or evaluate final reader QA accuracy. It does not reopen
Model Qualification or change the frozen reader execution configuration.

## 3. Frozen Upstream Decisions

Model Qualification is **CLOSED / QUALIFIED**. Official Attempt 3 at checkpoint
`fc45fd6` is archived separately with its
[qualification record](../results/model-qualification/attempt-03/qualification-record.md)
and [artifact](../results/model-qualification/attempt-03/qualification.json).
Its SHA-256 is
`125250b9501a3c64333e063d395ecc182036ca91529084b7045b050e1da3161b`.
These artifacts remain unchanged.

| Execution setting | Frozen value |
| --- | --- |
| Model | `meta-llama/llama-3.1-8b-instruct` |
| Gateway | OpenRouter |
| Requested provider endpoint | `coreweave/bf16` |
| `allow_fallbacks` | `false` |
| `require_parameters` | `true` |
| `temperature` | `0.0` |
| `top_p` | `1.0` |
| `max_output_tokens` | `2048` |
| Timeout | 180 seconds |
| Maximum infrastructure retries | 2 |
| Retry backoff | 1 second, 2 seconds |
| Retryable HTTP statuses | 408, 429, 500, 502, 503, 504 |

The request pins the endpoint with fallback disabled. Metadata identified
selected CoreWeave; it did not independently verify the `bf16` suffix.
The later closure decision governs this configuration despite older pending
qualification statements in historical design text.

Frozen retrieval behavior is dense retrieval over active memory using cosine
similarity, without recency weighting. After similarity, top-k, and token-budget
selection, selected entries are reordered oldest -> newest before reader-context
construction. This applies consistently to both retrieval tasks.

## 4. Calibration Isolation

The frozen LongMemEval-S Knowledge Update external-validation usable set is
N = 56. These units are validation only and must not be retrieval calibration
cases. Calibration data must not copy their underlying question or evidence
content, including content disguised by identifier changes or paraphrasing.

The calibration corpus is independently constructed synthetic/development data.
It is engineering calibration evidence, not an inferential sample for thesis
hypotheses, not part of the frozen validation set, and not a source of final
treatment-effect estimates. Case provenance and isolation must be verified
before calibration, without using validation outcomes to tune retrieval.

## 5. Retrieval Representation

Embed only each entry's atomic textual fact, stored as `text`. Do not embed
entry IDs, created times, last-updated times, explicit recency metadata, or
`annotation`. Ground-truth annotations are for validation and scoring, not
retrieval inputs or reader hints.

The maintenance query is the atomic candidate-memory text. The answer query is
the final natural-language question. Temporal metadata remains available for
deterministic context ordering and other non-embedding processing.

Apply cosine similarity ranking, top-k selection, and whole-entry token-budget
selection, then reorder the selected entries oldest -> newest for the reader.
No recency weighting is introduced. The exact serializer, chronological timestamp
basis, deterministic tie rules, and handling of a non-fitting whole entry must
be specified before execution and held constant across configurations; they
must not depend on oracle annotations or observed retrieval outcomes.

## 6. Retrieval Success Definitions

### 6.1 Maintenance retrieval

Changed-state and same-state cases are the primary target-bearing cases.
For each such case, `maintenance_retrieval_success = 1` if and only if the
uniquely annotated oracle existing active-memory entry remains in the final
retrieved context after similarity ranking, top-k selection, and context-token-
budget truncation. Otherwise success is 0.

Changed-state requires finding the existing state to support Update. Same-state
requires finding the existing state so Update/Noop semantics can be distinguished
correctly. These definitions measure target retention, not a generated operation.

New-key/Add cases have no existing oracle target. They remain diagnostic negative
controls and do not enter the primary maintenance-success denominator. Do not
count their lack of a target as either a primary success or a primary failure.

The primary maintenance gate is >= 95%: at least **57 / 60** target-bearing cases.

### 6.2 Answer retrieval

For each answer case, `answer_retrieval_success = 1` if and only if the single
current oracle memory entry needed to answer the final question remains in the
final retrieved context after similarity ranking, top-k selection, and context-
token-budget truncation. Otherwise success is 0.

Retrieving a stale competing version without the current oracle is failure.
The primary answer gate is >= 95%: at least **57 / 60** answer cases.
Final reader QA accuracy and the direction or magnitude of M1/M2/M3 differences
are not calibration objectives or tuning signals.

## 7. Calibration Dataset Specification

### 7.1 Composition

The corpus contains exactly **140 cases**:

| Task / case type | Cases | Primary denominator |
| --- | ---: | --- |
| Maintenance: changed-state | 30 | Maintenance |
| Maintenance: same-state | 30 | Maintenance |
| Maintenance: new-key/Add | 20 | None; diagnostic only |
| Answer retrieval | 60 | Answer |

For the 60 target-bearing maintenance cases, use 20 cases at each active-memory
size of 16, 64, and 128 entries. Distribute changed-state and same-state as evenly
as practicable across these strata (10 of each per stratum achieves balance).
Each case must include hard distractors with all three roles: same entity and
different attribute; different entity and same or semantically similar attribute;
and semantically related but different state key. The existing oracle target
must be unique.

The 20 new-key diagnostic cases must have no active entry matching the candidate
key and no oracle target. Their memory sizes also use 16, 64, or 128; no additional
size quota is imposed on this diagnostic group.

Answer cases cross query wording (direct, paraphrased), memory size (16, 64,
128), and stale competing version (absent, present): 2 x 3 x 2 = 12 cells, with
exactly 5 cases per cell, totaling 60. When stale competition is present, the
condition represents an M1/Add-only-like retrieval pool: an older/superseded
entry for the same underlying state key may coexist with the current entry
because M1 retains rather than replaces prior entries. The current entry remains
the sole oracle; retrieving only the stale retained entry is failure.
This diagnostic condition does not redefine superseded entries as active for
M2/M3: a superseded entry that has been replaced is absent from their active-memory
retrieval pool, consistent with the frozen methodology. The retrieval mechanism
and configuration remain shared across M1/M2/M3; only the available memory
contents may differ as a consequence of maintenance policy. General multi-hop
or multi-oracle QA is excluded unless later documented as a material protocol
change.

### 7.2 Machine-readable structure

[The dataset schema](../data/retrieval-calibration/schema.json) uses JSON Schema
Draft 2020-12. A complete dataset contains `schema_version` (`1.0`), `dataset_id`,
`source` (`synthetic_retrieval_calibration`), and `cases`.

Each case records `case_id`, `task`, `active_memory`, and `active_memory_size`.
Each memory entry contains `entry_id`, atomic `text`, `created_time`,
`last_updated_time`, and ground-truth `annotation`. Times use date-time strings.
Annotation contains `entity`, `attribute` (the canonical attribute/state key),
and `value`, with optional `diagnostic_tags`. The `(entity, attribute)` pair
identifies the underlying state key. Tags may be empty or omitted; entries need
not all be distractors. Annotation is never part of the embedding text.

Maintenance cases additionally contain `maintenance_case_type`, a `candidate`
with `text` and `annotation`, and `oracle_target_entry_id`. Changed-state and
same-state require a non-null target ID; new-key requires null. Answer cases
contain `query_wording`, boolean `stale_competing_version`, `question`, and
`oracle_entry_ids` with exactly one ID. Task-inappropriate fields are rejected.

### 7.3 Dataset validation beyond structural schema validation

Before use, a separate dataset validator and content review must verify:

- Globally unique case IDs and unique entry IDs within each case; every oracle
  reference resolves to an entry in that case.
- Exact 30 changed-state / 30 same-state / 20 new-key / 60 answer composition,
  maintenance size balance, and five answer cases in each of the twelve cells.
- Unique maintenance oracle keys, changed versus unchanged candidate values,
  absence of the new-key candidate key, and all required hard distractor roles.
- One current answer oracle; agreement between question, text, annotation, and
  oracle; stale presence/absence and the competitor's shared key, different
  superseded value, and older chronology.
- Atomic text fidelity to annotations, valid timestamp values, and chronological
  consistency, including created time not later than last-updated time.
- Diagnostic tags consistent with actual roles and oracle references; tags do
  not substitute for semantic/content validation.
- Provenance and no overlap with the 56 frozen validation units or their
  underlying question/evidence content.

The schema enforces total case count, allowed fields and values, single-oracle
answer cardinality, maintenance target nullability, and memory length matching
the declared size. It does not claim to enforce ID uniqueness across objects,
reference integrity, composition/cell quotas, or semantic isolation. These
remain mandatory dataset-validation requirements; no validator is implemented
in this specification task. Date-time format checking must be enabled explicitly
in a later validator, since support is not guaranteed by schema loading alone.

## 8. Token Counting

Use a tokenizer corresponding to the frozen Llama 3.1 8B Instruct reader for
retrieval-context budgeting. The backbone-matched principle is frozen; the exact
tokenizer repository/implementation ID, revision, checksum, and library versions
remain OPEN pending implementation verification. No unverified ID is prescribed.

Count tokens over the exact serialized context actually sent to the reader,
including delimiters and any metadata genuinely included in that context.
Whole-context overhead must fit the budget as well as entries. Verify the token
count of the final chronological serialization. An entry is included only when
its complete serialized representation fits the remaining budget; memory text
must never be partially truncated. Ground-truth annotations are not exposed to
the reader. Freeze serialization and token-counting details before measuring
candidate configurations.

## 9. Embedding Qualification

Contriever is the **first qualification candidate**, for methodological
comparability with Hu et al. It is **not yet the final frozen embedding model**.
Its exact implementation identifier and revision remain OPEN pending verification.

Apply an adequacy-first rule: evaluate Contriever first under this frozen
protocol; if it satisfies every required retrieval gate, freeze it. Do not run
further embedding comparisons merely to obtain a higher score. If it fails,
STOP and document the failure before defining or testing any fallback candidate.
Do not create an embedding leaderboard or silently choose an implementation ID.

## 10. Top-k Calibration

Frozen grids:

- `K_MAINT candidates = [1, 3, 5, 10]`
- `K_ANSWER candidates = [1, 3, 5, 10, 20]`

At the maximum pre-specified retrieval-context budget of 3072 tokens, choose the
smallest `K_MAINT` reaching maintenance success >= 0.95 and the smallest
`K_ANSWER` reaching answer success >= 0.95. Both gates are measured after
budget truncation. A larger k is not selected solely for a higher score once
the threshold is met. If either grid has no qualifying k, follow the stop rule
in Section 13.

## 11. Retrieval Context-Budget Calibration

Frozen grid:

`LME_RETRIEVAL_CONTEXT_TOKENS candidates = [512, 1024, 2048, 3072]`

First select the minimum qualifying maintenance and answer k values at 3072
tokens. Hold both k values fixed, then test budgets from smallest to largest.
Choose the smallest shared budget preserving **both** maintenance success >= 0.95
and answer success >= 0.95. Include entries whole; do not partially truncate
memory text. Do not change k while searching this budget grid.

## 12. B0 Context Calibration

B0 uses recent historical conversation context, not active-memory vector
retrieval. Select the smallest historical-window token budget that still contains
U7 and every conversation turn after U7 that must precede the final question.
The window must preserve that required historical suffix completely across the
calibration material. Append the final question after historical-window selection;
it does not count toward the historical-window budget.

Do not tune B0 on final QA accuracy. `B0_CONTEXT_TOKENS` remains OPEN until
deterministic calibration is executed. B0 history material and serialization
must be fixed before that execution; the active-memory case schema does not
purport to encode B0 conversation histories.

## 13. Selection and Freeze Rules

Pre-specify the dataset, implementation identities, serialization, and grids
before observing calibration results. Favor adequacy over leaderboard
maximization and the minimum qualifying configuration over maximum recall.
Do not tune on final QA accuracy, comparative M1/M2/M3 outcomes, or the 56 frozen
external-validation units. No post-hoc threshold reduction is permitted.

The threshold remains **0.95** for each primary retrieval task. If no
pre-specified configuration satisfies the required gates, **STOP** and document
the failure. Do not silently expand a grid, lower the threshold, switch embedding
model, or change cases. Any material change requires explicit documented
adjudication before another calibration run.

Freeze the qualifying embedding implementation, selected k values, smallest
shared retrieval-context budget, and deterministically calibrated B0 budget
with their provenance. No final parameter value is selected by this document.

## 14. Required Artifacts

Later implementation/execution must preserve at minimum:

- The exact calibration dataset, its checksum, and per-case oracle annotations.
- Exact embedding implementation ID/revision and tokenizer ID/revision, verified
  tokenizer provenance, and package/library versions.
- Candidate grids and per-configuration retrieval results, including per-case
  target retention after truncation, diagnostic new-key results, selected IDs,
  token counts, and deterministic serialization/ordering rules.
- Selected `K_MAINT`, `K_ANSWER`, and `LME_RETRIEVAL_CONTEXT_TOKENS`.
- Selected `B0_CONTEXT_TOKENS`, the fixed historical material used, and evidence
  that U7 and the required subsequent turns remain in each window.
- Final freeze record and source commit used for official calibration.

No result artifacts, calibration cases, retrieval implementation, or executable
retrieval configuration are created by this specification task.

## 15. Open Decisions

Only the following implementation/calibration decisions remain OPEN here:

- Exact Contriever implementation identifier/revision and final qualification
  outcome; Contriever is not yet the frozen final embedding.
- Exact Llama 3.1 tokenizer implementation identifier/revision and verified checksum.
- Exact package/library versions.
- Exact context serialization, chronological timestamp basis, deterministic
  ranking/ordering tie rules, and whole-entry overflow handling before execution.
- Exact B0 calibration history material and historical-window serialization.
- Final `K_MAINT`.
- Final `K_ANSWER`.
- Final `LME_RETRIEVAL_CONTEXT_TOKENS`.
- Final `B0_CONTEXT_TOKENS`.
