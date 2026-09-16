# Model Qualification

## Purpose

Model qualification verifies that the fixed experimental backbone can execute
the interfaces required by the study.

The procedure is not a model benchmark, model comparison, or capability
ranking.

Planned backbone:

`meta-llama/llama-3.1-8b-instruct`

Planned upstream provider:

`coreweave/bf16`

The qualification is performed before any comparative M1, M2, or M3
experiment.

## Qualification Scope

The model must support four experimental functions:

1. memory extraction;
2. memory maintenance;
3. answer generation; and
4. API interface and accounting requirements.

Qualification uses synthetic technical fixtures that are separate from CRST and
LongMemEval-S.

No CRST or LongMemEval-S experimental instance is used during qualification.

## Memory Representation

A memory item represents one current entity-attribute-value proposition.

Example:

- entity: `Mira`
- attribute: `locker_color`
- value: `cobalt`

The exact machine-readable schemas are defined by the qualification
implementation and validated locally.

## Technical Fixtures

### Extraction

Two extraction fixtures are used.

E1 tests extraction of a simple current fact.

Input meaning:

`Mira's locker is cobalt.`

Expected proposition:

- entity: Mira
- attribute: locker_color
- value: cobalt

E2 tests extraction of an explicitly revised current fact.

Input meaning:

`Mira changed her locker color from amber to cobalt.`

Expected current proposition:

- entity: Mira
- attribute: locker_color
- value: cobalt

Historical wording must not cause the superseded value to become the extracted
current value.

### Maintenance

Three maintenance fixtures are used.

M1 tests Add.

Existing memory:

empty

Candidate:

- entity: Mira
- attribute: locker_color
- value: cobalt

Expected operation:

`add`

M2 tests Update.

Existing memory:

- entity: Mira
- attribute: locker_color
- value: amber

Candidate:

- entity: Mira
- attribute: locker_color
- value: cobalt

Expected operation:

`update`

Expected target:

the existing Mira locker-color memory item

M3 tests Noop.

Existing memory:

- entity: Mira
- attribute: locker_color
- value: cobalt

Candidate:

- entity: Mira
- attribute: locker_color
- value: cobalt

Expected operation:

`noop`

### Answering

Two answering fixtures are used.

A1 tests direct use of current memory.

Active memory states that Mira's locker color is cobalt.

Question:

`What color is Mira's locker?`

Expected answer:

`cobalt`

A2 tests resistance to a stale value.

Active memory contains the current value `cobalt` and metadata identifying
`amber` as superseded historical information.

Question:

`What color is Mira's locker now?`

Expected answer:

`cobalt`

The model must not answer `amber`.

### End-to-End Interface

One end-to-end fixture verifies that extraction, maintenance, memory-state
application, and answering can be executed sequentially using the same frozen
schemas and model configuration.

The fixture starts with Mira's locker color as amber, introduces a revision to
cobalt, applies the resulting maintenance decision, and asks for the current
locker color.

Expected final answer:

`cobalt`

## Execution

The qualification contains eight logical calls:

- 2 extraction calls;
- 3 maintenance calls;
- 2 answering calls;
- 1 end-to-end verification call.

Calls are stateless at the API level.

Required state is supplied explicitly by the qualification program.

Concurrency is 1.

Automatic provider fallback is disabled.

## Output Validation

Every response required to be structured must:

1. return successfully;
2. contain parseable JSON;
3. pass the predefined local Pydantic schema;
4. contain no additional unsupported operation or target value.

A response is evaluated exactly once.

Semantic repair, corrective reprompting, best-of sampling, and LLM judging are
not used.

Infrastructure retries may occur only under the configured transport retry
policy.

## Qualification Criteria

The model configuration qualifies only if all of the following hold:

- all eight logical calls complete;
- every required structured response parses successfully;
- every structured response passes local schema validation;
- E1 and E2 produce the expected current proposition;
- M1 returns Add;
- M2 returns Update with the correct target;
- M3 returns Noop;
- A1 and A2 return the expected current value;
- the end-to-end fixture returns the expected current value;
- the requested model is the configured Llama 3.1 8B model;
- the observed provider is consistent with the pinned CoreWeave endpoint;
- automatic provider fallback does not occur;
- input-token and output-token accounting is available for successful model
  responses.

If any required condition fails, the configuration is not frozen for the main
experiment until the cause is reviewed.

A failed qualification does not authorize changing prompts, schemas, model
parameters, or providers and rerunning them repeatedly until a pass is
obtained. Any material change requires an explicit documented decision before
a new qualification run.

## Recorded Evidence

The qualification output must record:

- qualification timestamp;
- model identifier;
- requested provider;
- observed provider when exposed;
- generation parameters;
- prompt and schema identifiers;
- logical call identifiers;
- request status;
- parse status;
- schema-validation status;
- deterministic expected-versus-observed result;
- token accounting;
- latency;
- retry information;
- final qualification status.

Secrets must never be written to qualification artifacts.

## Outcome

There are only two qualification outcomes:

- `QUALIFIED`
- `NOT_QUALIFIED`

No numerical model score or cross-model ranking is produced.

A `QUALIFIED` result permits the exact model configuration to be frozen for the
main experimental workflow.
