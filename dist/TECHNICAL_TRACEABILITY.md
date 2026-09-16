# Technical contract and traceability

This file defines what Model Builder may claim. It is not a replacement for a licensed standard.

## Evidence badges

- **NORMATIVE** — implemented numeric requirement derived from DIN 6885-1:2021-11 within its stated range.
- **FVA-RESEARCH** — proposal or setup from the supplied 2025 FVA 600 III research report; not a current DIN requirement.
- **LITERATURE** — published comparison or engineering context; never an acceptance criterion.
- **CORE-SCREENING** — fast internal plausibility calculation. In particular, the uniform-bearing pressure calculation is **not** complete DIN 6892 Method B.
- **USER-OVERRIDE** — a user-selected value outside the normative series or geometry.

## Implemented normative data

`keyjoint_core.py` is the only source used by both the GUI and the Abaqus engine. It contains 26 diameter bands for `6 < d1 <= 500 mm`, including `b`, `h`, `t1`, `t2`, positive `t1` tolerance, `d2_add`, the standard length series, and separate `r1`/`r2` ranges. Values outside the diameter range are rejected; the first or last row is never extrapolated.

Forms A, B and AB are implemented. Their length semantics are explicit:

- `key_nominal_length`: overall DIN key length `l`.
- `slot_total_length`: total generated shaft-slot extent.
- `load_bearing_length`: A = `l-b`, B = `l`, AB = `l-b/2`.

Forms C–J and groove forms N2/N3 remain reference-only because their holes/chamfers or cutter geometry and associated dimensions have not yet been implemented. The application blocks them rather than silently generating a different form.

## DIN 6892 limitation

The current analytical pressure check is tagged **CORE-SCREENING**. A licensed complete DIN 6892 source, including the required tables and curves, is not present. Therefore neither the GUI nor generated reports may call this calculation “DIN 6892 Method B complete.” DIN 743/FKM checks are also outside the automatic acceptance scope.

## FVA 600 III limitation

The supplied material is treated as **FVA-RESEARCH**. The relative opening measure is `v = DeltaV / V_theo`, with the supplied research threshold `v_crit = 0.5`. A one-load-cycle NOJOB build is only a geometry/physics regression and pre-solve setup. It is not Method A: the supplied report proposes at least 10 load cycles and its numerical example uses 20.

## Distribution policy

The executable may include derived numeric tables, citations, formulas and these limitations. It must not bundle the supplied DIN/FVA PDFs, screenshots of protected pages, or reproduced standard figures without authorization.
