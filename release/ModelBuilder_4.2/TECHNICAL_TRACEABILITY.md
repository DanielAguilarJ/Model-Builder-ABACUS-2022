# Model Builder 4.2 — technical contract and traceability

**Applicable product:** Model Builder 4.2  
**Parameter schema:** 6  
**Accepted predecessor:** schema 5 through explicit migration  
**Mesh algorithm:** `auto-mesh-1.0`  
**DIN/FVA engine:** `din6892-methods-1.0`  
**Document revision:** 2026-09-11

This document defines what Model Builder may claim. It does not replace a licensed standard, an engineering release process, or independent verification of a solved model. `technical_contract.json` is the machine-readable companion.

## Evidence classification

- **NORMATIVE:** implemented numeric data derived from DIN 6885-1:2021-11, within declared range and geometry scope.
- **DIN-METHOD:** an implemented DIN 6892 equation workflow. It does not mean certification and cannot promote `USER-INPUT` factors.
- **FVA-RESEARCH:** data, equations, variants, or criteria from supplied FVA 600 III booklet 1686 (2025); not a current DIN edition.
- **USER-INPUT:** value or result requiring a licensed table/diagram, test, certificate, or explicit engineering decision.
- **NOT-IMPLEMENTED:** visible reference with no claimed implementation.
- **CORE-SCREENING:** internal uniform-pressure plausibility calculation, distinct from DIN 6892 Method B.
- **LITERATURE:** comparison/context only.
- **USER-OVERRIDE:** non-series value entered by the user.

Badges remain visible in GUI, parameter/audit JSON, human audit, and reports. Successful execution cannot upgrade research, external input, screening, literature, or overrides to normative evidence.

## Localization contract

`i18n/es.json`, `i18n/en.json`, and `i18n/de.json` are canonical UTF-8 catalogs with exact key and placeholder parity. `project.language` persists the locale and defaults to Spanish; fallback is requested locale, then Spanish, then English. GUI and reports localize presentation while JSON keys, methods, codes, badges, equations, and source IDs stay canonical. The Abaqus-side core does not import i18n and remains Python 2.7 compatible.

## Schema migration and aliases

The raw document's `schema_version` is inspected before defaults are merged. Schema 5 migrates to 6; schema 6 normalizes idempotently; schema 7 or any future version is rejected. Migration records source/target schema and actions.

Schema-6 canonical geometry is:

- `shaft.diameter_mm`;
- `hub.QA_shaft_over_outer = d_w / D_outer`.

`shaft.D` and `hub.hub_outer_over_shaft` remain synchronized deprecated aliases for existing scripts. Legacy `hub.QA` is interpreted only by the documented migration rule. Conflicting aliases raise a hard error; no value wins silently.

## DIN 6885-1 geometry scope

`keyjoint_core.py` contains 26 explicit diameter bands for `6 < d1 <= 500 mm`, implemented `b`, `h`, `t1`, `t2`, positive `t1` tolerance, `d2_add/d2_ref`, standard lengths, and separate `r1/r2` ranges. No band is clamped or extrapolated. Forms A, B, and AB and groove N1 are implemented. Forms C–J, N2/N3, and DIN 6888 Woodruff geometry remain unavailable.

`key_nominal_length`, `slot_total_length`, and `load_bearing_length` are distinct. The bearing length is `l-b` for A, `l` for B, and `l-b/2` for AB.

## DIN 6892 and FVA calculation scope

`din6892_methods.py` is the single pure-Python 2.7/3 implementation. GUI, core, reports, defaults, and self-tests do not duplicate its formulas.

### `A_FE_VOLUME`

Method A assesses external permanent-opening evidence:

- `V_theo = l_tr * t1tr * U_PF_mm`;
- `v = DeltaV / V_theo`;
- research criterion `v <= 0.5` by default;
- allowable torque only when trials bracket `v_crit`.

Conclusive evidence requires at least 10 cycles, identified step/frame, explicit unloaded-frame confirmation, and a persisted postprocess result whose `l_tr`, `t1tr`, and `U_PF` still match. The model builder does not claim to solve the source ODB.

`fva600_postprocess.py` accepts `x_mm,z_mm,opening_um`, rejects missing/duplicate/non-finite/negative grid data, integrates each rectangular cell by the four-corner mean, records area coverage and SHA-256, persists atomically, and can reverify the external source. Importing evidence does not enable the legacy CAE backend.

### `B_DIN_CURRENT`

The implemented chain uses equations 1–12:

`p_zul = f_S*f_H*Re`, `f_W = min(1, 2*N_W^-0.1)`, `K_V = 1/(i*phi)`, and

`M_t,zul = f_W*p_zul*d_w*l_tr*t1tr / (2*K_V*K_lambda*K_R*1000)`.

`K_lambda`, `K_R`, `f_H`, `f_S`, and `phi` retain `USER-INPUT` provenance when their licensed source is not embedded.

### `B_FVA_2025`

The research reformulation uses equations 26, 29, and 33–36:

- `f_Sv = 0.74*v + 0.63`;
- `f_WS = Rm/Re`;
- `f_S,ltr = -0.17*(l_tr/d_w) + 0.16`;
- `f_S,ges = f_WS + f_S,ltr`;
- `K_d = 2.08*d_w^-0.18` up to 100 mm, otherwise 0.82;
- `M_t,zul = f_Sv*f_S,ges*f_H*f_W*Re*d_w*l_tr*t1tr / (2*K_R*K_lambda*K_d*K_V*1000)`.

It is always `FVA-RESEARCH`, not a published DIN method revision.

### `C_PRELIMINARY`

Equations 30–31 use `p_zul = 0.9*Re_min` and

`M_t,zul = p_zul*(h-t1)*l_tr*(d_w/2)*i*phi/1000`.

This is preliminary sizing. Method A/B and DIN 743 remain independently applicable.

All calculable methods return `M_t,design = M_t,zul / safety_factor`, method ID, equations, source, badge, inputs, and limitations.

## FVA catalog and higher-strength material data

VB1–VB8 are discrete configurations from the supplied research context. They vary diameter, `l_tr/d_w`, `Q_A`, interference `xi`, key form, and load ratio. Applying variant geometry is explicit; catalog presence is not a claim that Abaqus can realize it.

Material pairs C45+N/C45+N and 42CrMoS4+QT/42CrMoS4+QT are available only at 20, 40, and 60 mm. No interpolation is allowed. The record includes measured `Re`, `Rm`, `E`, report hardness estimates, hub cyclic-curve parameters, shaft cyclic plasticity, and C45+QT key data under `FVA-RESEARCH`. `U_PF` (key–keyway opening) and `xi` (shaft–hub interference) remain separate.

## Standards registry

| ID | Badge | Implemented claim |
|---|---|---|
| `DIN_6885_1_2021` | NORMATIVE | declared geometry bands/forms |
| `DIN_6892` | DIN-METHOD | A/B/C equation workflows |
| `DIN_743` | USER-INPUT | external fatigue result required |
| `DIN_EN_ISO_286` | USER-INPUT | fits entered externally; tables not bundled |
| `DIN_EN_ISO_18265` | FVA-RESEARCH | report data only |
| `DIN_7190_1` | USER-INPUT | external frictional-closure input |
| `DIN_6880` | NOT-IMPLEMENTED | material/product reference only |
| `DIN_6888` | NOT-IMPLEMENTED | visible selection blocks unsupported geometry |

## Requested, derived, and realized

The core emits one DIN/FVA record with:

1. **requested:** method, variant, materials, load ratio, `U_PF`, `xi`, and selected standards;
2. **derived:** variant geometry, material source, effective `t1tr`, calculation inputs, factors, `M_t,zul`, and `M_t,design`;
3. **realized:** actual backend capability, matching status, Job/solver behavior, and blocking issues.

GUI and report use this record. They do not infer realized CAE support from a successful analytical calculation.

## CAE backend boundaries

### Legacy one-cycle regression

`d40_v3_refined_hex_nojob` is `LEGACY_PARTIAL_VB1_C45_1LW_NOJOB`. It supports only a Method-A setup adapted to the conical D40 V3 model, VB1, C45, one cycle, and strict NOJOB. It creates/submits no Job, is not complete Method A, and has `MATCHING NOT_VERIFIED` with respect to the exact FVA specimen. VB2–VB8, 42CrMoS4+QT, ten-or-more cycles, alternative methods, or incompatible geometry are blocked with stable codes; there is no fallback coercion.

### Connected 20-cycle numerical setup

`method_a_connected_mesh_v1` is a separate parametric cylindrical backend. The bundled `params_fva600_method_a_20lw_nojob.json` requests VB1/C45, 20 cycles, the Chaboche–Lemaître shaft, UML/Ramberg–Osgood hub and elastic-ideal-plastic key models, a contact target no greater than 1 mm, and verification of five matching interfaces. Four flank pairs are compared in tangential coordinates and shaft–hub in three dimensions. Matching remains `VERIFY_AT_BUILD` until actual assembly nodes are compared; equal seeds are not evidence. The requested tolerance is `1e-6 mm`, while the documented Abaqus 2022 coordinate-kernel floor makes the effective tolerance `max(requested, 5e-5 mm)`.

The backend has optional Job/submission capability, but the released companion preset keeps `analysis.enabled/create_job/submit=false`, `strict_no_job=true`, and `execution.create_job/submit_solver=false`. A NOJOB build may write a new isolated CAE, preview and `FVA_METHOD_A_SETUP.json`; it does not solve. No such connected-backend runtime artifact is bundled or claimed by the 4.2 source/release audit.

### Postprocessing and claim boundary

`fva600_odb_extract.py` opens an existing ODB read-only. Its negative-opening policy is recorded (`CLAMP_TO_ZERO` by default), and a last-frame/time match cannot by itself establish zero torque: the caller must explicitly confirm that the frame is unloaded. `fva600_postprocess.py` does not open an ODB; it rejects negative CSV openings and retains external source SHA-256.

A source or packaged self-test can close implementation and release-contract checks only. It does not execute Abaqus partitioning, meshing, matching, Job creation, solver submission or ODB review. A solved Method-A result still requires at least 10 evaluated cycles, an independently confirmed unloaded frame, volume evidence, convergence, equilibrium, contact, material and DIN 743 review.

## Mesh and build boundaries

Six versioned mesh templates apply hard gates before deterministic ranking. Global status is the worst piece. Requested element order is inherited except explicit quadratic policy; `C3D8R` is never auto-selected. The winning recipe is regenerated and exact equality is separated from advancing-front tolerance. Density/quality studies are not stress-convergence evidence.

Three outcomes remain separate:

1. core validation passed;
2. build audit passed (`BUILD_RESULT.ok == true`, audit `OK`, required topology/mesh/artifacts);
3. solved analysis accepted after independent ODB, convergence, equilibrium, contact-path, material, and engineering review.

A process return code, CAE existence, badge, or quality score alone is insufficient.

## Workspace, provenance, and report

Normal runs create isolated `input`, `generated`, `model`, `jobs`, `screenshots`, `reports`, and `logs` directories. Schema-6 audits record SHA-256 for exact runtime engine, core, and input. `report_generator.py` is the single report structure; it localizes presentation and includes DIN/FVA requested/derived/realized and standards tables. `report_template.tex` is only an ownership marker.

## Release immutability and whitelist

The 4.2 build uses only `release_staging` and can publish only `release/ModelBuilder_4.2`. `release/ModelBuilder_4.1`, its ZIP, and checksum file are protected historical artifacts. The pre-build source snapshot includes every protected 4.1 file path, size, and SHA-256. Publication fails if any protected file is added, removed, resized, or rehashed before or after 4.2 creation.

The whitelist excludes CAE/ODB/solver files, replay/journals, run audits, snapshots, temporary files, loose source, and licensed documents. `BUILD_MANIFEST.json` binds source hashes, protected-release verification, packaged self-test, and EXE hash; `SHA256SUMS.txt` and the ZIP checksum cover released payload.

## Validation scope

Source-level and Abaqus-kernel checks for 4.2 cover identity, migration/idempotence/future rejection, aliases, DIN/FVA catalogs, method golden values, backend block codes, CSV negatives/integration/persistence, defaults, trilingual GUI/report rendering, and Python 2.7 compilation/import of Abaqus-side pure modules. They do not start a solver.

Real Abaqus 2022 NOJOB mesh regressions from the protected 4.1 release remain historical evidence for the inherited geometry/mesh foundation. They are not relabeled as new 4.2 solver validation or exact FVA matching.
