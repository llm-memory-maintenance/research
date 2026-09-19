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

[Generator Qualification](generator-qualification.md) is CLOSED under Protocol v2:
G1 is `openai/gpt-5.6-sol` (qualified fallback `openai/gpt-5.6-terra`) and G2 is
`anthropic/claude-fable-5.1`. `anthropic/claude-sonnet-5` and
`anthropic/claude-opus-5` are not selected. Qualification required absolute
fidelity, not ranking.

**FROZEN assignment constraints after qualification:** assign at base-scenario
level, retain the complete triplet with its generator, allocate exactly 50/50
globally, and balance within each domain (difference at most one for an odd domain
count). Record generator identity in provenance; it is not a primary experimental
factor. Final N remains unresolved within the multiple-of-12 constraint.

**OPEN:** deterministic assignment mechanism/seed. Generator Qualification is
closed under Protocol v2: G1 is `openai/gpt-5.6-sol` with `openai/gpt-5.6-terra` as
qualified fallback, and G2 is `anthropic/claude-fable-5.1`
([Generator Qualification](generator-qualification.md) §14). The primary pair's
execution package and transport are FROZEN after Capability Probe Attempt-02 PASS.
STANDARD mode and intended first-party routing are selected; the versioned shared prompt/schema and validation contract are in
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

**FROZEN CRST candidate and memory-entry representation.** CRST uses gold/reference
candidates with no LLM extraction. Every initial fact (I1-I7) and every maintenance
candidate (U1-U7, N1, N2) is rendered by one deterministic renderer as the single
line

```text
For {entity_name}, the {attribute_meaning} is {current_value}.
```

The renderer uses only the entity name, the human-readable attribute meaning, and
the current value. It never exposes the state key, role, semantics label, event ID
or position, reference operation, previous or superseded values, gold answer,
revision count or intensity, or any current/superseded annotation. The same renderer
applies to I1-I7 initial-memory construction, U1-U7, N1, and N2. The rendering is
lossless with respect to the three allowed fields, is validated by exact round trip,
and involves no LLM paraphrasing or manual editing.

Storage follows the policy semantics of Section 6: Add stores the rendered candidate
text verbatim; Update replaces the entry text exactly with the rendered candidate
text verbatim, retaining the ID and creation time and advancing the last-updated
time; Noop changes neither entry text nor last-updated time; M1 stores every
candidate verbatim as its own entry, preserving historical candidates by separate
entries. The stored text is the `<TEXT>` of the Section 7 serialization. The state
key, role, semantics label, and reference operation remain harness and evaluator
data.

Naturalized conversational text is not a persistent-policy candidate. B0 uses the
naturalized raw conversation, Q is the naturalized final question, and M1, M2, and
M3 use canonical candidates and the active memory derived from them. This preserves
the no-extraction design and keeps candidates independent of naturalization.

Consequences for CRST structured material, as validation requirements: entity
names, attribute meanings, and values must produce a single line with no leading or
trailing whitespace and must round-trip exactly, and none may carry status or time
wording (such as "current", "now", "latest", "previous", or "new"), so that the
rendered text cannot expose a current or superseded annotation. Attribute meanings
must be distinct within an entity.

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

**FROZEN for the Small Pilot: maintenance prompt and response.** M2 and M3 use
separate policy-specific prompts and response schemas (`configs/crst-small-pilot.yaml`,
`experiments/crst_prompts.py`). The input is the frozen serialized active-memory
block plus the canonical candidate text, with no raw conversation. M2's action
space is Add/Update: an active entry for the same entity and attribute means Update
targeting it (a same-value reaffirmation remains Update), otherwise Add. M3's is
Add/Update/Noop: no such entry means Add, the same entity and attribute with a
different value means Update, and the same entity, attribute, and value means Noop.
The prompts define these policy semantics only. They never expose the event's
reference operation, event label, intensity, state key, or any evaluator annotation.
The response is `{"operation": ..., "target_id": ...}` with exactly those keys: the
operation is in the policy's enum, an Update carries a nonempty `target_id`, and Add
and Noop carry null. The provider response mode is the qualified `json_object`
mode (strict `json_schema` is not qualified for the backbone path and is never
requested); the policy-specific schema, including the conditional target rule, is
enforced locally, exactly and deterministically, right after parsing. There is
no semantic repair and no retry of a logical decision: a malformed or unmappable
response leaves state unchanged and is logged as an invalid decision, and an
unavailable target leaves state unchanged and is logged as a target error.
Infrastructure retries stay separate from logical decisions.

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

`<TEXT>` is the stored candidate text defined in Section 5. Order entries ascending by `last_updated_time`, then `created_time`, then
`memory_id`. Exclude evaluator/reference annotations. This is an explicit CRST
adjudication, not an assumption inherited from LongMemEval retrieval. Supply all
active entries, without retrieval, top-k, similarity selection, or token-budget
admission.

An M2 same-state Update advances `last_updated_time`; an M3 reference Noop does
not. Presentation order may therefore differ as an actual consequence of policy
semantics. Do not neutralize that consequence post hoc.

**FROZEN answering wording:** all conditions receive the same policy-neutral system
message, defined in Section 11.

**FROZEN for the Small Pilot: answer request and response.** The answering system
text is unchanged (Section 11; SHA-256
`8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e`). The answer-format
instruction belongs to the final user request, because Q is outside the B0 historical
token budget. Wrapper version `crst-pilot-answer-request/1.1.0` supersedes the never
executed 1.0.0. M1, M2, and M3 send one user request:

```text
Context:
{serialized_active_memory}

Question:
{Q}

Return exactly one JSON object with exactly one key named "answer".
The value of "answer" must contain only the answer to the question, with no explanation or additional text.
Do not return any other keys.
```

with no raw history, dense retrieval, or evaluator data. B0 keeps the frozen selected
raw-history messages under `B0_CONTEXT_TOKENS` and then appends one final user
message, which is the same text without the `Context:` block:

```text
Question:
{Q}

Return exactly one JSON object with exactly one key named "answer".
The value of "answer" must contain only the answer to the question, with no explanation or additional text.
Do not return any other keys.
```

The naturalized Q text stays verbatim inside the wrapper, and the final message never
enters the historical budget. The provider response mode is `json_object`. The local
answer schema is `{"answer": "<nonempty nonblank string>"}` with exactly that key,
validated right after parsing without repair; a malformed answer is an other error.
Adoption of these decisions for the confirmatory CRST remains a pre-main decision.

**OPEN:** handling of an unexpectedly oversized complete-memory request.
Qualification answering prompts do not establish a final experimental prompt. No
silent truncation or retrieval substitution may alter the complete-memory condition.

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

**FROZEN for the Small Pilot: scoring contract.** Scoring is whole-value
deterministic matching only. Normalization changes representation only: Unicode NFC,
trim, collapse internal whitespace, and casefold; no type-specific canonicalization
is used. Classification order: (1) a normalized answer equal to the normalized
current target is current-correct; (2) otherwise, equal to any normalized superseded
target value of that variant is a stale/superseded answer; (3) otherwise other error.
Other error covers invalid structured output, a blank answer, a verbose sentence, a
distractor value, multiple values, a current-plus-stale combination, and any
non-whole-value answer. There is no substring, containment, word-boundary, fuzzy,
embedding, LLM-judge, or paraphrase matching; raw exact equality is a diagnostic
only. The material validator must ensure the current target and all superseded target
values remain distinct after normalization. After the live pilot, all 24 final-answer
classifications are cross-checked manually against the scorer.

**OPEN:** missing/invalid-run handling and aggregation for confirmatory analysis.
The qualification fixture's normalization function is not the CRST scoring
implementation.

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
diagnostic. **FROZEN for the Small Pilot:** the primary count is the token count of the exact
complete serialized active-memory block presented at final Q, including its
per-entry metadata, and excluding the answer wrapper, Q, the system prompt, inactive
entries, non-active version history, evaluator annotations, and logs. The tokenizer
is `meta-llama/Llama-3.1-8B-Instruct` at revision
`0e9e39f249a16976918f6564b8830bc894c89659` with `add_special_tokens=False`. The
diagnostics are the text-only entry token count, the active-entry count, and the
active-memory size after each information event. B0 has no active-memory metric; its
selected marginal historical tokens are recorded separately. Confirmatory adoption
remains a pre-main decision.

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

**FROZEN for the Small Pilot: per-request and per-run evidence.** Every logical
request records its logical ID, policy, scenario, variant, event, the exact request
body and hash, model and provider, response, usage, latency, cost, and all physical
attempts. Every policy run records the final answer, its class, the CSA and SRR
contributions, MOA and Update-target diagnostics where applicable, primary and
text-only active-memory tokens, the active-entry trajectory, logical API calls,
physical attempts, logical and retry token usage separately, end-to-end time, the
API latency diagnostic, and supplemental cost. No policy-level pilot ranking or
aggregate accuracy comparison is computed or displayed.

**OPEN:** confirmatory accounting aggregation, missing-usage handling for failed
attempts in summaries, and exact local token-counting measures for CRST length
matching. The primary memory-size unit/sampling point and timing boundary above are
not open. Preserve actual per-attempt evidence rather than guessing details.

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

**FROZEN answering wording.** The fixed system message is the following text, stored
and hashed as one UTF-8 string with a blank line between the two parts
(SHA-256 `8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e`):

```text
You are a helpful assistant. Use only the information provided in the context to answer the user's final question.

Reply with the answer only.
```

It is policy-neutral: B0 supplies recent raw conversation as context, M1/M2/M3
supply active memory as context, and every condition receives the same
instruction. The wording contains no instruction about newer or older values.
It is defined in `configs/b0-calibration.yaml`.

**FROZEN:** `B0_CONTEXT_TOKENS = 71`, derived by the official calibration under
Section 12. Nothing in this section is open.

## 12. B0 Calibration Requirements

**FROZEN:** resolve and calibrate B0 before the confirmatory/main experiment.
Its selection criterion is structural retention of U7 and the required following
conversation, not final QA accuracy, CSA, SRR, comparative M1/M2/M3 results, or
main-experiment effect sizes. Freeze the chosen rule and budget before main
execution. **FROZEN structural retention requirement:** retain the complete U7
exchange and the complete N2 exchange. N1 precedes U7 and is not part of the
minimum retention criterion. Event identity is available only to the dedicated
structural calibration check, not to normal window selection.

**FROZEN calibration design** (`configs/b0-calibration.yaml`). The exchange,
overflow, and counting rules are fixed in Section 11. Do not infer B0 budgets from
the qualified dense-retrieval 512-token setting.

- **Material.** A dedicated calibration-only CRST set of 12 structured scenarios,
  one per frozen domain, each with Low/Medium/High variants under the frozen
  revision design (`data/b0-calibration`). It is separate from Generator
  Qualification fixtures, final confirmatory CRST cases, Model Qualification
  fixtures, LongMemEval-S, and probe material, and can never become any of them.
  Its identifiers, entities, attributes, and values are reserved and excluded from
  later final-CRST construction.
- **Histories.** Both final generators, `openai/gpt-5.6-sol` (G1) and
  `anthropic/claude-fable-5.1` (G2), naturalize every scenario: 12 scenarios x 2
  generators = 24 logical calls, each returning one Low/Medium/High triplet, giving
  72 calibration histories. Under the suffix-only procedure below, each history
  contains only the U7 and N2 events.
- **Retention.** Every calibration history must retain the complete U7 and N2
  exchanges (100%); no percentile rule applies.
- **Budget.** `B0_CONTEXT_TOKENS` is the maximum, over all calibration histories,
  of the smallest marginal-history budget that retains the complete U7 and N2
  exchanges. No headroom is added and no candidate grid is used.
- **Coverage failure.** A final CRST case that needs more than the frozen
  `B0_CONTEXT_TOKENS` to retain the complete required U7 and N2 suffix reveals a
  calibration-coverage failure. It is detected before the main experiment. The
  budget is not increased for that case, no exchange is truncated, the case is not
  altered, no headroom is added, and the failing case is not used as calibration
  material. Instead: (1) create new independent calibration-only extension
  scenarios; (2) naturalize them under the same frozen calibration procedure; (3)
  recompute `B0_CONTEXT_TOKENS` as the exact maximum over all original official
  calibration histories and all approved extension histories; (4) freeze the
  recalibrated budget before the main experiment. The final confirmatory CRST
  remains separate from B0 calibration material.

- **Collection attempts.** An official naturalization collection attempt is atomic
  and consists of the complete frozen set of 24 logical calls. Infrastructure
  retries follow only the frozen request retry policy. A parse failure, schema
  failure, refusal, truncation, required-empty-field failure, or other terminal
  output-contract failure is not selectively retried: it terminates the attempt
  and preserves the evidence already produced. Outputs of an incomplete attempt are
  never combined with outputs of another attempt, and no manual text repair, field
  completion, resampling of a single call, dropping of a variant, or generator
  substitution is allowed. An incomplete attempt is closed as CLOSED_INCOMPLETE and
  cannot yield `B0_CONTEXT_TOKENS`. Exactly one additional complete attempt is
  allowed. It reruns all 24 calls from call 1 under the same frozen scenarios,
  order, generator assignment, models, provider constraints, prompt, input
  contract, output schema, request construction, and design, without reusing any
  earlier output. If it completes, only it supplies the 72 histories. If it ends
  in another terminal failure, B0 calibration stops, no further attempt is created
  automatically, and a separate researcher decision is required. This is
  construction-quality handling; it does not change Generator Qualification.
  **Status:** this full-history procedure (17 naturalized events per variant) is
  CLOSED. Both attempts ended in a terminal output-contract failure in a field
  outside the calibration estimand (Attempt-01: empty `N1`, `N2` and `Q`;
  Attempt-02: empty `N1` with `U7` and `N2` present), so it produced no eligible
  complete calibration set. It remains reproducible historical evidence, and no
  output of either attempt is used to derive the budget.
- **Suffix-only naturalization.** The calibration estimand is the smallest marginal
  budget that retains the complete U7 and N2 exchanges, so the replacement
  procedure naturalizes only those two events. The same 12 structured scenarios
  and the same generators and provider constraints are used, and one logical call
  still returns the Low, Medium and High variants for one scenario and one
  generator, but each variant contains only `U7` and `N2` (both required and
  nonempty; no `I1`-`I7`, `U1`-`U6`, `N1` or `Q`). Each calibration history is
  exactly the U7 user message, `Noted.`, the N2 user message, `Noted.`, counted
  with the same chat-template rule. The procedure has its own prompt, input and
  output-schema versions (`b0-suffix-naturalization-*/1.0.0`), defined in
  `configs/b0-suffix-naturalization-contract.json` and planned in
  `configs/b0-suffix-calibration.yaml`; the Generator Qualification contract is
  unchanged. Failure handling is fixed before execution: only the frozen
  infrastructure retries repeat a request, and an empty U7 or N2, parse or schema
  failure, refusal, truncation, or other terminal execution or output-contract
  failure closes the attempt incomplete, with no selective resampling, repair,
  mixing of attempts, reuse of full-history output, or generator substitution.
  Exactly one complete suffix attempt is allowed (approved), and no second attempt
  starts automatically.
  **Semantic eligibility.** Semantic findings never stop later scheduled calls; if
  execution and schema stay valid, all 24 calls complete. A completed collection is
  eligible for `B0_CONTEXT_TOKENS` derivation only if all 72 suffix histories pass
  every required Level-1 check. For U7: entity, attribute, and supplied
  current-value fidelity, changed-state semantics, no superseded value, no invented
  value or change, and comprehensibility. For N2: entity, attribute, and supplied
  current-value fidelity, same-state semantics, no invented change, no historical or
  superseded value, and comprehensibility. Entity, value, and value-absence checks
  are deterministic and final; the rest are recorded by the researcher as PASS or
  FAIL in an audit bound to the archived evidence. No LLM judge is used. A Level-1
  failure makes the completed collection COMPLETE_BUT_INELIGIBLE and leaves
  `B0_CONTEXT_TOKENS` null and OPEN. Fluency-only defects with unambiguous meaning do
  not affect eligibility and are never used to rank generators. Derivation refuses
  unless the collection is complete, all outputs are schema-valid, the audit is
  complete, and no Level-1 failure remains. All estimand, rule, and coverage
  decisions above are unchanged.

**FROZEN result: B0 calibration is CLOSED and `B0_CONTEXT_TOKENS = 71`.** The
approved suffix-only procedure (`b0-suffix-collection/1.0.0`) completed in its sole
official Attempt-01: 24 of 24 logical calls, 72 suffix histories (12 scenarios x 2
generators x 3 variants). The full-history procedure had closed without an eligible
complete set after its two attempts. Human semantic adjudication covered 144 audit
items (72 histories x U7 and N2) with 0 Level-1 failures, so the collection is
ELIGIBLE; two fluency-only findings (both `G2` Purchase & Order, Medium, U7 and N2)
did not affect eligibility and are not used to rank generators. The exact maximum
over the 72 eligible histories of the smallest marginal budget retaining the
complete U7 and N2 exchanges is 71, attained by `G2` Travel High and `G2` Purchase &
Order Medium. All 72 histories retain the complete U7 and N2 exchanges at 71. No
percentile, candidate grid, or headroom was used. Q and the system prompt remain
outside `B0_CONTEXT_TOKENS`, and the tokenizer is `meta-llama/Llama-3.1-8B-Instruct`
at `0e9e39f249a16976918f6564b8830bc894c89659`. The value is frozen in
`configs/b0-suffix-calibration.yaml` and bound to the immutable derivation artifact
`results/b0-suffix-calibration/derivation/attempt-01.json` (SHA-256
`70ed6e326e82378f8f4ab0a4e88cf639a21f7da58cf255c9c693cf24eb4ed365`). The
calibration is closed and is not reopened because later experimental outcomes are
unfavorable; a final CRST case needing more than 71 to retain U7 and N2 is a
calibration-coverage failure handled only by the rule above. This validates
structural retention on the calibration material only; it says nothing about B0's
answer quality.

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
**PROVISIONAL numeric criteria:** the current manuscript requirements
specify maximum **5%** difference for specified within-triplet
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

**FROZEN pilot configuration** (`configs/crst-small-pilot.yaml`; material in
`data/crst-small-pilot/`): two pilot-only base scenarios, `pilot-scheduling-01`
under G1 `openai/gpt-5.6-sol` and `pilot-travel-01` under G2
`anthropic/claude-fable-5.1`. Their entities, attributes, values, and codes are new
and are not reused from Generator Qualification, Model Qualification, Dense
Retrieval Qualification, B0 calibration, LongMemEval-S, or the future confirmatory
CRST. Each scenario has Low, Medium, and High variants, each run under M1, M2, M3,
and B0: 6 variants, 24 policy runs, no technical repetition. Backbone logical calls
per variant are M1 1, B0 1, M2 9 maintenance plus 1 answer, and M3 the same, so 22
per variant and 132 in total (108 maintenance, 24 answering). Naturalization uses
2 logical generator units, one triplet per scenario. B0 uses the budget frozen in
`configs/b0-suffix-calibration.yaml`, which is authoritative for B0; the B0
placeholders in `configs/retrieval.yaml` are historical.

**FROZEN naturalization failure policy (construction only; it does not reopen
Generator Qualification or B0).** The unit is one triplet under its preassigned
generator. A terminal non-evaluable failure (parse or schema failure, a required
empty or blank field, a refusal, truncation, or an infrastructure-terminal failure
after the frozen retry policy) allows at most three total logical attempts per unit,
with the same generator, prompt, and structured input; each attempt is archived
separately. Field mixing, manual completion, selective field retry, and generator
substitution are prohibited. After three failures the unit is UNBUILDABLE and work
stops for a researcher decision. A schema-valid output with a Level-1
semantic/fidelity failure is not regenerated automatically; work stops for a
researcher decision. A fluency-only finding does not trigger regeneration; the
existing provenance-aware minimal surface-edit handling may be used before the final
dataset freeze, followed by revalidation. The cap is a bounded engineering policy
fixed prospectively.

**FROZEN pilot workflow and live gates.** (A) Build and validate the structured
material. (B) Live-naturalize the two triplets with
`experiments/naturalize_crst_pilot.py`, a separate gated construction step. (C) Audit
the naturalized material offline (`--audit`): structure, the frozen deterministic
semantic check, B0 coverage of U7 and N2 within the frozen budget, and, when the
check leaves findings, a bound researcher review. (D) Only after an eligible audit,
execute the 24 policy runs and 132 backbone logical calls with
`experiments/execute_crst_pilot.py`. (E) Replay and score offline from the archived
raw responses and evaluate the checklist. (F) The researcher reviews the 24
final-answer classifications. Each live step needs its explicit flags
(`--execute` and `--confirm-spend`), a clean committed worktree whose files are
tracked, matching source, config, and material identities, an absent fresh result
directory, and `OPENROUTER_API_KEY`; the backbone step additionally needs the
eligible audit bound to the archived naturalization collection and the pinned
tokenizer. A terminal infrastructure failure or routing violation in step D aborts
the pilot and preserves the evidence after the frozen infrastructure retry policy is
exhausted; it is never scored as a model decision or an other error, and a partial
execution is never continued or interpreted. A schema-invalid maintenance output from
the model remains an invalid model decision without semantic retry, and a malformed
final answer remains an other error.
Backbone calls use the qualified stateless transport (no fallback, no provider
conversation state, three physical attempts per logical request). There is no main
experiment in this workflow.

The pilot's results are never effect-size estimates, policy rankings,
power-analysis inputs, or reasons to change a policy. The binary mechanical
acceptance checklist is encoded in `configs/crst-small-pilot.yaml`; its offline
items are executable with `experiments/run_crst_pilot.py --checklist`, and its
post-naturalization and post-run items stay pending until the corresponding steps
exist. No pilot execution is authorized by this specification, and no pilot results
exist.

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

- The CRST response schema and request wrapper are FROZEN for the Small Pilot
  (Section 7); their adoption for the confirmatory CRST and the handling of an
  oversized complete-memory request remain OPEN. `B0_CONTEXT_TOKENS` is frozen at 71 (Section 12), and the calibration design and
  answering wording are frozen in Sections 11 and 12.
- Physical journal/version-history artifact schema and storage layout; semantic
  fields, canonical IDs, reference-target comparison, and execution rules are fixed.
- Scenario allocation/trajectories beyond frozen constraints, CRST schema, and
  deterministic generator-assignment mechanism/seed within the frozen balancing
  constraints.
- Confirmatory adoption of the pilot prompts, response/scoring contract, and
  active-memory token counting (frozen for the pilot in Sections 6-10), invalid-run
  treatment, resource aggregation, timer instrumentation, and length-measure
  implementation. Candidate text, memory serialization/order, and B0
  tokenizer/counting semantics are already frozen.
- Pilot execution authorization and other unresolved reproducibility details. The
  pilot size, cases, and acceptance checklist are FROZEN in Section 15.

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

**RECOMMENDATION:** resolve the remaining physical artifact schemas, experimental
prompts, and validation procedures before dependent dataset generation. This does
not reopen the newly adjudicated conversation, identity, or B0 counting rules.

This recommendation does not become FROZEN through inclusion in this document.

## 20. Explicit Non-Goals

This specification and its implementation-resolution update are documentation
only. They do not generate qualification fixtures, CRST or pilot cases,
naturalize text, invoke a model/API, calibrate B0, run policy experiments,
perform statistical simulation, select N/R/minimum effect of interest, or freeze
provisional statistical/length parameters. The accompanying Generator Qualification
plan and concise decision-log entries do not modify the external Proposal, configs,
completed qualifications, datasets, or Git history. This document makes no claim
that the full CRST, B0 calibration, or Small Pilot has already been executed.
