# Model Qualification

## 1. Purpose

Model qualification verifies that the fixed experimental backbone can execute
the interfaces required by the study.

The procedure is not a model benchmark, model comparison, or capability
ranking.

Planned model:

`meta-llama/llama-3.1-8b-instruct`

Planned provider:

`coreweave/bf16`

Qualification is completed before any comparative M1, M2, or M3 experiment.

## 2. Scope

The model must support four experimental functions:

1. memory extraction;
2. memory maintenance;
3. answer generation; and
4. API interface and accounting requirements.

Qualification uses synthetic technical fixtures that are separate from CRST
and LongMemEval-S.

No CRST or LongMemEval-S experimental instance is used during qualification.

## 3. Memory Representation

A memory item represents one current entity-attribute-value proposition.

Example:

- entity: Mira
- attribute: locker_color
- value: cobalt

Machine-readable responses are validated locally using predefined schemas.

## 4. Qualification Fixtures

### 4.1 Extraction

E1 tests extraction of a simple current fact.

Input meaning:

Mira's locker is cobalt.

Expected proposition:

- entity: Mira
- attribute: locker_color
- value: cobalt

E2 tests extraction after an explicit revision.

Input meaning:

Mira changed her locker color from amber to cobalt.

Expected current proposition:

- entity: Mira
- attribute: locker_color
- value: cobalt

The superseded value must not be extracted as the current value.

### 4.2 Maintenance

M1 tests Add.

Existing memory:

empty

Candidate:

- entity: Mira
- attribute: locker_color
- value: cobalt

Expected operation:

add

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

update

The existing locker-color memory item must be selected as the update target.

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

noop

### 4.3 Answering

A1 tests direct use of current memory.

Current memory states that Mira's locker color is cobalt.

Question:

What color is Mira's locker?

Expected answer:

cobalt

A2 tests resistance to stale information.

The current value is cobalt and amber is explicitly identified as superseded
historical information.

Question:

What color is Mira's locker now?

Expected answer:

cobalt

The model must not answer amber.

### 4.4 End-to-End Interface

One end-to-end fixture verifies extraction, maintenance, memory-state
application, and answering in sequence.

The fixture begins with Mira's locker color as amber, introduces a revision to
cobalt, applies the maintenance decision, and asks for the current locker
color.

Expected final answer:

cobalt

## 5. Execution

The qualification consists of eight logical calls:

- two extraction calls;
- three maintenance calls;
- two answering calls; and
- one end-to-end verification call.

Calls are stateless at the API level.

Required state is supplied explicitly by the qualification program.

Concurrency is one.

Automatic provider fallback is disabled.

## 6. Response Validation

Every structured response must:

1. return successfully;
2. contain parseable JSON;
3. pass the predefined local schema; and
4. conform to the expected operation and target constraints.

Each response is evaluated once.

Semantic repair, corrective reprompting, best-of sampling, and LLM judging are
not used.

Infrastructure retries are permitted only under the configured transport retry
policy.

## 7. Qualification Criteria

The configuration qualifies only if all of the following conditions hold:

- all eight logical calls complete;
- all required structured responses parse successfully;
- all structured responses pass local schema validation;
- E1 and E2 produce the expected current proposition;
- M1 returns Add;
- M2 returns Update with the correct target;
- M3 returns Noop;
- A1 and A2 return the expected current value;
- the end-to-end fixture returns the expected current value;
- the requested model matches the configured model;
- the observed provider is consistent with the pinned provider;
- automatic provider fallback does not occur; and
- input-token and output-token accounting is available for successful
  responses.

There are only two final outcomes:

- QUALIFIED
- NOT_QUALIFIED

No numerical model score is produced.

## 8. Failure Handling

A failed qualification does not authorize repeated changes until a passing
result is obtained.

Any material change to the model, provider, prompts, schemas, generation
parameters, or qualification criteria must be documented before a new
qualification run.

Infrastructure retry behavior follows the frozen transport configuration.

## 9. Recorded Evidence

The qualification records:

- timestamp;
- model identifier;
- requested provider;
- observed provider when available;
- generation parameters;
- logical-call identifier;
- request status;
- parse status;
- schema-validation status;
- deterministic expected-versus-observed result;
- token accounting;
- latency;
- retry information; and
- final qualification outcome.

Secrets are never written to qualification artifacts.
