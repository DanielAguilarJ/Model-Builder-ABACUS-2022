# Model Builder 4.2 — technical contract and traceability

**Applicable product:** Model Builder 4.2  
**Parameter schema:** 6  
**Accepted predecessor:** schema 5 through explicit migration  
**Mesh algorithm:** `auto-mesh-1.0`  
**DIN/FVA engine:** `din6892-methods-1.0`  
**Document revision:** 2026-09-15

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

One item is explicitly left unresolved. The DIN 6885-1:2021-11 keyway radius table groups the width column `b` into four `r1/r2` bands, and in the machine-extracted table the group boundaries are ambiguous: both `2,3 | 4,5,6 | 8..18 | 20,22` and `2..6 | 8..12 | 14..18 | 20,22` reproduce the printed 13 columns and 4 groups. The implemented grouping is therefore **not changed on a guess**; it is recorded here as an open item to be closed against the printed table. The affected quantity is the keyway root radius, which enters equation 9 through `r`, so a wrong grouping shifts `t1tr` and every derived torque. For the D40 default the value used is `r = 0.25 mm`.

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

`M_t,zul = f_W*p_zul*d_w*l_tr*t_tr / (2*K_V*K_lambda*K_R*1000)`.

The check runs separately for the shaft keyway, the hub keyway, and the key. Each component uses its own `Re`, **its own support and hardness factors, and its own bearing depth `t_tr`**, and the weakest component governs `M_t,zul`; the per-component table, `governing_component`, and `governing_bearing_depth_mm` are persisted.

#### Per-component bearing depth

DIN 6892 evaluates the shaft flank pressure over `l_tr*t1tr` and the hub flank pressure over `l_tr*t2tr`. Checking the hub with the shaft depth overstates the hub bearing area whenever `t2 < t1`, which is the normal DIN 6885 proportion, so the hub result would be optimistic. The implementation therefore assigns:

| Component | Depth | Reason |
|---|---|---|
| shaft | `t1tr` | equation 9 (or the selected depth policy) |
| hub | `t2tr` | its own flank height in the hub bore |
| key | `min(t1tr, t2tr)` | the key flank carries the same pressure as the mating keyway flank, so the smaller contact height is critical |

`t2tr` is derived from the geometry rather than assumed: the hub keyway sits in a **concave** bore, so the bore surface at the keyway edge lies below the bore apex and the flank is *taller* than the nominal depth `t2` by the chord correction. Bounded by the roof fillet `r1`, the chamfer `s2`, and the radial top clearance `g_c = t1 + t2 - h`:

`t2tr = t2 - (r1 + s2) - g_c + (d_w - sqrt(d_w^2 - (b + 2*s2)^2))/2`.

For the D40 default joint this gives `t2tr = 3.141491287186 mm` against `t1tr = 5.141491287186 mm`, so the hub is checked on 61 % of the area it was previously credited with. Without a usable `t2tr` the hub and key fall back to `t1tr` and the fallback is reported as `din6892_hub_bearing_depth_missing` instead of being silently accepted.

#### Equation 9 versus the shaft flank geometry

Equation 9 as transcribed **adds** the chord correction and therefore returns `t1tr > t1` for standard geometry, while the convex shaft flank geometry — and the standard's own wording that the effective depth is *reduced* by `s1` and `r` — requires **subtracting** it. An independent closed-form flank height is computed next to the equation and both values, the chord correction, their difference, and an `agrees` flag are reported:

| Quantity | D40 default |
|---|---|
| `t1tr` equation 9 as transcribed | `5.141491287186 mm` |
| `t1tr` shaft flank geometry | `2.758508712814 mm` |
| chord correction | `1.191491287186 mm` |
| relative difference | `46.35 %` |

Nothing is silently corrected. `bearing_depth_policy` selects which value the pressure checks use — `EQUATION_9` (default, so the transcribed standard is never overruled without being asked), `GEOMETRIC`, or `CONSERVATIVE` (the smaller of the two) — and a disagreement is always reported as `din6892_bearing_depth_optimistic`. The hub keyway is left alone by the policy because in a concave bore the same algebraic form with a plus sign *is* geometrically correct, which is itself the strongest evidence that the shaft sign or the `t1` datum needs a licensed clarification.

#### `N_W` is not the load cycle count

Equation 3 is driven by `N_W`, the number of **load direction reversals** (Lastrichtungswechsel), which is exactly what `f_W` penalises: the key alternately bearing on both shaft keyway flanks. Feeding the total load cycle count into `N_W` penalises a purely pulsating joint that never changes flank. The resolution order is:

| Situation | `N_W` | `f_W` | Reported as |
|---|---|---|---|
| explicit `N_W` | as given | equation 3 | `EXPLICIT_N_W` |
| `R < 0` | `load_cycles` | equation 3 | `din6892_load_reversal_derived` |
| `R >= 0` | `0` | `1.0` | `din6892_load_reversal_derived` |
| `R` unknown | `load_cycles` | equation 3 | `din6892_load_reversal_unknown_direction` |

`R >= 0` landing on `f_W = 1` is the `f_W = 1` plateau the standard's own diagram shows below about `10^3` reversals, and the unknown-direction fallback stays conservative on purpose.

#### Applied loading and both safeties

`M_teq = K_A*M_t,nom` builds the equivalent torque from the nominal drive torque, and `torque_applied_Nm` keeps precedence when both are supplied. From the applied equivalent torque the implementation reports the actual pressure of equation 6, `p_eq = K_V*K_lambda*K_R*F_eq/(l_tr*t_tr)` with `F_eq = 2*M_teq/d_w`, the equation-1 safety `S_Feq = M_t,zul/M_teq`, and the utilisation per component. When a rare peak torque is supplied it is checked against `p_max,zul = f_L*p_zul` and yields `S_Fmax` next to `S_Feq`.

#### `K_lambda` diagram gate

`K_lambda` is never interpolated or invented, but the reading is gated against the diagram it must have come from: `K_lambda` in `1.0..2.0`, `Q_A = d_w/D` in `0.3..0.9`, `l_tr/d_w` in `0.5..2`, and one of the three load-derivation diagrams (`FRONT`, `MIDDLE`, `REAR`) declared explicitly. Readings outside those bounds cannot have come from the standard and are reported as `din6892_k_lambda_outside_diagram`, `din6892_k_lambda_qa_outside_diagram`, or `din6892_k_lambda_length_outside_diagram`. The mapping from `a_0/l_tr` to one of the three diagrams is a declaration about the assembly and is deliberately not guessed.

`f_S` and `f_H` come from the DIN 6892 Table 2 block `DIN6892_TABLE2_SUPPORT`, indexed by component and by material class. The tabulated ranges are `1.1–1.4` for the key, `1.3–1.7` for a steel/cast-steel/nodular-iron shaft, `1.1–1.4` for a lamellar-cast-iron shaft, `1.5` for a steel hub, and `2.0` for a lamellar-cast-iron hub; `f_H = 1.15` applies to case-hardened steel and is undefined for lamellar cast iron, where an explicit `f_H` is demanded instead of a silent `1.0`. The default bound is the **lower** end of each range, because the standard itself requires the smaller value whenever the material is not known with certainty. `f_S_bound` may select `mid` or `upper` as a deliberate engineering decision. An explicit `f_S`/`f_H` always wins and is then marked `USER-INPUT`; a Table 2 value is marked `DIN-METHOD`. With no material class declared, the factors fall back to `1.0` with `USER-INPUT`, which is a placeholder and not a measurement.

`phi` follows equation 10 strictly: `1.0` for one key, and for two keys `0.75` when the allowable pressure is evaluated versus `0.90` for the peak pressure. Three or more keys are outside equation 10 and raise instead of reusing an invented `0.90`. The peak branch is therefore evaluated with its own `K_V`, not with the allowable-pressure one.

`t1tr` uses equation 9 including the key chamfer, `t1tr = t1 - (r + s1) + (d_w - sqrt(d_w^2 - (b + 2*s1)^2))/2`. `chamfer_s1_mm` defaults to the chamfer of the selected key geometry rather than to zero: for the D40 default joint the 0.8 mm chamfer lowers `t1tr` from 5.671215971661 to 5.141491287186 mm, so treating `s1` as zero overstates every Method-B and Method-C torque by 10.30 %. The value and its origin are persisted as `derived.chamfer_s1_mm` and `derived.chamfer_s1_source` (`GEOMETRY_KEY_CHAMFER` for the default) and printed in the audit block.

Equation 11 `D_ers = D2 / ((D2/D1)^4*(1 - c/l_tr) + c/l_tr)^0.25` is available for a shouldered hub, so `Q_A` is formed from the torsion-equivalent outer diameter instead of a raw one. Equation 12 `K_Req = (M_t,eq - q_eq*M_t,Rmin)/M_t,eq` with `q_eq = 0.5` for the interrupted joint is computed whenever a minimum slip torque is supplied, and is reported next to the FVA-corrected `K_R = 1` that is actually used; the DIN value and the correction never overwrite each other.

`K_lambda` is the only factor of this chain that still has no embedded source: it is read from the licensed DIN 6892 diagrams over roughly `1.0–2.0` and keeps `USER-INPUT` provenance. A licensed factor still sitting at the neutral value `1.0` with `USER-INPUT` provenance is a placeholder. In that state the result is reported as `PROVISIONAL_FACTORS` with `din6892_factor_placeholder`, and only becomes `CALCULATED` once the licensed values are supplied or `factors_acknowledged` is set after review.

For the bundled D40 C45+N default at `K_lambda = 1.0` the chain gives `M_t,zul = 999.182718802380 N·m` at `f_W = 1.0`, governed by the hub keyway on its own flank height:

| Component | `Re` | `f_S` | depth | `M_t,zul` |
|---|---|---|---|---|
| shaft | 377 MPa | 1.3 | `t1tr = 5.141491 mm` | `1915.082 N·m` |
| **hub** | **279 MPa** | **1.5** | **`t2tr = 3.141491 mm`** | **`999.183 N·m`** |
| key | 928 MPa | 1.1 | `t2tr = 3.141491 mm` | `2437.194 N·m` |

All three are tagged `DIN-METHOD`, the status is `PROVISIONAL_FACTORS`, and the only placeholder reported is `K_lambda`. The same joint under fully alternating torque (`R = -1`, `f_W = 0.796214341107`) drops to `795.563610096732 N·m`.

### `B_FVA_2025`

The research reformulation uses equations 26, 29, and 33–36:

- `f_Sv = 0.74*v + 0.63`;
- `f_WS = Rm/Re`;
- `f_S,ltr = -0.17*(l_tr/d_w) + 0.16`;
- `f_S,ges = f_WS + f_S,ltr`;
- `K_d = 2.08*d_w^-0.18` up to 100 mm, otherwise 0.82;
- `M_t,zul = f_Sv*f_S,ges*f_H*f_W*Re*d_w*l_tr*t1tr / (2*K_R*K_lambda*K_d*K_V*1000)`.

It is always `FVA-RESEARCH` and reports `status = RESEARCH_DIAGNOSTIC`, never `CALCULATED`, because it is not a published DIN method revision.

The limit-load criterion of FVA 600 III is the **relative plastic opening volume of the shaft keyway**. Equations 33 and 36 therefore use the shaft's `Re` and `Rm`, and `f_WS` takes the place of the shaft's tabulated `f_S`. Pairing one part's tensile strength with another part's yield strength is rejected by construction. The hub keyway was deliberately not measured by the project and hub cracking was out of scope, so hub and key appear in `components_not_covered` and still require the current Method-B or Method-C pressure check. For the D40 C45+N joint this gives `f_WS = 676/377 = 1.7931`, which is above the DIN Table 2 upper bound of 1.7 for a shaft and is exactly the capacity potential the report reports.

`K_R = 1` is the corrected friction-closure factor: the report shows numerically and experimentally that a superposed interference fit does **not** raise the quasi-static transmissible torque. The DIN equation-12 value is still reported next to it, and the press fit remains beneficial for long-term fatigue strength.

Equation 26 is normalised at the research criterion `v_krit = 0.5`, where `f_Sv = 1.0`. The ratio `f_Sv(1.0)/f_Sv(0.5) = 1.37` must therefore reproduce the support factors the report measured at both criticality levels: `2.36/1.72 = 1.372` for C45+N and `1.62/1.17 = 1.385` for 42CrMoS4+QT. `volume_support_factor_calibration()` checks this and the self-test fails if the deviation exceeds 2 %. This is the one part of the reformulation that can be validated without the licensed `K_lambda` diagram.

Three transcription and domain facts are reported rather than smoothed away:

- equation 29 gives `K_d = 0.9082` at `d_w = 100 mm` while the report's large-diameter value is a documented simplification of `0.82`; the step is surfaced as `fva_size_factor_transcription_step`;
- equations 15 and 34 were fitted for `0.5 <= l_tr/d_w <= 1.3` and `K_d` for roughly 10 to 450 mm; outside those ranges the result is flagged as extrapolated;
- the reformulation was calibrated on the discrete FVA material catalogue, so evaluating it with other material data is allowed but flagged as `din6892_material_source_not_fva`.

The measured reference results of variants VB1 to VB8 are retained in `FVA_REFERENCE_RESULTS` for comparison. Reproducing the absolute torques additionally needs `K_lambda` from the licensed diagram, so they are evidence for review and not goldens of the formula.

### `C_PRELIMINARY`

Equation 31 is `M_t,zul = p_zul*(h-t1)*l_tr*(d_w/2)*i*phi/1000`, and the allowable pressure has two selectable variants:

| `method_c_variant` | `p_zul` | Equations | Badge |
|---|---|---|---|
| `DIN_PUBLISHED` (default) | `0.9*Re_min` | 30, 31 | DIN-METHOD |
| `FVA_2025` | `1.0*Re_min` | 31, 32 | FVA-RESEARCH |

The FVA variant is equation 32 of the report, which proposes dropping the 10 % reduction of the published Method C. It is offered because the report argues for it, not because a DIN edition adopted it, so it carries `FVA-RESEARCH` and never becomes the default.

Like Method B, Method C is evaluated per component and the weakest one governs; passing only the scalar `Re_min_MPa` reproduces the classic single-value form exactly. For the D40 default this gives `572.508 N·m` (hub-governed) published and `636.12 N·m` in the FVA variant.

Equation 31 works with the hub-side engagement height `h - t1`, not with the nominal DIN 6885 hub depth `t2`. The two differ by the radial top clearance `g_c = t1 + t2 - h`, so `h - t1 = t2 - g_c` is automatically the smaller and therefore the conservative value. Both are reported (`3.0 mm` engaged against `t2 = 3.3 mm` at `g_c = 0.3 mm` for D40) so the clearance stays visible instead of looking like a transcription error. A negative `g_c` means the key is taller than the two keyway depths together and equation 31 does not describe the joint at all, which is reported as `din6892_method_c_clearance_negative`.

#### Method C as a sizing method

"Überschlägige Dimensionierung" is a *sizing* task, so the inverse of equation 31 is returned as well. The torque per unit bearing length `M_t/mm = p_zul*(h-t1)*(d_w/2)*i*phi/1000` is reported explicitly, and from a required torque the implementation returns the bearing length and the DIN 6885 nominal key length that satisfy `M_t,design >= M_t,required`:

`l_tr,required = M_t,required * safety_factor / (M_t/mm)`, then equation 8 in reverse for the key form.

For the D40 default and a `700 N·m` requirement at `S = 1.2` this gives `l_tr = 55.755 mm` and a form-A key length of `67.755 mm`, i.e. `l_tr/d_w = 1.394`. That is above the `1.3` limit where the rear part of the key transmits practically no pressure, so it is reported as `din6892_method_c_sizing_too_long` rather than returned as a usable answer — the joint needs more keys or a different type.

#### Method C must stay conservative against Method B

A preliminary method that allows *more* torque than the detailed method is worse than no method. `cross_method_consistency` reports `M_t,C / M_t,B` alongside `M_t,FVA / M_t,B` and names the governing analytical torque. For the D40 default the ratio is `0.573`, so Method C is conservative. When it is not — for instance at a high `K_lambda`, which only affects Method B — `din6892_method_c_not_conservative` is raised and the Method-B result governs.

This is preliminary sizing. Method A/B and DIN 743 remain independently applicable.

All calculable methods return `M_t,design = M_t,zul / safety_factor`, method ID, equations, source, badge, inputs, and limitations.

### Companion methods

Method A needs a solved ODB while Methods B and C are closed-form, so the three analytical methods are always evaluated next to the selected primary method on the same derived inputs and persisted under `din6892.companions`. This gives an A-versus-B comparison in a single run without weakening the rule that the FVA CAE route must itself request Method A. A companion that cannot be evaluated reports its own reason as `din6892_companion_invalid` and never invalidates the primary result.

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
| `DIN_7190_1` | USER-INPUT | minimum slip torque for equation 12 entered externally |
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

### Hybrid-hex numerical setup

`method_a_hybrid_hex_v2` inherits the physics, material-model and matching capability of the connected backend and replaces the all-tetrahedral volume fill with a quadratic hex-dominated mesh with bounded `C3D15`/`C3D10` transitions. Interface patterns, the 1 mm edge limit and the rectangular opening grid are verified at build, not assumed. `params_fva600_method_a_10lw_solve.json` is the solver-sized companion preset; `params_fva600_method_a_20lw_nojob.json` and `params_fva600_research_presolve_1lw.json` stay NOJOB.

The following is measured run behaviour, recorded so the cost of a full Method-A solve is not underestimated. A submitted D40 model of this backend produced 438,318 elements and 1,166,347 equations at 3.906e12 FLOPs per factorization, zero input errors, and distributing-coupling compatibility residuals no larger than 4.4e-25. Increment 1 of the fit step needed 12 equilibrium iterations, after which increments converged in one iteration each at roughly 2.2 min per iteration. The step structure is `FVA_FIT` and `FVA_SERVICE_FRICTION` at 1.0 time each with `maxInc = 0.05`, then `FVA_METHOD_A_CYCLES` at 20.0 time with `maxInc = 0.2`, so at least 140 increments are required. That is above 5 h even in the unreachable best case of one iteration per increment, and the report's own figure of 24–30 h for 20 cycles in Abaqus is the realistic order.

That run was deliberately terminated by the user at increment 8 of `FVA_FIT`. `abaqus terminate` is the supported way to do this: Abaqus stops at the end of the current increment, writes `***ERROR: Process terminated by external request`, `THE ANALYSIS HAS NOT BEEN COMPLETED`, and leaves a readable ODB with the frames written so far. Such an ODB is **not** Method-A evidence: no unloaded frame exists, no cycle is complete, and `state = FAILED` is the correct verdict.

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

The DIN/FVA part of that suite now also pins Table 2 lookups per component and bound, the equation-10 scope error above two keys, equation 9 with and without the chamfer, equations 11 and 12 with the FVA `K_R` override, the shaft-only component resolution of equation 33, both Method C variants, and the equation-26 calibration against the report's measured support factors. Method B and Method C golden values were revised in this revision; the earlier goldens were reproducible but derived from an OCR reading of the source and from a chamfer-free equation 9, and are not compatible with the current implementation.

Real Abaqus 2022 NOJOB mesh regressions from the protected 4.1 release remain historical evidence for the inherited geometry/mesh foundation. They are not relabeled as new 4.2 solver validation or exact FVA matching.
