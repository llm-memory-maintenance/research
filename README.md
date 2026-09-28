# LLM Memory Maintenance

Research repository for evaluating external conversational memory-maintenance
policies under repeated information revisions in multi-turn interactions with
large language models.

The study compares three maintenance policies:

- M1: Add only
- M2: Add + Update
- M3: Add + Update + Noop

B0 Recent Window has no persistent memory and receives a fixed-budget recent
portion of the raw conversation. It serves as a nonpersistent positive control
and is analyzed separately from M1–M3.

The policies are evaluated under controlled levels of revision intensity with
respect to effectiveness and resource efficiency. The experimental design uses
the Controlled Revision Stress Test (CRST), a synthetic dataset with Low, Medium
and High revision intensity (1, 4 and 7 target revisions), and the LongMemEval-S
Knowledge Update subset (N = 56) for external validation. The backbone is
`meta-llama/llama-3.1-8b-instruct` via OpenRouter on the `coreweave/bf16`
endpoint.

Prior work on long-term conversational memory provides the broader empirical
foundation for the study. Hu et al. (2026) serves as the closest methodological
reference for the controlled comparison of memory-maintenance operations.

## Repository layout

- `docs/`: research design, specifications, and the dated decision log
  (`docs/decisions.md`).
- `configs/`: frozen configurations and implementation freeze records.
- `data/`: fixtures, calibration material, and LongMemEval-S audit artifacts
  (see `data/README.md`).
- `experiments/`: builders, validators, and runners for each stage.
- `results/`: archived evidence from each attempt.
- `tests/`: offline tests, run with `uv run pytest`.

## Status

The following stages are closed, as recorded in `docs/decisions.md`:

- Model Qualification of the backbone (2026-09-16).
- Retrieval and context calibration (2026-09-17).
- Generator Qualification under Protocol v2 (2026-09-19), with G1
  `openai/gpt-5.6-sol` and G2 `anthropic/claude-fable-5.1`.
- B0 calibration (2026-09-19), with `B0_CONTEXT_TOKENS = 71`.
- CRST Small Pilot (2026-09-20).

Still open are the naturalization failure policy for the final CRST, the
generator assignment mechanism and seed, the statistical planning of the main
experiment, and final CRST generation.
