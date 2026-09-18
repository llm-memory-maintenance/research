# Generator Qualification

## 1. Purpose and Decision Status

**FROZEN plan; primary Attempt-01 CLOSED, both primaries FAIL.** Generators are
construction tools for CRST natural-language realization, not experimental
treatment factors. This document records researcher-adjudicated post-Proposal
implementation resolutions compatible with the
[CRST contract](crst-specification.md). No candidate is QUALIFIED by
designation. Capability Probe is CLOSED/PASS; 12 structured qualification-only
fixtures are frozen after final researcher review. Official Generator
Qualification Attempt-01 ran under the frozen implementation and fixture set
and closed 2026-09-18: G1 `openai/gpt-5.6-sol` FAIL, G2
`anthropic/claude-sonnet-5` FAIL (§10). Fallback qualification is pending.

Generator diversity addresses dependence on one model family. Qualification
uses absolute fidelity to fixed structured truth, not a relative ranking,
leaderboard, downstream effectiveness comparison, or model tournament.
Completed backbone Model Qualification and Dense Retrieval Qualification remain
CLOSED and unchanged; they do not qualify construction generators.

## 2. Candidates and Predeclared Fallbacks

| Slot | Primary candidate | Predeclared corresponding fallback | Current status |
| --- | --- | --- | --- |
| G1: OpenAI family | `openai/gpt-5.6-sol` | `openai/gpt-5.6-terra` | FAIL (Attempt-01); fallback eligible, not yet qualified |
| G2: Anthropic family | `anthropic/claude-sonnet-5` | `anthropic/claude-opus-5` | FAIL (Attempt-01); fallback eligible, not yet qualified |

**FROZEN:** use different OpenAI/Anthropic families/vendors to diversify
naturalization provenance. Consider a fallback only if its corresponding primary
fails the predeclared contract or becomes operationally unavailable. Preserve the
reason and evidence. Never switch on CRST policy outcomes, CSA/SRR, subjective
preference after seeing final dataset behavior, or final statistical effects.

Historical RC01–RC04 material, if supported by current repository artifacts, is
only prior engineering evidence. It is not Generator Qualification and cannot
establish qualification status. No such evidence is claimed here, and no RC
ranking workflow is revived. Current pricing is not a methodological selection
gate; actual cost may be logged descriptively.

## 3. Naturalization Unit and Output Boundary

**FROZEN:** one logical call naturalizes one complete base-scenario triplet. Its
input is already-fixed structured truth for Low, Medium, and High; its output is
all three variants in one machine-readable structured response. They remain
three separate dataset conversations, not one conversation joined across levels.

This guarantees one generator per triplet, allows common structured facts to be
supplied once, and enables joint matched-control, message-count, and wording
validation. The generator may naturalize wording only; it cannot choose or alter
entities, attributes, values, roles, schedules, state trajectories, reference
operations, Q intent, or gold answer.

The generator does not produce assistant acknowledgements. The deterministic
construction layer inserts exactly `Noted.` after each of the 16 information
messages in each variant. Q is a separate user message. The experimental final
answer is produced only in later policy execution, not by the naturalizer.
The assembled variant therefore has 32 pre-Q historical messages, 33 through Q,
and 34 only after experimental answering. System instructions are excluded.

**SPECIFIED:** shared prompt `crst-naturalization-prompt/1.1.0` and output schema
`crst-naturalization-triplet/1.0.0` are defined in the
[shared naturalization contract](generator-naturalization-contract.md), together
with minimum input requirements and validation responsibilities. Their exact
execution package is frozen after the completed two-call capability probe.
No acknowledgement or experimental answer is requested from the generator.

## 4. Dedicated Qualification Set

**FROZEN composition:** 12 base fixtures, one per frozen domain:

1. Scheduling
2. Travel
3. Project Planning
4. Task Assignment
5. Software Configuration
6. Personal Preference
7. Purchase & Order
8. Study Planning
9. Communication
10. Service & Subscription
11. Location & Logistics
12. Quantitative Planning

Each fixture contains a complete structured Low/Medium/High triplet. The same
frozen fixture set is used for both candidates and any activated fallback.
Primary qualification is **12 triplets × 2 candidate generators = 24 logical
model calls**. Physical infrastructure retries do not add logical cases.
An activated fallback requires its own complete 12-fixture qualification.

Fixtures must be separate from final confirmatory CRST scenarios, B0 calibration
material, LongMemEval-S, and historical Model Qualification fixtures. Fix their
structured truth and provenance before any qualification response is observed.
The [manifest](../data/generator-qualification/manifest.json) and
[construction/audit specification](generator-qualification-audit.md) record the
12 independently authored structured fixtures, reference schema, deterministic
projection and allocation, hashes, and blank manual-audit format. The fixture set
is FROZEN after final researcher review.
Low/Medium include a hard-distractor update; the dedicated N2 secondary never
changes. These explicit allocations apply only to qualification fixtures.
Post-review construction corrections remove Study Planning's repeated Q-intent
word, replace Communication's opaque schedule values with explicit daily clock
schedules, and make Quantitative Planning counts compatible with encountered
bundle sizes. Independent schedule/secondary-coverage/shared-value checks,
normalized entity-name distinctness and basic Q-intent lint are now enforced.
Identifier/code-valued N2 secondaries are retained as qualification-only stable
reaffirmation anchors; N1 supplies domain-specific same-state diversity. This does
not require identifier-valued N2 in final CRST. No qualification has executed.

Coverage must exercise target and secondary revisions, the hard distractor,
N1 target same-state reaffirmation, N2 dedicated-secondary same-state
reaffirmation, changed versus unchanged state, Q/gold-answer consistency, and
controlled entity/attribute/value preservation. Every fixture obeys the seven
initial-unit, seven-update, two-Noop-opportunity structure and triplet controls.

## 5. Absolute Qualification Gate

**FROZEN:** PASS/FAIL per model. QUALIFIED requires **all 12 triplets**, including
all three variants in each, to pass every required automated semantic/structural
check and manual audit. Both primary generators independently meet the same
contract. Do not average away a failure or rank generators that qualify.

The required checks are:

- Exact preservation of structured entity identity, attribute identity, and
  intended values; naturalization cannot redefine annotations.
- Correct event order and exact 1/4/7 target-revision schedules.
- U7 remains the final target revision.
- N1 remains a same-state reaffirmation of the then-current target.
- N2 remains a same-state reaffirmation of the dedicated, never-updated secondary.
- No changed event is weakened into hypothetical or conditional language.
- No same-state reaffirmation is converted into a state change.
- No information-bearing event is omitted or merged with another event.
- No invented state-changing fact.
- No assistant acknowledgement generation.
- No final-answer leakage before Q; prescribed information events, including
  U7's current-value statement, must remain intact rather than be suppressed.
  The prohibition concerns added answer disclosures/hints, not required facts.
- Correct Q semantic intent and relationship to the fixed gold answer.
- Correct machine-readable output schema and triplet separation.
- Matched controls and exact deterministic message structure after assembly.
- Natural, comprehensible English, confirmed by manual audit.

Automated validation and manual audit are both required; a structural parser
alone does not establish semantic fidelity. The runner, deterministic checks and
audit recording procedure are **IMPLEMENTED OFFLINE AND FROZEN** (§10), and
Attempt-01 applied them under both automated and completed human manual audit:
G1 and G2 both FAIL; neither is QUALIFIED.
The shared output schema
is specified in the naturalization contract. CSA, SRR, MOA, downstream policy
performance, and final statistical effects are not qualification criteria.

## 6. Failure, Retry, and Prompt Revision

Distinguish and preserve evidence for:

| Failure class | Required treatment |
| --- | --- |
| Infrastructure | Only the pre-frozen infrastructure retry policy applies; record every physical attempt separately from logical calls. Exhaustion is not passing evidence. |
| Malformed/schema output | Record the raw output and validation failure; do not disguise it as transport failure or silently repair/regenerate it into a pass. |
| Semantic/fidelity output | Record the failed checks/manual findings; do not silently regenerate until a satisfactory output appears. |

**FROZEN shared-contract revision rule:** if a defect in the shared naturalization
prompt/schema leads to a change, invalidate the affected attempt, version the
prompt/schema, and rerun the **full 12-fixture qualification for both primary
generators** under the new frozen version. Preserve the invalidated evidence.
Do not retain the previously passing primary's qualification under the changed
contract. Do not tune separate semantic prompts to make one model pass without
later explicit authorization of model-specific wrappers.

Provider/API syntactic wrappers may differ only where technically necessary;
the semantic naturalization contract must remain equivalent.

If one primary fails the frozen contract and the other passes, preserve both
outcomes and activate only the failed side's predeclared fallback. Qualify that
fallback on the same frozen fixtures and contract. Operational unavailability
may also trigger the corresponding fallback, with its reason recorded. No
replacement is qualified without the full absolute gate. Further fallback
changes require separate adjudication rather than an improvised search.

## 7. Standard Execution Selected; Capabilities Pending Verification

**FROZEN researcher decision:** use STANDARD execution for official qualification
and final full CRST naturalization. Lower operational/provenance complexity and
the researcher's sufficiently small expected total naturalization cost do not
justify a second asynchronous path solely for a batch discount. No batch model
IDs are permitted; qualification and final naturalization use the same mode.

Freeze intended first-party routing:

| Slot | Requested model | provider.order |
| --- | --- | --- |
| G1 | `openai/gpt-5.6-sol` | `["openai"]` |
| G2 | `anthropic/claude-sonnet-5` | `["anthropic"]` |

Both use `allow_fallbacks = false` and `require_parameters = true`. Requested
and observed model/provider identities are separate provenance fields; actual
route acceptance/evidence was verified by Attempt-02. Calls are stateless without
carry-over, tools, web/search, or plugins, with one complete triplet per logical
call and one shared semantic prompt/schema across both models.

**FROZEN after Capability Probe Attempt-02 PASS:** `reasoning.effort = low`, strict JSON-schema response using the exact versioned
schema, and `max_output_tokens = 16384`. This is a ceiling, not a target length.
Attempt-02 verified joint request acceptance, the strict-schema/API envelope,
and output-token mapping; hidden reasoning equivalence is not claimed. Do not invent unsupported
parameters or silently alter a rejected parameter. The reader configuration is
not a generator configuration.

Attempt-01 failed routing before inference. Its adjudication removes
`temperature` and `top_p` from both candidates' execution packages because
neither is advertised in the researcher-supplied catalog audit. No individual
causal attribution is made. See the [preserved evidence and adjudication](generator-naturalization-contract.md#8-two-call-capability-probe-and-attempt-01-adjudication).
The semantic versions are unchanged. Attempt-02 subsequently passed, verifying
the package and observed routing; Generator Qualification has not executed.

**FROZEN reviewed transport:** a 300-second
total per-attempt deadline, at most two infrastructure retries, 1s/2s backoff,
HTTP statuses 408/429/500/502/503/504 plus established network/transport timeout
classes. Semantic/schema/truncation/refusal failures are not infrastructure
retries. Do not continue an incomplete response or regenerate it into a pass.

The [shared contract](generator-naturalization-contract.md) records the completed
**two-logical-call compatibility probe**, one per primary, with the exact prompt,
schema, intended routes, and complete parameter combination. It is not Generator
Qualification. Its output cannot enter qualification evidence or final CRST data.
Parameter rejection requires STOP and adjudication. Nothing is probed here.

Official qualification and full final naturalization require a predeclared,
reproducible execution configuration. The primary pair's execution package,
transport constants, and physical input serialization are FROZEN after
Attempt-02; any activated fallback's capabilities remain OPEN. Record actual supported settings, versions/hashes, source commit,
requests, raw responses, routing evidence, validation/audit evidence, and physical
versus logical accounting. A later execution-mode change requires explicit
adjudication and qualification under the changed mode, not silent substitution.

## 8. Assignment for Final CRST

**FROZEN constraints, applicable after both generator slots qualify:** assign at
base-scenario level, keeping the whole triplet together. Allocate exactly 50/50
globally; final N is constrained to multiples of 12 and is therefore even, but
its value remains OPEN. Balance within each domain, with at most a one-scenario
difference when its count is odd. Coordinate domain imbalances to preserve the
exact global split.

**OPEN:** deterministic assignment mechanism/seed, to be frozen before final
generation. Record actual generator identity and configuration in dataset
provenance. Generator is a construction tool, not a primary experimental factor;
do not choose assignments from observed policy outcomes.

## 9. Length and Remaining Boundaries

The manuscript-current maximum 5% within-triplet and 2% aggregate revision-level
mean length tolerances remain **PROVISIONAL**, as in the CRST specification.
Qualification may record message/token lengths descriptively, but these numeric
values are not final pass/fail gates without separate adjudication. Exact
message-count requirements are independently frozen and must pass.

**OPEN:** fallback qualification (`openai/gpt-5.6-terra`,
`anthropic/claude-opus-5`) under the same frozen contract, assignment
mechanism/seed, B0 calibration material/grid/budget, and Small Pilot
size/acceptance procedure. Final CRST N/R/minimum effect of interest and
statistical procedures are not chosen here. Official Generator Qualification
Attempt-01 has executed and closed (§10); no naturalized CRST dataset or final
CRST experiment has been produced or executed, and completed qualifications
(Attempt-01) are not reopened.

## 10. Offline Qualification Runner — Attempt-01 CLOSED; Fallback-Capable Implementation FROZEN

**QUALIFICATION IMPLEMENTATION: FROZEN.** The implementation first reviewed
and committed at `e5e9d500d3e3f0805f5dfbce53eaed5d957ab74e` was extended,
offline only, to add the predeclared fallback candidate profile (§11). That
extension was reviewed, committed at
`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba`, and
`configs/generator-qualification-implementation-freeze.json` now pins that
commit and its three execution-critical source hashes. From the
implementation-identity perspective only, both profiles are technically
eligible for live execution; this is not itself authorization for either, and
neither has executed. This does not reinterpret Attempt-01's own
already-archived evidence: `replay()` verifies an archived attempt's
implementation identity against the git history of the commit *it* records
(the original `e5e9d500...`), not against the current live freeze record, so a
later, legitimately re-frozen implementation cannot break replay of an attempt
collected under an earlier freeze.

**ATTEMPT-01: CLOSED, both primaries FAIL.** The official attempt ran under
this frozen implementation and fixture set, archived at
`results/generator-qualification/attempt-01`. All 24 planned logical calls
completed; the attempt was not invalidated. One infrastructure retry occurred
and succeeded within the frozen retry budget. Completed human manual audit and
offline adjudication are recorded at
`results/generator-qualification/manual-audit/attempt-01.completed.json` and
`results/generator-qualification/adjudication/attempt-01.json`. G1
`openai/gpt-5.6-sol` FAIL: one researcher-approved manual `natural_english`
failure (`gq-study-planning-01`/`low`/`I6`). G2 `anthropic/claude-sonnet-5`
FAIL: four terminal strict-schema nonempty-string failures. Neither candidate
is QUALIFIED. Predeclared fallbacks `openai/gpt-5.6-terra` and
`anthropic/claude-opus-5` are now eligible but not qualified or executed; each
requires its own complete 12-fixture qualification under this same frozen
contract. See §11 for their offline-only design/implementation status.

`experiments/qualify_generators.py` (procedure
`generator-qualification-procedure/1.0.0`) has three modes, each taking
`--profile {primary,fallback}` (default `primary`; see §11):

| Mode | Invocation | Effect |
| --- | --- | --- |
| Preview (default) | no flags | Offline. Reports `NETWORK_DISABLED`, `CREDITS_NOT_SPENT`, the 24-call plan, frozen identities and the implementation status. Reads no API key and creates no directory. |
| Collection | `--execute --confirm-spend` and `OPENROUTER_API_KEY` | Refused unless every execution guard below holds. |
| Offline adjudication | `--attempt DIR --audit COPY --adjudication-output FILE` | Replays archived evidence, then adjudicates a completed audit copy. No network. |

**Plan.** 24 logical calls in a fixed order: G1 over all 12 frozen fixtures in
manifest order, then G2 over the same 12. Physical infrastructure retries
(at most 72 physical attempts) follow the frozen transport policy and add no
logical calls. Each request is built by the Capability Probe's frozen request
constructor with the frozen prompt, schema and execution package. Only the
model-facing input is swapped: the canonical fixture projection, checked by the
qualification input validator.

**Execution guards.** Execution requires both flags and a nonempty key. It also
requires a clean worktree (staged, unstaged and untracked changes all count),
tracked runner/probe/fixture-validator sources, and a valid implementation
freeze record. Frozen identities are rechecked immediately before the result
directory is reserved. These cover the execution package, semantic contract,
prompt and output-schema hashes, manifest hash, validated fixture/projection
hashes, and byte equality of every fixture file with fixture-set commit
`683c0416c5bf47c83021408f26bc7a7ab5e8becc`. An existing result directory is
never reused.

**Implementation provenance.** Every run records the SHA-256 of
`experiments/qualify_generators.py`, `experiments/probe_generators.py` and
`experiments/validate_generator_qualification_fixtures.py`, computed at run time
(no hardcoded self-hash). The freeze record
`configs/generator-qualification-implementation-freeze.json` (schema
`generator-qualification-implementation-freeze/1.0.0`) names the reviewed
implementation commit `3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba` (the reviewed
fallback-capable implementation) and these three hashes. The runner accepts it
only because that commit is an ancestor of HEAD and each source is
byte-identical to that commit and to the recorded hash. The record is a
separate file, so pinning creates no circular self-hash. If commit or source
identity ever drifts (as it did, correctly, between the first freeze and this
one), the status reverts to `NOT YET FROZEN FOR LIVE EXECUTION` and execution
is refused. These are software provenance hashes, not authorship metadata.

**Continuation and invalidation.** Each candidate receives all 12 planned calls.
A candidate's malformed, schema-invalid, refused, truncated or semantically
failing output is preserved as evidence, and collection continues for both
candidates. Such output never invalidates the attempt by itself. Nothing is
regenerated, repaired or automatically rerun.

**FROZEN (researcher adjudication): infrastructure retry exhaustion invalidates
the attempt.** A logical call can exhaust the bounded retry policy: 3 physical
attempts, each failing with a retryable HTTP status or transport timeout/network
error. The official attempt then becomes `INVALIDATED` with kind
`INFRASTRUCTURE_RETRY_EXHAUSTED`. The record names the candidate, fixture,
logical-call index and last retry reason. This is not a candidate qualification
FAIL, because infrastructure failure is not evidence of model capability.
Evidence already collected is preserved and checksummed, no further calls are
issued, and nothing reruns automatically. A later researcher-approved run must
use a new attempt directory.

The attempt is also `INVALIDATED`, with kind `EXECUTION_CONTRACT_FAILURE`, on
any of these shared execution-contract defects:

- a non-retryable non-200 response;
- returned model or selected provider mismatch;
- missing routing evidence;
- malformed usage;
- an API error envelope.

A runner exception invalidates it with kind `RUNNER_EXCEPTION`. Replay requires
the recorded invalidation to be exactly the one implied by the final archived
call, with no invalidating call before it. A non-invalidated attempt must
contain no call that should have invalidated it.

**Evidence.** Each attempt directory archives one redacted per-call record
`outputs/<g1|g2>/<fixture_id>.json`, `qualification.json`, a blank
`manual-audit.json` generated from it, and `SHA256SUMS` covering every one of
these files. The blank template is never edited in place. Reviewers complete a
separate copy outside the attempt directory, and adjudication writes a new
immutable file outside it, recording the completed copy's file hash.

Replay (run before every adjudication) rejects the following:

- malformed, unsafe (absolute, `..`, backslash) or duplicate checksum paths;
- checksum mismatches, and unlisted or missing files;
- a non-invalidated attempt without exactly 24 calls;
- call order, index, fixture, projection or provenance mismatch;
- attempts recorded without an implementation freeze, and archived provenance
  that differs from the current frozen identities;
- request drift;
- a blank template that differs from its regeneration.

For calls that passed, replay re-parses the archived raw response and re-runs
the route, envelope, schema and deterministic semantic gates offline. A terminal
failure must keep its fixed failure record and have no output hash, and any
archived HTTP-200 response must still fail those gates. A terminal failure
therefore cannot later become PASS.

**Deterministic checks.** Normalized literal matching (NFKC, case-folded,
whitespace-collapsed, word-bounded full expressions) records findings as `FAIL`
or `MANUAL_REVIEW_REQUIRED`. The following are deterministic `FAIL`s:

- an unambiguous known superseded or wrong value, or a foreign entity, in an event;
- a Q naming a foreign entity or a wrong attribute;
- a Q containing a target value;
- Q wording that is not identical across variants.

Absent literals (possible paraphrase) and lexical overlaps between values and
names require manual resolution. No deterministic PASS is semantic
qualification.

**Candidate adjudication.**

| Outcome | Condition |
| --- | --- |
| `INVALIDATED` | Attempt invalidated (retry exhaustion, execution-contract defect or runner exception). Applies to both candidates; never converted into candidate FAIL, even with a completed audit. |
| `FAIL` | Any terminal failure. Machine-detectable ones need no manual records: call failure (malformed JSON, schema-invalid, refusal, truncation, other terminal logical-call failure) or a deterministic automated `FAIL`. Otherwise a completed manual `FAIL` (ambiguity resolution, applicable check, or variant/fixture disposition, each with evidence notes). |
| `PENDING_MANUAL_AUDIT` | No terminal failure, but at least one applicable manual item is incomplete: an ambiguity resolution, an applicable check, or a variant, fixture or candidate disposition. |
| `QUALIFIED` | All 12 calls valid, parsed and schema-conformant. Every deterministic gate passed or its ambiguity was manually resolved PASS with notes. Every applicable manual check, all variant and fixture dispositions, and the candidate disposition are PASS. |

The following are all rejected as invalid audits rather than silently
adjudicated:

- a PASS disposition that contradicts a recorded failure;
- a candidate `FAIL` with no recorded failure;
- a manual `FAIL` without notes;
- manual values without reviewer and `reviewed_at`;
- a `reviewed_at` that is not an RFC 3339 timestamp with offset;
- any value in an NA cell.

See the [reviewer convention](generator-qualification-audit.md#5-blank-manual-result-audit-format).

## 11. Fallback Candidate Profile — Capability Probe Attempt-03 CLOSED/FAIL

**Fallback Capability Probe Attempt-03: CLOSED, overall FAIL (mixed
per-candidate outcome).** This section records the offline implementation
added to represent the predeclared fallback pair, and its first executed
evidence. No fallback Generator Qualification call has been made. Sol/Sonnet
already CLOSED FAIL (§10); Terra/Opus remain CANDIDATE, not qualified.

**Candidate-profile mechanism.** Both `experiments/probe_generators.py` and
`experiments/qualify_generators.py` take an explicit `--profile {primary,fallback}`
(default `primary`; every existing invocation and test is therefore unaffected).
`probe.PROFILES['fallback']` is fixed to exactly the predeclared pair -- G1
`openai/gpt-5.6-terra` (`provider.order=["openai"]`), G2 `anthropic/claude-opus-5`
(`provider.order=["anthropic"]`) -- with no open-ended model selection. The
CLOSED primary Capability Probe config, `configs/generator-capability-probe.yaml`,
and the primary `SLOTS` constant are unmodified; the primary path's default
behavior, byte-for-byte, is unchanged.

**Fallback Capability Probe.** A new, separate config,
`configs/generator-capability-probe-fallback.yaml`, is `status: OPEN`,
`capability_result: NOT_ASSESSED`, `execution_package: UNDER_DEVELOPMENT`,
`execution_compatibility: UNVERIFIED` -- never `CLOSED` in this task. It shares
the same naturalization contract, prompt, and output-schema identities as the
primary probe, and reuses the same existing capability-probe-only synthetic
input (`data/generator-capability-probe/probe-input.json`) -- not a downstream
Generator Qualification fixture. Its request package is the **researcher-approved
package**: identical to the primary's successful package except candidate
identity --
`allow_fallbacks=false`, `require_parameters=true`, `reasoning.effort=low`,
`max_tokens=16384`, strict JSON-schema response, the same 300s/2-retry/1s-2s-backoff
transport, and `temperature`/`top_p` intentionally OMITTED to stay consistent with
the qualified primary package. This was a deliberate choice, not a catalog audit
of Terra/Opus: **Terra and Opus's actual acceptance of this package is
empirical and untested** until their own Capability Probe executes and closes.
`python experiments/probe_generators.py --profile fallback` previews exactly 2
logical calls (Terra, then Opus), offline, with no key read and no directory
created; its `status` is explicitly `CAPABILITY_PROBE_FALLBACK_NOT_EXECUTED`
and `candidate_profile` is `FALLBACK`, so it cannot be confused with the CLOSED
primary preview.

**Fallback Generator Qualification.** `python experiments/qualify_generators.py
--profile fallback` previews the same 24-call plan structure as the primary --
12 Terra calls in frozen manifest order, then 12 Opus calls in the same order --
over the identical frozen 12 fixtures (`683c0416c5bf47c83021408f26bc7a7ab5e8becc`),
naturalization prompt, input contract, output schema, deterministic/manual
checks, absolute qualification gate, retry/invalidation semantics, and
no-regeneration rule. Its default output directory is
`results/generator-qualification/attempt-02`, distinct from the immutable
`attempt-01`; preview reports this path but creates nothing.

**Gate: live fallback qualification requires a CLOSED/PASS fallback Capability
Probe.** `collect()` refuses fallback execution
(`'Fallback qualification requires CLOSED/PASS fallback Capability Probe
evidence; the fallback Capability Probe has not executed and closed'`) by
reading `configs/generator-capability-probe-fallback.yaml` directly at
execution time; it stays OPEN/NOT_ASSESSED in this task, so the gate is refused.
The gate reads the fallback config specifically, so the primary's own real,
already-CLOSED/PASS evidence cannot satisfy it. Primary execution is unaffected
by this gate; it does not appear on the primary path at all.

**Historical replay compatibility.** Extending the implementation changed
`experiments/qualify_generators.py` and `experiments/probe_generators.py`
bytes; after researcher review, commit, and a new freeze record pinning
`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba` (§10), the live implementation
status is `FROZEN FOR LIVE EXECUTION` again. Attempt-01 remains fully
replayable and its adjudication still yields G1/G2 FAIL, unaffected by this
re-freeze: `replay()` verifies an
archived attempt's implementation claim against the git history of the commit
*that attempt itself* records, independent of whatever the current working
tree looks like mid-development. A fallback-profile `inputs` object cannot be
substituted to replay the primary archive; every archived call's returned
Sol/Sonnet identity mismatches the Terra/Opus slots at once.

**Status:** the extended implementation is reviewed, committed
(`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba`), and frozen (§10).

**Fallback Capability Probe Attempt-03 (result SHA-256
`96b3b1d4dcb31d2fdb0f3d545fb648d48c9d2969901721583ff5ac9d986c72b4`, preserved
under `results/generator-capability-probe/attempt-03/`): CLOSED.** Both
logical calls executed under the approved package, with no infrastructure
retry. G1 `openai/gpt-5.6-terra` call = PASS (HTTP 200, matching model/provider,
no refusal/truncation, parse and strict-schema checks passed). G2
`anthropic/claude-opus-5` call = FAIL by refusal (HTTP 200,
`finish_reason: content_filter`, `native_finish_reason: refusal`, before
parse/schema ran). Attempt-03 overall = FAIL, not infrastructure-invalidated.
Terra's PASS shows the approved package is not universally incompatible
across the pair; it does not establish that the package is unrelated to
Opus's refusal.

The shared `configs/generator-capability-probe-fallback.yaml` remains
`status: OPEN`, `capability_result: NOT_ASSESSED` -- it is **not** forced to
CLOSED/PASS, because the profile did not pass as a whole and its schema
represents one shared outcome, not a mixed per-candidate result. The
authoritative per-candidate outcome is recorded in
[decisions.md](decisions.md) ("Fallback Capability Probe Attempt-03") instead.
**Fallback Generator Qualification therefore remains blocked**: its
execution gate (§10) still refuses live execution because the fallback
Capability Probe has not closed CLOSED/PASS. No automatic re-probe of Opus and
no rerun of Attempt-03 are authorized by this closure; no second-level
fallback for the G2 slot is predeclared or frozen. Further G2 fallback action
requires separate researcher adjudication, not decided here. Terra/Opus
remain CANDIDATE, not qualified.
