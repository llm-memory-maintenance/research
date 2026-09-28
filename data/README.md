# Data

This directory contains research data and reproducibility artifacts used by the
experiments.

## LongMemEval

`longmemeval/raw/` contains the local copy of the source dataset. Raw
third-party data is excluded from version control.

`longmemeval/audit/` contains the frozen audit artifacts used to define the
Knowledge Update validation subset.

Derived datasets are reproducible from the source dataset and the tracked
selection metadata in `longmemeval/audit/`. Generated copies are not
committed unless they are required for reproducibility and cannot be
reconstructed deterministically.

## Retrieval calibration material

`retrieval-calibration/` holds the 140-case synthetic retrieval calibration
corpus (`calibration.json`) and its schema (`schema.json`).

## Generator qualification and B0 calibration material

`generator-qualification/` holds the 12 qualification-only fixtures.
`b0-calibration/` holds 12 calibration-only structured scenarios for the B0 Recent
Window calibration. The two sets, final confirmatory CRST cases, Model
Qualification fixtures, and LongMemEval-S material are kept separate, and neither
set is used for any other purpose. The B0 manifest records this prohibition and
reserves its identifiers and values for exclusion from later final-CRST
construction.

`generator-capability-probe/` holds the probe-only naturalization input
(`probe-input.json`).

## CRST Small Pilot material

`crst-small-pilot/` holds two pilot-only structured scenarios (`pilot-scheduling-01`,
`pilot-travel-01`) for the CRST Small Pilot (`configs/crst-small-pilot.yaml`).
They are separate from every set above, from final confirmatory CRST cases, and
from LongMemEval-S, and are not reused as any of them.
`experiments/build_crst_pilot_material.py --check` reproduces them.
