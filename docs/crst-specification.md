# Controlled Revision Stress Test Specification

## 1. Scope, Sources, and Status

This specification governs **CRST Specification + Small Pilot**: the Controlled
Revision Stress Test (CRST), dependencies for future B0 Recent Window resolution,
and the role of a later Small Pilot. It does not constitute a generated dataset,
implemented experiment, or pilot result.

Source hierarchy:

1. **FROZEN source authority:** the methodological requirements supplied for this
   workstream were externally audited against
   `PROPOSAL_REVISION__PreMicroPilot_v3__2026-09-12.pdf`. The Proposal is external
   and unavailable in this environment. This document relies on those supplied,
   Proposal-vetted requirements and the supplied methodological audit corrections;
   it does not claim independent PDF inspection.
2. **FROZEN repository resolutions:** committed research state at
   `44fcddf95d0d9409f72436336fe7ebf090f1e3b1`, inspected on branch
   `feat/crst-specification-small-pilot`, governs legitimately resolved
   post-Proposal placeholders.
3. **OPEN details:** absence of a decision is not permission to invent one.
   Recommendations require explicit later adjudication before implementation.

The methodology checkpoint is `75bd7e3`. This update records the researcher's
new explicit post-Proposal resolutions for conversation, memory, semantic time,
IDs/journaling, B0 exchange/counting rules, and the generator qualification plan;
it does not reinterpret prior recommendations as already-adopted decisions.

Repository sources inspected are [README](../README.md),
[Research Design](research-design.md), [Dataset Specification](dataset-specification.md),
[Research Decisions](decisions.md),
[Retrieval / Context Calibration](retrieval-context-calibration.md),
[model configuration](../configs/model.yaml),
[immutable retrieval input](../configs/retrieval.yaml), and
[qualified retrieval outcome](../configs/retrieval-qualified.yaml).
The [Model Qualification specification](model-qualification.md),
[qualification implementation](../experiments/qualify_model.py), and
[deterministic context helper](../experiments/retrieval_context.py) were also
inspected for interface, accounting, and temporal-order semantics.

Status labels throughout this document mean:

- **FROZEN:** established by the supplied Proposal-vetted requirements or a
  legitimate committed repository resolution; preserved here.
- **OPEN:** unresolved and requiring a recorded decision before dependent work.
- **PROVISIONAL:** an existing candidate methodological value, not an executable
  final threshold.
- **RECOMMENDATION:** a proposed safeguard, not an adopted decision.

No genuine conceptual repository contradiction was found. Older OPEN provider,
transport, embedding, tokenizer, and retrieval-depth statements in the general
research-design document are superseded by committed qualification decisions.
The null selected values in `configs/retrieval.yaml` preserve the historical
calibration input; `configs/retrieval-qualified.yaml` records the resolved
outcome. Qualification fixtures are not CRST policy-execution specifications.

## 2. Controlled Experimental Design

**FROZEN:** the primary factorial experiment crosses persistent-memory policy
with target revision intensity. Domain provides diversity, not a primary factor.

| Factor | Levels |
| --- | --- |
| F1: persistent-memory policy | M1 Add-only; M2 Add+Update; M3 Add+Update+Noop |
| F2: target revision intensity | Low = 1; Medium = 4; High = 7 target revisions |

B0 Recent Window is a separate nonpersistent comparison condition, outside the
persistent-memory policy factor and analyzed separately.

| Revision intensity | Target-update positions | Secondary-update positions |
| --- | --- | --- |
| Low | U7 | U1, U2, U3, U4, U5, U6 |
| Medium | U1, U3, U5, U7 | U2, U4, U6 |
| High | U1, U2, U3, U4, U5, U6, U7 | None |

Each variant has seven update events; U7 is always the final target update.
Each target revision changes its current value, and no superseded target value
returns as current. CRST spans **12 domains**.

**FROZEN domain inventory:**

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

**FROZEN allocation constraint:** final N is a multiple of 12 and therefore even;
this does not select its value or make domain a primary experimental factor.
**OPEN:** final base-scenario count N, scenario allocation details beyond the
frozen generator-balancing rules in Section 4, and technical repetition count R.

## 3. CRST Information Structure

**FROZEN:** each base scenario has seven initial information units:

- One target information unit.
- Six secondary information units: one hard distractor, one dedicated N2
  secondary that is never updated and is distinct from the hard distractor,
  and four updateable secondary information units.

Each variant contains I1–I7, U1–U7, N1, N2, and Q. There are **16
information-bearing events before Q**: seven initial units, seven updates, and
two Noop opportunities. The explicit message mapping is frozen in Section 13.

The ending is `... -> U6 -> N1 -> U7 -> N2 -> Q`.

- **N1: target same-state reaffirmation / Noop opportunity.** It reaffirms the
  current target state after U6 and before U7, without introducing a new value.
  It therefore does not simply repeat the final target answer introduced at U7.
- **N2: dedicated-secondary same-state reaffirmation / Noop opportunity.** It
  follows U7 and precedes Q, reaffirming the dedicated, never-updated secondary.
  That secondary is not the hard distractor; N2 introduces no new state.

Within each Low/Medium/High triplet, preserve the same structured initial
information, final target state, final question, gold answer, hard distractor,
N2 secondary, total update count, Noop-opportunity count, final target-update
position, and message count. Section 13 now freezes the actual message structure;
matching does not require equal intermediate target states or identical wording.

**OPEN:** exact allocation and trajectories of the four updateable secondaries,
and exact ordering of initial roles within I1–I7, subject to these invariants.
They must be fixed in structured truth before naturalization.

## 4. Structured Truth and Natural-Language Realization

**FROZEN:** structured truth precedes naturalization and independently determines
entity and attribute identities, target/secondary roles, initial values, update
trajectories, event positions, current state after every event, superseded values,
semantic/reference operations, final question, and gold answer. The naturalizer
cannot choose or alter these truths.

Use two LLM generators only for natural-language realization. A complete
Low/Medium/High triplet uses the same generator, and scenario allocation is
balanced across generators. Naturalization may vary wording but cannot change
structured truth. Assistant responses must remain neutral, introduce no new
state-changing information, and neither alter truth nor leak the final answer.

**FROZEN naturalization unit:** one logical call receives the already-fixed
structured truth for one complete base-scenario Low/Medium/High triplet and
returns all three variants in one structured response. They remain three separate
dataset conversations. This keeps the generator shared, permits supplying common
facts once, and supports joint matched-control, message-count, and wording checks.
The construction layer alone inserts the exact acknowledgement `Noted.`; neither
naturalization LLM generates acknowledgements or experimental final answers.

The [Generator Qualification plan](generator-qualification.md) predeclares G1
`openai/gpt-5.6-sol` and G2 `anthropic/claude-sonnet-5` as **CANDIDATE**, not
QUALIFIED. Corresponding fallback candidates are `openai/gpt-5.6-terra` and
`anthropic/claude-opus-5`. Qualification requires absolute fidelity, not ranking.

**FROZEN assignment constraints after qualification:** assign at base-scenario
level, retain the complete triplet with its generator, allocate exactly 50/50
globally, and balance within each domain (difference at most one for an odd domain
count). Record generator identity in provenance; it is not a primary experimental
factor. Final N remains unresolved within the multiple-of-12 constraint.

**OPEN:** qualification outcomes/final qualified pair, verified execution
capabilities/parameters listed in the qualification plan, and deterministic
assignment mechanism/seed. STANDARD mode and intended first-party routing are
selected; the versioned shared prompt/schema and validation contract are in
[the shared naturalization contract](generator-naturalization-contract.md).
Candidate IDs do not certify
API availability or compatibility. Controlled candidates and reference labels
remain independent of naturalization; no LLM candidate extraction is introduced.

## 5. Initial State and Treatment Boundary

**FROZEN:** I1–I7 establish identical initial memory state for M1, M2, and M3.
There is no LLM maintenance-classification decision for initialization.
Treatment begins only at U1–U7, N1, and N2.

CRST candidates are prepared from controlled/reference annotations. There is
no LLM candidate-extraction component or associated extraction cost. LLM
candidate extraction belongs to the distinct LongMemEval-S execution path.
Reference annotations are evaluator data, not hints supplied to the policy or
reader and not corrective actions after a model mistake.

## 6. Memory Policy Semantics

**FROZEN general semantics and CRST reference mapping:**

| Policy | Available actions | Decision mechanism | Changed existing state | Same-state reaffirmation |
| --- | --- | --- | --- | --- |
| M1 Add-only | Add | Deterministic append; no LLM operation classification | Append candidate | Append candidate |
| M2 Add+Update | Add, Update | LLM selects operation and Update target | Reference Update | Reference Update; Noop unavailable |
| M3 Add+Update+Noop | Add, Update, Noop | LLM selects operation and Update target | Reference Update | Reference Noop |

Add is a general reference action for a genuinely new state key. In CRST,
however, all seven keys already exist after I1–I7. There is **no reference Add**
among U1–U7, N1, or N2 for the classified M2/M3 treatment. Every M2 reference
operation is Update; M3 reference operations are Update at U1–U7 and Noop at
N1/N2. Add can still be an erroneous model decision within the available action
space. M1's unconditional append is its treatment mechanism, not an operation
classification to score against M2/M3 references.

**FROZEN state and actual-decision semantics:**

- M1 appends every candidate as a new active entry. Historical/superseded
  versions may coexist with current content in active memory.
- Update preserves entry identity and `created_time`, replaces active content,
  and advances `last_updated_time`.
- Content superseded by replacement is absent from M2/M3 active memory. Audit
  or version-history records must not be supplied as active reader memory.
- Noop changes neither active content nor `last_updated_time`; the Noop event
  is still logged.
- Reference trajectories and operations remain fixed despite model mistakes;
  evaluator annotations do not repair program state.
- An executable, valid LLM decision is executed even when semantically wrong;
  its effects may propagate to later memory state.
- An invalid or unavailable Update target leaves state unchanged and logs a
  target error.
- Output that cannot be mapped to the available action space leaves state
  unchanged and logs an invalid maintenance decision.

**FROZEN identity and reference lineage:** I1–I7 create `mem_0001`–`mem_0007`.
Each canonical ID remains the reference lineage for its original structured state
key throughout the run. Treatment events reserve `mem_0008`–`mem_0016` in actual
chronological event order (Section 13). A reserved ID becomes active only if Add
executes, including an erroneous Add; unused reservations never renumber later
births. Update retains the chosen existing ID, not the reserved birth ID.

The fixed structured reference trajectory defines one canonical Update target ID.
Target correctness compares the selected ID against that fixed ID; earlier errors
never redefine evaluator ground truth. Even if actual content diverges from its
original lineage, a semantically wrong but executable Update is still executed.
Reference lineage is evaluation data, never a state-repair mechanism.

**FROZEN journal requirements:** maintain an append-only execution journal separate
from reader-visible active memory. It must support scenario/run/policy identifiers,
`event_index`, reference state key and operation, canonical reference target ID
where applicable, raw model response, parsed operation, selected target ID,
execution/error status, pre-state, actual transition, post-state, and semantic
timestamp. Version/audit history is not active reader memory; M1's retained
historical entries are active by policy definition.

**OPEN:** physical journal/version-history artifact schema and storage layout.
These representation details must preserve the frozen identities, lineage,
execution semantics, and journal evidence.

The qualification helper's guarded application of its single expected Update
is a technical-fixture contract. It must not be promoted into a general policy
rule that rejects or corrects every semantically wrong decision in CRST.

## 7. CRST Answer Context

**FROZEN:** M1, M2, and M3 answer from the **complete active memory** using the
same answer-context construction principle and answer prompt. They receive no
additional raw conversation history. There is no dense retrieval, Contriever,
LongMemEval K_ANSWER, or LongMemEval retrieval-context token-budget cutoff in
CRST answering.

**FROZEN:** present active entries oldest-to-newest with temporal metadata,
including all of M1's retained historical versions. Evaluator annotations and
reference labels are excluded.

**FROZEN new explicit CRST implementation decision:** serialize each active entry
as one line in the following deterministic form:

```text
[memory_id=<ID>; created=<CREATED>; updated=<UPDATED>] <TEXT>
```

Order entries ascending by `last_updated_time`, then `created_time`, then
`memory_id`. Exclude evaluator/reference annotations. This is an explicit CRST
adjudication, not an assumption inherited from LongMemEval retrieval. Supply all
active entries, without retrieval, top-k, similarity selection, or token-budget
admission.

An M2 same-state Update advances `last_updated_time`; an M3 reference Noop does
not. Presentation order may therefore differ as an actual consequence of policy
semantics. Do not neutralize that consequence post hoc.

**OPEN:** exact CRST answer prompt, response schema, request wrapper, and handling
of an unexpectedly oversized complete-memory request. Qualification answering
prompts do not establish a final experimental prompt. No silent truncation or
retrieval substitution may alter the complete-memory condition.

## 8. Effectiveness Metrics

**FROZEN primary CRST terminology and meaning:**

- **CSA = Current-State Accuracy:** proportion of final answers matching the
  target information current when Q is asked.
- **SRR = Stale Reliance Rate:** proportion of revision-sensitive final answers
  using a superseded target value.

Deterministic outcome classes are **current-correct answer**,
**stale/superseded answer**, and **other error**. Structured current and
superseded values supply the evaluation keys. CRST scoring must not use LLM
semantic judging, fuzzy matching, or embedding similarity. B0 uses the same
CRST final-answer scoring rule, reported separately.

LongMemEval-S uses its official evaluator and **QA Accuracy**, not CRST CSA/SRR
as its official final-answer metric.

**OPEN:** exact CRST answer-format/normalization contract, treatment of ambiguous
multi-value outputs, and missing/invalid-run handling and aggregation. The
qualification fixture's normalization function is not automatically the final
CRST scoring implementation. Resolve deterministic rules before pilot scoring
and confirmatory execution, without adding semantic equivalence heuristics.

## 9. Maintenance Diagnostics

**FROZEN:** **MOA = Maintenance Operation Accuracy** is diagnostic, not a primary
effectiveness outcome. For a complete CRST run, M2 and M3 each have exactly nine
maintenance decisions: U1–U7, N1, N2. MOA compares the selected operation with the
fixed reference operation over these nine decisions. Earlier model mistakes do
not change the reference labels.

M1 has no MOA because it makes no LLM maintenance-classification decisions.
B0 has no MOA because it has no persistent-memory maintenance.

Update-target correctness is a **separate diagnostic**, evaluated only when
both the reference operation is Update and the model selects Update. Do not
combine operation and target correctness into a single metric.

**FROZEN target rule:** compare the selected target ID with the fixed canonical
reference ID from Section 6, including after earlier model mistakes. The existing
eligibility condition (reference Update and selected Update) remains unchanged.

**OPEN:** physical diagnostic representation and treatment of missing/invalid
responses or runs in summaries. Do not silently drop events or redefine the
fixed reference trajectory; invalid/unavailable targets still follow Section 6.

## 10. Efficiency and Logging

**FROZEN primary efficiency indicators:** LLM token usage, active-memory size,
logical API-call count, and end-to-end execution time. API latency is diagnostic;
dollar cost is supplemental/descriptive. No scalar composite merges effectiveness
with efficiency.

**FROZEN active-memory size:** the primary measure is token count across active
entries at the final query. Exclude version history, inactive entries, reference
annotations, and logs. Active-entry count and the memory-size trajectory are
diagnostic. The exact tokenizer for this CRST measure remains **OPEN** until
explicitly frozen; the retrieval tokenizer freeze does not settle its scope.

**FROZEN end-to-end CRST timing:** start the timer when U1 processing starts and
measure through completion of final answering. Exclude I1–I7 initial-state
construction as identical pre-treatment setup. Include local harness work,
memory operations, API time, and infrastructure retry waiting. This measures
end-to-end execution resources, not intrinsic model inference latency.

Lifecycle boundaries:

- CRST has no LLM extraction cost; its candidates come from controlled annotations.
- Initialization has no LLM maintenance-classification cost.
- M1 has no LLM maintenance-classification cost.
- B0 has answer-stage LLM processing only and no persistent memory.
- A complete run therefore requires one logical answering call for M1 or B0,
  and nine maintenance calls plus one answering call for M2 or M3. These are
  policy-execution counts, separate from any future dataset-naturalization work.
- Infrastructure retries do not add logical policy calls. Physical attempts and
  retry usage remain separately auditable; actual retry time/cost remain actual
  execution resources.

**FROZEN upstream interface evidence:** Model Qualification required observable
`prompt_tokens` and `completion_tokens` on successful calls, recorded available
`total_tokens`, cost, cached tokens, latency, and physical-attempt metadata, and
left unknown optional fields null. Preserve that observability and the frozen
transport configuration. Do not treat local tokenizer estimates as observed API
billing/usage or replace missing optional values with zero.

The pinned reader tokenizer is
`meta-llama/Llama-3.1-8B-Instruct` at
`0e9e39f249a16976918f6564b8830bc894c89659`, with artifact identities in
`configs/retrieval.yaml`. Its frozen `add_special_tokens=False` rule concerns
serialized retrieval memory blocks. B0 now has its own explicit marginal
chat-template counting rule in Section 11; CRST length-matching and active-memory
size counting are not automatically settled by that B0 scope extension.

**OPEN:** exact CRST accounting schema and aggregation, active-memory tokenizer
and counting representation, timer instrumentation, missing-usage handling for
failed attempts, and exact local token-counting measures for CRST length matching. The primary memory-size unit/sampling point and timing boundary above
are not open. Preserve actual per-attempt evidence rather than guessing details.

## 11. B0 Recent Window

**FROZEN Proposal-vetted principles:** B0 has no persistent memory. It receives
a recent portion of the raw conversation plus Q and is analyzed separately from
M1/M2/M3. Fix its historical-window budget before the main experiment, selecting
the smallest calibration budget retaining U7 and the required conversation after
U7. Append Q only after window selection; Q is excluded from the historical
budget. Policy outcomes do not select that budget.

**FROZEN derived anti-leakage invariant:** dedicated pre-main B0 calibration may
use U7 as a structural oracle solely to verify retention of U7 and the required
following conversation. Main-run window construction must apply the fixed recent-
window procedure mechanically; it must not search for, identify, or center the
window around U7. This is an implementation safeguard derived from the fixed-
budget design, not a quotation attributed to the Proposal.

**FROZEN new B0 execution decisions:** the atomic historical unit is one complete
user information message plus its immediate deterministic assistant `Noted.`
acknowledgement. Supply B0 as role-bearing chat messages. Starting with the newest
exchange, expand backward to construct a contiguous suffix of complete exchanges.
Never skip an exchange or partially retain one. Preserve chronology in the
selected history and count the complete proposed suffix at each admission.

When the next older exchange does not fit, stop without skipping or truncating.
If even the newest complete exchange cannot fit, select an empty history and
emit `history_unit_overflow`; that candidate budget cannot qualify in B0
calibration. Append Q only after selection. The fixed system prompt and Q are
outside `B0_CONTEXT_TOKENS`; their actual API resource usage remains recorded
separately. Main-run selection uses only the suffix procedure and fixed budget,
never U7 identity.

**FROZEN new B0 tokenizer scope:** use the pinned official
`meta-llama/Llama-3.1-8B-Instruct` tokenizer at
`0e9e39f249a16976918f6564b8830bc894c89659` and its local chat template.
Define the marginal historical token count as:

```text
T_history(selected_history)
  = T_chat(system + selected_history) - T_chat(system)
```

Here `+` denotes ordered role-bearing messages, not concatenation of raw text.
Both terms use the same fixed system prompt and pinned template, exclude Q,
and exclude the final assistant-generation prefix/output. `T_chat` counts the
local template token sequence without adding an answer-generation prefix.
The difference includes incremental role/message structure for selected exchanges
and excludes the fixed system-prompt contribution. This is not the LongMemEval
retrieval memory-block counting rule.

This local B0 count is a reproducible methodological protocol count, not a claim
that OpenRouter or the serving provider uses byte-identical internal chat
rendering. Provider-reported `prompt_tokens` remains a separate observed resource
metric. Local subtraction does not replace actual API accounting.

**OPEN:** exact fixed system/answer prompt wording, calibration history material,
candidate calibration grid, and final `B0_CONTEXT_TOKENS`.

## 12. B0 Calibration Requirements

**FROZEN:** resolve and calibrate B0 before the confirmatory/main experiment.
Its selection criterion is structural retention of U7 and the required following
conversation, not final QA accuracy, CSA, SRR, comparative M1/M2/M3 results, or
main-experiment effect sizes. Freeze the chosen rule and budget before main
execution. **FROZEN structural retention requirement:** retain the complete U7
exchange and the complete N2 exchange. N1 precedes U7 and is not part of the
minimum retention criterion. Event identity is available only to the dedicated
structural calibration check, not to normal window selection.

**OPEN:** exact calibration history material, candidate budget grid, and final
budget. The exchange, overflow, and counting rules are fixed in Section 11.
Do not infer B0 budgets from the qualified dense-retrieval 512-token setting.

**RECOMMENDATION FOR ADJUDICATION:** use dedicated B0 calibration material fully
separate from final confirmatory CRST cases. This is a proposed safeguard, not
an existing repository freeze. No candidate budget grid is proposed here.

Dense Retrieval Qualification is CLOSED. The broader Retrieval / Context
Calibration workstream still awaits this separate B0 resolution.

## 13. Conversation Format and Synthetic Semantic Time

**FROZEN new conversation decision:** each I1–I7, U1–U7, N1, and N2 event is
exactly one user message, immediately followed by exactly one deterministic
assistant acknowledgement with exact content `Noted.`. The construction layer
inserts it; neither naturalization LLM generates it. It is identical across
domains, generators, policies, and revision intensities. It neither changes
state nor repeats the fact, claims maintenance success, or leaks Q/gold answer.
Q is a separate final user message; the experimental final answer is a separate
assistant message afterward.

Every variant has 16 information messages plus 16 acknowledgements = **32
historical chat messages before Q**, **33 through Q**, and **34 in a complete
interaction record including the generated final answer**. System instructions
are outside the dataset message count. This explicitly preserves equal message
count within every Low/Medium/High triplet without grouping events.

**FROZEN semantic time:** `event_index` is the source of truth. Its synthetic UTC
mapping is `2000-01-01T00:00:00Z + event_index minutes`; thus I1 is at 00:01 and
N2 at 00:16. Keep `event_index` in non-reader audit records.

| Event | event_index | Canonical initial / reserved birth ID |
| --- | --- | --- |
| I1 | 01 | mem_0001 |
| I2 | 02 | mem_0002 |
| I3 | 03 | mem_0003 |
| I4 | 04 | mem_0004 |
| I5 | 05 | mem_0005 |
| I6 | 06 | mem_0006 |
| I7 | 07 | mem_0007 |
| U1 | 08 | mem_0008 |
| U2 | 09 | mem_0009 |
| U3 | 10 | mem_0010 |
| U4 | 11 | mem_0011 |
| U5 | 12 | mem_0012 |
| U6 | 13 | mem_0013 |
| N1 | 14 | mem_0014 |
| U7 | 15 | mem_0015 |
| N2 | 16 | mem_0016 |

Acknowledgements do not advance semantic time. API latency, infrastructure
retries, execution wall-clock time, and naturalization time never influence
these timestamps. Identical event positions are comparable across variants.
Scenario dates inside facts are distinct from system metadata time.

Initial and later Add set both `created_time` and `last_updated_time` to the
event timestamp. Update preserves creation time and sets last-update time to
the current event timestamp. Noop preserves both. Treatment birth IDs become
active only when Add actually executes; they are not Update replacement IDs.

## 14. Dataset Construction and Validation

**FROZEN construction sequence:** structured truth -> scenario flow -> natural-
language realization -> automated structural validation -> manual audit -> dataset
freeze -> main execution. Structured truth itself must pass validation before
naturalization. The final dataset is frozen before main M1/M2/M3 outcomes are
observed and cannot be revised in response to those outcomes.

Automated validation must eventually check at least:

- Seven initial keys and the one-target/six-secondary role composition;
  dedicated N2 identity distinct from the hard distractor and never updated.
- Seven updates, two same-state reaffirmations, and 16 pre-Q information events.
- Exact 1/4/7 target intensity, target placements, U7 finality, and N1/N2 ordering.
- Changed values for updates, no target-value return, current state after every
  event, and current-value preservation at N1/N2.
- Reference candidate/operation annotations, no reference Add treatment events,
  and final question/gold-answer agreement with structured truth.
- Matched triplet controls and the exact 32/33/34 message structure, deterministic
  acknowledgements, semantic timestamps, and ID reservations in Section 13.
- The exact twelve-domain inventory in Section 2, same generator within each
  triplet, and the global/per-domain allocation constraints in Section 4, using
  the deterministic assignment mechanism once it is frozen.
- Agreement between naturalized text and structured annotations, with exact
  automated/manual responsibilities fixed before final generation.

The final dataset requires exhaustive manual review. Audit explicit and
unambiguous revisions; clear entity/attribute/value identity; current and
superseded states; true Noop semantics; natural English; neutral assistant
responses; absence of answer leakage; hard-distractor relevance with distinct
identity/value; and absence of hidden conditional/hypothetical language posing
as an actual update.

**FROZEN length principle:** Low/Medium/High variants must have comparable length.
**PROVISIONAL numeric criteria:** the manuscript-current requirements supplied
for this task specify maximum **5%** difference for specified within-triplet
token measures and maximum **2%** difference across aggregate revision-level
means. Synchronized methodological status leaves these tolerances PROVISIONAL
pending pre-main adjudication; no later committed resolution was found. They
are preserved as manuscript-current values, not final validator thresholds.

**OPEN:** exact machine-readable CRST schema, validation implementation, naturalizer
configuration, final length-measure definitions/serialization and percentage
calculation, plus final adjudication of numeric tolerances. Do not invent which
serialized measures the manuscript intended where the supplied audit and
repository do not specify them.

## 15. Small Pilot Role

**FROZEN workstream scope:** a later Small Pilot performs pre-main mechanical
validation, not estimation of policy effectiveness. This is an implementation
validation role, not a claim that every pilot procedure appears in the Proposal.

It should verify generation structure, revision schedules, reference annotations,
policy transitions, M1 historical-version retention, M2 Update behavior, M3 Noop
behavior, complete-active-memory answering, and B0 mechanics once resolved.
It also checks metric logging, token/resource accounting, logical calls versus
infrastructure retries, provenance, and reproducibility.

**OPEN:** pilot case/sample count, case identities, execution procedure, and
mechanical acceptance checklist. No pilot cases or results exist by virtue of
this specification. Pilot outcomes must not be presented as confirmatory policy
effects or used to select a favored policy.

## 16. Reproducibility and Provenance

**FROZEN upstream state:** Model Qualification is CLOSED / QUALIFIED after
Attempt 3. Its source implementation/prompt commit is `fc45fd6`, as identified
by the [committed Attempt 3 record](../results/model-qualification/attempt-03/qualification-record.md).
The separate Model Qualification closure commit is `f29c5c7`
(`docs: close model qualification`); it archived the result and closure record.
The experimental backbone is
`meta-llama/llama-3.1-8b-instruct` via OpenRouter, requesting `coreweave/bf16`,
with fallback disabled and `require_parameters = true`. Generation is
`temperature = 0.0`, `top_p = 1.0`, `max_output_tokens = 2048`; timeout is
180 seconds, maximum infrastructure retries 2, backoffs 1 and 2 seconds, and
retryable HTTP statuses 408, 429, 500, 502, 503, 504. Calls are stateless and
required context is supplied explicitly. Provider metadata identified selected
CoreWeave, not independent verification of the BF16 suffix. Qualification is
not reopened by this workstream.

Dense Retrieval Qualification is also CLOSED / QUALIFIED, from Attempt 01 at
source `82977b7fe7baaa8221398329bcdb6b70c86048e9`, archived at `7bb7598` and
resolved at `8ce16f0`. Canonical `facebook/contriever` revision
`2bd46a25019aeea091fd42d1f0fd4801675cf699` is qualified with `K_MAINT = 3`,
`K_ANSWER = 5`, and `LME_RETRIEVAL_CONTEXT_TOKENS = 512`. These values concern
LongMemEval-S, not CRST answering or B0. Preserve the immutable input config,
resolved config, corpus, runner, and evidence; no qualification is rerun here.
LongMemEval-S external-validation usable N=56 remains fixed.

Before main execution, preserve dataset versions/hashes, structured trajectories,
naturalized text, generator assignment/identities, prompts, schemas, reference
labels, validation/manual-audit records, software/source commit, package versions,
seeds where used, policy/run IDs, timestamps, model/provider configuration, raw
outputs and parse status, operations/targets, actual state transitions, resource
usage, and physical attempts. Secrets are excluded. Provider-side chat state is
not a reproducibility dependency.

**OPEN:** physical CRST artifact schemas, scenario/run identifiers, assignment
seed values, run/repetition scheduling, and final experimental prompts/response
schemas. Memory IDs, event indices, and semantic journal fields are now frozen.
Record remaining decisions before dependent execution rather than infer them
from qualification fixtures.

## 17. Frozen Decisions

The FROZEN items in Sections 2–16 preserve the vetted design: M1/M2/M3 crossed
with 1/4/7 target revisions; the exact 12-domain inventory in Section 2; seven
initial units; seven updates; two Noop opportunities; fixed U7/N1/N2 placement
and triplet controls including equal message counts; structured
truth before two-generator naturalization; controlled candidates and common
initialization; policy action spaces and reference mapping; complete-active-memory
CRST answering; CSA/SRR primary outcomes and MOA/Update-target diagnostics;
lifecycle efficiency accounting; final-query active-entry token count as primary
memory size; timing from U1 through final answering, excluding initialization
and including local work/API/retry waiting; separate B0 with a pre-main
structural-retention criterion and main-run anti-leakage invariant; and pre-main
dataset freeze.

Executable valid decisions are applied even when semantically wrong; invalid or
unavailable Update targets leave state unchanged and log target errors; unmappable
outputs leave state unchanged and log invalid maintenance decisions. References
evaluate rather than repair behavior. Noop changes neither active content nor
last-updated time and is logged.

Post-Proposal qualification closures, exact model execution, reader-tokenizer
identity, and LongMemEval-S retrieval configuration remain intact. CRST retains
oldest-to-newest presentation with temporal metadata, now with explicitly frozen
CRST serialization and last-update/creation/ID ordering. Sections 6, 11, and 13
also freeze canonical IDs/reference targets, append-only journal semantics,
deterministic exchanges/acknowledgements, synthetic semantic time, and B0
exchange-suffix/marginal chat-template counting rules. Candidate generators and
qualification/assignment contracts are predeclared, not qualified by declaration.
Neither completed qualification nor final statistical values are reopened.

## 18. Open Decisions

**OPEN before dependent implementation or execution:**

- B0 calibration history material, candidate grid, and final
  `B0_CONTEXT_TOKENS`; fixed system/answer prompt wording before calibration.
- Physical journal/version-history artifact schema and storage layout; semantic
  fields, canonical IDs, reference-target comparison, and execution rules are fixed.
- Scenario allocation/trajectories beyond frozen constraints, CRST schema, and
  deterministic generator-assignment mechanism/seed within the frozen balancing
  constraints. Candidate IDs are declared; qualification outcomes remain pending.
- Generator execution capability verification: joint sampling/reasoning support,
  exact strict-schema acceptance, output ceiling/mapping, intended first-party
  route evidence, timeout/retry constants, and activated fallback settings.
  STANDARD mode and intended routes are selected; prompt/schema versions are
  specified in the shared contract. Exact input serialization remains to finalize.
- Exact CRST prompts, response/scoring contract, invalid-run treatment, resource
  aggregation, active-memory tokenizer/counting representation, timer
  instrumentation, and length-measure implementation. Memory serialization/order
  and B0 tokenizer/counting semantics are already frozen.
- Pilot size/cases/acceptance procedure and other unresolved reproducibility details.

**PROVISIONAL:** manuscript-current 5%/2% length tolerances await explicit
pre-main adjudication; they are not final enforcement thresholds.

**OPEN for Statistical Planning / Simulation:** final CRST N, technical repetition
R, minimum effect of interest, exact random-effects structure, exact H2 omnibus
procedure, bootstrap resample count, bootstrap interval method, final confidence-
interval procedures, and other still-provisional statistical parameters. No values
are chosen here or inferred from main outcomes. Preserve the documented repeated
factorial policy/intensity/interaction structure, M2-versus-M1 and M3-versus-M2
contrasts, separate CSA and SRR analyses, separate B0 reporting, paired
LongMemEval-S analysis, and effectiveness/efficiency trade-offs without a composite.

## 19. Recommendations Requiring Adjudication

**RECOMMENDATION:** keep B0 calibration material fully separate from final
confirmatory CRST cases. The current repository has not frozen that separation.

**RECOMMENDATION:** resolve the remaining physical artifact schemas, experimental
prompts, and validation procedures before dependent dataset generation. This does
not reopen the newly adjudicated conversation, identity, or B0 counting rules.

Neither recommendation becomes FROZEN through inclusion in this document.

## 20. Explicit Non-Goals

This specification and its implementation-resolution update are documentation
only. They do not generate qualification fixtures, CRST or pilot cases,
naturalize text, invoke a model/API, calibrate B0, run policy experiments,
perform statistical simulation, select N/R/minimum effect of interest, or freeze
provisional statistical/length parameters. The accompanying Generator Qualification
plan and concise decision-log entries do not modify the external Proposal, configs,
completed qualifications, datasets, or Git history. This document makes no claim
that the full CRST, B0 calibration, or Small Pilot has already been executed.
