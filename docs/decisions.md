# Research Decisions

## 2026-09-16 — Experimental Backbone

The experimental backbone is `meta-llama/llama-3.1-8b-instruct`.

The model is selected for methodological comparability with Hu et al. (2026),
which uses LLaMA-3.1-8B for memory extraction and answer generation in its
default experimental setting.

The language model is not an experimental factor in this study. The backbone
is selected before any comparative M1, M2, or M3 experiment is executed.

## 2026-09-16 — Upstream Provider

The planned OpenRouter endpoint is `coreweave/bf16`.

The provider was selected before model qualification using the following
priority order:

1. technical compatibility;
2. model fidelity;
3. service reliability;
4. operational efficiency;
5. cost.

At the time of inspection, the endpoint exposed BF16 quantization, a
131072-token context window, support for the required generation parameters,
structured-output support, high observed availability, and low observed
latency.

Automatic provider fallback is disabled for experimental execution.

The provider and request configuration passed technical qualification in official
Attempt 3; the execution configuration is now frozen for calibration/pilot work
as recorded below.

## 2026-09-16 — Model Qualification Closed / Qualified

Model Qualification is **CLOSED / QUALIFIED** after official Attempt 3 at
repository checkpoint `fc45fd6`. The frozen execution configuration for
subsequent calibration/pilot work is:

- Model: `meta-llama/llama-3.1-8b-instruct`; gateway: OpenRouter.
- Requested provider endpoint: `coreweave/bf16`; `allow_fallbacks = false`;
  `require_parameters = true`.
- Generation: `temperature = 0.0`, `top_p = 1.0`, `max_output_tokens = 2048`.
- Transport: timeout 180 s; maximum infrastructure retries 2; retry backoff
  1 s and 2 s; retryable HTTP statuses 408, 429, 500, 502, 503, 504.

All ten logical calls passed all qualification criteria, with ten HTTP 200
physical attempts and no retries. The request pinned `coreweave/bf16` with
fallback disabled; metadata identified selected CoreWeave but did not
independently verify the `bf16` suffix or precision variant.

The [Attempt 3 record](../results/model-qualification/attempt-03/qualification-record.md)
documents the evidence and preserved history. The
[archived artifact](../results/model-qualification/attempt-03/qualification.json)
has SHA-256 `125250b9501a3c64333e063d395ecc182036ca91529084b7045b050e1da3161b`.
This is pre-experimental technical evidence, not a thesis main-experiment
result. Reopening qualification requires a later documented technical reason.

## 2026-09-17 — Retrieval / Context Calibration Protocol

The [Retrieval / Context Calibration specification](retrieval-context-calibration.md)
and [dataset schema](../data/retrieval-calibration/schema.json) freeze the
engineering protocol before calibration results are observed. The 56 frozen
LongMemEval-S validation units and their underlying question/evidence content
are excluded from calibration.

The independent synthetic corpus contains 140 cases: 30 changed-state,
30 same-state, 20 new-key/Add diagnostic maintenance cases, and 60 answer cases.
Maintenance success requires the oracle existing target to remain after
similarity ranking, top-k selection, and token-budget truncation; new-key cases
are excluded from its primary denominator. Answer success requires the single
current oracle to remain after the same selection; stale-only retrieval fails.
Each primary gate is 95%, or at least 57/60 cases.

Embed atomic textual facts only, without IDs, timestamps, recency metadata, or
ground-truth annotations. Maintenance queries use candidate text; answer queries
use final questions. Use one embedding model for both tasks, cosine similarity,
no recency weighting, and oldest -> newest ordering after selection. Maintenance
retrieval applies to M2/M3 and answer retrieval to M1/M2/M3 in the LongMemEval-S
setting; CRST retains complete active-memory context.

Contriever was designated the first qualification candidate for methodological
comparability with Hu et al. The predeclared rule required it to be frozen
without further comparison if it satisfied all gates; otherwise, the workflow
would stop before any fallback was defined or tested. Its qualification outcome
is recorded below.

Frozen grids are `K_MAINT = [1, 3, 5, 10]`,
`K_ANSWER = [1, 3, 5, 10, 20]`, and retrieval-context token budgets
`[512, 1024, 2048, 3072]`. Select the smallest qualifying k for each task at
3072 tokens, then hold both fixed and select the smallest shared budget
preserving both gates. Count exact serialized context with a backbone-matched
Llama 3.1 8B Instruct tokenizer; include entries whole.

B0 separately selects the smallest historical window retaining U7 and every
required subsequent turn; append the final question afterward and exclude it
from the historical-window budget. No tuning uses final QA accuracy or
comparative M1/M2/M3 outcomes. A failed grid requires stopping and documented
adjudication, without silently expanding grids, reducing thresholds, switching
embeddings, or changing cases.

Implementation identities and package versions are frozen in the entry below.
Contriever's qualification and final `K_MAINT`, `K_ANSWER`, and
`LME_RETRIEVAL_CONTEXT_TOKENS` are resolved by Attempt 01 below.
`B0_CONTEXT_TOKENS`, exact B0 history material, and historical serialization
remain **OPEN**. Model Qualification and its frozen execution configuration
remain unchanged.

## 2026-09-17 — Dense Retrieval Implementation Freeze

Before any retrieval calibration result is observed, freeze the first candidate
as canonical unsupervised `facebook/contriever`, model and tokenizer revision
`2bd46a25019aeea091fd42d1f0fd4801675cf699`. The official reader tokenizer is
`meta-llama/Llama-3.1-8B-Instruct` at
`0e9e39f249a16976918f6564b8830bc894c89659`. Artifact checksums, model/tokenizer
classes, and execution details are recorded in
[configs/retrieval.yaml](../configs/retrieval.yaml) and the
[calibration specification](retrieval-context-calibration.md).

Use attention-mask-aware mean pooling of the last hidden state, float32 CPU
execution in evaluation/inference mode, and L2 normalization followed by a
float32 dot product for cosine. Contriever's verified input limit is 512 tokens
including special tokens; overlength input fails before truncation. There are
no external normalization steps or query/document prefixes.

The shared one-line serializer is
`[memory_id=<ID>; created=<CREATED>; updated=<UPDATED>] <TEXT>`, joined with one
newline. Count only that memory block with `add_special_tokens=False`. Rank by
cosine descending, breaking exact ties by SHA-256 of UTF-8 entry ID ascending.
Admit a whole-entry top-k prefix, stopping at the first oversized entry without
skipping or partial truncation. Then order by last-updated time, created time,
and entry ID ascending; fail if the final serialized block exceeds the budget.
This pre-calibration ordering correction reflects active-content recency: Update
replaces content and advances last-updated time while retaining entry identity
and created time. It affects only post-admission ordering, not similarity ranking,
and introduces no recency weighting.

The environment is Python 3.10.21, torch 2.8.0+cpu, Transformers 4.57.6, and
huggingface_hub 0.36.0; supporting versions are locked in `uv.lock`. Compatibility
verification uses only non-calibration fixtures and does not qualify retrieval
adequacy or select any k/budget. No hardware-independent bitwise reproducibility
is claimed.

Protocol checkpoint `24eb542`, corpus checkpoint `5b0d6fe`, and corpus SHA-256
`ce9605fe777febafde20b4675cb6a2fb456b0d12cd649001c25d703e6e4e9079`
remain unchanged, as do all gates and grids. At this implementation checkpoint,
Contriever was not yet qualified; Attempt 01 below resolves that outcome. B0 stays
separate from dense-retrieval qualification and must be resolved by deterministic
historical-window calibration before this workstream is closed.

## 2026-09-17 — Official Retrieval Calibration Attempt 01 Qualified

Official Attempt 01 is **QUALIFIED** (`embedding_qualified = true`). Canonical
`facebook/contriever` at `2bd46a25019aeea091fd42d1f0fd4801675cf699` is now the
qualified/frozen embedding for this research design. Freeze **K_MAINT = 3**,
**K_ANSWER = 5**, and **LME_RETRIEVAL_CONTEXT_TOKENS = 512** in the separate
[resolved configuration](../configs/retrieval-qualified.yaml). The reader
tokenizer remains `meta-llama/Llama-3.1-8B-Instruct` at
`0e9e39f249a16976918f6564b8830bc894c89659`.

At 3072 tokens, maintenance K=1 yielded 47/60 (fail); K=3, 5, and 10 each
yielded 60/60 (pass). Answer K=1 yielded 40/60 (fail), K=3 54/60 (fail),
K=5 58/60 (pass), and K=10 and 20 each 60/60 (pass). With K_MAINT=3 and
K_ANSWER=5 fixed, each shared budget of 512, 1024, 2048, and 3072 tokens
yielded 60/60 maintenance and 58/60 answer, passing both 0.95 gates.

512 was selected as the smallest shared qualifying budget. No selected top-k
context was budget-limited at 512; observed maxima were 177 maintenance tokens
and 283 answer tokens. `answer-021` and `answer-049` remained ranking misses at
K=5 because their oracles were absent from `ranked_top_k_ids`, not budget
failures. Answer K=10's 60/60 does not supersede K=5: the frozen rule selects
the smallest qualifying K. No post-hoc tuning was performed. These synthetic
engineering scores are neither downstream QA accuracy nor expected LongMemEval
performance.

The [immutable result](../results/retrieval-calibration/attempt-01/calibration.json)
has SHA-256 `fc761160890792c654a2b4083a09e46cd6c9b2a6c6893d036bda8ffafdaaeec0`,
source commit `82977b7fe7baaa8221398329bcdb6b70c86048e9`, and evidence archive
commit `7bb7598`. Protocol `24eb542`, corpus `5b0d6fe`, and implementation
`4a88d9b` remain unchanged. The immutable input `configs/retrieval.yaml` retains
SHA-256 `c00f6cf6fac8bf14f24bab6b16b7929c34a62369b9c2e8eee254faed919dbcf9`;
the corpus retains SHA-256
`ce9605fe777febafde20b4675cb6a2fb456b0d12cd649001c25d703e6e4e9079`.
The configuration's unresolved input fields are preserved for provenance; resolved outcomes
are recorded only in `configs/retrieval-qualified.yaml`.

Dense retrieval qualification is complete. **B0 remains OPEN**, including its
exact history material, historical serialization, and context budget. The
broader Retrieval / Context Calibration workstream is not fully closed until
that separate deterministic historical-context calibration is resolved under
the existing B0 rule.
