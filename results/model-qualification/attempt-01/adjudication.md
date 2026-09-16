# Model Qualification Attempt 1 adjudication

- Qualification attempt: 1
- Result: `NOT_QUALIFIED`
- Backbone: `meta-llama/llama-3.1-8b-instruct`
- Provider endpoint: `coreweave/bf16`
- Source implementation commit: `8410385` (also the repository HEAD at adjudication)
- Evidence: archived `qualification.json` in this directory
- Archived artifact SHA-256: `bcf0854fe0ba03250fe85eb696f3a067e13d231a898ba0174f39c31ec0c44e62`

The official `results/model-qualification/qualification.json` was copied verbatim
before prompt modification. The archive was created exclusively (refusing to
overwrite an existing file), and its bytes were checked against the source.
Preserve this archive permanently; later attempts must never overwrite it.
The qualification program's output path remains outside `attempt-01/`.

## Observed failures

- **E1:** Input `Mira's locker is cobalt.` produced `{"memories":[]}`.
  JSON parsing passed; schema validation failed because exactly one `MemoryItem`
  is required. Deterministic evaluation was not run for this invalid response.
- **M2:** Active memory `mem-1` held `Mira / locker_color / amber`; the candidate
  was `Mira / locker_color / cobalt`. The observed decision was
  `{"operation":"noop","target_id":null}` (whitespace omitted here only).
  Parsing and schema validation passed, but deterministic evaluation failed:
  the unchanged contract requires `{"operation":"update","target_id":"mem-1"}`.
- **E2E-M:** The same active memory and changed-value candidate again produced
  `{"operation":"noop","target_id":null}` (whitespace omitted here only).
  Parsing and schema validation passed, but deterministic evaluation failed.
  No local update was applied; active memory remained amber and E2E-A was
  blocked without a model call. The final result was `NOT_QUALIFIED`.

All nine successful logical responses passed routing/provider verification and
usage accounting. Their routing metadata identifies selected CoreWeave, and
prompt/completion token counts are present. This identifies the provider; it
does not establish an independently observed BF16 endpoint variant.
Infrastructure retries occurred only for retryable HTTP 429 responses: M1 and
A1 each retried once and then returned HTTP 200. There were eleven physical
attempts for nine executed logical calls, with E2E-A blocked within the fixed
ten-call qualification definition. A1 and A2 satisfied the answering contract.

## One material prompt revision before any further attempt

The extraction instruction will explicitly require retaining an explicitly
stated current fact, exactly one current item for these calls, and only the new
value when an old value is superseded. The maintenance instruction will state
an explicit entity-attribute matching and value-comparison procedure: no match
means add, a matched pair with a different value means update of the matching
ID, and a matched pair with the same value means noop. Pair existence alone
will explicitly be insufficient for noop. Both remain generic and vendor-neutral,
without fixture identities, values, or expected decisions. The answering prompt
is unchanged.

This is a material instruction clarification in response to observed omissions
and incorrect changed-value decisions, documented before any further attempt.
The evidence does not establish that prompt wording caused the failures or that
this revision will resolve them. It does not justify changing fixture truth or
expected outputs, or optimizing any research policy outcome.

Schemas, fixtures, expected outputs, normalization, evaluation, local state
application, ten logical IDs, response format, parsing, routing verification,
accounting, model/provider configuration, generation parameters, retry policy,
and all acceptance criteria remain unchanged. All criteria must still pass in
any later authorized attempt. No repair, reprompt, judging, selection, or extra
qualification calls are introduced.

This record is pre-experimental technical qualification evidence, not an
experimental research result. This adjudication and revision are offline only;
Attempt 2 is not executed or authorized by this work.
