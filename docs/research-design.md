# Research Design

## 1. Research Scope

This study evaluates external conversational memory-maintenance policies for
large language models under repeated information revisions.

The study does not introduce a new memory architecture and does not modify or
fine-tune the language model. The experimental software serves as research
infrastructure for applying memory policies, controlling experimental
conditions, recording measurements, and evaluating outcomes.

The primary object of study is the memory-maintenance policy rather than the
language model itself.

## 2. Research Questions

The study addresses three research questions:

1. How do Add-only, Add+Update, and Add+Update+Noop memory-maintenance
   policies differ in their effectiveness at preserving current information?

2. How do effectiveness differences among the three policies change as the
   revision intensity of the target information increases?

3. What trade-offs arise between effectiveness and resource efficiency for
   each memory-maintenance policy?

## 3. Scientific Positioning

Prior work on long-term conversational memory establishes that systems may
struggle not only to retrieve previously observed information, but also to
identify which information remains valid after updates.

LongMemEval provides the external basis for evaluating Knowledge Updates,
while LoCoMo, RealMem, Memora, Memory-R1, APEX-MEM, and related work provide
broader evidence on long-term memory, evolving information, stale information,
and alternative memory-management approaches.

Hu et al. (2026) is the closest methodological reference for the present study.
Their framework separates memory extraction, indexing, retrieval, and
answering, and analyzes memory-maintenance operations including Add, Update,
and Noop.

The present study extends this line of investigation by separating the
incremental contribution of the maintenance operations:

- M1: Add only
- M2: Add + Update
- M3: Add + Update + Noop

The M1–M2 comparison isolates the addition of Update, while the M2–M3
comparison isolates the addition of Noop. These comparisons are additionally
evaluated under controlled levels of repeated information revision.

The study is therefore not a replication of Hu et al. and does not attempt to
reproduce their complete memory architecture.

## 4. Experimental Design

The main experiment uses a controlled factorial design with two experimental
factors:

### 4.1 Memory-maintenance policy

- M1 — Add only
- M2 — Add + Update
- M3 — Add + Update + Noop

A Recent Window condition, denoted B0, is used as a separate non-persistent
comparison condition. B0 is not treated as a fourth level of the main policy
factor.

### 4.2 Revision intensity

Revision intensity refers to the number of explicit revisions applied to the
target information:

- Low: 1 target revision
- Medium: 4 target revisions
- High: 7 target revisions

The same underlying scenario is used across policy and revision-intensity
conditions so that comparisons are made over equivalent information.

## 5. Controlled Revision Stress Test

The Controlled Revision Stress Test (CRST) is the primary experimental
dataset.

Each base scenario contains seven initial information units:

- one target information unit;
- six secondary information units.

The initial information sequence I1–I7 establishes the same starting memory
state for all persistent-memory policies.

Each CRST variant contains:

- seven update events, U1–U7;
- two Noop opportunities, N1 and N2;
- one final query.

U7 is always the final update to the target information.

Target revisions are positioned as follows:

- Low: U7
- Medium: U1, U3, U5, U7
- High: U1, U2, U3, U4, U5, U6, U7

Update positions that are not assigned to the target contain secondary
information updates.

N1 occurs after U6 and before U7 and reaffirms the target state.

N2 occurs after U7 and before the final query and reaffirms secondary
information.

Target values do not return to a previously superseded value.

The dataset spans 12 scenario domains. Domain is used to diversify scenarios
and is not treated as a primary experimental factor.

Validation of the final CRST dataset is required before the confirmatory
experiment is executed.

## 6. External Validation

External validation uses the Knowledge Update subset of LongMemEval-S.

The source dataset contains 500 instances. The thesis audit identified 72
non-abstention Knowledge Update candidates. Following deterministic checks and
human adjudication, 56 instances were retained and 16 were excluded.

The usable validation set is therefore fixed at:

N = 56

The raw source dataset is excluded from version control. Audit metadata and the
frozen usable-instance identifiers are retained in:

`data/longmemeval/audit/`

LongMemEval-S is used as external validation and does not determine the CRST
revision-intensity design.

## 7. Language Model Backbone

The main experiment uses one fixed language model configuration.

Cross-model performance comparison is outside the scope of the study.

The reference backbone is:

`meta-llama/llama-3.1-8b-instruct`

This model is selected for methodological comparability with the LLaMA-3.1-8B
backbone setting reported by Hu et al. (2026), the closest prior work to the
maintenance-operation comparison investigated in this study.

The selection is made before the main M1–M3 experiment and is not based on
observed treatment effects.

Before the experimental configuration was frozen, the selected model passed a
technical qualification (Model Qualification official Attempt 3; see
[model-qualification.md](model-qualification.md) and [decisions.md](decisions.md))
confirming that it can reliably support the required research procedure,
including:

- memory extraction;
- structured maintenance decisions;
- Add, Update, and Noop operations where applicable;
- final answering;
- structured-response parsing;
- required API accounting and metadata.

Technical qualification is not a model benchmark or model-selection
competition.

## 8. Execution Principles

One fixed model configuration is used across experimental conditions wherever
the model is involved.

The experiment follows these principles:

- API calls are stateless with respect to provider-side conversation history;
- all required context is constructed explicitly by the experimental software;
- automatic model fallback is disabled during the main experiment;
- model, provider, inference parameters, prompts, and schemas are fixed before
  confirmatory execution;
- persistent-memory policies receive the same initial information;
- no future information may enter extraction, maintenance, or retrieval;
- failed infrastructure attempts are recorded separately from valid model
  behavior.

OpenRouter is the API gateway. The upstream provider endpoint is
`coreweave/bf16`, and the model configuration fixed by Model Qualification is
recorded in `configs/model.yaml`.

## 9. Memory and Retrieval Conditions

### 9.1 CRST

CRST answering uses the complete active memory state. Dense retrieval is not
used for the main CRST conditions.

Persistent-memory answering does not additionally receive the raw conversation
history.

### 9.2 LongMemEval-S

LongMemEval-S uses retrieval because the conversation histories are
substantially longer.

Candidate memory extraction is performed chronologically and shared across M1,
M2, and M3 so that policy comparisons do not differ because of independently
generated extraction inputs.

Retrieval uses `facebook/contriever` with `K_MAINT = 3`, `K_ANSWER = 5` and
`LME_RETRIEVAL_CONTEXT_TOKENS = 512`, fixed by the retrieval calibration
([retrieval-context-calibration.md](retrieval-context-calibration.md) and
`configs/retrieval-qualified.yaml`).

## 10. Effectiveness Measures

The primary CRST effectiveness measures are:

### Current-State Accuracy

Current-State Accuracy (CSA) measures whether the final answer uses the
information that remains valid at query time.

### Stale Reliance Rate

Stale Reliance Rate (SRR) measures whether the answer relies on information
that was previously valid but has since been superseded.

Maintenance Operation Accuracy (MOA) is used as a diagnostic measure for M2
and M3. It is not a primary effectiveness outcome.

Target-selection correctness for Update operations is recorded separately when
applicable.

LongMemEval-S uses its benchmark-compatible question-answering evaluation.
CSA and SRR are not imposed on LongMemEval-S.

## 11. Efficiency Measures

Resource efficiency is evaluated using:

- LLM token usage;
- active-memory size;
- logical API-call count;
- end-to-end execution time.

API latency is recorded as a diagnostic measure.

Monetary API cost may be reported descriptively but is not a primary
effectiveness-efficiency dimension.

Efficiency is evaluated across the memory lifecycle rather than only during
final answering.

## 12. Analysis Overview

CRST effectiveness is analyzed using a repeated factorial structure with:

- memory-maintenance policy;
- revision intensity;
- their interaction.

The principal policy contrasts are:

- M2 versus M1;
- M3 versus M2.

The interaction analysis evaluates whether policy differences change across
revision-intensity levels.

CSA and SRR are analyzed separately.

Efficiency measures are analyzed alongside effectiveness outcomes to evaluate
trade-offs rather than being collapsed into a single composite score.

LongMemEval-S is analyzed as a paired external-validation dataset because the
same usable instances are evaluated under each memory policy.

Exact statistical-model structure, confidence-interval procedures, bootstrap
settings, and final sample-size parameters are fixed before confirmatory
analysis.

## 13. Reproducibility

The final experimental configuration will record at least:

- model identifier;
- upstream provider;
- inference parameters;
- prompt versions;
- output schemas;
- retry and timeout policy;
- software environment;
- dataset hashes;
- CRST dataset version;
- LongMemEval-S usable-instance identifiers;
- retrieval configuration;
- random seeds where applicable.

Experimental results have to be reproducible from versioned configuration and
tracked research artifacts without depending on provider-side chat state.

## 14. Open Decisions

The following items remain unresolved and have to be fixed before the main
experiment:

- final prompt and schema definitions;
- CRST sample size;
- technical repetition count;
- naturalization failure policy for the final CRST, covering both non-evaluable
  and Level-1 failures;
- exact statistical random-effects structure;
- final confidence-interval and bootstrap procedures;
- final software environment.

The backbone provider, inference parameters, retry and timeout configuration,
naturalization generators, embedding model, retrieval depths, retrieval context
budget, B0 context budget and reader tokenizer were fixed earlier and are
recorded in [decisions.md](decisions.md).

The open decisions have to be finalized before comparative M1–M3 results are
inspected.
