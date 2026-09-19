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
`anthropic/claude-sonnet-5` FAIL (§10). Fallback Generator Qualification
Attempt-02 (Terra, G1 only) has run and closed under historical Protocol v1:
FAIL (§13). G2's fallback (Opus) remains capability CLOSED/FAIL, not
qualification-eligible. All dispositions above are historical **Protocol v1**
results. **Protocol v2 (§14) is frozen and implemented (implementation freeze
r2), and its offline re-adjudication of the archived evidence is closed: Sol
QUALIFIED, Terra QUALIFIED, Sonnet FAIL; G1 is Sol by frozen primary
precedence with Terra a qualified fallback; G2 remains unresolved.** The
second-level G2 candidate `anthropic/claude-fable-5.1` has since been named and frozen (§12), and
its capability probe closed PASS (Attempt-04); Generator Qualification has not run.
The Protocol-v1 results above are
preserved unchanged alongside, never overwritten.

Generator diversity addresses dependence on one model family. Qualification
uses absolute fidelity to fixed structured truth, not a relative ranking,
leaderboard, downstream effectiveness comparison, or model tournament.
Completed backbone Model Qualification and Dense Retrieval Qualification remain
CLOSED and unchanged; they do not qualify construction generators.

## 2. Candidates and Predeclared Fallbacks

| Slot | Primary candidate | Predeclared corresponding fallback | Current status |
| --- | --- | --- | --- |
| G1: OpenAI family | `openai/gpt-5.6-sol` | `openai/gpt-5.6-terra` | Primary Protocol-v1 FAIL (Attempt-01); fallback capability CLOSED/PASS (Capability Probe Attempt-03); fallback Generator Qualification Attempt-02 CLOSED, Protocol-v1 FAIL (§13); **Protocol-v2 (§14): Sol QUALIFIED, Terra QUALIFIED; G1 = Sol by frozen primary precedence, Terra qualified fallback** |
| G2: Anthropic family | `anthropic/claude-sonnet-5` | `anthropic/claude-opus-5` | Primary Protocol-v1 FAIL (Attempt-01), **Protocol-v2 FAIL (§14; four Level-1 terminal failures); G2 unresolved**; fallback capability CLOSED/FAIL by refusal (Capability Probe Attempt-03), not re-adjudicated; **second-level G2 candidate `anthropic/claude-fable-5.1` frozen before any output (§12); capability CLOSED/PASS (Capability Probe Attempt-04), Generator Qualification not run**; selection criteria unchanged (§12) |

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

## 5. Absolute Qualification Gate (Protocol v1; revised prospectively by §14)

**FROZEN (Protocol v1, `generator-qualification-procedure/1.0.0`):** PASS/FAIL per model. QUALIFIED requires **all 12 triplets**, including
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

Under Protocol v1 every item above, including natural English, is a
candidate-level gate. **Protocol v2 (§14)** keeps every item above as a
Level-1 hard gate except natural English, which it splits into
*comprehensibility* (Level-1 hard gate) and *fluency* (Level-2 item-quality
finding). The v1 text is retained unchanged as the historical rule under which
Attempt-01 and Attempt-02 were adjudicated.

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

**OPEN:** second-level G2 candidate qualification (candidate `anthropic/claude-fable-5.1` frozen with capability CLOSED/PASS, §12), handling of a final-CRST item with a
Level-1 failure (§14), assignment mechanism/seed, B0 calibration material/grid/budget, and Small Pilot
size/acceptance procedure. Final CRST N/R/minimum effect of interest and
statistical procedures are not chosen here. Official Generator Qualification
Attempt-01 and Attempt-02 have executed and closed under Protocol v1 (§10,
§13); no naturalized CRST dataset or final CRST experiment has been produced or
executed, and their Protocol-v1 dispositions are never rewritten.

## 10. Offline Qualification Runner — Attempt-01 CLOSED; Per-Slot-Capable Implementation FROZEN

**QUALIFICATION IMPLEMENTATION: FROZEN.** The implementation first reviewed
and committed at `e5e9d500d3e3f0805f5dfbce53eaed5d957ab74e` was extended,
offline only, to add the predeclared fallback candidate profile (§11), then
extended again to add generic per-slot capability state and single-slot
execution (§13). That second extension was reviewed and committed at
`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba`; the current reviewed
implementation, adding per-slot/single-slot support, is committed at
`585b5e2844504fec703287f8dd4869668615671d`, and
`configs/generator-qualification-implementation-freeze.json` now pins that
commit and its three execution-critical source hashes. From the
implementation-identity perspective only, every profile/slot combination is
technically eligible for live execution; this is not itself authorization for
any of them, and none has executed. This does not reinterpret Attempt-01's own
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
`results/generator-qualification/manual-audit/v1/attempt-01.completed.json` and
`results/generator-qualification/adjudication/v1/attempt-01.json`. G1
`openai/gpt-5.6-sol` FAIL: one researcher-approved manual `natural_english`
failure (`gq-study-planning-01`/`low`/`I6`). G2 `anthropic/claude-sonnet-5`
FAIL: four terminal strict-schema nonempty-string failures. Neither candidate
is QUALIFIED. Predeclared fallbacks `openai/gpt-5.6-terra` and
`anthropic/claude-opus-5` are now eligible but not qualified or executed; each
requires its own complete 12-fixture qualification under this same frozen
contract. See §11 for their offline-only design/implementation status.

`experiments/qualify_generators.py` has four modes, each taking
`--profile {primary,fallback}` (default `primary`; see §11) and
`--protocol-version {v1,v2}` (default `v1`, so every historical invocation is
unaffected; see §14):

| Mode | Invocation | Effect |
| --- | --- | --- |
| Preview (default) | no flags | Offline. Reports `NETWORK_DISABLED`, `CREDITS_NOT_SPENT`, the 24-call plan, frozen identities, the implementation status, and the procedure version the collection below would use. Reads no API key and creates no directory. |
| Collection | `--execute --confirm-spend` and `OPENROUTER_API_KEY` | Refused unless every execution guard below holds. Records the qualification procedure named by `--protocol-version`: `generator-qualification-procedure/1.0.0` (default) or, for a candidate not previously qualified under any protocol, `generator-qualification-procedure/2.0.0` with a native `generator-manual-audit/2.0.0` blank audit. Either way this is the SAME generation task -- identical frozen fixtures, prompt, input/output contract, and execution package; only the qualification/manual-audit interpretation differs (see §14, "Protocol v2 is also a direct qualification protocol"). |
| Offline adjudication | `--attempt DIR --audit COPY --adjudication-output FILE` `[--protocol-version {v1,v2}]` | Replays archived evidence, then adjudicates a completed audit copy under the selected protocol's schema/rules. For a `--attempt` collected under Protocol v1 (every attempt so far), `--protocol-version v2` here means "adjudicate a completed, historically-mapped v2 audit" (see the offline mapping mode below), not "this archive was collected under v2". No network. |
| Offline v1→v2 mapping | `--attempt DIR --audit V1_COMPLETED_COPY --v2-mapping-output FILE` | Derives a Protocol-v2 audit template plus a `pending_reclassification` list from a completed Protocol-v1 audit, per the historical mapping rule below. HISTORICAL-EVIDENCE ONLY: refused for evidence collected natively under Protocol v2, which starts with its own native v2 audit template instead (see Collection above). Does not adjudicate. No network. |

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
implementation commit `585b5e2844504fec703287f8dd4869668615671d` (the
reviewed per-slot-capable implementation; supersedes the prior
`3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba` fallback-capable freeze) and these
three hashes. The runner accepts it only because that commit is an ancestor
of HEAD and each source is byte-identical to that commit and to the recorded
hash. The record is a separate file, so pinning creates no circular
self-hash. If commit or source identity ever drifts (as it correctly has
twice now, between successive freezes), the status reverts to
`NOT YET FROZEN FOR LIVE EXECUTION` and execution is refused. These are
software provenance hashes, not authorship metadata.

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

## 12. Per-Slot Capability Adjudication and Second-Level G2 Fallback (Frozen)

**Researcher-approved methodological decision**, adjudicating the mixed
Attempt-03 outcome without altering its evidence. Full rationale is recorded
in [decisions.md](decisions.md) ("Fallback Per-Slot Capability Adjudication
and Second-Level G2 Selection Principles — Frozen").

**FROZEN: capability compatibility is adjudicated per candidate slot, not per
attempt.** Attempt-03's attempt-level `FAIL` is an execution/archive roll-up
(stop-on-first-non-PASS order across the profile's slots); it does not erase a
valid, independently evaluated PASS for a different slot within the same
attempt. Consequently, from Attempt-03 (§11):

- **G1 fallback `openai/gpt-5.6-terra`: capability status = CLOSED / PASS.**
  Capability-compatible only; **not** Generator-Qualified.
- **G2 fallback `anthropic/claude-opus-5`: capability status = CLOSED / FAIL**
  (provider-policy refusal). **Not eligible for Generator Qualification.**

Attempt-03's own recorded overall status remains FAIL, unchanged. **No
identical Opus re-probe is authorized**: refusal is terminal/non-retryable
under the frozen transport policy. The shared config
`configs/generator-capability-probe-fallback.yaml`'s whole-profile
`status`/`capability_result` fields are unchanged (still `OPEN`/
`NOT_ASSESSED`) -- the profile did not pass as a whole. A minimal, additive
`slots:` section (schema_version `generator-capability-probe-fallback-config/
1.1.0`) now represents this per-candidate outcome structurally (§13); it does
not alter or redefine the existing whole-profile fields.

**FROZEN: the G2 slot remains an Anthropic-family slot.** Opus's capability
FAIL does not relax the two-generator, vendor-family-diversified design (§2).
Relaxing this requirement later needs its own separate, explicit
methodological adjudication.

**FROZEN: second-level G2 selection principles** (no candidate named or
called). Before any replacement G2 candidate is named or called, it must:

- belong to the Anthropic family;
- be distinct from `anthropic/claude-sonnet-5` and `anthropic/claude-opus-5`;
- be available through the intended OpenRouter route at selection time;
- use the Anthropic first-party provider route;
- be evaluated with the same capability request package, unless a separately
  reviewed and versioned contract change is adopted first;
- be named and frozen before observing any CRST or naturalization-quality
  outcome from it;
- never be chosen by retry-until-pass, post-hoc sample quality, or downstream
  effectiveness;
- preserve every failed probe/qualification attempt, as Attempt-01 and
  Attempt-03 are preserved.

An ordered backup list, if adopted, must itself be frozen in writing before
the first candidate on it is probed.

**FROZEN: second-level G2 candidate `anthropic/claude-fable-5.1`** (named and frozen 2026-09-19,
before any capability-probe or qualification call to it; **no output from it
has been observed**). Exact immutable identifier: no moving alias (not
`~anthropic/claude-fable-latest`) and not the `:batch` variant, so the
candidate stays reproducible if a later Fable model is released. Route: the
repository's existing first-party pinning, `provider.order=["anthropic"]` with
`allow_fallbacks=false` and `require_parameters=true` -- no OpenRouter
multi-provider auto-routing and no Azure/Vertex/Bedrock substitution. The
selection is eligibility-based against the frozen criteria above -- Anthropic
family; distinct from `anthropic/claude-sonnet-5` and `anthropic/claude-opus-5`;
available through OpenRouter with a first-party Anthropic route;
structured-output support; exact identifier available -- and not justified by
benchmark ranking, model prestige or any expected pass probability. Those
availability, route and structured-output facts are researcher-attested at
selection time and were **not independently verified offline**: the capability
probe is their first empirical test. The candidate is evaluated with the same
capability request package, unchanged (`configs/generator-capability-probe-
second-level-g2.yaml`, identical to the fallback config except candidate
identity, with per-slot capability OPEN/NOT_ASSESSED and no evidence). No
ordered backup list is adopted: a capability FAIL is recorded and the process
stops, with no retry-until-pass, and any further candidate needs its own
written freeze before it is probed. If capability closes PASS, the candidate is
eligible for native Protocol-v2 Generator Qualification
(`generator-qualification-procedure/2.0.0`, `generator-manual-audit/2.0.0`, the
same frozen 12 fixtures, prompt, schema, semantic checks, comprehensibility/
fluency audit and r2 adjudicator, none changed for it).

The candidate's capability probe closed PASS (Capability Probe Attempt-04,
`probe.json` SHA-256
`4821739b668e2b5894a28e8f345588dd9869aa92420384cc10120d637fcc9365`), recorded in the per-slot record of
`configs/generator-capability-probe-second-level-g2.yaml`. This is capability
compatibility only: the candidate remains a CANDIDATE, Generator Qualification has
not run, and G2 remains unresolved until it completes. The official CLIs
select candidates from profiles in the pinned sources, so support was added as the
`second_level_g2` profile: one G2 slot with this exact candidate, the routing
above and the frozen config. The probe input, fixtures, prompt, schema, reasoning
and max-token settings, retry policy and v2 criteria are unchanged. The profile
supports the capability preview (`--profile second_level_g2`: one G2 call) and,
should capability close PASS, native qualification (`--profile second_level_g2
--slot G2 --protocol-version v2`: the same 12 frozen fixtures as 12 G2 calls, no
G1 call), so a capability PASS needs no further source change. The implementation
freeze revision r3 covered the profile support (§14) and is superseded by r4, which
is pending. Live qualification additionally requires an explicit
`--output-directory`. The closed results (Sol, Terra, Sonnet, Opus and all
Protocol-v1 and Protocol-v2 attempt artifacts) and the G1 resolution are not
affected.

**Approved future procedural order:** (1) freeze these decisions -- done; (2)
implement generic per-slot capability state and single-slot probe/
qualification support -- **implemented offline, see §13; not yet reviewed,
committed, or re-frozen**; (3) researcher review; (4) commit; (5) re-freeze
the execution-critical implementation; (6) Generator Qualification of Terra
may then run independently on the same frozen 12 fixtures; (7) separately
select the next G2 candidate using the frozen criteria above; (8) run that
candidate's own Capability Probe; (9) only if capability closes PASS, run its
full 12-fixture Generator Qualification; (10) final CRST generator assignment
(§8) remains blocked until both G1 and G2 slots each contain a
Generator-Qualified candidate. Steps (3)-(10) have not occurred.

## 13. Per-Slot Capability State and Single-Slot Execution — Frozen; Terra Attempt-02 CLOSED (Protocol v1 FAIL)

**Implemented offline, reviewed, committed, and re-frozen** (implementation
commit `585b5e2844504fec703287f8dd4869668615671d`, freeze commit `7b28ea2`).
This section records the software representation of the §12 decisions, the
single-slot execution support built to act on them, and its first executed
result: Terra Generator Qualification Attempt-02, CLOSED under historical
Protocol v1.

**Per-slot capability representation.** `configs/generator-capability-probe-
fallback.yaml` gained a `schema_version` field and an additive `slots:`
section (one entry per logical-call slot: `model`, `status`,
`capability_result`, `reason`, `evidence_attempt`, `evidence_path`,
`evidence_sha256`). The existing whole-profile fields (`status`,
`capability_result`, `execution_package`, ...) are untouched, so `load_bundle`
and every existing check against this file are unaffected. `probe.
slot_capability(profile_name, slot)` reads this section, checked against the
slot's **exact model identity**, not just its symbolic name (`G1`/`G2`): a
recorded entry only applies when its `model` matches the slot currently
occupying that position, so a future replacement candidate has no evidence
until its own entry exists. A profile config with no `slots:` section (the
CLOSED primary, `configs/generator-capability-probe.yaml`, unmodified) is
handled by the same function generically -- derived uniformly from that
profile's whole-config `status`/`capability_result`, exactly reproducing
existing primary behavior. This is one generic mechanism, not a Terra/Opus
special case.

Current recorded state, unchanged from §12: **G1 `openai/gpt-5.6-terra`:
capability CLOSED/PASS. G2 `anthropic/claude-opus-5`: capability CLOSED/FAIL**
(reason: provider-policy refusal). Attempt-03's own archived evidence and
overall FAIL status are untouched.

**Single-slot execution.** `experiments/probe_generators.py` and
`experiments/qualify_generators.py` both take an optional `--slot {G1,G2}`
(default: omitted, meaning the full profile -- byte-identical historical
behavior). `load_bundle()` always validates the config against the full
predeclared pair (unchanged); only the active/planned/requested slot list is
filtered afterward, so a single-slot run still confirms the config correctly
declares the whole profile. A single-slot Capability Probe preview plans
exactly 1 logical call for the named candidate; a single-slot Generator
Qualification preview plans exactly 12 (that candidate's fixtures only, same
frozen order, no calls for the other slot). No arbitrary model ID can be
supplied -- only `G1`/`G2` from the already-declared profile.

**Per-slot Generator Qualification gate.** `qualify_generators.
slot_capability_gate(profile_name, slot)` replaces the former whole-profile
`fallback_capability_gate()`. `collect()` now calls it for every active slot,
for every profile, generically: selecting G1 Terra for live Generator
Qualification is permitted from the capability-status perspective (CLOSED/
PASS); selecting G2 Opus is refused (CLOSED/FAIL); a future unassessed G2
candidate is refused until its own exact CLOSED/PASS evidence exists; the
primary's own CLOSED/PASS evidence, read from its own config, cannot satisfy
a fallback slot. For the primary profile the gate transparently passes (no
`slots:` section, uniform whole-profile CLOSED/PASS), so primary execution is
unaffected. `execute_probe()` additionally refuses to reopen a per-slot
already-CLOSED candidate (either PASS or FAIL) when given `profile_name`,
guarding against an accidental automatic Terra/Opus re-probe beyond the
existing whole-profile CLOSED guard.

**FROZEN: official Terra single-slot Generator Qualification path.**
`results/generator-qualification/attempt-02`. Rationale (researcher-approved):
Attempt-01 is the immutable CLOSED Sol/Sonnet primary qualification; attempt
numbering is sequential within the same Generator Qualification result
category; this is a new qualification attempt of the predeclared G1 fallback,
not a rerun or repair of Attempt-01; it will contain only G1 Terra's 12
planned calls, never Opus's. The runner does not hardcode this path as a
default for `--slot` (no default result-path convention exists in general for
an arbitrary single-slot attempt, and none is invented here); a researcher
invoking a single-slot preview or execution passes it explicitly via
`--output-directory results/generator-qualification/attempt-02`. Without an
explicit `--output-directory`, preview still shows the literal placeholder
`"OPEN: official single-slot result-path identity not yet decided"` for any
*other*, not-yet-decided single-slot case (for example, a future single-slot
G2 attempt) -- only the Terra/G1 path is frozen by this decision.

**Historical compatibility.** Extending the implementation changed
`experiments/qualify_generators.py` and `experiments/probe_generators.py`
bytes again; after researcher review, commit, and a new freeze record pinning
`585b5e2844504fec703287f8dd4869668615671d` (§10), the live implementation
status is `FROZEN FOR LIVE EXECUTION` again. Live execution of any
profile/slot remains gated on the additional checks in §10/§11 (clean
worktree, capability gate, etc.); this freeze only restores implementation
eligibility. Primary Capability Probe Attempt-01/Attempt-02, fallback
Capability Probe Attempt-03, and Generator Qualification Attempt-01 (replay,
completed audit, and adjudication: G1/G2 FAIL) all remain unchanged and were
reverified after this freeze.

**Terra Generator Qualification Attempt-02 (result SHA-256
`c15a6f2ab6e087c719e32c92f0f6268d4bf6a5728629a4ff8b1a033761560d5c`, preserved
under `results/generator-qualification/attempt-02/`): CLOSED under
historical Protocol v1.** All 12 logical calls completed for G1
`openai/gpt-5.6-terra`; no infrastructure invalidation; 12/12 passed schema/
execution. Automated result: 11 PASS, 1 MANUAL_REVIEW_REQUIRED (Task
Assignment `q_attribute`, manually resolved PASS as a faithful paraphrase).
`gq-purchase-order-01` failed the historical Protocol-v1 `natural_english`
criterion at I2 and I3 in all three variants -- structured meaning remained
recoverable and every semantic-fidelity check passed; this is a wording
failure, not a truth-corruption failure. Completed human audit and offline
adjudication are recorded at
`results/generator-qualification/manual-audit/v1/attempt-02.completed.json`
and `results/generator-qualification/adjudication/v1/attempt-02.json`
(`attempt-NN/` = immutable raw execution evidence; `manual-audit/v1/...` =
completed historical v1 human audit; `adjudication/v1/...` = derived
historical v1 disposition; Attempt-01's derived artifacts were moved to the
same `v1/` layout by pathname-only normalization, byte-identical).
**Final Protocol-v1 disposition: G1 (Terra) = FAIL.**

**Protocol v2 status.** At Attempt-02's closure Protocol v2 was only a
proposal; it was **not applied** anywhere in that closure, and the
`procedure_version` recorded throughout Attempt-02's evidence and adjudication
is `generator-qualification-procedure/1.0.0` (historical Protocol v1),
unchanged. Protocol v2's methodology has since been frozen and implemented
(§14), and a Protocol-v2 re-adjudication has since been performed as a
separate, explicitly versioned derived artifact that does not overwrite this v1
result (Terra: Protocol-v2 QUALIFIED; see §14).

**Status:** Terra Generator Qualification Attempt-02 is CLOSED; Terra's
Protocol-v1 disposition is FAIL, so Terra is **not** Generator-Qualified under
Protocol v1. No new G2 candidate has been selected. Opus remains capability
CLOSED/FAIL (provider-policy refusal, §11/§12). As of this closure Sol, Sonnet,
Terra, and Opus all remained not Generator-Qualified under Protocol v1; the
later Protocol-v2 offline re-adjudication (§14) is recorded separately and
does not alter this v1 closure.

## 14. Protocol v2 — Two-Level Quality Model (Methodology FROZEN; Implementation Freeze r4 Pending; Offline Re-adjudication Closed)

**Status.** The Protocol-v2 methodology is frozen. The offline re-adjudication of
the archived evidence is closed (Sol and Terra qualified, Sonnet failed, G1 is
Sol, G2 is unresolved; see "Protocol-v2 re-adjudication results" below). No
Protocol-v1 result or artifact is changed by this section.

**Implementation freeze lineage.** The first Protocol-v2 implementation (Commit A,
`6412b368e9c49891510aeb73d1fa208442df3c01`, "feat: implement generator
qualification protocol v2") was frozen by revision 1 of the implementation
freeze. A later audit found that the v2 adjudicator required the reviewer to mark
variant, fixture and candidate dispositions manually, a Protocol-v1 requirement,
although the frozen v2 rule and the v1 -> v2 mapping decision treat them as
derived. The correction (see "Human decisions versus derived outcomes (v2)")
changed `experiments/qualify_generators.py`; it was committed as Commit C
(`30d65102e618aa5713f0710964978f1eb46c4a15`, "fix: derive protocol v2
qualification dispositions") and frozen by revision 2,
`configs/generator-qualification-implementation-freeze-v2-r2.json`, which
superseded revision 1.

Support for the second-level G2 candidate profile (`second_level_g2`; see §12)
then changed `experiments/probe_generators.py` and
`experiments/qualify_generators.py`, two of the three pinned sources. Revision 2
therefore remains as historical provenance of the earlier implementation and no
longer freezes the current code. Revision 3,
`configs/generator-qualification-implementation-freeze-v2-r3.json`, names the
implementation commit that carries this support (`45f06ae8508485ff2f4d5a886fef89f01bf1b807`,
"feat: support second-level G2 generator profile") and pinned the sources at that
commit; it froze that implementation, and live execution was not performed under it.

Recording the second-level candidate's capability closure then changed the package
hash pinned in `experiments/qualify_generators.py`, so revision 3 is in turn
historical provenance. The active freeze record is revision 4,
`configs/generator-qualification-implementation-freeze-v2-r4.json`, to be created
against the implementation commit that carries that change. Until it exists,
`implementation('v2')` reports NOT_FROZEN and live `--protocol-version v2
--execute` refuses before any network request. The revision suffix names the
implementation freeze only; the procedure and audit versions remain
`generator-qualification-procedure/2.0.0` and `generator-manual-audit/2.0.0`.

**Implementation freeze records.** All records use the same protocol-agnostic schema
(`generator-qualification-implementation-freeze/1.0.0`), which pins a commit and
the SHA-256 of the three qualification-runner source files and has no
procedure-version field. The association with the qualification procedure is
therefore recorded in prose and in the record filenames rather than in a new
schema field. Each record is immutable and names an implementation commit that
already existed when the record was created:

- `configs/generator-qualification-implementation-freeze.json`: the Protocol-v1-era
  record. It pins commit `585b5e2844504fec703287f8dd4869668615671d` and the pre-v2
  sources, and is never repinned to Protocol-v2-capable bytes.
- `configs/generator-qualification-implementation-freeze-v2.json` (revision 1):
  pins Commit A (`6412b368e9c49891510aeb73d1fa208442df3c01`;
  `experiments/qualify_generators.py` SHA-256
  `38896235ec7a4b9b1fff59d2ae0d0ec6ef7c22ee567e131ac614ca8134355dc0`).
- `configs/generator-qualification-implementation-freeze-v2-r2.json` (revision 2):
  pins Commit C (`30d65102e618aa5713f0710964978f1eb46c4a15`;
  `experiments/qualify_generators.py` SHA-256
  `4f985518dec34731737794009f4c7841a3584dc0d11c1a9c83ee2e367644f09e`).
- `configs/generator-qualification-implementation-freeze-v2-r3.json` (revision 3):
  pins the implementation commit `45f06ae8508485ff2f4d5a886fef89f01bf1b807`
  (`experiments/qualify_generators.py` SHA-256
  `6765c1e456a7223ea2108cb79851cbfd8858f0f7eba557beb67ff871afe5687d`;
  `experiments/probe_generators.py` SHA-256
  `b48729d6603fa2f5abdf4c468d67ed7e00e335162abf4fbf7f86d680d33248c0`).
- `configs/generator-qualification-implementation-freeze-v2-r4.json` (revision 4):
  the active record; not yet created.

`validate_generator_qualification_fixtures.py` is unchanged across all v2 revisions
and `probe_generators.py` across revisions 1 and 2. `implementation('v1')` reads only the v1
record and `implementation('v2')` reads only the current v2 record; no record
substitutes for another, and a historical revision cannot freeze the current
implementation. Historical Protocol-v1 replay and adjudication of Attempt-01 and
Attempt-02 is unaffected and reproduces `{'G1': 'FAIL', 'G2': 'FAIL'}` and
`{'G1': 'FAIL'}`. Offline Protocol-v2 operations that generate no new evidence
(the historical v1 -> v2 mapping, v2 audit-template construction and v2
adjudication of a completed audit) consult no freeze record; the freeze gate
applies only to live qualification execution. Protocol v2 supports offline
re-adjudication of archived Protocol-v1 evidence (mapping below) and native
qualification of a candidate not previously qualified
(`--protocol-version v2 --execute`), which shares the same generation contract
and is recorded under the 2.0.0 procedure and audit versions from the start. No
live v2 qualification has been executed; the archived evidence was re-adjudicated
offline under the r2 freeze (see "Protocol-v2 re-adjudication results" below).

**Versions.** Protocol v2: `generator-qualification-procedure/2.0.0`,
`generator-manual-audit/2.0.0`. Protocol v1 remains
`generator-qualification-procedure/1.0.0`, `generator-manual-audit/1.0.0`;
every v1 artifact stays immutable and remains a valid historical record.

**Rationale and disclosure.** Protocol v2 corrects a *level-of-analysis
mismatch* in Protocol v1. Protocol v1 treats every natural-English defect both
as a defect of the generated item and as a candidate-level disqualifying
defect. The pre-existing CRST methodology (`crst-specification.md` §14)
already requires the **final dataset** to undergo exhaustive manual review,
including natural English, before dataset freeze. A purely surface-level
fluency defect whose naturalized text still carries a clear, single meaning therefore
does not threaten internal validity the way semantic corruption does: a missed
semantic defect corrupts the gold label a memory policy is measured against,
whereas a fluency defect affects realism and is already caught and resolved
by final-item review. Protocol v2 keeps final-dataset naturalness strict and
assigns each defect's consequence to the appropriate level. The revision is
**not** motivated by rescuing any candidate, by model prestige, or by any
expectation that particular models should pass. **Disclosure:** this is a
post-hoc revision, introduced *after* Generator Qualification outcomes were
observed (Attempt-01, Attempt-02), but *before* final CRST generation, final
CRST dataset freeze, and any M1/M2/M3 experimental outcome.

**Level 1 — candidate/generator suitability (hard gates, zero tolerance).**
One applicable Level-1 failure fails the fixture, and one failed fixture fails
the candidate. No numeric failure-rate threshold is introduced.

- *Execution/contract:* parse failure; strict-schema violation; required empty
  field; refusal; truncation; any other terminal call failure.
- *Semantic/structural:* `entity_fidelity`, `attribute_fidelity`,
  `current_value_fidelity`, `changed_vs_hypothetical_wording`,
  `same_state_fidelity`, `superseded_value_leakage`,
  `invented_information_or_state_change`, `merged_or_omitted_event`,
  `q_intent_fidelity`, `answer_leakage`, `output_boundary` failures; Q wording
  not identical across Low/Medium/High where identity is required; any
  deterministic automated semantic FAIL.
- *Comprehensibility:* naturalized text whose relevant meaning is not clear and
  single-interpretation **from the text itself** (see the judgment basis below).

**Level 2 — generated-item quality (recorded findings).** Protocol-v1
`natural_english` is split into two distinct Protocol-v2 checks:

- `comprehensibility` — Level 1, hard candidate gate;
- `fluency` — Level 2, item-level quality finding (awkward, redundant,
  unnatural, or unidiomatic wording whose meaning is nevertheless
  comprehensible under the judgment basis below).

**FROZEN comprehensibility judgment basis.** Comprehensibility is judged from
the naturalized text as presented in the conversation context available to the
experimental model -- never from what the generator probably intended. A PASS
requires that the relevant entity, attribute, value/state, changed-state or
same-state meaning, revision meaning, and (where applicable) question intent
are each understandable clearly from that text, without multiple reasonable
interpretations. Structured truth **may** be used by the reviewer as the
reference for checking semantic fidelity (whether the clearly expressed
meaning is the correct one); it **must not** be used to supply meaning the
generated text itself fails to express clearly enough. Therefore:

- awkward, redundant, or unidiomatic wording that has a single clear meaning in
  context ⇒ `comprehensibility` may PASS; `fluency` may FAIL (Level 2);
- wording with more than one reasonable semantic interpretation, missing
  necessary meaning, or meaning recoverable only by consulting hidden
  structured truth ⇒ `comprehensibility` FAIL (Level 1).

A fluency FAIL alone does **not** fail the fixture or the candidate, must be
recorded with notes, and does not permit an affected *final CRST* item to enter
the frozen dataset without correction (below). Qualification fixtures are never
corrected or regenerated; their fluency findings remain evidence of generator
behavior.

**Candidate qualification rule (v2).** A candidate is QUALIFIED only if all 12
frozen fixtures have zero Level-1 failures, every applicable required manual
cell is complete, every automated ambiguity finding is human-resolved, and no
unresolved Level-1 ambiguity remains. Level-2 fluency findings are counted and
reported descriptively only; they do not disqualify, and candidates are never
ranked, scored, or placed on a leaderboard by them. Generator Qualification
remains PASS/FAIL.

**Human decisions versus derived outcomes (v2).** Under Protocol v2 the human
reviewer decides only the applicable manual CHECKS (cells) and the automated
ambiguity resolutions. Terminal Level-1 failures are read directly from the
archived evidence. Variant, fixture and candidate dispositions are
deterministic derived outcomes, never manual reviewer inputs: a variant FAILs
iff an applicable Level-1 check FAILs in it and is otherwise PASS once every
required cell in it is complete; a fixture FAILs iff it has a terminal failure,
an ambiguity resolved FAIL, or a failed variant, and is otherwise PASS once its
required review is complete; a candidate FAILs iff any fixture or terminal
Level-1 failure exists and is QUALIFIED iff all 12 fixtures contain zero
Level-1 failures and all required review is complete. A deterministic Level-1
terminal failure suffices to FAIL a candidate even when unrelated manual cells
were never reviewed. Level-2 fluency findings never cause any of these to
FAIL. The v2 audit template keeps the summary fields for shape compatibility
but they must remain unset: the adjudicator rejects a manually supplied v2
summary disposition rather than using or ignoring it, and reports the derived
outcomes in its `derived_dispositions` basis. Historical Protocol v1 is
unchanged and still records these dispositions manually.

**Final-CRST fluency-only correction rule (prospective).** If a final CRST item
fails *fluency only*, a human reviewer may make a minimal surface edit to the
affected event text. The edit must not add, remove, or change an entity,
attribute, or value expression; alter current/superseded state meaning,
changed-state vs same-state polarity, revision chronology, or Noop semantics;
or alter Q intent or the gold answer. Required provenance: original generated
text, corrected text, before/after hashes, reviewer identity, timestamp,
correction reason, and the correction count attributable to the generator.
After correction: rerun deterministic automated validation, manually re-review
every applicable Level-1 check for the edited event, and re-review fluency; the
item enters the frozen dataset only if all checks PASS. No model resampling or
retry-until-pass is permitted for a fluency-only defect. A defect that cannot
be repaired by a minimal surface edit without touching structured meaning is
not fluency-only and is a Level-1 semantic/comprehensibility issue.

**OPEN: final-dataset Level-1 failure policy.** Handling of a newly generated
*final-CRST* item with a Level-1 semantic, structural, comprehensibility,
schema, refusal, or truncation failure remains **OPEN** and must be frozen
**before** final CRST generation begins. No regeneration policy is invented
here. This OPEN item does not block offline v2 re-adjudication of archived
qualification evidence.

**Protocol v2 is also a direct qualification protocol.** Nothing above ties
Protocol v2 to re-interpreting existing evidence: it is the same
`generator-qualification-procedure/2.0.0` / `generator-manual-audit/2.0.0`
methodology whether applied to already-archived Protocol-v1 evidence (the
offline mapping below) or run as the FIRST qualification of a candidate that
has never been qualified under any protocol -- for example a future
second-level G2 candidate qualified after this section is implemented. Such a
candidate is executed natively under v2 from the start: same frozen
qualification fixtures, naturalization prompt, input/output contract, and
execution package as Protocol v1 (Protocol v2 changes qualification/manual-
audit interpretation, not the generation task); its qualification evidence is
labelled `generator-qualification-procedure/2.0.0`, and its blank manual audit
is a native `generator-manual-audit/2.0.0` template (`comprehensibility` /
`fluency` from the start) -- never a Protocol-v1 audit later mapped forward.
The offline mapping below applies only to evidence already collected under
Protocol v1; it is refused for evidence collected natively under Protocol v2.

**Historical v1 → v2 mapping (offline; Protocol-v1 evidence only).** Every v1 manual cell other than
`natural_english` carries forward unchanged. v1 `natural_english = PASS` maps
mechanically to `comprehensibility = PASS`, `fluency = PASS`. Each v1
`natural_english = FAIL` must be reclassified by the human reviewer, with
mandatory notes and under the comprehensibility judgment basis above, as
exactly one of: (A) `comprehensibility = FAIL` (fluency not
independently outcome-determining) ⇒ Level-1 failure; or (B)
`comprehensibility = PASS`, `fluency = FAIL` ⇒ Level-2 finding only.
Classification must never depend on candidate identity or desired outcome.
Historical v1 reviewer notes stating that meaning "remained recoverable" are
Protocol-v1 records, not Protocol-v2 comprehensibility judgments; every v1
`natural_english` FAIL is reclassified afresh under the judgment basis above.

**Symmetric offline re-adjudication.** Protocol v2 applies symmetrically to all
archived Generator Qualification evidence: Sol (Attempt-01), Sonnet
(Attempt-01), and Terra (Attempt-02). It is offline only, with no new
generation calls. Protocol-v1 dispositions are reported alongside, never
overwritten by, Protocol-v2 dispositions. Opus is not re-adjudicated: it failed
at the capability stage and has no Generator Qualification evidence.

**Primary precedence (frozen before any v2 re-adjudication).** Originally
designated primaries retain precedence over their fallbacks. For G1 (primary
`openai/gpt-5.6-sol`, fallback `openai/gpt-5.6-terra`): if both qualify under
v2, Sol occupies G1 and Terra remains a qualified fallback; if Sol fails v2 and
Terra qualifies, Terra occupies G1; if both fail, G1 remains unresolved. The
choice is never made by fluency counts, subjective output quality, price,
token usage, model prestige, downstream CRST performance, or any M1/M2/M3
outcome. This rule exists specifically to prevent post-hoc candidate selection.

**G2 status.** Sonnet is re-adjudicated offline under v2 from Attempt-01; its
historical terminal strict-schema/nonempty-string failures remain Level-1
failures unless archived evidence proves otherwise. Opus remains capability
CLOSED/FAIL. G2 remains an Anthropic-family slot. No second-level G2 candidate
is selected here, and the second-level selection criteria (§12) are unchanged.

**Protocol-v2 re-adjudication results (closed offline 2026-09-19).** Produced
only by the frozen offline v1 -> v2 mapping and the r2-frozen Protocol-v2
adjudicator (freeze revision r2, Commit C `30d65102e618aa5713f0710964978f1eb46c4a15`);
no API call and no generation was used, and the raw `attempt-NN/` evidence and
every Protocol-v1 artifact are untouched (all Protocol-v1 dispositions are
preserved alongside, unchanged). The human reviewer, Muhammad Rafly Ash
Shiddiqi (`reviewed_at` 2026-09-19T12:40:11+07:00), made exactly seven
cell-level judgments -- the historical v1 natural_english FAIL cells --
each approved as comprehensibility PASS / fluency FAIL (a Level-2 finding
only), judged from the model-visible conversation and never using structured
truth to supply meaning: Sol `gq-study-planning-01`/low/I6 ("Study plan Wren
is designated Desk Oris as its study desk." -- entity, attribute and value
explicit, one clear reading; grammatically malformed/unidiomatic) and Terra
`gq-purchase-order-01` I2 and I3 in low, medium and high ("Order Kittiwake has
an ordered number of 120 sleeves of empty storage sleeves." / "Order
Sandpiper has an ordered number of 330 sleeves of empty storage sleeves." --
redundant "sleeves" construction, but the conversation consistently expresses
the attribute as the ordered number of empty storage sleeves and later
mentions give the same attribute as N sleeves, so one dominant reading; one
classification for all six cells sharing that realization pattern). All other
cells were mapped mechanically or carried forward unchanged from v1.
Variant, fixture and candidate dispositions were derived by code, not entered
by the reviewer. Final individual Protocol-v2 dispositions (regenerated
byte-identically from the completed audits): **Sol (Attempt-01 G1)
QUALIFIED** -- 0 Level-1 failures, 1 Level-2 fluency finding, all 12 fixtures
derive PASS; **Terra (Attempt-02 G1) QUALIFIED** -- 0 Level-1 failures, 6
Level-2 fluency findings, all 12 fixtures derive PASS; **Sonnet (Attempt-01
G2) FAIL** -- 4 Level-1 terminal strict-schema "Expected nonempty string"
failures (`gq-project-planning-01`, `gq-task-assignment-01`,
`gq-personal-preference-01`, `gq-service-subscription-01`), which alone make
qualification impossible, so its 8 remaining fixtures' manual cells were
correctly left unreviewed. **G1 primary precedence, applied only after these
individual dispositions:** Sol and Terra both qualify, so **Sol occupies G1
and Terra remains a qualified fallback** (Terra's Protocol-v1 FAIL and
Protocol-v2 QUALIFIED are both preserved; no fluency count or subjective
quality was used). **G2 remains unresolved:** Sonnet FAILs Protocol v2, Opus
remains capability CLOSED/FAIL and outside qualification, and no second-level
G2 candidate is selected here (the §12 criteria are unchanged). The r2
implementation freeze (Commit C) is the implementation freeze under which
these results were produced.
Artifacts:
`results/generator-qualification/manual-audit/v2/attempt-01.completed.json`,
`.../attempt-02.completed.json` and
`results/generator-qualification/adjudication/v2/attempt-01.json`,
`.../attempt-02.json`.

**Anti-bias safeguards (frozen).** Preserve every Protocol-v1 result and
artifact; disclose that v2 was introduced after observing qualification
outcomes; justify it solely by level-of-analysis alignment with the
pre-existing final-dataset QC requirement; freeze v2 before any v2
re-adjudication; apply v2 symmetrically to Sol, Sonnet, and Terra; make no new
API calls for v2 re-adjudication; never repeat generation until a preferred
candidate passes; never let an M1/M2/M3 outcome inform qualification; freeze
primary precedence before re-adjudication; keep the final dataset subject to
exhaustive QC regardless of candidate qualification; never rewrite a
Protocol-v1 artifact to make v2 appear pre-specified.

**Artifact layout.** Immutable execution evidence stays in
`results/generator-qualification/attempt-NN/`. Historical v1 derived artifacts
stay in `results/generator-qualification/manual-audit/v1/` and
`results/generator-qualification/adjudication/v1/`. Future v2 derived
artifacts go to `results/generator-qualification/manual-audit/v2/` and
`results/generator-qualification/adjudication/v2/` (now created and closed by
the re-adjudication above). v1
artifacts are never overwritten. `generator-qualification-audit.md` §5
describes the historical v1 audit contract and is superseded prospectively by
this section for v2 audits only.
