# Generator Qualification

## 1. Purpose and Decision Status

**FROZEN plan; qualification NOT EXECUTED.** Generators are construction tools
for CRST natural-language realization, not experimental treatment factors.
This document records researcher-adjudicated post-Proposal implementation
resolutions compatible with the [CRST contract](crst-specification.md).
No candidate is QUALIFIED by designation; API availability/support has not been
verified in this documentation task. No qualification fixtures are created here.

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

**OPEN:** exact shared semantic prompt and machine-readable response schema.
Freeze/version them before qualification. The schema must support separate,
ordered realization of every required information event and Q for each variant,
without acknowledgement generation or an experimental final answer.

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
Do not generate or populate these fixtures in this documentation task.

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
procedure and response schema before execution. CSA, SRR, MOA, downstream policy
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

## 7. Execution Configuration: Pending Verification

**INTENDED COMMON DEFAULTS, not yet verified execution settings:**

- `temperature = 0` and `top_p = 1`.
- Structured JSON-schema response.
- Sufficient max output tokens for a complete triplet without truncation.
- Stateless calls with no conversational carry-over between fixtures.

Verify exact OpenRouter/provider parameter support before execution. Do not
invent reasoning controls, provider parameters, model revisions, or token limits.
The frozen experimental reader configuration is not a generator configuration.

**OPEN before qualification:**

- Exact provider pin for Sol.
- Exact provider pin for Sonnet.
- Exact reasoning-effort/control semantics per model.
- Exact maximum output tokens.
- Exact timeout/retry constants, retryable infrastructure conditions, and backoff.
- Standard versus batch execution.
- Corresponding provider/capability/execution settings for any activated fallback.

Official qualification and full final naturalization must use a predeclared,
reproducible execution configuration. Any later batch option for cost reduction
requires explicit adjudication and verification; it cannot silently replace
standard execution after standard qualification. Freeze and record the actual
supported settings, prompt/schema versions, provider/model identities, input and
output provenance, validation/audit evidence, and physical/logical call accounting.
No API-capability inspection or inference occurs in this task.

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

**OPEN:** fixture contents, validator/audit implementation, shared prompt/schema,
verified execution settings, qualification outcomes, assignment mechanism/seed,
B0 calibration material/grid/budget, and Small Pilot size/acceptance procedure.
Final CRST N/R/minimum effect of interest and statistical procedures are not
chosen here. This plan generates no fixtures or dataset, performs no model/API
call or experiment, and does not reopen completed qualifications.
