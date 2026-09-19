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
No recency weighting is introduced. Implementation rules are frozen in
[configs/retrieval.yaml](../configs/retrieval.yaml) before any calibration result
is observed. Rank by float32 cosine similarity descending; exactly equal scores
are ordered by SHA-256 of UTF-8 `entry_id`, ascending. This hash is solely a
deterministic tie-break, not a retrieval feature. Neither timestamp affects
similarity or retrieval rank. Nonfinite scores or duplicate entry IDs fail closed.

After selection and budget admission, order entries by `last_updated_time` ascending,
then `created_time` ascending, then stable `entry_id` ascending. Compare
timestamps as UTC instants. These rules are shared across maintenance and answer
retrieval and never depend on oracle annotations or observed outcomes.
Here oldest -> newest reflects the effective recency of active content: Update
replaces content and advances `last_updated_time` while preserving entry identity
and `created_time`. Creation time is the deterministic secondary key and entry ID
the final tie-break. This pre-calibration correction affects only post-admission
ordering, never similarity ranking, and introduces no recency weighting.

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
remain mandatory dataset-validation requirements. The corpus checkpoint
`5b0d6fe` includes an offline structural/semantic validator with explicit UTC
timestamp checks; it does not claim full JSON Schema Draft 2020-12 validation.

## 8. Token Counting

Use the official `meta-llama/Llama-3.1-8B-Instruct` tokenizer pinned to
`0e9e39f249a16976918f6564b8830bc894c89659`, loaded as
`PreTrainedTokenizerFast` with Transformers 4.57.6. The exact tokenizer artifact
SHA-256 checksums are recorded in `configs/retrieval.yaml`. Official gated
artifacts were accessed directly; no mirror or Llama model weights are used.

Serialize each selected entry as exactly:

```text
[memory_id=<ID>; created=<CREATED>; updated=<UPDATED>] <TEXT>
```

Join entries with exactly one newline, without a trailing newline or trailing
whitespace. Preserve the stored ID, timestamp strings, and atomic fact text;
reject invalid multiline or trailing-whitespace fields rather than rewriting
them. The empty selection produces an empty string. Include only these four
fields: no annotations, diagnostic tags, scores, ranks, policy labels,
active-state labels, or other evaluator metadata.

Count the complete block with
`len(tokenizer.encode(context, add_special_tokens=False))`. All entry metadata,
delimiters, spaces, and joining newlines count toward
`LME_RETRIEVAL_CONTEXT_TOKENS`. The final question, maintenance candidate, system
prompt, and other prompt wrappers are outside this budget. BOS/EOS and chat
template tokens are excluded because this budget covers memory-context content,
not the full model request.

For each candidate k, take the first k entries from similarity ranking. Admit
whole entries in rank order as a prefix, recounting the complete proposed block
after each addition. When the next entry would exceed the budget, STOP admission:
do not partially truncate it, skip it, or admit any lower-ranked entry. After
admission, reorder chronologically using Section 5 and recount the final block.
If it exceeds the same budget, fail closed; do not repair the selection. This is
prefix admission, not packing. The deterministic helper and offline tests use
non-calibration fixtures; they do not implement a calibration runner.

## 9. Embedding Qualification

Contriever was the **first qualification candidate**, for methodological
comparability with Hu et al. Official Attempt 01 qualified it; it is now the
**qualified/frozen embedding model** for this research design (Section 13.1).
The implementation remains canonical unsupervised
`facebook/contriever` at full repository revision
`2bd46a25019aeea091fd42d1f0fd4801675cf699`. Its associated tokenizer uses the same
repository and revision. No MS MARCO or multilingual variant is substituted.

Apply an adequacy-first rule: evaluate Contriever first under this frozen
protocol; if it satisfies every required retrieval gate, freeze it. Do not run
further embedding comparisons merely to obtain a higher score. If it fails,
STOP and document the failure before defining or testing any fallback candidate.
Do not create an embedding leaderboard or silently change the implementation ID.

### 9.1 Frozen embedding implementation

The [pinned canonical model card](https://huggingface.co/facebook/contriever/blob/2bd46a25019aeea091fd42d1f0fd4801675cf699/README.md)
specifies masked mean pooling of the last hidden state. Load via
`AutoModel.from_pretrained` as `BertModel`, with float32 parameters,
`attn_implementation="eager"`, and `trust_remote_code=False`. Load the associated
tokenizer via `AutoTokenizer` with `use_fast=True` as `BertTokenizerFast`.
Both tokenizer and model configuration specify 512 positions/tokens, including
special tokens; the model has 12 layers, hidden size 768, and vocabulary 30522.
The pinned configuration declares architecture `Contriever` and model type
`bert`; the canonical Transformers model-card path uses `AutoModel`.

Tokenize each input first without truncation, including special tokens, to
detect lengths above 512. Such inputs must STOP execution with an error before
embedding; never silently truncate unexpected content. For admitted inputs,
use `padding=True`, `truncation=True`, `max_length=512`,
`add_special_tokens=True`, and `return_tensors="pt"`. Apply no query/document
prefixes, instruction prefixes, or external text normalization. The pinned
English tokenizer's own lowercasing/normalization remains in effect.

Run on CPU in evaluation mode under `torch.inference_mode()`, using float32
throughout, eager attention, one intra-op and one inter-op thread, deterministic
algorithms enabled, and float32 matmul precision `highest`. Use memory batches
of at most 32 entries in stored order and each query as a single-text batch.
No autocast or reduced-precision embedding representation is used.

For last hidden states `H` and attention mask `M`, compute exactly:

```python
pooled = H.masked_fill(~M[..., None].bool(), 0.0).sum(dim=1) / M.sum(dim=1)[..., None]
```

This produces one 768-dimensional float32 vector per input, includes all
mask-valid tokens (including special tokens), and excludes padding. Reject
empty masks, nonfinite vectors, or zero vector norms. No CLS/max pooling or
sentence-transformers wrapper is used.

Cosine uses `torch.nn.functional.normalize(v, p=2, dim=-1, eps=1e-12)` on both
query and memory vectors, then `query_unit @ memory_unit.T` in float32. Do not
round scores before tie-breaking. No recency weighting is applied.

### 9.2 Environment and artifact provenance

Use Python 3.10.21 on Linux x86_64 with torch 2.8.0+cpu, Transformers 4.57.6,
huggingface_hub 0.36.0, tokenizers 0.22.2, NumPy 2.2.6, and safetensors 0.8.0.
`pyproject.toml` and `uv.lock` record the dependencies; only torch uses the
explicit official PyTorch CPU index. CUDA is not used. This environment freeze
does not claim hardware-independent bitwise embedding reproducibility.

Model/tokenizer files were obtained from official Hugging Face resolve URLs at
the pinned revisions, locally staged under
`/tmp/retrieval-implementation-identity/{contriever,reader}` for verification.
These temporary paths are not portable artifact identities. Record and verify
the repository revisions and file checksums in `configs/retrieval.yaml` whenever
restoring artifacts to a local cache; never fall back to unpinned `main`.
The Contriever weight checksum is checked against official LFS metadata.

Compatibility checks use only new non-calibration text and serialization
fixtures. They load Contriever and both tokenizers, check masked mean pooling
and token counting, and do not evaluate any calibration k, budget, or gate.
Passing these checks freezes implementation identity, not retrieval adequacy.

### 9.3 Completed compatibility verification

Offline verification on 2026-09-17 passed with the versions above and all
recorded artifact checksums matching. Contriever loaded without missing,
unexpected, or mismatched keys. The two smoke sentences below tokenized to
10 and 12 Contriever tokens; masked pooling of the `(2, 12, 768)` last hidden
state produced finite, nonzero float32 vectors of shape `(2, 768)`. Pooling
agreed with a manual mean over mask-valid tokens and was unchanged when padded
hidden states were replaced with large values. L2 normalization passed; the
cosine expression was checked separately using artificial numeric vectors.
An artificial 515-token input was detected without being passed to the model.

The reader tokenizer counted this exact two-entry block as 98 tokens, its first
line alone as 48 tokens, and an empty block as 0 tokens, deterministically with
`add_special_tokens=False`:

```text
[memory_id=smoke-a; created=2025-01-02T00:00:00Z; updated=2025-01-02T01:00:00Z] A paper crane rests on a shelf.
[memory_id=smoke-b; created=2025-01-03T00:00:00Z; updated=2025-01-03T01:00:00Z] Three glass beads sit inside a small wooden box.
```

No calibration case was embedded, no retrieval-success result was observed,
and no calibration or reader inference ran during these compatibility checks.

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

Do not tune B0 on final QA accuracy. `B0_CONTEXT_TOKENS` remains OPEN until the
official calibration is executed. The calibration material and rule are frozen in
`configs/b0-calibration.yaml` and CRST specification Section 12: a dedicated
calibration-only set (`data/b0-calibration`) of 12 structured scenarios naturalized
by both final generators (72 histories), an all-history retention requirement, and
the exact-maximum budget rule with no headroom and no candidate grid. History is
serialized as role-bearing chat messages under the pinned chat template
(CRST specification Section 11); the active-memory case schema does not purport to
encode B0 conversation histories.

B0 is not part of dense-retrieval embedding qualification. Its budget remains OPEN
and must be derived by the separate historical-window calibration before this
workstream is closed.

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
with their provenance. Section 13.1 records the resolved dense-retrieval values;
the B0 budget remains OPEN.

### 13.1 Official Retrieval Calibration Attempt 01 — QUALIFIED

The [immutable Attempt 01 result](../results/retrieval-calibration/attempt-01/calibration.json)
records `status = QUALIFIED` and `embedding_qualified = true`. The resolved
outcome is frozen separately in
[configs/retrieval-qualified.yaml](../configs/retrieval-qualified.yaml):
`K_MAINT = 3`, `K_ANSWER = 5`, and `LME_RETRIEVAL_CONTEXT_TOKENS = 512`.
[configs/retrieval.yaml](../configs/retrieval.yaml) remains the unchanged,
immutable calibration input; its unresolved fields are historical input state,
not the current qualification outcome.

At the pre-specified maximum budget of 3072 tokens, the 0.95 gates yielded:

| K | Maintenance | Gate | Answer | Gate |
| --- | --- | --- | --- | --- |
| 1 | 47/60 | Fail | 40/60 | Fail |
| 3 | 60/60 | Pass | 54/60 | Fail |
| 5 | 60/60 | Pass | 58/60 | Pass |
| 10 | 60/60 | Pass | 60/60 | Pass |
| 20 | Not in maintenance grid | — | 60/60 | Pass |

With the selected K values held fixed:

| Shared budget (tokens) | Maintenance | Answer | Both gates |
| --- | --- | --- | --- |
| 512 | 60/60 | 58/60 | Pass |
| 1024 | 60/60 | 58/60 | Pass |
| 2048 | 60/60 | 58/60 | Pass |
| 3072 | 60/60 | 58/60 | Pass |

512 was selected because it was the smallest shared qualifying budget. No
selected top-k context was budget-limited at 512 tokens; maximum serialized
context lengths were 177 tokens for maintenance and 283 for answer retrieval.
`answer-021` and `answer-049` remained ranking misses at K=5: their oracles were
absent from `ranked_top_k_ids`, so these were not budget failures. Answer K=10
scoring 60/60 does not supersede K=5 because the protocol selects the smallest
qualifying K. No post-hoc tuning was performed.

Provenance: protocol `24eb542`, corpus `5b0d6fe`, retrieval implementation
`4a88d9b`, official runner/source commit
`82977b7fe7baaa8221398329bcdb6b70c86048e9`, and evidence archive commit `7bb7598`.
The result SHA-256 is
`fc761160890792c654a2b4083a09e46cd6c9b2a6c6893d036bda8ffafdaaeec0`;
the input configuration SHA-256 is
`c00f6cf6fac8bf14f24bab6b16b7929c34a62369b9c2e8eee254faed919dbcf9`;
the dataset SHA-256 remains
`ce9605fe777febafde20b4675cb6a2fb456b0d12cd649001c25d703e6e4e9079`.

These synthetic engineering calibration scores measure retrieval target
retention, not downstream QA accuracy or expected LongMemEval performance.
Dense retrieval qualification is complete. The broader Retrieval / Context
Calibration workstream remains open until the separate B0 historical-context
budget is derived under the frozen B0 calibration design.

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

The corpus is frozen as `retrieval-calibration-v1`, seed `20260917`, 140 cases,
at checkpoint `5b0d6fe`, with SHA-256
`ce9605fe777febafde20b4675cb6a2fb456b0d12cd649001c25d703e6e4e9079`.
Protocol checkpoint `24eb542` and corpus contents are unchanged by the
implementation freeze and Attempt 01. The runner is frozen at `82977b7`;
Section 13.1 identifies the archived evidence and resolved configuration.

## 15. Open Decisions

Only the following implementation/calibration decisions remain OPEN here:

- Final `B0_CONTEXT_TOKENS`, derived by the official B0 calibration run. The
  calibration material, serialization, and rule are frozen (Section 12).
