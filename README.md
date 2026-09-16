# Model Builder 4.2

Model Builder automates traceable shaft–hub–parallel-key models for Abaqus/CAE. Version 4.2 uses parameter schema 6, adds explicit DIN 6892/FVA 600 III calculation workflows, imports external Method-A opening-volume evidence, and reports **requested**, **derived**, and **realized in CAE** states separately.

> **Engineering boundary:** a successful build verifies the implemented automation contract; it is not certification of a joint. `DIN-METHOD` identifies an implemented equation workflow, not regulatory approval. `FVA-RESEARCH` identifies supplied research data/proposals. Licensed diagram/table factors remain `USER-INPUT`. The legacy FVA backend is `LEGACY_PARTIAL`, `MATCHING NOT_VERIFIED`, and never runs a solver.

## Idioma / Language / Sprache

**ES.** La interfaz, validaciones y el informe ofrecen **Español**, **English** y **Deutsch**; español es el idioma predeterminado. `project.language` conserva la selección. Los identificadores JSON, métodos, códigos, badges y nombres DIN/FVA permanecen canónicos.

**EN.** The GUI, validation messages, and report provide **Español**, **English**, and **Deutsch**; Spanish is the default. `project.language` persists the selection. JSON identifiers, methods, codes, badges, and DIN/FVA names remain canonical.

**DE.** Oberfläche, Validierungsmeldungen und Bericht stehen auf **Español**, **English** und **Deutsch** bereit; Spanisch ist die Standardsprache. `project.language` speichert die Auswahl. JSON-Bezeichner, Verfahren, Codes, Badges und DIN-/FVA-Namen bleiben kanonisch.

The catalogs under `i18n/` have exact key and placeholder parity. Runtime fallback is `requested locale → es → en`.

## Release identity

- Product: **Model Builder 4.2**
- Parameter schema: **6**
- Accepted input schemas: **5 and 6**; schema 5 is explicitly migrated before defaults are merged
- Future schemas: rejected
- Mesh algorithm: **`auto-mesh-1.0`**
- Platform: Windows
- Abaqus compatibility target: **Abaqus 2022 / Python 2.7**
- New shareable target: `release\ModelBuilder_4.2\` or `release\ModelBuilder_4.2.zip`
- Protected historical artifacts: `release\ModelBuilder_4.1*` are immutable and are not launch/build targets for 4.2

The 4.2 release builder records every protected 4.1 file (path, size, SHA-256) before packaging and verifies the same snapshot before and after publication. It can clean only `release\ModelBuilder_4.2`; any other output path is rejected.

## Requirements

Packaged users need Windows, a local licensed Abaqus/CAE installation, write access to the selected project base, and optionally `latexmk` or `pdflatex`. The EXE does not bundle Abaqus, a license, LaTeX, licensed standards, or protected FVA/DIN documents. Running from source requires Python 3.9+ with Tkinter.

## Quick start

1. Extract `ModelBuilder_4.2.zip`; do not run from inside the ZIP.
2. Start `ModelBuilder.exe` and select Español, English, or Deutsch.
3. In **1 Project**, set project/model identity, output location, and Abaqus launcher.
4. In **2 DIN geometry**, choose implemented form A, B, or AB and review derived dimensions.
5. In **3 Mesh and materials** and **4 Analysis**, configure discretization and optional generic analysis. Leave submission disabled unless an independently reviewed solve is intended.
6. In **5 DIN 6892 / FVA**, choose method, FVA variant/material, factors, standards, external Method-A evidence, and—only when appropriate—the legacy one-cycle NOJOB backend.
7. Press **Validate**. Unsupported combinations remain visible and are blocked; they are never coerced to VB1/C45/one cycle.
8. In **6 Run and evidence**, generate the isolated project and review `BUILD_RESULT.json`, audits, model, screenshots, and report. A zero process return code alone is not proof of success.

Keep project workspaces outside the application directory. The default is `Documents\ModelBuilder Projects`.

## Schema 6 and geometry semantics

`keyjoint_core.py` is the shared source for schema migration, DIN 6885 geometry, derivations, validation, mesh policy, evidence metadata, and the requested/derived/realized record.

Canonical schema-6 geometry keys are:

- `shaft.diameter_mm = d_w`
- `hub.QA_shaft_over_outer = d_w / D_outer`

Deprecated `shaft.D`, `hub.hub_outer_over_shaft`, and old `hub.QA` remain synchronized compatibility aliases with recorded provenance. Conflicting canonical/alias values are rejected rather than silently selected.

DIN 6885-1 support is limited to 26 explicit bands for `6 < d1 <= 500 mm`, forms A/B/AB, groove N1, listed key lengths, and implemented `b`, `h`, `t1`, `t2`, `d2_ref`, `r1`, and `r2` data. Forms C–J and N2/N3 remain blocked. DIN 6888 is visible but its Woodruff-key solid backend is not implemented.

Three lengths remain distinct:

| Quantity | Meaning |
|---|---|
| `key_nominal_length` | overall nominal key length `l` |
| `slot_total_length` | total generated shaft-slot extent |
| `load_bearing_length = l_tr` | bearing length used by DIN/FVA calculations |

For forms A/B/AB, `l_tr` is respectively `l-b`, `l`, and `l-b/2`.

## Evidence badges

- **NORMATIVE** — implemented DIN 6885-1 data within declared scope.
- **DIN-METHOD** — implemented DIN 6892 equation workflow; not certification.
- **FVA-RESEARCH** — data or proposal from supplied FVA 600 III research.
- **USER-INPUT** — factor/result requiring a licensed source, test, certificate, or engineering decision.
- **NOT-IMPLEMENTED** — visible reference with no claimed executable procedure.
- **CORE-SCREENING** — internal plausibility check, separate from DIN 6892 Method B.
- **LITERATURE** — comparison/context only.
- **USER-OVERRIDE** — explicit non-series user value.

## DIN 6892 methods and allowable torque

The single pure-Python 2.7/3 engine is `din6892_methods.py`. Every method returns source, equations, badge, limitations, `M_t,zul`, and `M_t,design = M_t,zul / safety_factor` when calculable.

### Method A — `A_FE_VOLUME`

Method A consumes external permanent-opening evidence; Model Builder does not claim to solve the source ODB.

- `V_theo = l_tr · t1tr · (U_PF / 1000)` in mm³ when `U_PF` is in µm.
- `v = ΔV / V_theo`.
- Research criterion: `v <= v_crit`, default `v_crit = 0.5`.
- Conclusive evidence requires at least 10 cycles, an identified step/frame, explicit confirmation that the frame is unloaded, and unchanged `l_tr`, `t1tr`, and `U_PF`.
- `M_t,zul` is obtained only from sufficient bracketing trials around `v_crit`; otherwise status remains `EXTERNAL_RESULT_REQUIRED` or `NEEDS_BRACKETING_TRIALS`.

The CSV columns are exactly `x_mm,z_mm,opening_um`. The importer accepts a finite, non-negative rectangular grid, integrates each cell by its four-corner mean, records area/coverage and SHA-256, and persists the result without copying the external source into a release.

### Current Method B — `B_DIN_CURRENT`

Implemented chain:

```text
p_zul    = f_S · f_H · Re
f_W      = min(1, 2 · N_W^(-0.1))
K_V      = 1 / (i · phi)
M_t,zul  = f_W · p_zul · d_w · l_tr · t1tr
           / (2 · K_V · K_lambda · K_R · 1000)
```

`K_lambda`, `K_R`, `f_H`, `f_S`, and `phi` remain explicit `USER-INPUT` values whenever their licensed tables/diagrams or external verification are unavailable.

### FVA proposed Method B — `B_FVA_2025`

This research diagnostic implements the FVA 600 III proposal, not a published DIN revision:

```text
f_Sv     = 0.74 · v + 0.63
f_WS     = Rm / Re
f_S,ltr  = -0.17 · (l_tr / d_w) + 0.16
f_S,ges  = f_WS + f_S,ltr
K_d      = 2.08 · d_w^(-0.18)  for d_w <= 100 mm; otherwise 0.82
M_t,zul  = f_Sv · f_S,ges · f_H · f_W · Re · d_w · l_tr · t1tr
           / (2 · K_R · K_lambda · K_d · K_V · 1000)
```

### Preliminary Method C — `C_PRELIMINARY`

```text
p_zul    = 0.9 · Re_min
M_t,zul  = p_zul · (h - t1) · l_tr · (d_w / 2) · i · phi / 1000
```

Method C is preliminary sizing; applicable Method A/B and DIN 743 verification remain separate.

## FVA variants and material catalog

VB1–VB8 are discrete research configurations, not an interpolated domain:

- VB1: D40 baseline; VB2/VB3: D20/D60.
- VB4: shorter `l_tr/d_w`; VB5: changed `Q_A = d_w/D_outer`.
- VB6: shaft–hub interference `xi`; VB7: form B; VB8: reversed loading `R = -1`.

Cataloged material pairs are C45+N/C45+N and 42CrMoS4+QT/42CrMoS4+QT, with C45+QT key data. Properties exist only at 20, 40, and 60 mm; no interpolation is performed. Higher-strength formulas therefore use the selected discrete `Re`, `Rm`, cyclic parameters, and hardness-derived report data with `FVA-RESEARCH` provenance.

`U_PF` (key–keyway permanent opening) and `xi` (shaft–hub diametral interference) are separate quantities and are never substituted for one another.

## Standards registry and actual support

| Standard | Role | Actual support |
|---|---|---|
| DIN 6885-1:2021 | parallel-key geometry | implemented numeric scope |
| DIN 6892 | load capacity | A/B/C equation workflows; external factors remain inputs |
| DIN 743 | shaft fatigue | external result required |
| DIN EN ISO 286 | fits | user input; complete tables not bundled |
| DIN EN ISO 18265 | hardness conversion | report/FVA data only |
| DIN 7190-1 | frictional closure | user-supplied `M_Rmin`/`K_R` |
| DIN 6880 | key material | reference only |
| DIN 6888 | Woodruff keys | visible but not implemented; selection blocks generation |

## CAE realization boundaries

Two CAE backends are intentionally distinct; neither upgrades a prepared model to a validated solution.

| Backend / companion preset | Prepared scope | Build-time evidence | Job / solver with the companion preset | Claim allowed before a solve |
|---|---|---|---|---|
| `d40_v3_refined_hex_nojob` / `params_fva600_research_presolve_1lw.json` | Adapted conical D40 V3, VB1/C45, exactly 1 LW | Historical pre-solve audit; matching to the exact FVA specimen is `NOT_VERIFIED` | Never creates or submits a Job | `LEGACY_PARTIAL` one-cycle regression only |
| `method_a_connected_mesh_v1` / `params_fva600_method_a_20lw_nojob.json` | Parametric cylindrical Method-A setup, VB1, C45, 20 LW, constitutive models and five matching interfaces | Actual assembly-node comparison is executed only during an Abaqus build | `strict_no_job=true`, generic analysis disabled, `create_job=false`, `submit_solver=false` | Connected model prepared; Method A remains incomplete |

The connected backend is capable of creating and submitting a Job only when a different, independently reviewed request explicitly enables both operations. That capability is not exercised by either bundled companion preset and is not release-validation evidence.

For the connected preset, matching is `VERIFY_AT_BUILD`, not a source-code or self-test result. Four key-flank interfaces are compared in their tangential coordinates and the shaft–hub interface in 3D. The requested tolerance is `1e-6 mm`; Abaqus 2022 coordinate reprojection imposes a documented `5e-5 mm` kernel floor, so the effective check is `max(requested, 5e-5 mm)`. Equal nominal seed sizes are never accepted as proof. No connected-backend `FVA_METHOD_A_SETUP.json` runtime artifact is bundled or claimed by this release.

`fva600_odb_extract.py` opens an existing ODB read-only and writes CSV/JSON evidence; it does not solve. Its default negative-opening policy is recorded as `CLAMP_TO_ZERO`. Final-frame position/time checks are necessary but not sufficient: conclusive evidence requires the caller to confirm explicitly that the selected frame is unloaded. The CSV-only importer rejects negative openings and independently retains source size and SHA-256.

Requested calculation, derived values, realized backend capability, and external result evidence are recorded independently. The release self-test validates schemas, formulas, preset invariants and pure postprocessing only. A solved Method-A claim additionally requires an independently accepted ODB, at least 10 evaluated cycles, a confirmed unloaded frame, opening-volume evidence, convergence, equilibrium, contact-path, material and DIN 743 review.

## Automatic mesh policy

Six versioned templates are available: `AUTO_BALANCED`, `QUALITY_CRITICAL`, `FAST_PREVIEW`, `HEX_DOMINANT`, `QUADRATIC_ACCURACY`, and `ROBUST_FALLBACK`.

- Hard gates precede score: non-empty mesh, zero failed elements, one component, expected fillet, hard budget, and reproducible winner.
- Global quality is the worst piece, never an average.
- Ranking is deterministic; wall-clock time is audit-only.
- `C3D8R` is never auto-selected.
- The winner is regenerated before assembly; exact equality and advancing-front tolerance are separate records.
- A density/quality study is not stress-convergence evidence.

## Project and report evidence

Each GUI run creates `project.json` and separate `input`, `generated`, `model`, `jobs`, `screenshots`, `reports`, and `logs` directories. Abaqus uses `jobs` as working directory. Schema-6 audits retain SHA-256 for the exact engine, core, and parameter JSON consumed at runtime.

`report_generator.py` is the only runtime LaTeX source. Reports are localized and contain DIN/FVA requested/derived/realized rows, selected standards with support levels, validation codes, mesh evidence, provenance, limitations, and screenshots. `report_template.tex` is only an ownership marker. Missing LaTeX leaves a usable `report.tex`, `report_data.json`, and localized log.

A successful geometry/mesh run requires all of: process return code zero; `BUILD_RESULT.ok == true`; audit verdict `OK`; expected model/screenshots; plausible topology/fit/mesh evidence; and no hard validation error. A solved analysis additionally requires independent ODB, convergence, equilibrium, contact-path, material, and engineering checks.

## Validation status and historical evidence

Model Builder 4.2 source checks cover schema migration/idempotence/future rejection, catalogs, DIN 6892 golden values, backend blocking, CSV postprocessing/persistence, trilingual GUI/report rendering, and Python 2.7 compatibility of the Abaqus-side pure modules. These checks do **not** run a solver.

The D40/D25/D50/tapered real-CAE NOJOB mesh regressions documented for the protected 4.1 release remain historical evidence for the inherited geometry/mesh foundation. They are not relabeled as new 4.2 solver or exact-FVA-specimen validation.

## Running from source

```powershell
py -3 model_builder_gui.py
```

`run_builder.bat` prefers only `release\ModelBuilder_4.2\ModelBuilder.exe`, otherwise source mode. It deliberately does not launch the protected 4.1 release or historical `dist`. `build_headless.bat` remains an explicit legacy flat-output route and requires `--legacy-flat`.

## Building a clean 4.2 release

```powershell
.\make_exe.bat
```

The script uses pinned PyInstaller 6.22.2, compiles source, validates defaults/catalogs/contract/preset, snapshots source and protected 4.1 artifacts, builds only in `release_staging`, runs the packaged self-test, verifies unchanged source and 4.1 hashes, and publishes only the 4.2 whitelist. The release includes the EXE, README, traceability document, technical contract, default and FVA preset JSON, manifest, and checksums. Loose source, CAE/ODB/solver files, replay/journals, run audits, and licensed documents are rejected.

## Copyright and responsibility

Derived values, formulas, source identifiers, and limitations may be distributed. Do not bundle licensed DIN/FVA PDFs, protected figures, or screenshots without authorization. Each recipient remains responsible for licensed standards, engineering review, and release acceptance. No claim is made that a badge, calculation, generated model, or completed solve is automatically safe or certified.
