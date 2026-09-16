# Model Builder 4.1

Model Builder automates traceable shaft–hub–parallel-key models for Abaqus/CAE. It derives the implemented DIN 6885-1 dimensions, builds and meshes the parts, keeps every run in an isolated project workspace, writes machine-readable audits, captures model views, and generates a LaTeX report from those artifacts.

> **Engineering scope:** a successful build verifies the automated geometry/mesh workflow; it is not a certification of the joint. The analytical pressure calculation is **CORE-SCREENING**, not complete DIN 6892 Method B. The FVA preset is **FVA-RESEARCH**, not a current DIN requirement and not complete Method A.

## Release identity

- Product: **Model Builder 4.1**
- Parameter schema: **5**
- Mesh algorithm: **`auto-mesh-1.0`**
- Platform: Windows
- Abaqus integration tested on: **Abaqus 2022**
- Final shareable package: `release\ModelBuilder_4.1\` or `release\ModelBuilder_4.1.zip`
- Integrity and build metadata: `BUILD_MANIFEST.json` and `SHA256SUMS.txt` in the release package

Do not distribute the historical `dist` directory as a folder. It can contain old Abaqus CAE, journal, replay and audit files. The release builder copies only an explicit whitelist into a clean package.

## Requirements

For colleagues using the packaged EXE:

1. Windows 10/11 or a compatible managed Windows workstation.
2. Abaqus/CAE installed locally, with a valid license and a callable launcher such as `abaqus.bat` or `abq2022.bat`.
3. Write permission in the selected project base directory.
4. Optional: `latexmk` or `pdflatex` on `PATH` to compile `report.pdf`. Without either compiler, Model Builder still writes a complete `report.tex`, `report_data.json`, and `latex_build.log`.

`ModelBuilder.exe` contains the GUI and Python resources, but it does **not** contain Abaqus, an Abaqus license, or a LaTeX distribution. Normal users do not need a separate Python installation. Running from source requires Python 3 with Tkinter.

## Quick start

1. Extract `ModelBuilder_4.1.zip` to a normal application folder. Do not run it from inside the ZIP.
2. Double-click `ModelBuilder.exe`.
3. In **1 Proyecto**, choose a project name, model name, project base directory, and Abaqus launcher. Use **Detectar Abaqus** or browse to the full `.bat` path if needed.
4. In **2 Geometría DIN**, select form A, B, or AB and enter the independent dimensions. Review the derived values and badge.
5. Configure mesh and analysis options in tabs 3 and 4. Leave analysis disabled for a geometry/mesh-only NOJOB build.
6. Press **Validar**. Hard errors must be corrected before generation.
7. Press **GENERAR PROYECTO**. A new timestamped project is created for this run.
8. Review the final status, `generated\BUILD_RESULT.json`, `generated\PARAM_BUILD_AUDIT.*`, screenshots, and report. A process return code of zero alone is not sufficient evidence of a valid model.

Keep the project base outside the application/release folder. The default is `Documents\ModelBuilder Projects`.

## Supported geometry and DIN behavior

`keyjoint_core.py` is the single source for the parametric DIN table, derivations, validation rules, evidence badges, and length semantics used by both the GUI and Abaqus engine.

- Implemented diameter range: **`6 < d1 <= 500 mm`**, using 26 explicit bands. Values outside the range are rejected; no clamping or extrapolation is performed.
- Implemented key forms: **A, B, AB**.
- Implemented groove form: **N1**.
- Forms C–J and groove forms N2/N3 are blocked until their required holes, chamfers, cutters, and dimensions are implemented. Another shape is never substituted silently.
- Implemented DIN-derived values include `b`, `h`, `t1`, `t2`, positive `t1` tolerance, `d2_ref`, standard key lengths, and separate `r1`/`r2` ranges.
- A user override remains visible as **USER-OVERRIDE** and is validated; it is not relabelled as normative.

### Length semantics

The three lengths are intentionally distinct:

| Quantity | Meaning |
|---|---|
| `key_nominal_length` | Overall nominal DIN key length `l` |
| `slot_total_length` | Total axial extent of the generated shaft slot |
| `load_bearing_length` | Length used by the internal bearing-pressure screening |

The bearing length is `l-b` for form A, `l` for form B, and `l-b/2` for form AB. With automatic DIN snapping, Model Builder selects the longest listed standard length that fits; it does not invent a fallback length.

## Evidence badges

Every source or result is classified:

- **NORMATIVE** — numeric requirement derived from the implemented DIN 6885-1 source scope.
- **USER-OVERRIDE** — user-selected input that is not asserted to be the normative series value.
- **CORE-SCREENING** — internal plausibility calculation; specifically not complete DIN 6892 Method B.
- **FVA-RESEARCH** — supplied research setup/proposal, not a current DIN edition.
- **LITERATURE** — comparison/context only, never an acceptance criterion.

See `TECHNICAL_TRACEABILITY.md` and `technical_contract.json` for the claim policy and implemented requirements.

## Operating modes

### 1. Parametric geometry/mesh build (default)

With analysis disabled, Abaqus creates the parts, materials, mesh, assembly, sets, audit, CAE and screenshots. No contact, load step, BC, solver job, or ODB is created. This is the default NOJOB workflow.

### 2. Optional generic torsion analysis

When enabled, the engine can add contact, a torsion step, boundary conditions and loads. Job creation and submission are separate switches. If a job is submitted, all solver files use the project `jobs` directory as their working directory. Solved stresses require independent mesh-convergence, equilibrium, contact-path and engineering checks before quotation.

### 3. FVA 600 III research pre-solve

The D40 preset is tagged **FVA-RESEARCH** and uses a locked internal geometry backend whose filename retains `v3` for traceability. The product identity remains Model Builder 4.1 with parameter schema 5. The preset can create a research physics setup with contacts, steps, BCs, amplitude and one load cycle, while a strict guard prevents creation or submission of an Abaqus Job.

That one-cycle setup is a pre-solve/regression artifact. It is **not** complete Method A: the supplied research workflow requires at least 10 cycles and uses `v_crit = 0.5` under the FVA-RESEARCH badge.

## Automatic mesh policy

Model Builder 4.1 provides six versioned templates: `AUTO_BALANCED`, `QUALITY_CRITICAL`, `FAST_PREVIEW`, `HEX_DOMINANT`, `QUADRATIC_ACCURACY`, and `ROBUST_FALLBACK`. AUTO evaluates complete recipes independently for Shaft, Key, Hub, and optional Bushing. “Best” means highest-ranked **admissible** candidate under `auto-mesh-1.0`; it does not mean a universally perfect mesh.

- Hard gates run before scoring: elements > 0, failed elements = 0, one connected component, expected fillet detected, hard element budget respected, and winner reproduction inside declared tolerances.
- Global quality is the worst piece status/score, never an average.
- Ranking uses hard-gate admissibility, status, score, hex percentage, warnings, bulk aspect ratio, element count, then stable recipe order. Wall-clock time is audit-only.
- All templates inherit requested order except explicit `QUADRATIC_ACCURACY`. Linear profiles are `C3D8`, `C3D8I`, or explicitly requested `C3D8R`, plus `C3D4` fallback. Quadratic profiles are `C3D20 + C3D10` fallback.
- `C3D8R` is never selected automatically. Final histograms are checked against the resolved profile.
- The winning recipe is regenerated before assembly. The audit separates exact signature equality from declared advancing-front equivalence (2% nodes/elements, 2 percentage points hex, 5 score points).
- Hex coverage, warning count, bulk AR and soft element budget are policy scoring targets, not universal structural acceptance limits.
- The optional mesh study is a density/quality study without a stress solve. It is not stress-convergence evidence.

## Project structure

Every GUI run creates a new `<project>_YYYYMMDD_HHMMSS` directory:

```text
project.json
input/
  params.json
  technical_contract.json
generated/
  PARAM_BUILD_AUDIT.txt
  PARAM_BUILD_AUDIT.json
  BUILD_RESULT.json
model/
  <model>.cae
  <model>.jnl
jobs/
  <job>.inp / .odb / .sta / .msg / ... (only when a job is created)
screenshots/
  <model>_preview.png
  <model>_preview_Front.png
  <model>_preview_Right.png
  <model>_notch_mesh.png
reports/
  report_data.json
  report.tex
  report.pdf             (only when LaTeX compilation succeeds)
  latex_build.log
logs/
  abaqus.log             (subprocess output from the packaged GUI)
```

`project.json` records identity, configuration, run state and discovered artifacts. Absolute artifact routes are written into `input\params.json`; Abaqus runs with `jobs` as its working directory so solver files cannot leak beside the EXE. Schema-5 audit JSON and `BUILD_RESULT.json` also record SHA-256 for the exact engine, shared core and input JSON consumed by Abaqus; compare these with `BUILD_MANIFEST.json.build_provenance.source_inputs`.

A failed or cancelled run is intentionally retained for diagnosis. Check `logs\abaqus.log`, `generated\BUILD_RESULT.json`, and any Abaqus `.msg/.dat/.sta` files before retrying.

## Report generation

The report is generated from `project.json`, `PARAM_BUILD_AUDIT.json`, and the images in `screenshots`; values are not hardcoded in the LaTeX template. If `latexmk` exists, it is preferred. Otherwise `pdflatex` is run twice. If neither exists, the source report remains usable and the reason is recorded in `latex_build.log`.

To compile manually from the project `reports` directory:

```powershell
latexmk -pdf -interaction=nonstopmode -halt-on-error report.tex
```

or:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error report.tex
pdflatex -interaction=nonstopmode -halt-on-error report.tex
```

## How to decide whether a run succeeded

For a geometry/mesh build, verify all of the following:

1. Abaqus process return code is zero.
2. `generated\BUILD_RESULT.json` exists and `ok` is the JSON boolean `true` (not `null`).
3. `PARAM_BUILD_AUDIT.json.verdict` is exactly `OK`; a `CHECK` result is a failed automated contract and requires a corrected new run.
4. The expected CAE and screenshots exist.
5. Mesh counts, failed elements, connected components, fit checks and evidence badges are plausible.
6. If analysis was requested, verify job completion, readable ODB, expected steps/frames/fields and equilibrium independently.

## Verified 4.1 integration cases

Real NOJOB regressions were run in Abaqus 2022 for the current schema-5 engine:

| Case | Effective profile | Result |
|---|---|---|
| D40, form A, `AUTO_BALANCED` | linear `C3D8/C3D4` | 114,378 elements, 93.0% hex, score 85, zero failed; Shaft/Key/Hub winners reproduced |
| D25, form B, `AUTO_BALANCED` | linear `C3D8/C3D4` | 103,478 elements, score 85, zero failed; nominal/bearing length 22/22 mm |
| D50, form AB, `QUADRATIC_ACCURACY` | `C3D20/C3D10` | 71,364 elements and 283,280 nodes, score 85, zero failed; nominal/bearing length 50/43 mm |
| D40 tapered, `FAST_PREVIEW`, Bushing | linear `C3D8/C3D4` | 48,487 elements across four pieces, hard gates passed; tapered audit makes no local-notch-seeding claim |

A D40 seed-scale density/quality study retained its inadmissible coarse point rather than hiding it and restored the nominal winner exactly. These runs prove the automated build, policy gates and artifact routing—not stress convergence, structural suitability or regulatory acceptance. No LaTeX compiler was installed on the QA machine; `report.tex`, `report_data.json` and the explicit compiler-absence log were verified, not a PDF.

## Troubleshooting

### Abaqus is not found

Use **Detectar Abaqus**, or select the full launcher path, for example:

```text
C:\SIMULIA\Commands\abaqus.bat
C:\SIMULIA\Commands\abq2022.bat
```

If the launcher starts but no license is available, inspect `logs\abaqus.log` and the local Abaqus licensing diagnostics.

### No PDF appears

Open `reports\latex_build.log`. Install a LaTeX distribution that provides `latexmk` or `pdflatex`, ensure the executable is on `PATH`, then compile the existing `report.tex`. Missing LaTeX does not invalidate the CAE/audit build.

### `BUILD_RESULT.ok` is false or missing

Read the audit and Abaqus log. Do not infer success from an existing CAE alone. Correct the input or mesh problem and create a new project rather than overwriting the failed one.

### Antivirus or application-control warning

The EXE is a one-file PyInstaller application and may be extracted to a temporary directory at runtime. Validate it against `SHA256SUMS.txt`, distribute it through the organization's approved channel, and sign it with the organization's code-signing certificate if required. This project does not claim that the EXE is digitally signed.

## Running from source

Developer prerequisites: Python 3 with Tkinter, plus Abaqus. Use:

```powershell
py -3 model_builder_gui.py
```

`run_builder.bat` is a convenience launcher that prefers the clean 4.1 release and otherwise uses `py -3`; it never launches the historical `dist` tree. `build_headless.bat` is retained only for explicit legacy flat-output reproduction; it is not included in the shareable package and refuses to run unless `--legacy-flat` is supplied.

## Building a clean release

From the source directory:

```powershell
.\make_exe.bat
```

The script pins PyInstaller 6.22.2, compiles sources, records a SHA-256 snapshot before PyInstaller, builds only in `release_staging`, verifies that no input changed, runs the packaged `--self-test`, and invokes `make_release.py`. The release helper copies only this whitelist:

- `ModelBuilder.exe`
- `README.md`
- `TECHNICAL_TRACEABILITY.md`
- `technical_contract.json`
- `params_default.json`
- `params_fva600_research_presolve_1lw.json`
- generated `BUILD_MANIFEST.json` and `SHA256SUMS.txt`

It rejects Abaqus databases, solver files, replay/journal files, run-specific audits, source snapshots and loose source files. `BUILD_MANIFEST.json` binds hashes of every declared pre-build input to the EXE; `SHA256SUMS.txt` covers released payload and manifest, and `ModelBuilder_4.1.zip.sha256` covers the ZIP. The self-test validates 4.1/schema 5 identity, all six templates, deterministic ranking, effective element profiles, packaged resources and defaults; it does not start Abaqus or prove an engineering analysis.

## Distribution and copyright

Derived numeric data, citations, formulas, and explicit limitations may be distributed with the application. Do **not** bundle licensed DIN/FVA PDFs, screenshots of protected pages, or reproduced standard figures without authorization. Each recipient remains responsible for access to the licensed standards required for normative engineering work.

No claim is made that CORE-SCREENING replaces DIN 6892, that the FVA preset is a current standard, or that a generated/solved model is automatically safe for design release.