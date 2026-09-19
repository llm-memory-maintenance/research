# Generator Qualification Fixture Construction and Audit

> **Status notice — historical Protocol v1 audit contract.** The manual-audit
> rules in this document (§5) define the historical `generator-manual-audit/1.0.0`
> contract used by Protocol v1 (`generator-qualification-procedure/1.0.0`). Its
> behavior of treating any applicable `natural_english` failure as an absolute
> fixture (and therefore candidate) failure belongs to Protocol v1 only.
> Protocol v2 methodology is defined in, and its
> `generator-manual-audit/2.0.0` audit schema/implementation are specified
> in, [generator-qualification.md §14](generator-qualification.md) (the
> implementation is frozen at revision r2; under v2 the reviewer
> decides only cell-level checks and ambiguities, while variant, fixture and
> candidate dispositions are derived by the adjudicator); no official
> Protocol-v2 re-adjudication result is recorded. This document remains
> authoritative only
> for reproducing historical Protocol-v1 audits. The fixture-set construction
> content (§1–§4) is unaffected.

## 1. Status and Boundaries

Exactly 12 qualification-only base fixtures have been constructed offline, one
per frozen domain. **GENERATOR QUALIFICATION FIXTURE SET: FROZEN.** Final
researcher review passed after the targeted pre-freeze adjudication. No natural-language outputs, model-result audit
records, qualification calls, final CRST scenarios, B0 histories, or pilot data
have been generated. Sol and Sonnet remain CANDIDATE. Capability Probe remains
CLOSED/PASS; its execution package and semantic contract versions are unchanged.

The [manifest](../data/generator-qualification/manifest.json) records each raw
fixture SHA-256, canonical model-facing projection SHA-256, roles, schedules,
coverage, and exact secondary allocations. The same approved, immutable set will
be used independently for G1 and G2 (and any authorized corresponding fallback).
These construction fixtures cannot become final confirmatory CRST data.

Construction provenance is the committed HEAD recorded in the manifest, meaning
the upstream baseline at construction, not a claim that the new files were
already committed there. The later official qualification must additionally
record the reviewed fixture manifest hash and its own exact committed source.

## 2. Reference Truth and Model-Facing Projection

Each file has `schema_version`, `fixture_id`, `purpose`, and `reference`. There is
one authored semantic truth. Reference truth contains inventories, initial values,
ordered trajectories, per-event previous and superseded values, complete state
traces, final state, target identity, and gold current value. All canonical values
are nonempty strings with units or explicit interpretation in the attributes.
No numeric parsing or external factual knowledge is required.

`project(fixture)` derives the input 1.1.0 object using explicit allowlists:
`domain`, `entities`, `attributes`, `state_keys`, `initial_order`,
`question_intent`, and `variants`. Each event exposes only its event label,
state-key reference, current value and initial/changed_state/same_state semantics.
Previous/superseded values, state traces, inventories, gold answers, fixture-purpose
metadata, evaluator information, memory IDs, timestamps, and policy operations
are reference-only. No independently edited projection files exist.

Projection hashing uses UTF-8 JSON, `ensure_ascii=False`, sorted keys, compact
separators, no nonfinite numbers, and no trailing newline. Reference/schema/manifest
files use UTF-8, two-space indentation, deterministic field order and a trailing
newline. No creation timestamps or stochastic sampling enter construction.

The Pydantic models generate the [strict reference JSON Schema](../data/generator-qualification/reference-schema.json)
and perform structural validation using the existing project dependency. Objects
forbid extra fields. `initial_order`, `state_after`, and `final_state` are bounded
maps with enumerated keys and string values; state traces contain only keys
initialized by that point. Their key coverage is checked in deterministic code.
Cross-file fixture/domain uniqueness, reference resolution, trajectories and
manifest integrity require that validator, not JSON Schema alone. No generic
JSON Schema Draft 2020-12 validation engine is claimed.

## 3. Qualification-Only Allocation and Coverage

Every fixture uses `k_target`, `k_hard`, `k_n2`, and `k_a`–`k_d` as local structured
keys, not memory-entry IDs. Target and hard distractor concern the same attribute
of distinct explicitly named entities; their value inventories do not overlap.
The N2 secondary belongs to the primary entity and has its own identifier attribute.
Researcher adjudication retains this convention for all 12 qualification fixtures:
stable identifier/code values provide an unambiguous never-updated reaffirmation
anchor, while N1 exercises same-state diversity across the domain-specific target
types. This is not a claim of inherent superiority and does not require identifier
attributes for N2 in final CRST scenarios.

For zero-based domain index i in the frozen domain order:

1. Rotate `[k_a,k_b,k_c,k_d]` left by i modulo 4.
2. Low: form `[k_hard, rotated_four..., rotated_four[0]]`, rotate left by i modulo
   6, and assign to U1–U6. Thus all four other secondaries occur and one repeats.
3. Medium: form `[k_hard, rotated_four[1], rotated_four[2]]`, rotate left by i
   modulo 3, and assign to U2/U4/U6. The other two cannot all occur within the
   three available events; rotation varies the covered pair across fixtures.
4. High has no secondary updates. N2 is never updated in any variant.

The hard distractor changes at least once in Low and Medium. This is an explicit
qualification-set construction requirement, not the capability probe's local
allocation and not a general final-CRST allocation freeze. The probe validator
remains unchanged; its Software Configuration restriction and protected hard
secondary are probe-local. The new validator accepts the 12-domain contract and
this qualification-specific allocation.

Initial roles rotate by i modulo 7 across I1–I7, identically within each triplet.
Every target has eight distinct values. High uses indices 1–7 after index-0
initialization; Medium uses 1/3/5/7; Low uses 7. All converge to index 7 without
reversion. Secondary revisions advance through their own inventories. N1 and N2
copy the then-current reference value without state change.

| Fixture ID | Domain | Target entity / hard-distractor entity | Shared target/distractor attribute | N2 attribute |
| --- | --- | --- | --- | --- |
| gq-scheduling-01 | Scheduling | Tern rehearsal / Gull rehearsal | start_time | session_code |
| gq-travel-01 | Travel | Voyage Pavo / Voyage Grus | destination | booking_code |
| gq-project-planning-01 | Project Planning | Project Halcyon / Project Petrel | milestone | project_code |
| gq-task-assignment-01 | Task Assignment | Task Vireo / Task Siskin | assignee | task_code |
| gq-software-configuration-01 | Software Configuration | Render profile Ibis / Render profile Egret | export_format | profile_code |
| gq-personal-preference-01 | Personal Preference | Person Fenli / Person Gavri | notebook_style | member_code |
| gq-purchase-order-01 | Purchase & Order | Order Kittiwake / Order Sandpiper | item_count | order_code |
| gq-study-planning-01 | Study Planning | Study plan Wren / Study plan Lark | topic | plan_code |
| gq-communication-01 | Communication | Channel Skylark / Channel Starling | digest_schedule | channel_code |
| gq-service-subscription-01 | Service & Subscription | Service account Curlew / Service account Avocet | plan | account_code |
| gq-location-logistics-01 | Location & Logistics | Parcel route Plover / Parcel route Dunlin | destination_bay | route_code |
| gq-quantitative-planning-01 | Quantitative Planning | Plan Osprey / Plan Kestrel | sheet_count | plan_code |

Coverage includes clock times, invented calendar labels, fictional locations,
configuration labels, preferences, assignments, quantities, subscription states,
communication settings, ordering, planning, categorical expressions and numbers
with units. This is descriptive coverage, not an inferential taxonomy. Values do
not require live prices, actual calendar arithmetic, or external factual truth.
Names/structured content were independently authored, not copied from external
validation, retrieval calibration, Model Qualification, or the probe. The
validator checks probe identity/entity non-reuse; it does not claim that an
automated lexical comparison can prove absence of all conceivable semantic overlap.

## 4. Offline Validation and Reproduction

Run in the project environment:

```bash
python experiments/validate_generator_qualification_fixtures.py
python experiments/build_generator_qualification_fixtures.py --check
pytest -q tests/test_generator_qualification_fixtures.py
```

The constructor exists for byte-level reproducibility and uses no model. Its
write mode refuses an existing dataset directory. `--check` regenerates only in
memory and compares all bytes against the recorded construction provenance.
The validator checks every reference event, full state traces, fixed schedules,
reaffirmations, changed values, non-reversion, final convergence, role counts,
identity resolution, projection field discipline, set composition, schema and
manifest hashes. Input validation occurs before any future request construction.

Independent semantic checks explicitly assert the 1/4/7 target schedules without
consulting the allocation helper. Low must contain six secondary updates: exactly
one hard-distractor update, all four ordinary secondaries, and one repeat of an
ordinary secondary. Medium must contain three secondary updates: the hard
distractor and two distinct ordinary secondaries. High contains none; N2 is never
updated. Shared target U positions must have identical values across variants.
Entity display names must be nonempty and distinct after Unicode NFKC, case-folded
word normalization. Q-intent lint requires the primary entity name and rejects
immediately repeated normalized words; semantic Q review remains manual.

Exact initial rotation, exact secondary rotation, and inventory-index selection
remain builder conventions, not semantic validation requirements. The manifest
records secondary allocations extracted from actual reference events. Reproduction
still compares the builder's exact bytes; it does not replace independent semantic
checks or manual audit.

The pre-freeze source review corrections are limited to three fixtures. Study
Planning now asks for the "current study topic", removing the repeated word.
Communication digest schedules use target values `daily at 08:00` through
`daily at 15:00` and disjoint hard-distractor values `daily at 16:00` through
`daily at 18:00`, in one-hour increments. These are self-contained daily clock
schedules, with no dated event or timezone conversion; `times` coverage is added.
Quantitative Planning target counts are 420, 450, 480, 510, 540, 570, 600 and 630
sheets; hard-distractor counts are 720, 750 and 780 sheets. All are divisible by
the 10/15 sheets-per-bundle values encountered in the trajectories. Entities,
attributes, roles, N2 values and event/allocation structure are preserved.
The fixtures are FROZEN after final researcher review. Future changes require
explicit defect adjudication and a new fixture-set version and freeze record. No
naturalization or Generator Qualification has run; Sol/Sonnet remain CANDIDATE.

Known superseded expressions remain available only to reference-side validation.
Later output checks must require current values, flag known superseded expressions
in the corresponding event, and reject unambiguous historical restatement.
Substring matching alone cannot establish semantic correctness; ambiguous lexical
or formatting overlap requires manual adjudication. All same-state messages must
state only the still-current fact. These fixtures contain no naturalized outputs.

## 5. Blank Manual Result-Audit Format

Use one audit record per model/fixture/variant/event after authorized qualification.
Required record fields (no records are filled in this task):

- Model ID, observed provider, qualification attempt, fixture ID/hash, manifest hash.
- Prompt/input/output-schema versions; raw response hash and event-text location.
- Variant (`low`, `medium`, `high`); event (I1–I7, U1–U6, N1, U7, N2, Q).
- Reviewer identifier, review date, notes, and evidence supporting every failure.

For each event, record PASS/FAIL for each applicable check:

| Check | Review question |
| --- | --- |
| Natural English | Is the text natural and comprehensible? |
| Entity fidelity | Does it preserve the exact intended entity? |
| Attribute fidelity | Does it preserve the intended attribute? |
| Current-value fidelity | Does it state the assigned current value faithfully? |
| Actual-change wording | Is a changed state asserted as actual, not conditional/hypothetical? |
| Same-state fidelity | Does a reaffirmation preserve the current state without a change? |
| Superseded-value leakage | Is historical-value restatement absent? |
| Invented information | Is any extra state-changing fact or implication absent? |
| Event integrity | Is exactly this event expressed, without omission or merging? |
| Q intent fidelity | Does Q ask for the current target alone, identically across variants? |
| Answer leakage | Are answer hints/answers absent beyond required information events? |
| Output boundary | Are acknowledgements, assistant messages and evaluator data absent? |

**FROZEN (researcher adjudication):** the applicability rules below. Applicability is
fixed, not chosen per review. The generated template
pre-fills `NA` for every inapplicable (check, event) pair and records the table
under `check_applicability`. Reviewers cannot overwrite an `NA`, and cannot
mark an applicable check `NA`:

| Check (template key) | Applicable events | Reason for NA elsewhere |
| --- | --- | --- |
| `changed_vs_hypothetical_wording` | U1–U7 | Only updates assert a state change. |
| `same_state_fidelity` | N1, N2 | Only reaffirmations are same-state. |
| `q_intent_fidelity`, `answer_leakage` | Q | Pre-Q added hints are reviewed under invented information. |
| `current_value_fidelity` | I1–I7, U1–U7, N1, N2 | Q states no value. |
| `superseded_value_leakage` | U1–U7, N1, N2, Q | Nothing is superseded during I1–I7. |
| `natural_english`, `entity_fidelity`, `attribute_fidelity`, `invented_information_or_state_change`, `merged_or_omitted_event`, `output_boundary` | all 17 | — |

A terminally failed call (no parsed, schema-valid output) has no event
records. The candidate fails on that evidence without meaningless manual
entries. This never waives an applicable requirement.

**FROZEN reviewer convention:** `reviewer` identifies the human reviewer chosen
by the researcher. The runner leaves it blank and it is never auto-populated
with any software or tool identity. `reviewed_at` must be an RFC 3339
timestamp with an explicit offset (format example only:
`2026-09-18T21:30:00+07:00`). The adjudicator validates its format and calendar
validity. Every manual value requires both fields. Every manual FAIL requires
evidence notes, and every ambiguity resolution requires notes. The completed
audit is a separate copy of the archived blank template. Also record variant-level
completeness/order and shared-control checks. A separate per-model/per-fixture
summary records **overall fixture PASS/FAIL**, reviewer notes and links to all
three variants' event reviews. Any applicable failed automated/manual check makes
the fixture FAIL; the model qualifies only when all 12 fixtures pass. No subjective
scores, rankings or policy outcome criteria are used. No LLM judge is used.

## 6. Remaining Review and Execution Boundaries

The qualification runner, automated naturalized-output fidelity checks, audit
storage and adjudication procedure are implemented offline but **NOT YET
FROZEN**. See [Generator Qualification §10](generator-qualification.md#10-offline-qualification-runner--implemented-not-frozen).
Live execution requires the reviewed implementation commit and a subsequent
freeze record pinning it. The 5%/2%
length tolerances remain PROVISIONAL and are not pass/fail gates here. Generator
assignment mechanism/seed, final N/R/MOI/statistical details, B0 material/grid/budget
and Small Pilot details remain unresolved in their respective workstreams.
