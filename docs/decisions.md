# Research Decisions

## 2026-09-16 — Experimental Backbone

The experimental backbone is `meta-llama/llama-3.1-8b-instruct`.

The model is selected for methodological comparability with Hu et al. (2026),
which uses LLaMA-3.1-8B for memory extraction and answer generation in its
default experimental setting.

The language model is not an experimental factor in this study. The backbone
is selected before any comparative M1, M2, or M3 experiment is executed.

## 2026-09-16 — Upstream Provider

The planned OpenRouter endpoint is `coreweave/bf16`.

The provider was selected before model qualification using the following
priority order:

1. technical compatibility;
2. model fidelity;
3. service reliability;
4. operational efficiency;
5. cost.

At the time of inspection, the endpoint exposed BF16 quantization, a
131072-token context window, support for the required generation parameters,
structured-output support, high observed availability, and low observed
latency.

Automatic provider fallback is disabled for experimental execution.

The provider and request configuration must pass technical qualification before
the configuration is frozen for the main experiment.
