# Dataset Specification

## 1. Scope

The study uses two datasets with different roles:

1. the Controlled Revision Stress Test (CRST) as the primary controlled experimental dataset; and
2. the Knowledge Update subset of LongMemEval-S as an external validation dataset.

CRST is designed to isolate the effects of memory-maintenance policy and revision intensity under controlled conditions.

LongMemEval-S is retained as an externally developed benchmark and is not used to determine the CRST experimental structure.

## 2. Controlled Revision Stress Test

### 2.1 Design Unit

A CRST base scenario defines one coherent conversational context containing seven initial information units:

- one target information unit; and
- six secondary information units.

The target information is the item whose revision intensity is experimentally manipulated.

The secondary information units provide surrounding conversational state and controlled distractors.

Each base scenario is instantiated at three target-revision intensities:

- Low;
- Medium; and
- High.

The underlying scenario semantics remain equivalent across the three intensities.

### 2.2 Initial Information

The initial sequence is denoted:

I1, I2, I3, I4, I5, I6, I7

These information units establish the same initial state before any experimental update is applied.

Initial-state construction is identical across M1, M2, and M3.

The initial information establishes the experimental state and is not counted as a maintenance-policy treatment event.

### 2.3 Update Sequence

Each CRST variant contains seven update events:

U1, U2, U3, U4, U5, U6, U7

U7 is always the final update to the target information.

Target-update placement is fixed by revision intensity:

| Revision intensity | Target-update positions |
| --- | --- |
| Low | U7 |
| Medium | U1, U3, U5, U7 |
| High | U1, U2, U3, U4, U5, U6, U7 |

Update positions not assigned to the target contain updates to secondary information.

The total number of update events therefore remains constant across revision intensities. Only the allocation of target versus secondary updates changes.

### 2.4 Noop Opportunities

Each variant contains two controlled Noop opportunities:

- N1 occurs after U6 and before U7; and
- N2 occurs after U7 and before the final query.

The sequence is therefore:

I1–I7 -> U1–U6 -> N1 -> U7 -> N2 -> Q

N1 reaffirms information whose current state is already represented and provides a controlled opportunity for the Noop operation.

N2 occurs after the final target update and concerns secondary information.

The semantic content of a Noop opportunity is not allowed to introduce a new state or invalidate an existing current state.

### 2.5 Target-Value Constraints

Target revisions are subject to the following constraints:

- every explicit target revision changes the current target value;
- a superseded target value does not become current again later in the same scenario;
- the final target value is determined before natural-language realization;
- the correct final answer is derivable from the final structured state; and
- historical target values remain identifiable for stale-reliance evaluation.

These constraints prevent ambiguity between a legitimate final state and a previously superseded state.

### 2.6 Secondary Information

Each scenario contains six secondary information units.

The secondary information serves several controlled roles, including:

- ordinary state updates;
- contextual information;
- distractor information; and
- the secondary Noop opportunity.

One secondary information unit is the hard distractor; it is distinct from the N2 secondary.

One secondary information unit is reserved for the N2 reaffirmation and is not updated elsewhere in the same variant.

The remaining secondary information units may receive updates as required to fill non-target update positions.

The exact assignment of secondary roles is fixed in the structured scenario representation before natural-language realization.

### 2.7 Scenario Domains

CRST contains 12 scenario domains.

Domains provide semantic diversity and are not treated as a primary experimental factor.

Each domain has to support scenarios in which information can be revised naturally without requiring specialized external knowledge.

The 12 domains are listed in the CRST specification (Section 2).

### 2.8 Structured Representation

Each CRST scenario is defined first in a structured representation.

The structured representation is required to record at least:

- scenario identifier;
- domain;
- information-unit identifiers;
- target identifier;
- secondary identifiers;
- initial values;
- update events;
- Noop events;
- revision-intensity condition;
- final current state;
- historical target values; and
- expected final answer.

Natural-language text is generated only after the structured state has passed validation.

The structured representation is the authoritative source for experimental ground truth.

### 2.9 Natural-Language Realization

Natural-language realization converts the validated structured scenario into multi-turn conversational text.

The realization process is required to preserve:

- entity identity;
- attribute identity;
- event order;
- update semantics;
- Noop semantics;
- final current state; and
- expected answer.

Naturalization is not allowed to add information that changes the structured ground truth.

Naturalization uses the qualified generators and the shared contract in [generator-naturalization-contract.md](generator-naturalization-contract.md). The naturalization failure policy for the final CRST is open (Section 5).

### 2.10 Validation

CRST validation is performed before the main experiment.

Automatic validation is required to verify at least:

- required event counts;
- target-update placement;
- U7 as the final target update;
- N1 and N2 placement;
- no return to superseded target values;
- consistency between structured state and expected answer; and
- equivalence of scenario identity across Low, Medium, and High variants.

The final generated CRST dataset is additionally subject to exhaustive manual review before it is frozen for confirmatory execution.

After the confirmatory dataset has been frozen, no M1, M2, or M3 comparative results are used to revise it.

## 3. LongMemEval-S Knowledge Update Subset

### 3.1 Source

External validation uses the cleaned LongMemEval-S dataset.

Local source file:

`data/longmemeval/raw/longmemeval_s_cleaned.json`

SHA-256:

`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`

The raw dataset is excluded from version control.

### 3.2 Candidate Definition

Knowledge Update candidates are identified using the following predicate:

    instance["question_type"] == "knowledge-update" \
    and not instance["question_id"].endswith("_abs")

The source dataset contains:

- 500 total instances;
- 78 Knowledge Update instances;
- 6 abstention variants; and
- 72 non-abstention Knowledge Update candidates.

### 3.3 Frozen Usable Set

A completed audit of the 72 candidates produced:

- 56 usable instances;
- 16 excluded instances; and
- 0 unresolved instances.

The external-validation sample size is therefore fixed at:

N = 56

The final usable identifiers are stored in:

`data/longmemeval/audit/frozen_usable_ids.json`

The historical audit evidence is preserved under:

`data/longmemeval/audit/`

The audit is not repeated.

### 3.4 Subset Construction

The executable LongMemEval-S subset is required to be reconstructed deterministically from:

1. the verified raw source dataset; and
2. `frozen_usable_ids.json`.

A separate manually edited copy of the 56-instance subset is not treated as an authoritative data source.

The reconstruction procedure is required to fail if:

- the source hash differs from the expected hash;
- a frozen identifier cannot be found;
- duplicate identifiers are encountered; or
- the reconstructed count differs from 56.

### 3.5 Experimental Role

LongMemEval-S is used only for external validation.

It does not determine:

- CRST revision-intensity levels;
- CRST scenario construction;
- the number or position of CRST update events; or
- the memory-policy definitions.

The same frozen LongMemEval-S instances are evaluated under all persistent memory-maintenance policies.

## 4. Dataset Versioning

The following artifacts have to be fixed before confirmatory execution:

- final CRST structured dataset;
- final CRST natural-language dataset;
- CRST validation report;
- CRST dataset hash;
- LongMemEval-S source hash; and
- LongMemEval-S usable-instance identifiers.

Generated experimental results are required to record the exact dataset versions or hashes used during execution.

## 5. Open Dataset Decisions

The following dataset-related decisions remain open:

- final number of CRST base scenarios;
- final number of technical repetitions;
- naturalization failure policy for the final CRST, covering both non-evaluable and Level-1 failures;
- generator assignment mechanism and seed for the final CRST;
- exact machine-readable CRST schema; and
- final automatic-validation implementation.

These decisions have to be fixed before the confirmatory dataset is frozen.
