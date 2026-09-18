# Generator Qualification

## 1. Purpose and Decision Status

**FROZEN plan; qualification NOT EXECUTED.** Generators are construction tools
for CRST natural-language realization, not experimental treatment factors.
This document records researcher-adjudicated post-Proposal implementation
resolutions compatible with the [CRST contract](crst-specification.md).
No candidate is QUALIFIED by designation. Capability Probe is CLOSED/PASS;
12 structured qualification-only fixtures are now frozen after final researcher
review. Generator Qualification has not run.

Generator diversity addresses dependence on one model family. Qualification
uses absolute fidelity to fixed structured truth, not a relative ranking,
leaderboard, downstream effectiveness comparison, or model tournament.
Completed backbone Model Qualification and Dense Retrieval Qualification remain
CLOSED and unchanged; they do not qualify construction generators.

## 2. Candidates and Predeclared Fallbacks

| Slot | Primary candidate | Predeclared corresponding fallback | Current status |
| --- | --- | --- | --- |
| G1: OpenAI family | `openai/gpt-5.6-sol` | `openai/gpt-5.6-terra` | CANDIDATE; not qualified |
| G2: Anthropic family | `anthropic/claude-sonnet-5` | `anthropic/claude-opus-5` | CANDIDATE; not qualified |

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
alone does not establish semantic fidelity. **OPEN:** exact validator/audit
implementation/recording procedure before execution. The shared output schema
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

**OPEN:** qualification runner,
naturalized-output validator and manual-audit execution procedure, fallback capabilities,
qualification outcomes, assignment mechanism/seed,
B0 calibration material/grid/budget, and Small Pilot size/acceptance procedure.
Final CRST N/R/minimum effect of interest and statistical procedures are not
chosen here. Only structured qualification fixtures have been constructed; no
naturalized dataset, model/API call or experiment has been produced or executed,
and completed qualifications are not reopened.
