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

Contriever is the first qualification candidate for methodological comparability
with Hu et al., not yet the final frozen embedding. If it satisfies all gates,
freeze it without further comparison for higher scores; otherwise stop and
document failure before defining or testing a fallback.

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
Final `K_MAINT`, `K_ANSWER`, `LME_RETRIEVAL_CONTEXT_TOKENS`, and
`B0_CONTEXT_TOKENS` remain **OPEN**, together with Contriever's retrieval
qualification outcome and exact B0 history material. Model Qualification and
its frozen execution configuration remain unchanged.

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
remain unchanged, as do all gates and grids. Contriever remains the first
qualification candidate, not yet the qualified final embedding. B0 stays
separate from dense-retrieval qualification and must be resolved by deterministic
historical-window calibration before this workstream is closed.
