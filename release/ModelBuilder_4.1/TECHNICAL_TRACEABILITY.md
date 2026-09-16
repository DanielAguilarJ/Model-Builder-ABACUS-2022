# Model Builder 4.1 — technical contract and traceability

**Applicable product:** Model Builder 4.1  
**Parameter schema:** 5  
**Mesh algorithm:** `auto-mesh-1.0`  
**Document revision:** 2026-09-10  

This document defines what Model Builder may claim. It is not a replacement for a licensed standard, an engineering release process, or independent verification of a solved model. The machine-readable companion is `technical_contract.json`.

## Evidence badges

- **NORMATIVE** — an implemented numeric requirement derived from DIN 6885-1:2021-11, used only within its stated range and feature scope.
- **FVA-RESEARCH** — a proposal, setup, or factor from supplied FVA 600 III research material; not a current DIN requirement.
- **LITERATURE** — a published comparison or engineering context value; never an acceptance criterion.
- **CORE-SCREENING** — a fast internal plausibility calculation. The uniform-bearing pressure calculation is not complete DIN 6892 Method B.
- **USER-OVERRIDE** — a user-selected value that is not asserted to be a normative series value.

Badges remain visible in GUI, parameter/audit JSON, human audit and generated report. Successful execution cannot promote research, literature, screening or override data to NORMATIVE.

## Implemented normative data

`keyjoint_core.py` is the single source consumed by GUI and Abaqus engine for the DIN table, derivations, validation rules and evidence metadata. It contains:

- 26 explicit diameter bands for `6 < d1 <= 500 mm`;
- `b`, `h`, `t1`, `t2`, positive `t1` tolerance and `d2_add/d2_ref`;
- the implemented standard key-length series;
- separate `r1` and `r2` ranges;
- exact A, B and AB form semantics.

Values outside the diameter range are rejected; no row is clamped or extrapolated. If no listed standard length fits, Model Builder rejects the selection rather than inventing a fallback. Forms C–J and groove forms N2/N3 remain reference-only because their required geometry and dimensions are not implemented.

The three lengths are intentionally distinct: `key_nominal_length`, `slot_total_length` and `load_bearing_length`. Bearing length is A = `l-b`, B = `l`, AB = `l-b/2`.

## Automatic mesh policy

Schema 5 provides six pre-saved, versioned policies: `AUTO_BALANCED`, `QUALITY_CRITICAL`, `FAST_PREVIEW`, `HEX_DOMINANT`, `QUADRATIC_ACCURACY` and `ROBUST_FALLBACK`. They select among five complete recipes per piece. “Best” means the highest-ranked admissible candidate under `auto-mesh-1.0`; it is not a claim of universally perfect discretisation.

For each Shaft, Key, Hub and optional Bushing candidate, hard gates precede score: elements must exist, Abaqus failed elements must be zero, connectivity must be one component, an expected fillet must be detected, hard element budget must hold and winner regeneration must match declared tolerances. The aggregate uses the worst piece, never an average. Candidate wall-clock time is recorded but does not affect deterministic ranking.

All templates except explicit `QUADRATIC_ACCURACY` inherit the requested element order. Linear profiles are `C3D8|C3D8I|C3D8R + C3D4 fallback`; quadratic profiles are `C3D20 + C3D10 fallback`. `C3D8R` is never selected automatically. Final type histograms are checked against the effective profile. Soft targets such as hexahedral coverage, warning count and bulk aspect ratio affect score but are not universal engineering acceptance criteria.

The winner is regenerated before assembly. Exact signature equality is reported separately from allowed advancing-front equivalence: at most 2% relative nodes/elements, 2 percentage points hex coverage and 5 score points. Outside tolerance is a hard failure.

## User overrides

A permitted override is validated geometrically and retains **USER-OVERRIDE** provenance. Passing validation means only that the implemented model can be built under checked constraints; it does not transform an override into a DIN series value.

## DIN 6892, fatigue and FVA limits

The pressure check is **CORE-SCREENING** and omits required licensed DIN 6892 Method B tables, curves and factors. Neither GUI nor reports may call it complete Method B. DIN 743/FKM fatigue verification remains external.

The FVA content is **FVA-RESEARCH**. The relative opening measure is `v = DeltaV / V_theo`, with research threshold `v_crit = 0.5`. The backend filename retains `v3` as a locked internal revision; product identity remains 4.1/schema 5. Its one-cycle setup is pre-solve/regression, not complete Method A. `strict_no_job` prevents creation or submission of an Abaqus Job. Here NOJOB means no solver Job, not necessarily no physics setup.

## Build, analysis and report boundaries

Three outcomes must be separated:

1. **Core validation passed:** parameter/geometry rules raised no hard error.
2. **Build audit passed:** expected meshes, profiles, reproduction, quality policy, topology and fit gates passed; `BUILD_RESULT.ok` is boolean `true` and audit verdict is `OK`.
3. **Solved analysis accepted:** requires independent job/ODB, step/frame/field, mesh-convergence, equilibrium, contact-path, material and engineering checks.

A process return code, CAE existence or quality score alone is insufficient. A generated LaTeX report reproduces the audit evidence. PDF compilation depends on external `latexmk` or `pdflatex`; absence is recorded and does not change Abaqus build verdict.

## Workspace and provenance requirements

Each normal run creates `project.json` plus `input`, `generated`, `model`, `jobs`, `screenshots`, `reports` and `logs`. Artifact routes are absolute and Abaqus uses `jobs` as working directory.

Each schema-5 audit and `BUILD_RESULT.json` records SHA-256 for the exact Abaqus engine, shared core and input JSON consumed at runtime. The release manifest records a pre-PyInstaller source snapshot, verifies it did not change before publication, and binds that snapshot to the packaged EXE hash. A validation claim should retain product/schema/algorithm, input and contract, audits/result, CAE/screenshots, report status, Abaqus version/log, executable hash and exact test scope.

The packaged `--self-test` checks 4.1/schema 5 identity, six templates, deterministic ranking, effective profile validation, packaged engine/core/defaults/contract resources, DIN table and default validation. It does not start Abaqus, consume a license, build geometry, run a solver or compile LaTeX.

## Abaqus 2022 validation scope

Separate real-CAE NOJOB checks covered D40/Form A/AUTO, D25/Form B/AUTO, D50/Form AB/QUADRATIC_ACCURACY and tapered FAST_PREVIEW with Bushing. The retained audits report zero failed elements, one component per piece, successful winner reproduction and passing hard gates. A density/quality study is not stress convergence evidence. Run-specific CAE and audits are deliberately excluded from the shareable application package.

## Distribution policy

The clean release is assembled only from `release_staging`, never historical `dist`. Its whitelist excludes Abaqus databases/results, solver files, journals/replay, run-specific audits, temporary Python files, source snapshots and loose source. Licensed DIN/FVA PDFs, screenshots of protected pages and standard figures are not bundled.

Users distribute only `release\ModelBuilder_4.1` or `release\ModelBuilder_4.1.zip`. README, this document, machine-readable contract, manifest and checksums are mandatory companions to the EXE.
