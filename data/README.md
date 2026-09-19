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

## Generator Qualification and B0 calibration material

`generator-qualification/` holds the 12 qualification-only fixtures.
`b0-calibration/` holds 12 calibration-only structured scenarios for the B0 Recent
Window calibration. The two sets, final confirmatory CRST cases, Model
Qualification fixtures, and LongMemEval-S material are separate, and neither set
may be reused as another. The B0 manifest records this prohibition and reserves its
identifiers and values for exclusion from later final-CRST construction.
