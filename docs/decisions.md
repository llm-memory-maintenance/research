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

Exact embedding implementation ID/revision, tokenizer ID/revision, package
versions, and final `K_MAINT`, `K_ANSWER`, `LME_RETRIEVAL_CONTEXT_TOKENS`, and
`B0_CONTEXT_TOKENS` remain **OPEN**, together with the implementation details
listed in the specification. Model Qualification and its frozen execution
configuration remain unchanged.
