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

## 2026-09-17 — CRST Conversation, Memory, and B0 Implementation Resolutions

New researcher-adjudicated post-Proposal resolutions are frozen in the
[CRST specification](crst-specification.md), without changing its factorial
methodology or completed qualifications. Each of the 16 information events is
one user message followed by deterministic `Noted.`; Q and the final answer
are separate messages. Counts are 32 before Q, 33 through Q, and 34 after the
answer, excluding system instructions. Naturalization models never generate
the acknowledgements.

Explicitly freeze the CRST one-line memory format
`[memory_id=<ID>; created=<CREATED>; updated=<UPDATED>] <TEXT>` and ascending
last-update/creation/memory-ID order over COMPLETE active memory. No retrieval
selection or budget admission applies. M2 same-state Update advances recency;
M3 Noop does not. Do not neutralize this policy consequence post hoc.

Semantic time is the fixed UTC baseline `2000-01-01T00:00:00Z` plus
`event_index` minutes: I1–I7=01–07, U1–U6=08–13, N1=14, U7=15, N2=16.
Acknowledgements and actual execution time never advance semantic time.
Canonical initial IDs are `mem_0001`–`mem_0007`; treatment events reserve
`mem_0008`–`mem_0016` in chronological order, activated only by executed Add.
Fixed canonical target IDs remain evaluator ground truth after model mistakes.
An append-only journal records reference and actual transitions separately;
physical journal storage/schema remains open. Existing actual-decision/error
and Noop execution semantics are unchanged.

B0 uses a contiguous suffix of complete user/acknowledgement exchanges: expand
backward, stop at the first nonfitting exchange, never skip or truncate, and
present chronologically. An oversized newest exchange yields empty history
and `history_unit_overflow`, failing calibration. Structural calibration must
retain complete U7 and N2 exchanges; main selection is blind to U7 identity.

Explicitly extend the pinned Llama tokenizer
`meta-llama/Llama-3.1-8B-Instruct` at
`0e9e39f249a16976918f6564b8830bc894c89659` to B0 marginal chat-template counting:
`T_chat(system + history) - T_chat(system)`, excluding Q and final generation
prefix/output. The system prompt is outside the historical budget. This local
protocol count is distinct from provider-reported usage and does not assert
identical provider rendering. B0 history material, grid, and final budget remain
OPEN; no B0 calibration has run.

## 2026-09-17 — Generator Qualification Plan and Candidate Pair

The [Generator Qualification plan](generator-qualification.md) declares primary
candidates `openai/gpt-5.6-sol` and `anthropic/claude-sonnet-5`, with corresponding
fallbacks `openai/gpt-5.6-terra` and `anthropic/claude-opus-5`. They are CANDIDATE,
not QUALIFIED. Different vendor/family construction tools must independently
pass an absolute fidelity contract, not a ranking or downstream performance gate.
Fallbacks activate only for corresponding contract failure or unavailability.

One logical naturalization call returns one complete structured-truth-controlled
Low/Medium/High triplet. Dedicated qualification comprises 12 base fixtures,
one per frozen domain, separate from final CRST, B0 material, LongMemEval-S, and
Model Qualification fixtures: 24 logical calls for the primary pair. Every
triplet must pass automated checks and manual audit. Do not regenerate semantic
failures into passes. A defective shared prompt/schema revision invalidates the
affected attempt and requires full requalification of both primaries.

After qualification, assign by base scenario with exact 50/50 global allocation
and per-domain balance (at most one difference for odd counts). Final N is a
multiple of 12 but remains unselected; assignment mechanism/seed remains OPEN.
Provider pins, reasoning controls, output limits, timeout/retry settings, and
standard versus batch execution require verification before execution; intended
JSON-schema defaults are not verified capabilities. The initially proposed
zero-temperature/top_p=1 controls were subsequently removed by the Attempt-01
capability adjudication below.
The 5%/2% length tolerances remain PROVISIONAL and are not qualification gates.
No fixtures, qualification calls, or CRST data are created by these records.


## 2026-09-17 — Standard Generator Execution and Shared Naturalization Contract

The researcher selects STANDARD execution for both Generator Qualification and
final full CRST naturalization. Its lower operational/provenance complexity and
the sufficiently small expected naturalization cost do not justify another
asynchronous path for a batch discount. No batch model IDs are used.

Freeze intended routing: `openai/gpt-5.6-sol` with provider order `["openai"]`,
and `anthropic/claude-sonnet-5` with `["anthropic"]`; both disable fallback and
require parameter support. Preserve requested versus observed model/provider
identity separately. Actual route and parameter acceptance remain to verify.
Calls have no tools, web/search, carry-over, or provider-side conversational state.

The [shared naturalization contract](generator-naturalization-contract.md)
specifies prompt `crst-naturalization-prompt/1.1.0`, output schema
`crst-naturalization-triplet/1.0.0`, minimum structured input, and deterministic
validation/manual-audit boundaries. One response contains low/medium/high named
user-text fields only. Deterministic code inserts `Noted.`; gold answers,
experimental answers, and evaluator metadata are not requested outputs.

Low reasoning effort, strict JSON-schema response, and 16,384 maximum output
tokens remain PROPOSED / VERIFY BEFORE FREEZE as a joint combination. Originally
proposed temperature 0 and top-p 1 were removed by the Attempt-01 adjudication
below. A 300-second per-attempt deadline, two infrastructure retries,
1s/2s backoff, established retry statuses and transport classes are recommended
pending probe-implementation review. Schema/semantic/truncation/refusal failures
are not infrastructure retries.

A later two-logical-call capability probe uses this exact contract and intended
pins once per primary model. It checks compatibility/provenance, not semantic
qualification; parameter rejection requires STOP and adjudication. Probe output
cannot become qualification evidence or final CRST data. No probe, fixture
generation, qualification, or experiment is executed by this decision record.


## Generator Capability Probe Attempt-01 — Sampling-Control Adjudication

Attempt-01 (source `a1b03949c25846afed854e0d73e9612eda2bf138`) is valid FAIL
evidence, preserved without modification under
`results/generator-capability-probe/attempt-01/`; result SHA-256:
`9a5f11f458f641914f5cb923a315cd81da9f2dcf6b6153aaa0b56b6d528d0cb9`.
G1 failed HTTP 404 at routing `Filter by Parameters`, with no selected provider
or completion; it did not reach inference. G2 was blocked by the STOP rule.

The researcher-supplied subsequent non-inference catalog audit advertises neither
`temperature` nor `top_p` for either candidate. Remove both symmetrically from
the common execution package; the evidence does not establish either control
as the individual cause. Keep low reasoning, 16,384 output-token ceiling, strict
schema, intended provider pins, transport, and semantic versions unchanged.
This pre-qualification capability correction does not invalidate Attempt-01.
Attempt-02 is required before claiming compatibility; reasoning, schema,
`max_tokens`, and observed routing remain VERIFY. Both generators remain
CANDIDATE. See the [adjudication](generator-naturalization-contract.md#8-two-call-capability-probe-and-attempt-01-adjudication).


## Generator Capability Probe Attempt-02 — CLOSED / PASS

Attempt-02, source `a86ba717e419918765edcc056c8bd852ea94a13b`, passed execution
compatibility on both first-party routes with one HTTP 200 attempt each, no
retry/refusal/truncation, matching model/provider identities, and passed parse
and schema checks. Result SHA-256:
`b8982ac18e74fded527c3680e26082cf505fadbe33edf53ea103494b7ad57c8f`.
Attempt-01 remains preserved VALID FAIL; Attempt-02 remains preserved PASS.
See the [evidence and claim boundary](generator-naturalization-contract.md#9-attempt-02-closure--capability-compatibility-pass).

Freeze for Generator Qualification and final CRST naturalization: STANDARD;
`openai/gpt-5.6-sol` via `[openai]`, `anthropic/claude-sonnet-5` via `[anthropic]`;
no fallback, require_parameters true; low reasoning mapped to `reasoning.effort`,
16,384 output tokens mapped to `max_tokens`, exact strict JSON-schema envelope.
Temperature/top_p remain removed. Prompt/input 1.1.0 and output schema 1.0.0 are
unchanged. Freeze the reviewed 300-second total physical-attempt deadline,
two infrastructure retries, 1s/2s backoff, HTTP 408/429/500/502/503/504 and
established network/connect/read/write/pool timeout classes. Semantic/schema,
refusal/truncation/provider mismatch failures do not trigger infrastructure retries.
The reader timeout is unchanged. No next probe attempt is scheduled.

This resolves the earlier execution VERIFY statements, not semantic qualification.
Sol/Sonnet remain CANDIDATE; Generator Qualification has not executed. No hidden
reasoning equivalence or cross-provider reasoning-token comparability is claimed;
zero reasoning tokens does not imply disabled/ignored reasoning. Later changes
require explicit adjudication and requalification as applicable.


## Generator Qualification — Structured Fixture Construction Pending Review

Construct exactly 12 qualification-only triplets, one per frozen domain, with
one authoritative reference layer and an allowlisted deterministic input-1.1.0
projection. Previous/superseded values, state traces and gold values remain
reference-only. Same approved fixture set for G1/G2; never final CRST/B0/probe
or external-validation material. Semantic prompt/schema and frozen execution
package remain unchanged; no qualification or naturalization is executed.

The qualification-only allocation rotates secondary assignments by domain index:
Low covers the hard distractor and all four other updateable secondaries, with
one repeat; Medium covers the hard distractor and two rotating others; High has
no secondary updates. Dedicated N2 never changes. Exact allocations and hashes
are in the [manifest](../data/generator-qualification/manifest.json). This resolves
construction for these fixtures, not final-CRST secondary allocation. The
capability probe's local allocation/validator is unchanged.

The [audit specification](generator-qualification-audit.md) documents
validation, reproducibility and a blank absolute PASS/FAIL manual-review format.
Sol/Sonnet remain CANDIDATE; Capability Probe remains CLOSED/PASS.

## Generator Qualification — Pre-Freeze Fixture Adjudication

Retain all 12 identifier/code-valued dedicated N2 secondaries as a qualification-set
convention: stable reaffirmation anchors, with domain-specific same-state diversity
already exercised by N1. This neither claims inherent superiority nor requires
identifier-valued N2 for final CRST.

Correct Study Planning's repeated "current" in Q intent; replace Communication's
opaque digest-schedule values with explicit daily 08:00–15:00 target and
16:00–18:00 distractor schedules; use Quantitative Planning target counts
420/450/480/510/540/570/600/630 and distractor counts 720/750/780 sheets, compatible
with encountered bundle sizes. Preserve all other fixture semantics and allocations.

Independently validate target schedules, secondary coverage and shared-position
target values without the builder's allocation helper; require normalized distinct
entity names and basic Q-intent lint. Exact rotations remain construction choices.
Rebuild from authoritative source and update hashes. Semantic contract and frozen
execution package are unchanged; no naturalization or Generator Qualification has
run; Sol/Sonnet remain CANDIDATE.

## Generator Qualification — Fixture Set Freeze

**GENERATOR QUALIFICATION FIXTURE SET: FROZEN.** Final researcher review passed
after the targeted adjudication. Exactly 12 qualification-only fixtures, one per
frozen CRST domain, are immutable and must be used as the same set for G1 and G2.
They cannot become final CRST scenarios. Identifier/code-valued N2 is a
qualification-set convention only. Future changes require explicit defect
adjudication and a new fixture-set version and freeze record. The manifest's
construction-source commit remains the upstream base used to build the artifacts;
it is not a circular claim about the commit that records this freeze. Generator
Qualification has not run; Sol/Sonnet remain CANDIDATE.

## Generator Qualification — Runner Procedural Adjudications

Researcher review of the offline qualification runner design: PASS. Frozen
procedural rules:

1. **Infrastructure retry exhaustion:** a logical call that exhausts the bounded
   retry policy (3 physical attempts, all retryable infrastructure failures)
   makes the official attempt INVALIDATED. It is not a candidate qualification
   FAIL. Collected evidence is preserved with the exact reason, no further calls
   are issued, and nothing reruns automatically. Any approved rerun uses a new
   attempt directory. Candidate semantic/output failures remain qualification
   evidence and do not invalidate the attempt.
2. **Manual-audit applicability:** changed-vs-hypothetical wording applies to
   U1–U7; same-state fidelity to N1/N2; Q-intent fidelity and answer leakage to
   Q only. Current-value fidelity is NA for Q. Superseded-value leakage is NA for
   I1–I7. Output boundary applies to all 17 fields.
3. **Reviewer convention:** `reviewer` is the human reviewer chosen by the
   researcher, never auto-populated. `reviewed_at` is an RFC 3339 timestamp with
   offset. Existing failure/ambiguity notes remain required.

The qualification implementation is NOT YET FROZEN. Live execution requires the
reviewed implementation commit and a subsequent freeze record pinning that
commit and the execution-critical source hashes. Generator Qualification has not
run; Sol/Sonnet remain CANDIDATE.

## Generator Qualification — Implementation Freeze

**GENERATOR QUALIFICATION IMPLEMENTATION: FROZEN.** The reviewed runner
implementation is pinned to implementation commit
`e5e9d500d3e3f0805f5dfbce53eaed5d957ab74e` (`feat: implement generator
qualification runner`). `configs/generator-qualification-implementation-freeze.json`
(schema `generator-qualification-implementation-freeze/1.0.0`) records that
commit and the SHA-256 of the three execution-critical sources:
`experiments/qualify_generators.py`, `experiments/probe_generators.py`, and
`experiments/validate_generator_qualification_fixtures.py`. Live execution
fails closed if the pinned commit, its recorded source hashes, or the current
working-tree source bytes ever drift from one another.

The fixture set, naturalization contract, output schema, and execution package
remain separately frozen and unchanged by this record. Generator Qualification
itself is still NOT EXECUTED; Sol/Sonnet remain CANDIDATE.

## Generator Qualification Attempt-01 — Closed

**GENERATOR QUALIFICATION ATTEMPT-01: CLOSED.** Official Attempt-01 completed
2026-09-18 under the frozen implementation and fixture set, archived at
`results/generator-qualification/attempt-01`. All 24 planned logical calls
completed; the attempt was not invalidated. One infrastructure retry occurred
(G1 `gq-quantitative-planning-01`, HTTP 429 then success) and succeeded within
the frozen retry budget.

Completed human manual audit and adjudication:
`results/generator-qualification/manual-audit/v1/attempt-01.completed.json` and
`results/generator-qualification/adjudication/v1/attempt-01.json`.

**G1 `openai/gpt-5.6-sol` = FAIL.** Basis: one researcher-approved manual
`natural_english` failure at `gq-study-planning-01` / `low` / `I6`. All other
applicable manual checks across G1's 12 fixtures were reviewed PASS. The
task-assignment `q_attribute` automated ambiguity (`gq-task-assignment-01`, all
three variants) was manually resolved PASS as a faithful paraphrase of the
assignee attribute.

**G2 `anthropic/claude-sonnet-5` = FAIL.** Basis: four terminal strict-schema
nonempty-string failures (`gq-project-planning-01`, `gq-task-assignment-01`,
`gq-personal-preference-01`, `gq-service-subscription-01`), each a
machine-detectable terminal failure per the frozen adjudication rule. No
candidate is QUALIFIED.

**No primary generator qualified.** Predeclared fallback paths are now
eligible: `openai/gpt-5.6-terra` (G1) and `anthropic/claude-opus-5` (G2).
Neither fallback has been qualified or executed. Each requires its own
complete 12-fixture qualification under the same frozen contract before any
assignment for final CRST naturalization.

## Fallback Candidate Profile — Offline Implementation, Not Executed

Extended the qualification runner offline to represent the predeclared
fallback pair (`openai/gpt-5.6-terra`, `anthropic/claude-opus-5`) via an
explicit `--profile {primary,fallback}` mechanism, without altering the CLOSED
primary Capability Probe's config, `SLOTS`, or default behavior. Added a
separate, never-CLOSED `configs/generator-capability-probe-fallback.yaml`
(status OPEN/NOT_ASSESSED/UNDER_DEVELOPMENT) using the same shared
naturalization contract, prompt, schema, and probe-only input as the primary,
with the researcher-approved request package identical to the successful
primary package except candidate identity; `temperature`/`top_p` remain
intentionally omitted, not catalog-audited for Terra/Opus. Live fallback
Generator Qualification is gated on the fallback Capability Probe's config
showing CLOSED/PASS, checked at execution time against that file directly, so
the primary's own CLOSED/PASS evidence cannot satisfy it.

This source change means `configs/generator-qualification-implementation-freeze.json`
(pinning `e5e9d500...`) no longer matches current bytes; the runner now
correctly reports `NOT YET FROZEN FOR LIVE EXECUTION` again rather than
falsely claiming FROZEN. `replay()` was changed to verify an archived attempt's
implementation identity against the git history of the commit that attempt
itself records, rather than against the current working tree, so Attempt-01
remains fully replayable and its adjudication is unchanged: G1/G2 FAIL, no
candidate QUALIFIED. Neither fallback Capability Probe nor fallback Generator
Qualification has executed. Terra/Opus remain CANDIDATE. This implementation
is NOT YET FROZEN; it requires researcher review, commit, and a new freeze
record before any live execution.

## Fallback-Capable Generator Qualification Implementation — Frozen

**FALLBACK-CAPABLE GENERATOR QUALIFICATION IMPLEMENTATION: FROZEN.** The
fallback-capable runner implementation (adding the predeclared Terra/Opus
candidate profile, §"Fallback Candidate Profile" above) was reviewed and is
committed at `3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba`
(`feat: support fallback generator qualification`).
`configs/generator-qualification-implementation-freeze.json` (schema
`generator-qualification-implementation-freeze/1.0.0`) now pins that commit
and the SHA-256 of the three execution-critical sources:

- `experiments/qualify_generators.py`: `df5cddae7385f02f5e283cc84523326297e1d147d5c5ff4288873e77132d9664`
- `experiments/probe_generators.py`: `232be57f0fa527d792c9c0e7f1ad77970a3ebd563f5fe862902b603a40470e92`
- `experiments/validate_generator_qualification_fixtures.py`: `2b099896e4f63022dbe54c08eaa6d37a2ff781625907943e4bf30c26f3604f3e`

This replaces the prior freeze record (which pinned `e5e9d500...`, the
implementation that produced Attempt-01) using the same established,
non-parallel freeze schema and gate mechanism -- no new schema was needed.
Live execution fails closed if the pinned commit, its recorded source hashes,
or current working-tree source bytes ever drift from one another.

This freeze makes both candidate profiles technically eligible for live
execution from the implementation-identity perspective only; it is not itself
authorization, and no qualification call has been made under it. The fallback
Capability Probe remains OPEN/NOT_ASSESSED and has not executed, so
qualification's execution gate still refuses live fallback Generator
Qualification. Terra/Opus remain CANDIDATE, not qualified.

Attempt-01 remains unaffected and fully reproducible: `replay()` verifies an
archived attempt's implementation identity against the git history of the
commit *that attempt itself* records (`e5e9d500...`), independent of the
current live freeze record, so this update does not reinterpret Attempt-01 as
Terra/Opus. Replay, completed human audit validation, and offline adjudication
were reverified after this freeze and still yield G1 FAIL / G2 FAIL, no
candidate QUALIFIED.

## Fallback Capability Probe Attempt-03 — CLOSED / FAIL (Mixed Per-Candidate Outcome)

**FALLBACK CAPABILITY PROBE ATTEMPT-03: CLOSED.** Official Attempt-03 executed
2026-09-18 under the frozen fallback-capable implementation
(`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba`, freeze commit
`d96db6d17b5283316216bca79250a5938fa99750`) and the approved fallback request
package (Sec. 1, "Fallback Candidate Profile"), preserved without modification
under `results/generator-capability-probe/attempt-03/`; result SHA-256:
`96b3b1d4dcb31d2fdb0f3d545fb648d48c9d2969901721583ff5ac9d986c72b4`.

Both logical calls executed; no infrastructure retry occurred on either. G1
`openai/gpt-5.6-terra` call = **PASS** under the approved package: HTTP 200,
matching requested/observed model and provider, no refusal or truncation,
passed parse and strict-schema checks. G2 `anthropic/claude-opus-5` call =
**FAIL**: HTTP 200 with matching model/provider identities, but the response
was a provider/model refusal (`finish_reason: content_filter`,
`native_finish_reason: refusal`) before any parse/schema check could run.
Attempt-03 overall = **FAIL** under the shared all-or-nothing stop-on-first-
non-PASS design; it was not infrastructure-invalidated.

Terra's PASS demonstrates that the approved package is not universally
incompatible across the fallback pair. This does not establish that the
request package cannot interact with Opus's model-specific refusal behavior;
that question is not resolved by this evidence and requires separate review.

No fallback Generator Qualification call was made. Neither Terra nor Opus is
QUALIFIED. The shared `configs/generator-capability-probe-fallback.yaml`
config is left unchanged (`status: OPEN`, `capability_result: NOT_ASSESSED`):
its existing schema represents one shared outcome for the profile as a whole
and cannot represent a mixed per-candidate PASS/FAIL result without a schema
change, which is out of scope for this closure. The authoritative per-candidate
outcome is recorded here instead. Generator Qualification's fallback execution
gate (`fallback_capability_gate()`) therefore continues to refuse live fallback
qualification, correctly and as designed.

No automatic re-probe of Opus is authorized by this closure. No identical
rerun of Attempt-03 is authorized. No second-level fallback for the G2 slot is
currently predeclared or frozen. What happens next for G2 -- whether Opus's
refusal is adjudicated as reproducible/content-specific, and what (if
anything) follows from that -- is a separate methodological decision, not
made here. Primary Attempt-01 (G1/G2 FAIL) and the primary Capability Probe's
own Attempt-01/Attempt-02 evidence remain unaffected and unchanged.

## Fallback Per-Slot Capability Adjudication and Second-Level G2 Selection Principles — Frozen

**Researcher-approved methodological decision, following read-only
adjudication of the Attempt-03 mixed outcome.** Nothing in this entry reopens
or alters Attempt-03 evidence, executes any probe or qualification call, or
selects a replacement model.

**1. Capability compatibility is adjudicated per candidate slot, not per
attempt.** The attempt-level `PASS`/`FAIL` recorded by `execute_probe()` is an
execution/archive roll-up (stop-on-first-non-PASS across the profile's slots
in fixed order); it does not erase a valid, independently evaluated PASS
result for a different slot. This was always the frozen intent of per-slot
qualification (`generator-qualification.md` §5/§6: "Both primary generators
independently meet the same contract"; "activate only the failed side's
predeclared fallback"), now made explicit for capability probing as well.

Therefore, from Fallback Capability Probe Attempt-03 evidence
(`results/generator-capability-probe/attempt-03/`, result SHA-256
`96b3b1d4dcb31d2fdb0f3d545fb648d48c9d2969901721583ff5ac9d986c72b4`, unchanged):

- **G1 fallback `openai/gpt-5.6-terra`: capability status = CLOSED / PASS.**
  HTTP 200, matching requested/returned model and provider, no refusal or
  truncation, strict schema passed, exact approved package sent.
- **G2 fallback `anthropic/claude-opus-5`: capability status = CLOSED / FAIL.**
  Reason: provider-policy refusal (HTTP 200, `finish_reason: content_filter`,
  `native_finish_reason: refusal`), not a schema, parameter, routing, or
  infrastructure failure.

Attempt-03's own recorded overall status remains **FAIL**, unchanged. Terra is
**capability-compatible only** -- it is **not** Generator-Qualified; capability
compatibility is a prerequisite for, not a substitute for, the absolute
12-fixture qualification gate. Opus is **not eligible for Generator
Qualification** on this evidence. **No identical Opus re-probe is
authorized**: refusal is a terminal, non-retryable outcome under the frozen
transport policy, and the naturalization contract prohibits turning a refusal
into a pass through regeneration or continuation without an explicitly
reviewed and versioned contract change, for which no defect evidence exists.

**2. The G2 slot remains an Anthropic-family slot.** Opus's capability FAIL
does not relax the frozen two-generator, vendor-family-diversified design
(`generator-qualification.md` §2: "use different OpenAI/Anthropic
families/vendors to diversify naturalization provenance"). Any later decision
to relax this vendor-family requirement -- for example, if no further
Anthropic-family candidate proves viable -- requires its own separate,
explicit methodological adjudication and is not decided here.

**3. Second-level G2 selection principles (frozen; no candidate named).**
Before any replacement G2 candidate is named or called, its selection must
satisfy all of the following, decided in advance of observing that
candidate's behavior:

- belongs to the Anthropic family;
- is distinct from the already-failed `anthropic/claude-sonnet-5` (primary)
  and `anthropic/claude-opus-5` (first fallback);
- is available through the intended OpenRouter route at selection time;
- uses the Anthropic first-party provider route (`provider.order=["anthropic"]`);
- is evaluated using the same capability request package used for the primary
  and first fallback pair, unless a separately reviewed and versioned contract
  change is adopted first;
- is named and frozen before any CRST or naturalization-quality outcome from
  that candidate is observed;
- is never chosen by retry-until-pass, post-hoc sample quality, or downstream
  effectiveness;
- has every failed probe/qualification attempt preserved, exactly as Attempt-01
  and Attempt-03 are preserved.

If an ordered list of backup candidates is later adopted, that ordering itself
must be frozen, in writing, before the first candidate on it is probed --
never assembled reactively after seeing a result.

**4. Approved future procedural order (none of these steps is executed by
this entry):**

1. Freeze these methodological decisions (this entry).
2. Implement generic per-slot capability state and single-slot probe/
   qualification support (a code/config change, reviewed separately).
3. Researcher review of that implementation.
4. Commit.
5. Re-freeze the execution-critical implementation (a new
   `configs/generator-qualification-implementation-freeze.json` pinning the
   reviewed commit).
6. Generator Qualification of Terra may then run independently, on the same
   frozen 12 fixtures, prompt, schema, and absolute gate.
7. Separately select the next G2 candidate using the frozen criteria in item 3.
8. Run that candidate's own Capability Probe.
9. Only if capability closes PASS, run its full 12-fixture Generator
   Qualification.
10. Final CRST generator assignment (`generator-qualification.md` §8, "applicable
    after both generator slots qualify") remains blocked until both G1 and G2
    slots each contain a Generator-Qualified candidate.

No step beyond (1) has been performed. Sol, Sonnet, and Opus remain
disqualified/not-qualified as already recorded; Terra remains CANDIDATE for
Generator Qualification, not qualified. No new G2 model has been selected.

## Per-Slot Capability State and Single-Slot Execution — Implemented Offline

Implemented step (2) of the approved future procedural order above: generic
per-slot capability state and single-slot Capability Probe / Generator
Qualification support. Offline only; not executed, not yet researcher-reviewed,
not committed, not re-frozen.

`configs/generator-capability-probe-fallback.yaml` gained a `schema_version`
and an additive `slots:` section recording, per candidate slot, exactly the
frozen adjudication above: G1 `openai/gpt-5.6-terra` CLOSED/PASS; G2
`anthropic/claude-opus-5` CLOSED/FAIL (provider-policy refusal); both citing
Attempt-03. The whole-profile `status`/`capability_result` fields are
unchanged (`OPEN`/`NOT_ASSESSED`) and remain the attempt-level roll-up. A
capability entry only applies when its recorded `model` matches the slot's
current candidate exactly; a stale or replaced candidate has no evidence.

`experiments/probe_generators.py` and `experiments/qualify_generators.py`
both gained an optional `--slot {G1,G2}` (default: full profile, unchanged
historical behavior). `qualify_generators.slot_capability_gate()` replaces the
former whole-profile `fallback_capability_gate()`; it runs generically for
every profile and slot in `collect()`, passing transparently for the primary
(uniform CLOSED/PASS, no `slots:` section) and correctly gating the fallback
per candidate: G1 Terra permitted, G2 Opus refused, any future unassessed G2
candidate refused, primary evidence unable to satisfy a fallback slot.
`execute_probe()` additionally refuses to reopen an already-CLOSED slot when
given its profile name.

The official result-path identity for a single-slot attempt is left OPEN
(not invented); preview shows an explicit placeholder string, and live
single-slot execution requires an explicit `--output-directory`.

This source change means the current implementation freeze
(`configs/generator-qualification-implementation-freeze.json`, pinning
`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba`) no longer matches; the runner
correctly reports `NOT YET FROZEN FOR LIVE EXECUTION` again. Primary
Capability Probe Attempt-01/Attempt-02, fallback Capability Probe Attempt-03,
and Generator Qualification Attempt-01 (replay, completed audit, adjudication:
G1/G2 FAIL) were all reverified unchanged after this implementation. Terra
Generator Qualification has not executed. No new G2 candidate has been
selected. Terra/Opus remain CANDIDATE, not Generator-Qualified.

## Per-Slot Implementation Freeze and Official Terra Attempt-02 Path

**PER-SLOT GENERATOR QUALIFICATION IMPLEMENTATION: FROZEN.** The reviewed
per-slot-capable runner implementation (generic per-slot capability state and
single-slot Capability Probe / Generator Qualification support, prior entry
above) is committed at `585b5e2844504fec703287f8dd4869668615671d`
(`feat: support per-slot generator qualification`).
`configs/generator-qualification-implementation-freeze.json` (schema
`generator-qualification-implementation-freeze/1.0.0`, unchanged, no parallel
mechanism introduced) now pins that commit and the SHA-256 of the three
execution-critical sources:

- `experiments/qualify_generators.py`: `89f82fe9f617275d117d793f936ca1d81fd63aa2ed6f138a8bd8e5b4bc731258`
- `experiments/probe_generators.py`: `bf414f46d02400127ba60aa0af1bbcfd4f72c12acba0cdcc8718c9b34774c9cf`
- `experiments/validate_generator_qualification_fixtures.py`: `2b099896e4f63022dbe54c08eaa6d37a2ff781625907943e4bf30c26f3604f3e`

This replaces the prior freeze record (which pinned
`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba`, the fallback-capable
implementation that produced no live evidence on its own) using the same
established schema. Live execution fails closed if the pinned commit, its
recorded source hashes, or current working-tree source bytes ever drift from
one another.

**FROZEN: official Terra single-slot Generator Qualification path =
`results/generator-qualification/attempt-02`.** Rationale: Attempt-01 is the
immutable CLOSED Sol/Sonnet primary qualification; attempt numbering is
sequential within the Generator Qualification result category; this is a new
qualification attempt of the predeclared G1 fallback, not a rerun or repair
of Attempt-01; it will contain only G1 Terra's 12 planned calls, never
Opus's. This freezes only the identity for this specific single-slot attempt;
it does not invent a general default for every future single-slot case (for
example, no G2-slot single-slot path is decided here).

Reverified after this freeze: G1 Terra capability status = CLOSED/PASS
(Attempt-03); G2 Opus capability status = CLOSED/FAIL, provider-policy
refusal (Attempt-03); the per-slot Generator Qualification gate passes for
Terra's exact identity and refuses for Opus's; primary evidence cannot
satisfy the fallback gate; a hypothetical replaced G2 candidate has no
recorded evidence. The G1-only Generator Qualification preview (with
`--output-directory results/generator-qualification/attempt-02`) plans
exactly 12 logical calls for `openai/gpt-5.6-terra` over the frozen 12
fixtures in frozen manifest order, 12 distinct request hashes, no Opus calls,
`qualification_implementation_status: FROZEN FOR LIVE EXECUTION`,
`qualification_status: NOT EXECUTED`. `attempt-02` does not exist.

Primary Capability Probe Attempt-01/Attempt-02, fallback Capability Probe
Attempt-03, and Generator Qualification Attempt-01 (replay, completed audit,
adjudication: G1/G2 FAIL) were all reverified byte-identical and unchanged
after this freeze. Terra Generator Qualification has not executed. No new G2
candidate has been selected. Terra/Opus remain CANDIDATE, not
Generator-Qualified.

## Terra Generator Qualification Attempt-02 — Protocol v1 Closed

**TERRA GENERATOR QUALIFICATION ATTEMPT-02 — PROTOCOL v1 CLOSED.** Official
single-slot Attempt-02 (candidate `openai/gpt-5.6-terra`, G1) completed
2026-09-18/19 local time under the frozen per-slot-capable implementation
(`585b5e2844504fec703287f8dd4869668615671d`, freeze commit
`7b28ea2`), preserved without modification under
`results/generator-qualification/attempt-02/`; result SHA-256
`c15a6f2ab6e087c719e32c92f0f6268d4bf6a5728629a4ff8b1a033761560d5c`.

All 12 logical calls completed; no infrastructure invalidation; 12/12 calls
passed schema/execution (HTTP 200, matching model/provider, parse and strict
schema passed on every call). Automated result: 11 PASS, 1
MANUAL_REVIEW_REQUIRED (`gq-task-assignment-01`, `q_attribute` on Q across
all three variants). The completed human manual audit and offline
adjudication are recorded at
`results/generator-qualification/manual-audit/v1/attempt-02.completed.json`
and `results/generator-qualification/adjudication/v1/attempt-02.json`.

The Task Assignment `q_attribute` ambiguity was manually resolved **PASS** as
a faithful paraphrase of the assignee attribute ("Who is currently assigned
to Task Vireo?"), preserving intended entity/attribute and not leaking the
answer.

`gq-purchase-order-01` failed the historical Protocol-v1 `natural_english`
criterion at events I2 and I3, in all three variants (Low, Medium, High),
for both the Kittiwake and Sandpiper constructions ("has an ordered number
of \<N\> sleeves of empty storage sleeves"). Structured meaning remained
recoverable, and every semantic-fidelity check on this fixture passed; this
is a wording failure, not a truth-corruption failure. The adjudicator's
recorded basis contains exactly **10** `manual_failures` entries for G1: the
6 cell-level natural_english FAILs (I2 and I3, each in Low/Medium/High), the
3 variant-level FAILs those cells produce (one per variant), and 1
fixture-level FAIL for `gq-purchase-order-01` itself, recorded as its own
list entry rather than represented separately.

**Final Protocol-v1 candidate disposition: G1 (Terra) = FAIL.** No other
fixture failed. **Protocol v2 (the proposed comprehensibility/fluency split)
has NOT been frozen or applied anywhere in this closure**; the recorded
`procedure_version` is `generator-qualification-procedure/1.0.0` throughout,
unchanged. Attempt-02's archive remains immutable and byte-identical to its
original execution; Attempt-01's historical v1 dispositions (G1/G2 FAIL) were
reverified unaffected. Opus remains capability CLOSED/FAIL (provider-policy
refusal). No new G2 candidate has been selected. Neither Terra nor Opus is
Generator-Qualified.

## Generator Qualification Protocol v2 — Methodology Frozen, Implementation Freeze r3, Offline Re-adjudication Closed

The methodology is frozen and the offline re-adjudication is closed (see the
final entries of this section). Implementation freeze revision r3 is the current
record; revision r2 (Commit C) is historical provenance. Full specification:
`generator-qualification.md` §14.
Versions: `generator-qualification-procedure/2.0.0`,
`generator-manual-audit/2.0.0`; Protocol v1 (`.../1.0.0`) and all its
artifacts remain immutable historical records.

**Freeze lineage.** Four distinct immutable records: the historical v1 record; v2
revision 1 (`...-freeze-v2.json`, Commit A); v2 revision 2 (`...-freeze-v2-r2.json`,
Commit C `30d65102e618aa5713f0710964978f1eb46c4a15`); and v2 revision 3
(`...-freeze-v2-r3.json`, commit `45f06ae8508485ff2f4d5a886fef89f01bf1b807`), the current record. Each superseded the
previous one when second-level G2 profile support changed the pinned sources (see
the final entries below). The methodology stays 2.0.0.

**Two-commit freeze workflow, revision 1 (historical).** Commit A
(implementation, `6412b368e9c49891510aeb73d1fa208442df3c01`, "feat: implement
generator qualification protocol v2") was committed; its freeze (Commit B)
created `configs/generator-qualification-implementation-freeze-v2.json`,
naming Commit A's real hash -- never an invented or self-referential commit
(`experiments/qualify_generators.py` SHA-256
`38896235ec7a4b9b1fff59d2ae0d0ec6ef7c22ee567e131ac614ca8134355dc0`;
`probe_generators.py`/`validate_generator_qualification_fixtures.py`
unchanged). It reuses the existing protocol-agnostic freeze schema unchanged
rather than forking it (it pins source identity, not a procedure version, so
no new field is invented; the association with
`generator-qualification-procedure/2.0.0` is documented here and in
`generator-qualification.md` §14, and by the `-v2` filename, not by a schema
field). The historical
`configs/generator-qualification-implementation-freeze.json` record is
untouched and still pins only the pre-v2 (per-slot-support) implementation,
and is never read or substituted for a v2 record. Purely offline
v2 operations that create no new evidence (historical v1 → v2 mapping, v2
audit-template construction, v2 adjudication of an already-completed audit)
still consult no freeze record and behave identically regardless of its
presence. Historical Protocol-v1 replay/adjudication of
Attempt-01/Attempt-02 remains unchanged. Protocol v2 supports both offline
re-adjudication of already-archived Protocol-v1 evidence (the v1 → v2
mapping below) and native direct qualification of a future candidate never
qualified under any protocol. No live v2 qualification has been executed.

**Rationale.** Protocol v1 treats every natural-English defect as both an item
defect and a candidate-level disqualifying defect, although the pre-existing
CRST methodology already requires exhaustive manual review of natural English
in the final dataset before freeze. This is a level-of-analysis mismatch: a
fluency defect whose naturalized text still carries a clear, single meaning does not
threaten internal validity like semantic corruption. **Disclosed timing:** v2
is a post-hoc revision introduced after Generator Qualification outcomes were
observed, but before final CRST generation, dataset freeze, and any M1/M2/M3
outcome. It is not motivated by rescuing any candidate.

**Rules.** Level 1 (zero-tolerance hard gates; one failure fails the fixture
and candidate): execution/contract failures (parse, strict schema, required
empty field, refusal, truncation, other terminal failure); every semantic/
structural manual check; cross-variant Q identity; any deterministic automated
semantic FAIL; and **comprehensibility**, judged from the naturalized text as
presented to the experimental model (every relevant entity, attribute,
value/state, change-vs-same-state and revision meaning, and Q intent clear with
a single reasonable interpretation; structured truth is a fidelity reference
only and must never supply meaning the text fails to express; ambiguity,
missing meaning, or meaning recoverable only from hidden structured truth is a
Level-1 FAIL). Level 2: **fluency** — recorded with
notes, counted descriptively, never disqualifying, never ranked. v1
`natural_english` splits into `comprehensibility` (Level 1) and `fluency`
(Level 2). Qualification fixtures are never corrected. A candidate qualifies
only with zero Level-1 failures across all 12 fixtures, all applicable manual
cells complete, and all ambiguities human-resolved.

**Final-CRST fluency-only correction (prospective).** Minimal human surface
edit only, never touching entity/attribute/value, state meaning, polarity,
chronology, Noop semantics, Q intent, or gold answer; full provenance
(original/corrected text, hashes, reviewer, timestamp, reason, per-generator
count); automated re-validation plus manual re-review of all Level-1 checks and
fluency; no resampling. A defect not repairable this way is Level 1.
**OPEN:** handling of a final-CRST item with a Level-1 failure, to be frozen
before final CRST generation; it does not block offline v2 re-adjudication.

**v1 → v2 mapping.** Non-`natural_english` cells carry forward;
`natural_english = PASS` ⇒ comprehensibility PASS, fluency PASS; each
`natural_english = FAIL` is reclassified by the human reviewer, with notes, as
under the same model-visible-text basis (v1 "recoverable meaning" notes are
not v2 judgments), either comprehensibility FAIL (Level 1) or comprehensibility PASS + fluency
FAIL (Level 2), independent of candidate identity or desired outcome.

**Re-adjudication and precedence.** Offline only, symmetric across Sol and
Sonnet (Attempt-01) and Terra (Attempt-02); no new API calls; v1 dispositions
reported alongside, never overwritten. Opus is not re-adjudicated (capability
CLOSED/FAIL; no qualification evidence). **Primary precedence, frozen before
re-adjudication:** if Sol and Terra both qualify under v2, Sol occupies G1 and
Terra is a qualified fallback; if only Terra qualifies, Terra occupies G1; if
neither, G1 is unresolved — never decided by fluency counts, subjective
quality, price, tokens, prestige, or any CRST/M1/M2/M3 outcome. Sonnet's
terminal schema/nonempty-string failures remain Level 1 unless archived
evidence proves otherwise. G2 remains Anthropic-family; no second-level G2
candidate is selected; §12 criteria unchanged.

**Safeguards and layout.** All v1 results preserved; timing disclosed; v2
frozen before re-adjudication; symmetric application; no repeated generation;
no M1/M2/M3 influence; final dataset still exhaustively QC'd; no v1 artifact
rewritten. Future v2 derived artifacts go to
`results/generator-qualification/manual-audit/v2/` and `.../adjudication/v2/`
(created by the closure recorded below); raw evidence stays in `attempt-NN/`.

### Protocol-v2 adjudicator correction: summaries are derived, not manual; freeze revision r2 (2026-09-19)

An audit found an implementation defect: the v2 adjudicator inherited
Protocol v1's requirement that the reviewer manually mark variant, fixture and
candidate dispositions, although the frozen Protocol-v2 rule
(`generator-qualification.md` §14) and the frozen v1 → v2 mapping decision
(summaries left blank, to be recomputed) treat them as derived; only the v1
adjudication table and v1 audit format require manual summaries. Under v2 the
human reviewer now decides only applicable cell-level checks and ambiguity
resolutions; terminal Level-1 failures come directly from archived evidence;
variant, fixture and candidate outcomes are derived by code (Level-2 fluency
never propagates; a Level-1 terminal failure suffices to FAIL a candidate
without reviewing unrelated cells); and a manually supplied v2 summary is
rejected. Protocol-v1 behavior is unchanged. No methodology changed.

Because `experiments/qualify_generators.py` changed, revision 1 of the v2
implementation freeze
(`configs/generator-qualification-implementation-freeze-v2.json`, Commit A) is
superseded for the corrected implementation. It stays immutable historical
provenance of the first v2 implementation (not renamed, modified, deleted or
repurposed). The active v2 freeze target is now
`configs/generator-qualification-implementation-freeze-v2-r2.json`, decided as
the version-safe successor path; `r2` names the freeze revision only, and the
methodology versions remain `generator-qualification-procedure/2.0.0` /
`generator-manual-audit/2.0.0`. The corrected implementation was committed as
Commit C (`30d65102e618aa5713f0710964978f1eb46c4a15`); the separate freeze commit creates r2, naming
Commit C and pinning `experiments/qualify_generators.py` SHA-256
`4f985518dec34731737794009f4c7841a3584dc0d11c1a9c83ee2e367644f09e`
(`probe_generators.py`/`validate_generator_qualification_fixtures.py`
unchanged), after which `implementation('v2')` reports FROZEN and live v2
execution is enabled by r2 (before r2 existed it correctly reported
NOT_FROZEN). The official result closure was then produced under r2 (see the
final entry of this section).

### Protocol-v2 offline re-adjudication closed under the r2 freeze; G1 = Sol; G2 unresolved (2026-09-19)

Results were produced only by the frozen offline v1 → v2 mapping and the
r2-frozen Protocol-v2 adjudicator (implementation freeze r2, Commit C
`30d65102e618aa5713f0710964978f1eb46c4a15`, the implementation freeze under
which these results were produced; methodology unchanged at 2.0.0). No API call
or generation was used; raw Attempt-01/02 evidence and all Protocol-v1 artifacts and
dispositions are untouched and preserved alongside (Sol, Sonnet and Terra
remain Protocol-v1 FAIL).

The human reviewer, Muhammad Rafly Ash Shiddiqi (2026-09-19T12:40:11+07:00),
made exactly seven cell-level judgments, each approved as comprehensibility
PASS / fluency FAIL (Level-2 finding only), judged from the model-visible
conversation and never from structured truth: Sol
`gq-study-planning-01`/low/I6 (entity, attribute and value explicit, one clear
reading, grammatically malformed) and Terra `gq-purchase-order-01` I2/I3 in
low/medium/high (redundant "sleeves of empty storage sleeves"; the
conversation consistently expresses the attribute as the ordered number of
empty storage sleeves, later mentions giving N sleeves; one dominant reading;
one classification for all six cells sharing the realization pattern). Every
other cell was mapped mechanically or carried forward unchanged from v1.
Variant, fixture and candidate dispositions are derived by code, not human
judgments; the completed audits carry none.

**Final individual Protocol-v2 dispositions (regenerated byte-identically from
the completed audits):** Sol QUALIFIED (0 Level-1 failures; 1 Level-2 fluency
finding; all 12 fixtures derive PASS); Terra QUALIFIED (0 Level-1 failures; 6
Level-2 fluency findings; all 12 fixtures derive PASS); Sonnet FAIL (4 Level-1
terminal "Expected nonempty string" failures in `gq-project-planning-01`,
`gq-task-assignment-01`, `gq-personal-preference-01` and
`gq-service-subscription-01`, which alone make qualification impossible; its 8
remaining fixtures' manual cells were correctly left unreviewed).

**G1 resolution, applied only after the individual dispositions:** by the
frozen primary-precedence rule (both qualify), **Sol occupies G1; Terra
remains a qualified fallback**. No fluency count, subjective quality, price,
token usage or downstream outcome was used. **G2 remains unresolved:** Sonnet
FAILs Protocol v2, Opus remains capability CLOSED/FAIL and outside
qualification, and no second-level G2 candidate is selected here (§12 criteria
unchanged). Artifacts:
`results/generator-qualification/manual-audit/v2/attempt-0{1,2}.completed.json`
and `results/generator-qualification/adjudication/v2/attempt-0{1,2}.json`. This
is a derived, explicitly versioned Protocol-v2 result; it does not amend the
frozen methodology and was not informed by any M1/M2/M3 outcome.


## Second-level G2 candidate frozen: `anthropic/claude-fable-5.1` (2026-09-19)

G2 remains unresolved (Sonnet Protocol-v2 FAIL; Opus capability CLOSED/FAIL;
G1 resolved to Sol, unchanged). Applying the frozen second-level selection
principles (item 3 above), the researcher named `anthropic/claude-fable-5.1` as the second-level G2
candidate **before any capability-probe or qualification call to it; no output
from it has been observed**.

**Identity and route.** Exact immutable identifier `anthropic/claude-fable-5.1`; moving aliases (e.g.
`~anthropic/claude-fable-latest`) and the `:batch` variant are excluded so the
candidate stays reproducible if Anthropic later releases another Fable model.
Provider route: the repository's existing first-party pinning,
`provider.order=["anthropic"]`, `allow_fallbacks=false`,
`require_parameters=true`; no OpenRouter multi-provider auto-routing and no
Azure/Vertex/Bedrock substitution. No new provider policy was invented.

**Basis (eligibility only).** Anthropic family; distinct from
`anthropic/claude-sonnet-5` and `anthropic/claude-opus-5`; available through
OpenRouter with a first-party Anthropic route; structured-output support;
exact identifier available. Not benchmark ranking, prestige or any expected
pass probability. Availability, route and structured-output support are
researcher-attested at selection time and were not independently verified
offline; the capability probe is their first empirical test.

**Package and procedure.** Same capability request package, unchanged; the
frozen record is `configs/generator-capability-probe-second-level-g2.yaml`
(identical to the fallback config except candidate identity; per-slot
capability OPEN/NOT_ASSESSED, no evidence; validated offline by the existing
frozen loader, no source change). No ordered backup list is adopted. Step (8)
of the approved procedural order (this candidate's own Capability Probe) is
pending; a capability FAIL is recorded and the process stops (no
retry-until-pass); only a capability PASS makes it eligible for native
Protocol-v2 Generator Qualification (procedure/audit 2.0.0, same 12 fixtures,
prompt, schema, semantic checks, comprehensibility/fluency audit and r2
adjudicator, all unchanged). Generator Qualification has not run; G2 remains
unresolved until it completes.

**Launch prerequisite.** Candidate profiles are defined in the pinned sources, so
enabling the official CLIs for this candidate required a separate implementation
change (see the next entry).

Sol, Terra, Sonnet, Opus, all Protocol-v1 artifacts, the Protocol-v2
Attempt-01/02 artifacts and the G1 resolution are not reopened or modified.

### Second-level G2 profile support; implementation freeze r3 pending (2026-09-19)

Support for the frozen second-level G2 candidate was added as a `second_level_g2`
profile in `experiments/probe_generators.py` and
`experiments/qualify_generators.py`. The profile resolves exactly one candidate,
G2 `anthropic/claude-fable-5.1` (exact identifier; no alias or `:batch` variant),
from `configs/generator-capability-probe-second-level-g2.yaml`. Routing is
unchanged: `provider.order=["anthropic"]`, `allow_fallbacks=false`,
`require_parameters=true`. The request package is the existing one; the probe
input, qualification fixtures, prompt, output schema, reasoning setting, max
tokens, retry policy and Protocol-v2 criteria are unchanged. Only candidate and
profile routing were added.

The profile supports both stages, so a capability PASS needs no further source
change. The capability preview (`--profile second_level_g2`) contains exactly one
logical call, G2 only. The qualification preview (`--profile second_level_g2
--slot G2 --protocol-version v2`) contains exactly 12 G2 calls on the same 12
frozen fixtures under native Protocol v2, with no G1 call. Qualification remains
blocked by the per-slot capability gate until this candidate's own capability
probe closes PASS. Execution requires an explicit `--output-directory` (no result
path convention exists for single-slot runs), and a `--slot G1` request against
this single-slot profile is rejected instead of selecting zero calls. No call has
been made to this candidate and no output from it exists.

**Freeze consequence.** The pinned sources changed, so the r2 freeze (Commit C) is
historical provenance of the earlier implementation and no longer freezes the
current code. The active v2 freeze target is now the successor path
`configs/generator-qualification-implementation-freeze-v2-r3.json`, which does
not exist yet. Until it is created against the implementation commit,
`implementation('v2')` reports NOT_FROZEN and live v2 execution refuses before
any network request. No historical freeze record (v1, r1, r2) is modified, and
the methodology versions remain 2.0.0. Closed results and the G1 resolution are
unchanged; G2 remains unresolved.

### Protocol-v2 implementation freeze revision r3 (2026-09-19)

Revision 3, `configs/generator-qualification-implementation-freeze-v2-r3.json`,
freezes the implementation that adds the second-level G2 profile. It uses the
existing freeze schema, names implementation commit `45f06ae8508485ff2f4d5a886fef89f01bf1b807`, and
pins `experiments/qualify_generators.py`
(`6765c1e456a7223ea2108cb79851cbfd8858f0f7eba557beb67ff871afe5687d`),
`experiments/probe_generators.py`
(`b48729d6603fa2f5abdf4c468d67ed7e00e335162abf4fbf7f86d680d33248c0`) and
`experiments/validate_generator_qualification_fixtures.py`
(`2b099896e4f63022dbe54c08eaa6d37a2ff781625907943e4bf30c26f3604f3e`). The v1, r1
and r2 records are unmodified and none can substitute for r3: with r3 hidden,
`implementation('v2')` reports NOT_FROZEN even though r1 and r2 exist.

With r3 present, `implementation('v2')` reports FROZEN, so the v2 freeze gate no
longer blocks live execution. Qualification of the second-level G2 candidate
remains blocked by the per-slot capability gate until its own capability probe
closes PASS. The offline previews are unchanged: the capability preview contains
one call (G2, `anthropic/claude-fable-5.1`, first-party Anthropic route) and the
qualification preview contains 12 G2 calls on the same 12 frozen fixtures under
native Protocol v2. No call has been made to this candidate.
