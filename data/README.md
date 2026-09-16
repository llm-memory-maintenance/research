# Data

This directory contains research data and reproducibility artifacts used by the
experiments.

## LongMemEval

`longmemeval/raw/` contains the local copy of the source dataset. Raw
third-party data is excluded from version control.

`longmemeval/audit/` contains the frozen audit artifacts used to define the
Knowledge Update validation subset.

Derived datasets should be reproducible from the source dataset and tracked
selection metadata. Generated copies are not committed unless they are required
for reproducibility and cannot be reconstructed deterministically.
