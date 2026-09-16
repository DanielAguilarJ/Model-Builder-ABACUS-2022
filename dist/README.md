# Parametric Model Builder v2 — Shaft / Key (Form A|B) / Hub

Set the USER parameters, press **BUILD**, and the whole Abaqus model is
regenerated, meshed, assembled, audited and saved. Everything that DIN 6885
fixes is **derived** from the shaft diameter `D`, so you cannot get an
inconsistent key by hand.

The model stays **NOJOB**: geometry + materials + mesh + assembly + sets, with
no contact, steps, loads, boundary conditions or job.

## What changed in v2 (professor's review)

| Review note | What was done |
|---|---|
| `Key -> SWITCH Form A / Form B` | Radio switch. **Form A = rounded ends (pill)**, **Form B = square ends (rectangle)**, per DIN 6885. |
| `b, h dependent on D (DIN 6885)` | `b`, `h`, `t1`, `t2` are read from the DIN 6885-1 table for `D`. Not editable by hand. |
| `l USER`, `c USER`, `phi_c 45°` | Key length and corner chamfer are USER; chamfer angle fixed at 45°. `l = 0` means auto. |
| `y_min = R-t`, `y_max = R-t+h`, `x_w = b/2` | Derived and shown in the GUI *Derived* panel. |
| `L = 3 x D` | `L_over_D` parameter, default 3. |
| `z_0 = R_cap + 5`, `z_1 = z_0 + 2 R_cap + dz` | Implemented exactly; `dz` is USER, `R_cap = b/2`. |
| `y_F = R - t`, `r_2 USER` | Keyway floor derived; root fillet radius is USER. |
| `Sec 3: Why tapered hub` + `Cylindrical Hub` | New **cylindrical hub seated directly on the shaft** (`d_i = D`) is now the default. The tapered bushing is kept as `hub_type = "tapered"` so nothing is lost. |
| `d_i = D`, `Q_A USER`, `d_a = D * Q_A` | Implemented. `Q_A` is the wall-thickness ratio (2.0 gives the old Ø80 hub for D40). |
| `r_1 USER` | Fillet radius at the hub keyway roof corners (mirror of `r_2` on the shaft). |
| `Top clearance g_c = t1 + t2` (per DIN) | Hub groove roof at `R + t2`, so `g_c = t1 + t2 - h` (0.300 mm for D40). Reported and checked. |
| `C45QT_KEY -> steel_key`, need `STEEL_SHAFT`, `STEEL_HUB` | Materials renamed to **`STEEL_SHAFT`**, **`STEEL_HUB`**, **`STEEL_KEY`** with sections `SEC_STEEL_*`. |
| `Sec 5: rely on linear hexahedral elements` | Default is **linear hexahedra**, fully integrated (see the row below). Measured 97.7–99.5 % hexahedra. |
| `Sec 6.1: Why c = 0.8 ?` | Now **answered with numbers** in the audit. `c` is USER, and the build derives the governing condition `c >= r2` plus the actual clearance `(c - r2)/sqrt(2)`. See below. |
| `Sec 5: fully integrated, not reduced` | Default is **`C3D8`** hex + **`C3D4`** tet (linear) and **`C3D20`** + **`C3D10`** (quadratic). No `C3D8R` / `C3D20R` / `C3D10M` anywhere. |
| `R_cap` (left blank in the notes) | Exposed as USER with `0 = auto = b/2` (end-mill radius). |
| `we need C45` | All three materials carry `grade = "C45"`, an Abaqus description, and a reference yield `Re` reported in the audit (model stays linear elastic). |

### Why c = 0.8 mm (Sec 6.1)

The bottom corner chamfer of the key must clear the **keyway root fillet `r2`** in
the shaft. The fillet centre sits at `(x_w - r2, y_F + r2)`, and both of its
tangent points lie on the line `y - x = y_F - x_w + r2`. The chamfer face is the
line `y - x = y_min - (x_w - c)`. Because `y_min = y_F`, this collapses to

```
condition:              c >= r2
perpendicular clearance = (c - r2) / sqrt(2)
```

For the D40 default (`r2 = 0.25`, `c = 0.8`) that is **0.3889 mm** of clearance,
and the top chamfer keeps **0.6086 mm** from the hub roof fillet `r1`. Both
numbers are printed in `PARAM_BUILD_AUDIT.txt`, so the value is justified rather
than assumed. Verified: setting `c = 0.20` (below `r2`) makes the audit report
`-0.0354 mm` and the verdict flips to CHECK.

## Literature-based additions

The builder now cross-checks the design against published work. All of it is
reported in `PARAM_BUILD_AUDIT.txt`, with a `REFERENCES` block.

**Sources** (the first two are the PDFs already in this project):

- [1] N. L. Pedersen, *Stress concentrations in keyways and optimization of
  keyway design*, J. Strain Analysis for Engineering Design **45**(8), 593–604, 2010.
- [2] F. Kresinsky, E. Leidich, A. Hasse, *Different Failure Mechanisms in Keyed
  Shaft–Hub Connections under Dynamic Torque Load*, ICSI 2019, TU Chemnitz.
- [3] M. Eissa, H. Fessler, *Reduction of elastic stress concentrations in
  end-milled keyed connections*, Experimental Mechanics **23**, 401–408, 1983.
- [4] DIN 6892 (parallel key strength), DIN 743 (shaft fatigue / notch effect).

**What was added**

| Feature | Grounded in |
|---|---|
| Nominal torsional stress `tau_nom = T/Wt`, `Wt = pi D^3/16`, and peak-stress estimates using the published `Kts = 2.93` (shaft) and `3.90` (hub) | [1] |
| Report of `KvM = 22.3` for the DIN design in 3D with contact, and that a super-elliptic keyway (`eta = 3.1`) reached a 67 % reduction in 2D / 78 % in 3D | [1] |
| DIN 6892-style surface pressure on both sides, using bearing heights `t1 - c` and `h - t1 - c` (so the chamfer's cost is quantified), the bearing length `l_tr` (`l - b` for Form A), utilisations and the transmissible torque | [4] |
| Hub wall classification `d/D1 = d_i/d_a` against the 0.70 threshold, with the expected failure location | [2] |
| Note that the governing criterion (pressure vs fatigue crack) depends on shaft strength | [2] |
| Notch resolution check: elements across the fillet arc, plus model DOF against the `4.4e6` at which [1] found convergence | [1] |

For the D40 default at `T = 200 N m`: `tau_nom = 15.92 MPa`, `p_shaft = 62.7 MPa`,
`p_hub = 119.6 MPa`, governing transmissible torque `719 N m`, `d/D1 = 0.500`
(thick-walled, so failure is expected at the shaft keyway contact).

### Honest finding on notch refinement

The audit revealed the mesh resolves the `r2 = 0.25 mm` fillet with only **2
elements on the arc**, which is not enough to quote a stress concentration
factor. A `fillet_arc_elems` option was added, and measured:

| `fillet_arc_elems` | elements on arc | notch element size | worst aspect ratio |
|---:|---:|---:|---:|
| 0 (default) | 2 | 0.196 mm | 22.5 |
| 4 | 4 | 0.098 mm | 33.9 |
| 6 | 6 | 0.065 mm | 68.9 |

Only the *tangential* size shrinks, so elements become slender. Attempting to
compensate by seeding the neighbouring edges by size made it worse, not better
(edge seeds apply to the whole edge, so long edges near the notch subdivided
along their full length: 0.7 to 10.3 million elements, aspect ratio up to 130).

Therefore the option **defaults to off**, and the audit prints the trade-off
instead of hiding it. A correct local refinement needs a dedicated partition
around the keyway root; that is the recommended next step, not something the
current seeding can deliver.

### New design checks

| Check | Meaning |
|---|---|
| `chamfer c vs root fillet r2` | fails if `c < r2` (chamfer would bite into the fillet) |
| `bottom / top chamfer clearance` | the actual perpendicular gaps in mm |
| `straight flank left on key` | `h - 2c`, the height still available to carry torque |
| `hub wall left above keyway` | `d_a/2 - (R + t2)`; fails if the hub keyway breaks through the wall. Verified: `Q_A = 1.15` reports `-0.300 mm` and flips the verdict. |

## Files

| File | What it is |
|------|------------|
| `build_parametric_model.py` | Engine. Runs **inside Abaqus**, builds everything from a JSON. |
| `model_builder_gui.py` | The form (GUI). Normal Python; launches Abaqus. |
| `params_default.json` | Default parameter set (D40). |
| `run_builder.bat` / `build_headless.bat` / `make_exe.bat` | Launchers and exe builder. |
| `build_parametric_model_LEGACY_TAPERED.py.bak` | The v1 engine, kept as a reference. |
| `Report_KeyJoint_DIN6885.tex` | Report for submission (English). Sections are split as requested and Sec. 8 answers every review comment point by point. Compile with `pdflatex` twice; figures are `preview\keyFormA-preview.png` and `keyFormB-preview.png`. |

There is also an **Abaqus plug-in** in `<home>\abaqus_plugins\parametric_builder\`
(menu *Plug-ins > Parametric Model Builder*) that needs no Python install.

## USER vs DERIVED

**USER (you type these)**

- Shaft: `D`, `L_over_D`, `dz`, `z0_offset`, `r2`, mesh seed
- Key: `l` (0 = auto), `c`, mesh seed
- Hub: `L_hub`, `Q_A`, `r1`, groove clearance, mesh seed
- Materials: `E`, `nu` per material, common density
- Options: key form, hub type, element order, AR repair threshold

**DERIVED (computed, read-only)**

`R = D/2`, `L = L_over_D · D`, `b`, `h`, `t1`, `t2` (DIN 6885),
`R_cap = b/2`, `z_0 = R_cap + z0_offset`, `z_1 = z_0 + 2·R_cap + dz`,
`y_F = R − t1`, `y_min`, `y_max = R − t1 + h`, `x_w = b/2`,
`d_i = D`, `d_a = D·Q_A`, groove roof `= R + t2`, `g_c = t1 + t2 − h`,
auto key length (`2·R_cap + dz` for Form A, `dz` for Form B).

## Verified results (D = 40, linear C3D8R)

| Case | Verdict | Hex | Tet | Notes |
|---|---|---:|---:|---|
| Form A, cylindrical hub | OK | 97.7 % | 2.3 % | key fills the keyway, `l = 50` |
| Form B, cylindrical hub | OK | 99.5 % | 0.5 % | key 100 % hex, AR 3.25 |
| Form A, D = 50 | OK | 97.9 % | 2.1 % | DIN switches to b14×h9, t1 5.5, t2 3.8 |

All cases: `failed = 0`, one connected component per part, all fit/clearance
checks pass (`g_c = 0.300`, hub groove side clearance 0.0107 mm).

## How to use

GUI: double-click `run_builder.bat` (or `python model_builder_gui.py`).
Set `D`, pick **Form A** or **Form B**, press **Refresh derived** to see what DIN
gives you, then **BUILD**. Outputs `<model>.cae`, `PARAM_BUILD_AUDIT.txt` and
`<model>_preview.png`.

No GUI: edit `params.json` and run
`abaqus cae noGUI=build_parametric_model.py -- params.json`.

## Honest limits

- The remaining tetrahedra sit in the **rounded caps** of the keyway and of a
  Form A key: the straight wall meets the cap arc tangentially, which no
  hexahedron can fill. They are reported per part in the audit.
- The shaft worst aspect ratio is ~21 next to the `r2 = 0.25` fillet. Lower
  `ar_repair_threshold` to trade hexahedra for a better aspect ratio.
- `r_1` is interpreted as the **hub keyway roof fillet** (the mirror of `r_2`).
  If the intent was an outer hub edge chamfer, say so and it is a one-line change.
- Still NOJOB: no contact, step, load, BC or job.
