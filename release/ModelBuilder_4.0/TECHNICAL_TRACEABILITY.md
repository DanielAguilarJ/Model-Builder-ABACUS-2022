# Model Builder 4.0 — technical contract and traceability

**Applicable product:** Model Builder 4.0  
**Parameter schema:** 4  
**Document revision:** 2026-09-10  

This document defines what Model Builder may claim. It is not a replacement for a licensed standard, an engineering release process, or an independent verification of a solved model. The machine-readable companion is `technical_contract.json`.

## Evidence badges

- **NORMATIVE** — an implemented numeric requirement derived from DIN 6885-1:2021-11, used only within its stated range and feature scope.
- **FVA-RESEARCH** — a proposal, setup, or factor from the supplied 2025 FVA 600 III research material; not a current DIN requirement.
- **LITERATURE** — a published comparison or engineering context value; never an acceptance criterion.
- **CORE-SCREENING** — a fast internal plausibility calculation. In particular, the uniform-bearing pressure calculation is not complete DIN 6892 Method B.
- **USER-OVERRIDE** — a user-selected value that is not asserted to be the normative series value.

Badges must remain visible in the GUI, parameter/audit JSON, human audit, and generated report. A value must not be promoted from research, literature, screening, or override to NORMATIVE by formatting or by successful execution.

## Implemented normative data

For the general parametric workflow, `keyjoint_core.py` is the single source consumed by the GUI and Abaqus engine for the DIN table, derivations, validation rules and evidence metadata. It contains:

- 26 explicit diameter bands for `6 < d1 <= 500 mm`;
- `b`, `h`, `t1`, `t2`, positive `t1` tolerance and `d2_add/d2_ref`;
- the implemented standard key-length series;
- separate `r1` and `r2` ranges;
- exact A, B and AB form semantics.

Values outside the diameter range are rejected. The first/last row is never clamped or extrapolated. If no listed standard length fits, Model Builder rejects the selection rather than inventing a fallback.

Forms A, B and AB are implemented with these distinct lengths:

- `key_nominal_length`: overall nominal DIN key length `l`;
- `slot_total_length`: total generated shaft-slot extent;
- `load_bearing_length`: A = `l-b`, B = `l`, AB = `l-b/2`.

Forms C–J and groove forms N2/N3 remain reference-only because their holes, chamfers, cutter geometry and associated dimensions are not implemented. The application blocks them rather than generating a different form silently.

## User overrides

A permitted override is validated geometrically and retains **USER-OVERRIDE** provenance where applicable. Passing validation means that the implemented model can be built under the checked constraints; it does not transform the override into a DIN series value. Important independent inputs and derived results remain separated in `input\params.json` and the audit.

## DIN 6892 and fatigue limitation

The current analytical pressure check is tagged **CORE-SCREENING**. It uses a uniform-bearing plausibility calculation and does not include a complete licensed DIN 6892 Method B implementation, including all required tables, curves and factors. Neither the GUI nor generated reports may call it “complete DIN 6892 Method B.”

DIN 743/FKM fatigue verification is outside the automatic acceptance scope. Literature stress-concentration factors are comparisons and planning aids, not model-specific acceptance values.

## FVA 600 III limitation

The supplied material is treated as **FVA-RESEARCH**. The relative opening measure is `v = DeltaV / V_theo`, with the supplied research threshold `v_crit = 0.5`.

The packaged FVA preset uses an internal geometry backend whose filename retains `v3` as a locked revision identifier. This does not change the product/schema identity (v4/schema 4). The preset may define contacts, steps, boundary conditions, an amplitude and one load cycle while its strict guard prevents creation or submission of an Abaqus Job. In this context NOJOB means “no solver Job,” not “no physics setup.”

The one-cycle workflow is a pre-solve/regression setup, not complete Method A. The supplied research workflow proposes at least 10 load cycles and its numerical example uses 20.

## Build, analysis and report boundaries

Three outcomes must be distinguished:

1. **Core validation passed:** parameter/geometry rules did not raise a hard error.
2. **Build audit passed:** expected parts were meshed, failed-element/component/fit checks passed, and `BUILD_RESULT.ok` is boolean `true`.
3. **Solved analysis accepted:** requires separate checks of job completion, ODB readability, expected steps/frames/fields, mesh convergence, equilibrium, contact path, material model and engineering criteria. Model Builder does not infer this acceptance from process exit code or CAE existence.

A generated LaTeX report reproduces project and audit evidence. Successful PDF compilation depends on an external `latexmk` or `pdflatex`; missing LaTeX does not change the Abaqus build verdict and must be recorded in `latex_build.log`.

## Workspace and provenance requirements

Each normal GUI run creates a unique project root with `project.json` and these fixed directories:

`input`, `generated`, `model`, `jobs`, `screenshots`, `reports`, `logs`.

Artifact routes passed to Abaqus are absolute. The Abaqus subprocess uses `jobs` as its working directory. A release or validation claim should retain, at minimum:

- product version and parameter schema;
- input JSON and technical contract;
- TXT/JSON build audits and `BUILD_RESULT.json`;
- CAE and generated screenshots;
- report data/TeX and PDF status;
- Abaqus version and run log where the packaged subprocess is used;
- executable hash and release manifest;
- the exact scope of every self-test or manual integration test.

The packaged `--self-test` checks resources, defaults, table size and core derivation/validation. It does not start Abaqus, consume a license, build geometry, run a solver, or compile LaTeX. Those claims require separate evidence.

## Distribution policy

A release may contain derived numeric tables, citations, formulas, examples and these limitations. It must not bundle supplied DIN/FVA PDFs, screenshots of protected pages, or reproduced standard figures without authorization.

The clean release is assembled by whitelist. Abaqus databases/results (`*.cae`, `*.odb`, solver files), journals/replay files, run-specific audits, temporary Python files and loose source files are excluded. Historical files in `dist` are preserved rather than deleted automatically; users distribute `release\ModelBuilder_4.0` or its ZIP.

README, this traceability document, the machine-readable contract, release manifest and checksums are mandatory companions to the EXE, not optional marketing material.