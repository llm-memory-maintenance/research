# LLM Memory Maintenance

Research repository for evaluating external conversational memory-maintenance
policies under repeated information revisions in multi-turn interactions with
large language models.

The study compares three maintenance policies:

- Add only
- Add + Update
- Add + Update + Noop

The policies are evaluated under controlled levels of revision intensity with
respect to effectiveness and resource efficiency. The experimental design uses
a controlled synthetic dataset and a Knowledge Update subset of LongMemEval-S
for external validation.

Prior work on long-term conversational memory provides the broader empirical
foundation for the study. Hu et al. (2026) serves as the closest methodological
reference for the controlled comparison of memory-maintenance operations.
