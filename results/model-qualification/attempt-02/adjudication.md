# Model Qualification Attempt 2 adjudication

- Qualification attempt: 2
- Result: `NOT_QUALIFIED`
- Backbone: `meta-llama/llama-3.1-8b-instruct`
- Provider endpoint: `coreweave/bf16`
- Qualification implementation/prompt checkpoint: repository commit `4dafe82`
- Evidence: archived `qualification.json` in this directory
- Archived artifact SHA-256: `8b7026589b3eea9899113b06879b19fd6ec19b89ec62d0f7f08ccb1c458fc45c`

The official `results/model-qualification/qualification.json` was copied verbatim
before modifying the extraction prompt. Exclusive file creation refused to
overwrite any existing Attempt 2 archive. The archive was verified byte-for-byte
against the source. Preserve this archive permanently; later runs must never
overwrite it. The program's output path remains outside `attempt-02/`.
The Attempt 1 archive and adjudication note remain unchanged.

## Evidence and adjudication

Attempt 2 executed all ten logical calls. E1 was the only failure.
Its input was `Mira's locker is cobalt.` and its observed output was:

```json
{"memories":[{"entity":"Mira's locker","attribute":"color","value":"cobalt"}]}
```

The unchanged qualification contract requires:

```json
{"memories":[{"entity":"Mira","attribute":"locker_color","value":"cobalt"}]}
```

E1's request, routing verification, usage accounting, JSON parsing, and Pydantic
schema validation passed. Deterministic canonical evaluation failed. The output
retained the factual content but decomposed entity and attribute differently.
Stable canonical `(entity, attribute)` keys are required for subsequent memory
matching and maintenance. This is not grounds for accepting semantic equivalence,
changing the evaluator, or changing fixture text or expected output.

The other nine logical calls (E2, M1, M2, M3, A1, A2, E2E-E, E2E-M, E2E-A)
passed all call-level qualification criteria. M2 and E2E-M correctly returned
`{"operation":"update","target_id":"mem-1"}` after the previous documented
prompt revision. E2E local state application succeeded, producing active memory
`Mira / locker_color / cobalt` at `mem-1`. E2E-A executed and passed with `cobalt`.
These observations do not independently establish the cause of improvement.

Routing/provider verification and usage accounting passed for all ten successful
calls. There were exactly ten physical attempts, each HTTP 200, and no
infrastructure retries. The final outcome remains `NOT_QUALIFIED` because every
qualification criterion must pass.

## One narrowly scoped extraction clarification

All existing extraction instructions are retained. The following text is appended:

> The entity is the primary owner/subject whose state is remembered; the attribute is the property associated with that entity. For possessive constructions giving a property of an owned or associated object, keep the owner/subject as entity and combine object and property in a snake_case attribute when needed for a stable key. Do not collapse the owner and possessed object into one entity string when the owner can be represented separately. Use the same canonical (entity, attribute) representation for semantically corresponding direct-state and revision statements. For example, "Jordan's bicycle is green." uses entity "Jordan", attribute "bicycle_color", and value "green", rather than entity "Jordan's bicycle".

This material prompt clarification is documented before any further attempt.
Its purpose is consistent canonical representation across possessive direct-state
and revision statements. The example is independent of the qualification
fixtures. This does not establish that another attempt will pass.

Maintenance and answering prompts remain unchanged, as do all fixture inputs,
expected outputs, schemas, normalization, deterministic evaluation, local state
application, ten logical IDs, response format, parse-once behavior, retry policy,
provider verification, accounting, model/provider configuration, generation
parameters, and acceptance criteria. No semantic equivalence handling, repair,
corrective reprompt, best-of sampling, judging, or additional calls are added.
Any later authorized Attempt 3 must still satisfy every criterion.

This is pre-experimental technical qualification evidence, not a thesis
main-experiment result. This adjudication and clarification are offline only;
Attempt 3 is neither executed nor authorized by this work.
