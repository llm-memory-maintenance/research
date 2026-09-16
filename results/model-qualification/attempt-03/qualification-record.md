# Model Qualification Attempt 3 record

- Qualification attempt: 3
- Result: `QUALIFIED`; Model Qualification is CLOSED.
- Qualification checkpoint: repository commit `fc45fd6`
- Permanent artifact: [qualification.json](qualification.json)
- Artifact SHA-256: `125250b9501a3c64333e063d395ecc182036ca91529084b7045b050e1da3161b`

## Frozen execution configuration

| Setting | Value |
| --- | --- |
| Backbone | `meta-llama/llama-3.1-8b-instruct` |
| Gateway | OpenRouter |
| Requested provider endpoint | `coreweave/bf16` |
| `allow_fallbacks` | `false` |
| `require_parameters` | `true` |
| `temperature` | `0.0` |
| `top_p` | `1.0` |
| `max_output_tokens` | `2048` |
| `timeout_seconds` | `180` |
| Maximum infrastructure retries | `2` |
| Retry backoff | 1 s, 2 s |
| Retryable HTTP statuses | 408, 429, 500, 502, 503, 504 |

## Qualification evidence

All ten logical calls executed and passed request completion, JSON parsing,
local schema validation, deterministic evaluation, routing verification, and
usage accounting.

- E1 and E2 produced the required canonical extraction:
  `Mira / locker_color / cobalt`.
- M1 produced Add with a null target; M2 produced Update targeting `mem-1`;
  M3 produced Noop with a null target.
- A1 and A2 passed with `cobalt`.
- E2E-E passed with the required canonical extraction; E2E-M produced Update
  targeting `mem-1`. Local state application succeeded. E2E-A executed and
  passed with `cobalt`.
- Final active memory contained `mem-1 = Mira / locker_color / cobalt`, the
  current value.
- All ten physical attempts returned HTTP 200. No infrastructure retry occurred.
- The final artifact status was `QUALIFIED`.

Requests explicitly pinned `coreweave/bf16` with fallback disabled and required
parameters enabled. OpenRouter metadata identified CoreWeave as the selected
provider. The returned metadata did not independently expose or verify the
`bf16` suffix or precision variant.

## Provenance and closure

Attempt 1 was `NOT_QUALIFIED` and is permanently archived under
[attempt-01/](../attempt-01/qualification.json), with its
[adjudication](../attempt-01/adjudication.md). Attempt 2 was `NOT_QUALIFIED` and
is permanently archived under [attempt-02/](../attempt-02/qualification.json),
with its [adjudication](../attempt-02/adjudication.md). Prompt revisions between
attempts were documented before reruns. Fixtures, expected outputs, and
acceptance criteria were not weakened between attempts.

This is pre-experimental technical qualification evidence, not a thesis
main-experiment result. Official Attempt 3 is sufficient to freeze the exact
execution configuration and qualification checkpoint above for subsequent
calibration/pilot work unless a later documented technical reason requires
reopening qualification.

This closure record was prepared offline without inference or a qualification
rerun. The archived artifact checksum was verified, and the root mutable
artifact was verified byte-identical and retained. Attempt 1 and Attempt 2
archives were unchanged. Future work must preserve these permanent archives.
