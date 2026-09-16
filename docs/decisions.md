# Research Decisions

## 2026-09-16 — Reference language model

The planned experimental backbone is
`meta-llama/llama-3.1-8b-instruct`.

The model is selected for methodological comparability with Hu et al. (2026),
which uses LLaMA-3.1-8B for both memory extraction and answer generation in its
default experimental setting.

The language model is not an experimental factor in this study. The selection
is fixed before any comparative M1, M2, or M3 experiment is executed.

## 2026-09-16 — Upstream provider

The planned OpenRouter endpoint is `coreweave/bf16`.

The endpoint was selected before model qualification using the following
priority order:

1. technical compatibility;
2. model fidelity;
3. service reliability;
4. operational efficiency;
5. cost.

At the time of selection, the endpoint exposed BF16 quantization, a 131072-token
context window, structured-output support, complete support for the required
generation parameters, the strongest observed short-term availability among
the eligible endpoints, and the lowest observed median latency.

Automatic provider fallback is disabled for experimental execution.

Provider availability and request compatibility must still be confirmed during
technical qualification.
