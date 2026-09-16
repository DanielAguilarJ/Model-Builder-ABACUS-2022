# -*- coding: utf-8 -*-
"""
================================================================================
 keyjoint_core.py  -  shared core of the parametric key-joint builder (v4)
================================================================================
 Pure Python. NO Abaqus imports, so the very same module is used by

   * build_parametric_model.py   -> runs inside the Abaqus kernel (Python 2.7)
   * model_builder_gui.py        -> runs on a normal Python 3 with Tkinter
   * report_generator.py         -> normal Python 3 report generation

 Everything that is standardised or derived lives here and ONLY here:

   - the DIN 6885-1 parallel key table  (b, h, t1, t2 as a function of D)
   - the DIN 6885-1 standard length series
   - the default parameter set
   - derive()      : every derived quantity (geometry, fits, design check)
   - validate()    : hard errors / warnings BEFORE anything is built
   - fit_checks()  : the clearance table printed in the audit
   - auto mesh seeds and the notch-refinement band geometry

 Before v3 the DIN table and the derived formulas existed twice (engine + GUI)
 and could drift apart. Now there is a single source of truth.

 Written to run unchanged on Python 2.7 and Python 3.x.
================================================================================
"""
from __future__ import print_function, division

import hashlib
import json
import math
import os

import din6892_methods as din6892

SCHEMA_VERSION = 6
PREVIOUS_SCHEMA_VERSION = 5
BUILDER_VERSION = "4.2"
MESH_ALGORITHM_VERSION = "auto-mesh-2.0"
SUPPORTED_MESH_ALGORITHM_VERSIONS = ("auto-mesh-1.0", MESH_ALGORITHM_VERSION)
MESH_TOPOLOGY_REQUIREMENTS = (
    "MIXED_ALLOWED", "HEX_PREFERRED", "HEX_ONLY", "HYBRID_HEX")
MESH_TOPOLOGY_TOLERANCE = 1.0e-9

# Evidence badges used in the GUI, audit and generated report.  They prevent
# research proposals or comparison values from being presented as current DIN
# requirements.
EVIDENCE_NORMATIVE = "NORMATIVE"
EVIDENCE_DIN_METHOD = "DIN-METHOD"
EVIDENCE_FVA_RESEARCH = "FVA-RESEARCH"
EVIDENCE_USER_INPUT = "USER-INPUT"
EVIDENCE_NOT_IMPLEMENTED = "NOT-IMPLEMENTED"
EVIDENCE_LITERATURE = "LITERATURE"
EVIDENCE_CORE_SCREENING = "CORE-SCREENING"
EVIDENCE_USER_OVERRIDE = "USER-OVERRIDE"
EVIDENCE_BADGES = (EVIDENCE_NORMATIVE, EVIDENCE_DIN_METHOD,
                   EVIDENCE_FVA_RESEARCH, EVIDENCE_USER_INPUT,
                   EVIDENCE_NOT_IMPLEMENTED, EVIDENCE_LITERATURE,
                   EVIDENCE_CORE_SCREENING, EVIDENCE_USER_OVERRIDE)

KEY_FORMS_IMPLEMENTED = ("A", "B", "AB")
KEY_FORMS_REFERENCE_ONLY = ("C", "D", "E", "F", "G", "H", "J")

TRACEABILITY = {
    "DIN6885_DIMENSIONS": {
        "badge": EVIDENCE_NORMATIVE,
        "source": "DIN 6885-1:2021-11",
        "scope": "Table-derived b, h, t1, t2, +tol(t1), d2 reference and radii",
        "distribution": "Derived numeric data only; source document not bundled"
    },
    "DIN6885_FORMS": {
        "badge": EVIDENCE_NORMATIVE,
        "source": "DIN 6885-1:2021-11",
        "scope": "Forms A, B and AB implemented; C-J documented but unavailable",
        "distribution": "No protected figures are bundled"
    },
    "DIN6892_METHODS": {
        "badge": EVIDENCE_DIN_METHOD,
        "source": "DIN 6892 licensed/user-supplied context",
        "scope": "Methods A, B and C with allowable-torque calculation",
        "limitation": "Licensed diagram/table factors remain explicit USER-INPUT values"
    },
    "FVA600_III": {
        "badge": EVIDENCE_FVA_RESEARCH,
        "source": "FVA 600 III research report, 2025",
        "scope": "Research setup, proposed factors and v_crit=0.5",
        "limitation": "Research proposal; not a published DIN edition"
    },
    "PUBLISHED_COMPARISONS": {
        "badge": EVIDENCE_LITERATURE,
        "source": "Pedersen; Kresinsky et al.; Eissa/Fessler; supplied literature",
        "scope": "Comparison values only, never acceptance criteria"
    }
}

MAT_SHAFT = 'STEEL_SHAFT'
MAT_HUB = 'STEEL_HUB'
MAT_KEY = 'STEEL_KEY'
SEC = {MAT_SHAFT: 'SEC_STEEL_SHAFT',
       MAT_HUB: 'SEC_STEEL_HUB',
       MAT_KEY: 'SEC_STEEL_KEY'}
MATERIALS = (MAT_SHAFT, MAT_HUB, MAT_KEY)

# --------------------------------------------------------------------- literature
# Published results, reported for comparison only. They are NOT computed here.
REFS = [
    ('[1] N. L. Pedersen, "Stress concentrations in keyways and optimization of '
     'keyway design", J. Strain Analysis for Engineering Design 45(8), 593-604, 2010.'),
    ('[2] F. Kresinsky, E. Leidich, A. Hasse, "Different Failure Mechanisms in Keyed '
     'Shaft-Hub Connections under Dynamic Torque Load", ICSI 2019, TU Chemnitz.'),
    ('[3] M. Eissa, H. Fessler, "Reduction of elastic stress concentrations in '
     'end-milled keyed connections", Experimental Mechanics 23, 401-408, 1983.'),
    ('[4] DIN 6892 (parallel key strength) and DIN 743 (shaft fatigue / notch effect).'),
    ('[5] DIN 6885-1 (parallel keys, dimensions and tolerances).'),
]
KTS_SHAFT_LIT = 2.93        # [1] 2D pure torsion, DIN 6885 keyway, max fillet
KTS_HUB_LIT = 3.90          # [1] hub, outer diameter three times the inner one
KVM_3D_DIN_LIT = 22.3       # [1] full 3D WITH contact, standard DIN design
KVM_2D_OPT_LIT = 5.9        # [1] optimised super-elliptic key, 2D contact model
RED_2D_SYM_LIT = 67.0       # % reduction, double-symmetric optimum, 2D
RED_3D_UNSYM_LIT = 78.0     # % reduction, unsymmetrical optimum, verified in 3D
ETA_OPT_LIT = 3.1
DOF_CONVERGED_LIT = 4.4e6   # [1] DOF at which the stress had converged (~1%)
D_OVER_D1_THICK = 0.70      # [2] hub wall classification threshold

# --------------------------------------------------------------------- DIN 6885-1
# Derived numeric transcription of DIN 6885-1:2021-11 Tables 1 and 2.
# Interval convention is strict at the lower bound and inclusive at the upper:
#     d_from < d1 <= d_upto
# Values: d_from, d_upto, b, h, t1, t2, positive tolerance on t1, d2-d1.
# The licensed source document and its figures are intentionally not bundled.
DIN6885 = [
    (6.0,   8.0,   2.0,   2.0,  1.2,  1.0, 0.1,  2.5),
    (8.0,  10.0,   3.0,   3.0,  1.8,  1.4, 0.1,  3.5),
    (10.0, 12.0,   4.0,   4.0,  2.5,  1.8, 0.1,  4.0),
    (12.0, 17.0,   5.0,   5.0,  3.0,  2.3, 0.1,  5.0),
    (17.0, 22.0,   6.0,   6.0,  3.5,  2.8, 0.1,  6.0),
    (22.0, 30.0,   8.0,   7.0,  4.0,  3.3, 0.2,  8.0),
    (30.0, 38.0,  10.0,   8.0,  5.0,  3.3, 0.2,  8.0),
    (38.0, 44.0,  12.0,   8.0,  5.0,  3.3, 0.2,  8.0),
    (44.0, 50.0,  14.0,   9.0,  5.5,  3.8, 0.2,  9.0),
    (50.0, 58.0,  16.0,  10.0,  6.0,  4.3, 0.2, 11.0),
    (58.0, 65.0,  18.0,  11.0,  7.0,  4.4, 0.2, 11.0),
    (65.0, 75.0,  20.0,  12.0,  7.5,  4.9, 0.2, 12.0),
    (75.0, 85.0,  22.0,  14.0,  9.0,  5.4, 0.2, 14.0),
    (85.0, 95.0,  25.0,  14.0,  9.0,  5.4, 0.2, 14.0),
    (95.0, 110.0, 28.0,  16.0, 10.0,  6.4, 0.2, 16.0),
    (110.0,130.0, 32.0,  18.0, 11.0,  7.4, 0.2, 18.0),
    (130.0,150.0, 36.0,  20.0, 12.0,  8.4, 0.3, 21.0),
    (150.0,170.0, 40.0,  22.0, 13.0,  9.4, 0.3, 23.0),
    (170.0,200.0, 45.0,  25.0, 15.0, 10.4, 0.3, 26.0),
    (200.0,230.0, 50.0,  28.0, 17.0, 11.4, 0.3, 28.0),
    (230.0,260.0, 56.0,  32.0, 20.0, 12.4, 0.3, 32.0),
    (260.0,290.0, 63.0,  32.0, 20.0, 12.4, 0.3, 32.0),
    (290.0,330.0, 70.0,  36.0, 22.0, 14.4, 0.3, 36.0),
    (330.0,380.0, 80.0,  40.0, 25.0, 15.4, 0.3, 40.0),
    (380.0,440.0, 90.0,  45.0, 28.0, 17.4, 0.3, 45.0),
    (440.0,500.0,100.0,  50.0, 31.0, 19.5, 0.3, 50.0),
]
DIN_D_MIN = 6.0
DIN_D_MAX = 500.0

# DIN 6885-1 standard key lengths [mm].
DIN6885_LENGTHS = [6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32, 36, 40, 45, 50,
                   56, 63, 70, 80, 90, 100, 110, 125, 140, 160, 180, 200, 220,
                   250, 280, 320, 360, 400]

# Width bands and the two distinct radius ranges from DIN 6885-1.
# r1 is the mouth/edge radius; r2 is the groove-floor radius.
DIN6885_RADII = [
    (2.0,   6.0, 0.16, 0.25, 0.08, 0.16),
    (8.0,  12.0, 0.25, 0.40, 0.16, 0.25),
    (14.0, 20.0, 0.40, 0.60, 0.25, 0.40),
    (22.0, 28.0, 0.60, 0.80, 0.40, 0.60),
    (32.0, 45.0, 1.00, 1.20, 0.70, 1.00),
    (50.0, 63.0, 1.60, 2.00, 1.20, 1.60),
    (70.0,100.0, 2.50, 3.00, 2.00, 2.50),
]


def din6885_row(D):
    """Return the exact DIN 6885-1 row for ``6 < D <= 500``.

    No clamping or extrapolation is allowed: a diameter outside the normative
    table raises ``ValueError`` so the caller cannot accidentally claim DIN
    compliance using the nearest row.
    """
    D = float(D)
    if not (DIN_D_MIN < D <= DIN_D_MAX):
        raise ValueError('DIN 6885-1 normative range is 6 < d1 <= 500 mm; '
                         'received %.6g mm. No extrapolation is performed.' % D)
    for d_from, d_upto, b, h, t1, t2, t1_tol, d2_add in DIN6885:
        if d_from < D <= d_upto:
            return {
                'b': float(b), 'h': float(h),
                't1': float(t1), 't2': float(t2),
                't1_tol_plus': float(t1_tol),
                'd2_add': float(d2_add),
                'd2_ref': D + float(d2_add),
                'D_from': float(d_from), 'D_upto': float(d_upto),
                'in_table': True, 'badge': EVIDENCE_NORMATIVE,
                'source_id': 'DIN6885_DIMENSIONS'
            }
    raise ValueError('No DIN 6885-1 row found for d1 = %.6g mm.' % D)


def din6885_key(D):
    """Standard parallel-key cross-section and groove values for D [mm]."""
    r = din6885_row(D)
    return dict((k, r[k]) for k in
                ('b', 'h', 't1', 't2', 't1_tol_plus', 'd2_add', 'd2_ref'))


def din6885_radii(b):
    """Return separate r1 and r2 ranges for nominal key width ``b``."""
    b = float(b)
    for b_from, b_upto, r1_lo, r1_hi, r2_lo, r2_hi in DIN6885_RADII:
        if b_from <= b <= b_upto:
            return {'r1_min': r1_lo, 'r1_max': r1_hi,
                    'r2_min': r2_lo, 'r2_max': r2_hi,
                    'badge': EVIDENCE_NORMATIVE,
                    'source_id': 'DIN6885_DIMENSIONS'}
    raise ValueError('Key width %.6g mm is not in the DIN 6885-1 radius bands.' % b)


def nearest_standard_length(l):
    """Largest DIN length not exceeding ``l``; fail if none can fit."""
    l = float(l)
    usable = [float(v) for v in DIN6885_LENGTHS if float(v) <= l + 1e-9]
    if not usable:
        raise ValueError('No DIN 6885-1 standard key length fits in %.6g mm; '
                         'the shortest standard length is %.0f mm.'
                         % (l, DIN6885_LENGTHS[0]))
    return usable[-1]


def din_fillet_range(b):
    """Compatibility helper: DIN groove-floor radius r2 range."""
    r = din6885_radii(b)
    return (r['r2_min'], r['r2_max'])


def normalize_key_form(value):
    """Return an implemented DIN form without silently truncating input."""
    form = str(value or '').strip().upper()
    if form in KEY_FORMS_IMPLEMENTED:
        return form
    if form in KEY_FORMS_REFERENCE_ONLY:
        raise ValueError('DIN 6885-1 Form %s needs hole/chamfer dimensions that '
                         'are not implemented; choose A, B or AB.' % form)
    raise ValueError('Unknown key form %r; implemented forms are A, B and AB.'
                     % value)


def traceability_manifest():
    """JSON-safe copy of every evidence classification used by the builder."""
    return json.loads(json.dumps(TRACEABILITY))


# =============================================================== mesh policy
# Versioned, JSON-safe recipes.  The Abaqus backend interprets
# ``control_strategy``; all ranking and quality decisions remain pure Python so
# they can be tested identically under CPython 3 and Abaqus Python 2.7.
MESH_PARTS = ("Shaft", "Key", "Hub", "Bushing")
MESH_CONTROL_STRATEGIES = (
    "HEX_STRUCTURED", "HEX_SWEEP_MEDIAL", "HEX_SWEEP_ADVANCING",
    "HEX_DOMINATED", "TET_FREE")

MESH_RECIPE_CATALOG = {
    "STRUCTURED_HEX": {
        "control_strategy": "HEX_STRUCTURED", "seed_scale": 1.00,
        "notch_mode": "profile", "max_repairs": 2},
    "SWEEP_MEDIAL": {
        "control_strategy": "HEX_SWEEP_MEDIAL", "seed_scale": 1.00,
        "notch_mode": "profile", "max_repairs": 3},
    "SWEEP_ADVANCING": {
        "control_strategy": "HEX_SWEEP_ADVANCING", "seed_scale": 0.95,
        "notch_mode": "profile", "max_repairs": 3},
    "HEX_DOMINATED": {
        "control_strategy": "HEX_DOMINATED", "seed_scale": 0.90,
        "notch_mode": "profile", "max_repairs": 3},
    "FREE_TET": {
        "control_strategy": "TET_FREE", "seed_scale": 0.85,
        "notch_mode": "profile", "max_repairs": 1}
}

# Candidate order is deliberately piece-specific.  A successful API call is
# not treated as proof of quality: every generated candidate is measured and
# ranked later by ``select_best_mesh_candidate``.
MESH_PART_RECIPE_ORDER = {
    "Shaft": ("STRUCTURED_HEX", "SWEEP_MEDIAL", "SWEEP_ADVANCING",
              "HEX_DOMINATED", "FREE_TET"),
    "Key": ("STRUCTURED_HEX", "SWEEP_MEDIAL", "HEX_DOMINATED",
            "SWEEP_ADVANCING", "FREE_TET"),
    "Hub": ("SWEEP_MEDIAL", "STRUCTURED_HEX", "SWEEP_ADVANCING",
            "HEX_DOMINATED", "FREE_TET"),
    "Bushing": ("SWEEP_MEDIAL", "STRUCTURED_HEX", "HEX_DOMINATED",
                "SWEEP_ADVANCING", "FREE_TET")
}

_BASE_MESH_TARGETS = {
    "pass_score": 75.0,
    "warn_score": 50.0,
    "min_hex_pct": 55.0,
    "max_non_hex_pct": 100.0,
    "max_warnings": 25,
    "max_bulk_ar": 25.0,
    "max_repairs": 3,
    "fillet_arc_min": 2,
    "fillet_band_min": 1
}

# These are pre-saved *policies*, not claims that one topology is universally
# perfect.  AUTO means best admissible candidate under the selected policy.
MESH_TEMPLATES = {
    "AUTO_BALANCED": {
        "label": "Automatic balanced",
        "description": "Balanced quality/cost search with piece-specific candidates.",
        "selection": "auto", "element_order": "inherit",
        "linear_hex_code": "inherit", "quadratic_hex_code": "inherit",
        "topology_requirement": "MIXED_ALLOWED", "max_attempts": 4,
        "seed_scale": 1.0, "fail_on_quality": True,
        "recipe_ids": ("STRUCTURED_HEX", "SWEEP_MEDIAL",
                       "SWEEP_ADVANCING", "FREE_TET"),
        "targets": dict(_BASE_MESH_TARGETS),
        "part_targets": {
            "Shaft": {"min_hex_pct": 55.0},
            "Key": {"min_hex_pct": 65.0},
            "Hub": {"min_hex_pct": 75.0},
            "Bushing": {"min_hex_pct": 45.0}},
        "budgets": {"soft_elements": 300000, "hard_elements": 900000}
    },
    "QUALITY_CRITICAL": {
        "label": "Quality critical",
        "description": "Finer search, stricter quality thresholds and larger budget.",
        "selection": "auto", "element_order": "inherit",
        "linear_hex_code": "inherit", "quadratic_hex_code": "inherit",
        "topology_requirement": "MIXED_ALLOWED", "max_attempts": 5,
        "seed_scale": 0.80, "fail_on_quality": True,
        "recipe_ids": ("STRUCTURED_HEX", "SWEEP_MEDIAL",
                       "SWEEP_ADVANCING", "HEX_DOMINATED", "FREE_TET"),
        "targets": {"pass_score": 82.0, "warn_score": 62.0,
                    "min_hex_pct": 70.0, "max_non_hex_pct": 100.0,
                    "max_warnings": 8, "max_bulk_ar": 20.0,
                    "max_repairs": 2, "fillet_arc_min": 4,
                    "fillet_band_min": 2},
        "part_targets": {
            "Shaft": {"min_hex_pct": 60.0},
            "Key": {"min_hex_pct": 75.0},
            "Hub": {"min_hex_pct": 85.0},
            "Bushing": {"min_hex_pct": 55.0}},
        "budgets": {"soft_elements": 600000, "hard_elements": 1500000}
    },
    "FAST_PREVIEW": {
        "label": "Fast preview",
        "description": "Two low-cost attempts; inherits the requested element order and keeps hard topology gates mandatory.",
        "selection": "auto", "element_order": "inherit",
        "linear_hex_code": "inherit", "quadratic_hex_code": "inherit",
        "topology_requirement": "MIXED_ALLOWED", "max_attempts": 2,
        "seed_scale": 1.60, "fail_on_quality": False,
        "recipe_ids": ("STRUCTURED_HEX", "SWEEP_MEDIAL"),
        "targets": {"pass_score": 62.0, "warn_score": 35.0,
                    "min_hex_pct": 35.0, "max_non_hex_pct": 100.0,
                    "max_warnings": 50, "max_bulk_ar": 40.0,
                    "max_repairs": 3, "fillet_arc_min": 2,
                    "fillet_band_min": 1},
        "part_targets": {},
        "budgets": {"soft_elements": 120000, "hard_elements": 500000}
    },
    "HEX_DOMINANT": {
        "label": "Hex dominant",
        "description": "Prioritises admissible hexahedral coverage before cost.",
        "selection": "auto", "element_order": "inherit",
        "linear_hex_code": "inherit", "quadratic_hex_code": "inherit",
        "topology_requirement": "HEX_PREFERRED", "max_attempts": 5,
        "seed_scale": 0.90, "fail_on_quality": True,
        "recipe_ids": ("STRUCTURED_HEX", "SWEEP_MEDIAL",
                       "SWEEP_ADVANCING", "HEX_DOMINATED", "FREE_TET"),
        "targets": {"pass_score": 78.0, "warn_score": 55.0,
                    "min_hex_pct": 80.0, "max_non_hex_pct": 100.0,
                    "max_warnings": 20, "max_bulk_ar": 28.0,
                    "max_repairs": 3, "fillet_arc_min": 3,
                    "fillet_band_min": 1},
        "part_targets": {
            "Shaft": {"min_hex_pct": 65.0},
            "Bushing": {"min_hex_pct": 60.0}},
        "budgets": {"soft_elements": 500000, "hard_elements": 1200000}
    },
    "QUADRATIC_ACCURACY": {
        "label": "Quadratic accuracy",
        "description": "Explicit second-order search; selecting it intentionally changes order.",
        "selection": "auto", "element_order": "quadratic",
        "linear_hex_code": "inherit", "quadratic_hex_code": "inherit",
        "topology_requirement": "MIXED_ALLOWED", "max_attempts": 4,
        "seed_scale": 1.20, "fail_on_quality": True,
        "recipe_ids": ("STRUCTURED_HEX", "SWEEP_MEDIAL",
                       "SWEEP_ADVANCING", "FREE_TET"),
        "targets": {"pass_score": 78.0, "warn_score": 55.0,
                    "min_hex_pct": 55.0, "max_non_hex_pct": 100.0,
                    "max_warnings": 20, "max_bulk_ar": 25.0,
                    "max_repairs": 3, "fillet_arc_min": 3,
                    "fillet_band_min": 1},
        "part_targets": {"Hub": {"min_hex_pct": 70.0}},
        "budgets": {"soft_elements": 450000, "hard_elements": 1200000}
    },
    "ROBUST_FALLBACK": {
        "label": "Robust free tetrahedral fallback",
        "description": "Deterministic free-tet recipe for difficult topology.",
        "selection": "fixed", "element_order": "inherit",
        "linear_hex_code": "inherit", "quadratic_hex_code": "inherit",
        "topology_requirement": "MIXED_ALLOWED", "max_attempts": 1,
        "seed_scale": 0.85, "fail_on_quality": True,
        "recipe_ids": ("FREE_TET",),
        "targets": {"pass_score": 65.0, "warn_score": 40.0,
                    "min_hex_pct": 0.0, "max_non_hex_pct": 100.0,
                    "max_warnings": 40, "max_bulk_ar": 35.0,
                    "max_repairs": 1, "fillet_arc_min": 2,
                    "fillet_band_min": 1},
        "part_targets": {},
        "budgets": {"soft_elements": 700000, "hard_elements": 1600000}
    },
    "HEX_CERTIFIED": {
        "label": "Certified quadratic hex only",
        "description": "Strict all-hexahedral search with no tetrahedral fallback or repair.",
        "selection": "auto", "element_order": "quadratic",
        "linear_hex_code": "inherit", "quadratic_hex_code": "C3D20R",
        "topology_requirement": "HEX_ONLY", "max_attempts": 3,
        "max_repairs": 0, "seed_scale": 0.85, "fail_on_quality": True,
        "recipe_ids": ("STRUCTURED_HEX", "SWEEP_MEDIAL",
                       "SWEEP_ADVANCING"),
        "targets": {"pass_score": 85.0, "warn_score": 70.0,
                    "min_hex_pct": 100.0, "max_non_hex_pct": 0.0,
                    "max_warnings": 0, "max_bulk_ar": 8.0,
                    "max_repairs": 0, "fillet_arc_min": 4,
                    "fillet_band_min": 2},
        "part_targets": {},
        "budgets": {"soft_elements": 750000, "hard_elements": 2000000}
    },
    "FVA_METHOD_A_HYBRID": {
        "label": "FVA Method A quadratic hybrid hex",
        "description": "Quadratic hex-dominated Method-A mesh with bounded wedge/tet content.",
        "selection": "fixed", "element_order": "quadratic",
        "linear_hex_code": "inherit", "quadratic_hex_code": "C3D20R",
        "topology_requirement": "HYBRID_HEX", "max_attempts": 1,
        "max_repairs": 0, "seed_scale": 1.0, "fail_on_quality": True,
        "recipe_ids": ("HEX_DOMINATED",),
        "targets": {"pass_score": 78.0, "warn_score": 55.0,
                    "min_hex_pct": 50.0, "max_non_hex_pct": 50.0,
                    "max_warnings": 20, "max_bulk_ar": 25.0,
                    "max_repairs": 0, "fillet_arc_min": 3,
                    "fillet_band_min": 1},
        "part_targets": {},
        "budgets": {"soft_elements": 750000, "hard_elements": 1800000}
    }
}


def _json_clone(value):
    """Deep-copy JSON-compatible policy data on Python 2.7 and 3.x."""
    return json.loads(json.dumps(value))


def _sha256_json(value):
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'))
    if not isinstance(payload, bytes):
        payload = payload.encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def mesh_template_catalog():
    """Return an isolated, serialisable copy of every pre-saved template."""
    return _json_clone(MESH_TEMPLATES)


def mesh_template_names():
    """Stable template order for GUIs and reports."""
    preferred = ("HEX_CERTIFIED", "FVA_METHOD_A_HYBRID",
                 "AUTO_BALANCED", "QUALITY_CRITICAL", "FAST_PREVIEW",
                 "HEX_DOMINANT", "QUADRATIC_ACCURACY", "ROBUST_FALLBACK")
    return [name for name in preferred if name in MESH_TEMPLATES]


def _merge_copy(base, extra):
    out = _json_clone(base)
    if isinstance(extra, dict):
        deep_update(out, extra)
    return out


def mesh_element_profile(order, linear_hex_code='C3D8',
                         quadratic_hex_code='C3D20R',
                         topology_requirement='MIXED_ALLOWED'):
    """Return the exact element family permitted by the resolved topology."""
    resolved_order = str(order or 'linear').strip().lower()
    if resolved_order not in ('linear', 'quadratic'):
        raise ValueError("Element order must be 'linear' or 'quadratic'.")
    topology = str(topology_requirement or 'MIXED_ALLOWED').strip().upper()
    if topology not in MESH_TOPOLOGY_REQUIREMENTS:
        raise ValueError('Topology requirement %r is unsupported; expected one of %s.' %
                         (topology, ', '.join(MESH_TOPOLOGY_REQUIREMENTS)))

    if resolved_order == 'quadratic':
        primary = str(quadratic_hex_code or 'C3D20R').strip().upper()
        if primary not in ('C3D20', 'C3D20R'):
            raise ValueError('Quadratic hexahedron code must be C3D20 or C3D20R.')
        tet_code, wedge_code = 'C3D10', 'C3D15'
        linear_active, quadratic_active = False, True
    else:
        primary = str(linear_hex_code or 'C3D8').strip().upper()
        if primary not in ('C3D8', 'C3D8I', 'C3D8R'):
            raise ValueError('Linear hexahedron code must be C3D8, C3D8I or C3D8R.')
        tet_code, wedge_code = 'C3D4', 'C3D6'
        linear_active, quadratic_active = True, False

    if topology == 'HEX_ONLY':
        fallback = None
        fallback_types = []
        allowed = [primary]
    elif topology == 'HYBRID_HEX':
        fallback = tet_code
        fallback_types = [wedge_code, tet_code]
        allowed = [primary, wedge_code, tet_code]
    else:
        fallback = tet_code
        fallback_types = [tet_code]
        allowed = [primary, tet_code]
    label = primary if fallback is None else '%s + %s fallback' % (
        primary, ' + '.join(fallback_types))
    return {
        'order': resolved_order,
        'primary': primary,
        'fallback': fallback,
        'fallback_types': fallback_types,
        'allowed_types': allowed,
        'linear_hex_code_active': linear_active,
        'quadratic_hex_code_active': quadratic_active,
        'topology_requirement': topology,
        'allow_tet_fallback': topology != 'HEX_ONLY',
        'label': label
    }


def validate_realized_element_profile(mesh_plan, parts):
    """Check final audit histograms against the resolved element family."""
    plan = mesh_plan or {}
    profile = plan.get('element_profile') or mesh_element_profile(
        plan.get('element_order', 'linear'),
        plan.get('linear_hex_code', 'C3D8'),
        plan.get('quadratic_hex_code', 'C3D20R'),
        plan.get('topology_requirement', 'MIXED_ALLOWED'))
    allowed = set(profile.get('allowed_types') or [])
    failures = []
    if not parts:
        return ['realised audit contains no part element histograms']
    for part in sorted(parts.keys()):
        item = parts.get(part) or {}
        metrics = item.get('metrics') or {}
        hist = item.get('types') or metrics.get('types') or {}
        present = sorted([str(code) for code, count in hist.items()
                          if int(_number(count, 0)) > 0])
        element_count = int(_number(item.get(
            'elements', metrics.get('elements', 0)), 0))
        if element_count > 0 and not present:
            failures.append('%s has elements but no element-type histogram' % part)
            continue
        unexpected = [code for code in present if code not in allowed]
        if unexpected:
            failures.append('%s uses %s outside effective profile %s' % (
                part, ', '.join(unexpected), profile.get('label', '?')))
    return failures


def resolve_mesh_plan(params, d=None):
    """Resolve a versioned, deterministic candidate plan for every piece."""
    cfg = params.get('mesh', {}) or {}
    template_id = str(cfg.get('template', 'HEX_CERTIFIED')).strip().upper()
    if template_id not in MESH_TEMPLATES:
        raise ValueError('Unknown mesh template %r. Available: %s.' %
                         (template_id, ', '.join(mesh_template_names())))
    tpl = _json_clone(MESH_TEMPLATES[template_id])
    algorithm = str(cfg.get('algorithm_version', MESH_ALGORITHM_VERSION)).strip()
    if algorithm not in SUPPORTED_MESH_ALGORITHM_VERSIONS:
        raise ValueError('Mesh algorithm version %r is unsupported; expected one of %s.' %
                         (algorithm, ', '.join(SUPPORTED_MESH_ALGORITHM_VERSIONS)))
    selection = str(cfg.get('selection', tpl['selection'])).strip().lower()
    if selection not in ('auto', 'fixed'):
        raise ValueError("mesh.selection must be 'auto' or 'fixed'.")
    max_attempts = int(cfg.get('max_attempts', tpl['max_attempts']) or 0)
    if max_attempts < 1:
        raise ValueError('mesh.max_attempts must be at least 1.')

    order = str(tpl.get('element_order', 'inherit')).lower()
    if order == 'inherit':
        order = str(params.get('element_order', 'quadratic')).lower()
    if order not in ('linear', 'quadratic'):
        raise ValueError("Effective element order must be 'linear' or 'quadratic'.")
    hex_code = str(tpl.get('linear_hex_code', 'inherit')).upper()
    if hex_code == 'INHERIT':
        hex_code = str(params.get('linear_hex_code', 'C3D8')).upper()
    if hex_code not in ('C3D8', 'C3D8I', 'C3D8R'):
        raise ValueError('Effective linear hex code must be C3D8, C3D8I or C3D8R.')
    quadratic_hex_code = str(
        tpl.get('quadratic_hex_code', 'inherit')).upper()
    if quadratic_hex_code == 'INHERIT':
        quadratic_hex_code = str(
            params.get('quadratic_hex_code', 'C3D20R')).upper()
    if quadratic_hex_code not in ('C3D20', 'C3D20R'):
        raise ValueError('Effective quadratic hex code must be C3D20 or C3D20R.')
    topology = str(cfg.get(
        'topology_requirement',
        tpl.get('topology_requirement', 'MIXED_ALLOWED'))).strip().upper()
    if topology not in MESH_TOPOLOGY_REQUIREMENTS:
        raise ValueError('mesh.topology_requirement %r is unsupported; expected one of %s.' %
                         (topology, ', '.join(MESH_TOPOLOGY_REQUIREMENTS)))
    allow_tet_fallback = topology != 'HEX_ONLY'
    element_profile = mesh_element_profile(
        order, hex_code, quadratic_hex_code, topology)

    targets_override = cfg.get('targets', {}) or {}
    parts_override = cfg.get('parts', {}) or {}
    budgets_override = cfg.get('budgets', {}) or {}
    allowed = tuple(tpl.get('recipe_ids') or ())
    fixed_recipe = str(cfg.get('fixed_recipe', '') or '').strip().upper()
    plan_parts = {}
    for part in MESH_PARTS:
        targets = _merge_copy(tpl.get('targets', _BASE_MESH_TARGETS),
                              targets_override)
        deep_update(targets, (tpl.get('part_targets', {}) or {}).get(part, {}))
        part_override = parts_override.get(part, {}) or {}
        deep_update(targets, part_override.get('targets', {}) or {})
        budgets = _merge_copy(tpl.get('budgets', {}), budgets_override)
        deep_update(budgets, part_override.get('budgets', {}) or {})
        ordered = [rid for rid in MESH_PART_RECIPE_ORDER[part] if rid in allowed]
        if fixed_recipe:
            if fixed_recipe not in MESH_RECIPE_CATALOG:
                raise ValueError('Unknown mesh.fixed_recipe %r.' % fixed_recipe)
            ordered = [fixed_recipe]
        if not ordered:
            raise ValueError('Template %s has no candidate recipe for %s.' %
                             (template_id, part))
        if selection == 'fixed':
            ordered = ordered[:1]
        else:
            ordered = ordered[:max_attempts]
        candidates = []
        part_seed_scale = float(part_override.get('seed_scale', 1.0) or 1.0)
        for index, recipe_id in enumerate(ordered):
            recipe = _json_clone(MESH_RECIPE_CATALOG[recipe_id])
            recipe['recipe_id'] = recipe_id
            recipe['attempt_index'] = index
            recipe['seed_scale'] = (float(recipe.get('seed_scale', 1.0)) *
                                    float(tpl.get('seed_scale', 1.0)) *
                                    part_seed_scale)
            if 'max_repairs' in tpl:
                recipe['max_repairs'] = int(tpl.get('max_repairs', 0) or 0)
            candidates.append(recipe)
        tapered = str(params.get('hub_type', 'cylindrical')).strip().lower() == 'tapered'
        fillet_expected = (not tapered and part in ('Shaft', 'Hub') and
                           bool((params.get('notch', {}) or {}).get('enabled', True)))
        if part == 'Hub':
            fillet_expected = fillet_expected and bool(
                (params.get('notch', {}) or {}).get('apply_to_hub', True))
        plan_parts[part] = {
            'targets': targets,
            'budgets': budgets,
            'fillet_expected': fillet_expected,
            'topology_requirement': topology,
            'allow_tet_fallback': allow_tet_fallback,
            'element_profile': _json_clone(element_profile),
            'candidates': candidates
        }
    return {
        'algorithm_version': algorithm,
        'template': template_id,
        'template_label': tpl.get('label', template_id),
        'description': tpl.get('description', ''),
        'selection': selection,
        'max_attempts': max_attempts,
        'fail_on_quality': bool(cfg.get('fail_on_quality',
                                        tpl.get('fail_on_quality', True))),
        'element_order': order,
        'linear_hex_code': hex_code,
        'quadratic_hex_code': quadratic_hex_code,
        'topology_requirement': topology,
        'allow_tet_fallback': allow_tet_fallback,
        'element_profile': element_profile,
        'parts': plan_parts
    }


def validate_mesh_configuration(params):
    """Return deterministic configuration issues without requiring Abaqus."""
    out = []
    cfg = params.get('mesh', {}) or {}
    template_id = str(cfg.get('template', 'HEX_CERTIFIED')).strip().upper()
    template = MESH_TEMPLATES.get(template_id, {}) or {}
    requested_topology = str(cfg.get(
        'topology_requirement',
        template.get('topology_requirement', 'MIXED_ALLOWED'))).strip().upper()
    if requested_topology not in MESH_TOPOLOGY_REQUIREMENTS:
        out.append({
            'level': 'error', 'code': 'mesh_topology_requirement',
            'msg': 'mesh.topology_requirement %r must be one of %s.' % (
                requested_topology, ', '.join(MESH_TOPOLOGY_REQUIREMENTS))})
        return out
    try:
        plan = resolve_mesh_plan(params)
    except (TypeError, ValueError, KeyError) as exc:
        return [{'level': 'error', 'code': 'mesh_plan_invalid', 'msg': str(exc)}]
    if int(params.get('schema_version', SCHEMA_VERSION)) != SCHEMA_VERSION:
        out.append({'level': 'error', 'code': 'schema_version_mismatch',
                    'msg': 'Parameter schema %r does not match required schema %d.' %
                           (params.get('schema_version'), SCHEMA_VERSION)})
    for part in MESH_PARTS:
        policy = plan['parts'][part]
        targets = policy['targets']
        budgets = policy['budgets']
        if float(targets.get('warn_score', 0.0)) > float(targets.get('pass_score', 0.0)):
            out.append({'level': 'error', 'code': 'mesh_score_thresholds',
                        'msg': '%s warn_score cannot exceed pass_score.' % part})
        try:
            min_hex = float(targets.get('min_hex_pct', 0.0))
        except (TypeError, ValueError):
            min_hex = -1.0
        if not (0.0 <= min_hex <= 100.0):
            out.append({'level': 'error', 'code': 'mesh_hex_target',
                        'msg': '%s min_hex_pct must be between 0 and 100.' % part})
        try:
            max_non_hex = float(targets.get('max_non_hex_pct', 100.0))
        except (TypeError, ValueError):
            max_non_hex = -1.0
        if not (0.0 <= max_non_hex <= 100.0):
            out.append({'level': 'error', 'code': 'mesh_non_hex_target',
                        'msg': '%s max_non_hex_pct must be between 0 and 100.' % part})
        soft = int(budgets.get('soft_elements', 0) or 0)
        hard = int(budgets.get('hard_elements', 0) or 0)
        if soft < 0 or hard <= 0 or (soft and hard < soft):
            out.append({'level': 'error', 'code': 'mesh_budget_invalid',
                        'msg': '%s budgets require 0 <= soft <= hard and hard > 0.' % part})
        for candidate in policy['candidates']:
            if candidate.get('control_strategy') not in MESH_CONTROL_STRATEGIES:
                out.append({'level': 'error', 'code': 'mesh_strategy_invalid',
                            'msg': '%s recipe %s has unsupported strategy %r.' %
                                   (part, candidate.get('recipe_id'),
                                    candidate.get('control_strategy'))})
            if float(candidate.get('seed_scale', 0.0)) <= 0:
                out.append({'level': 'error', 'code': 'mesh_seed_scale_invalid',
                            'msg': '%s recipe %s has a non-positive seed scale.' %
                                   (part, candidate.get('recipe_id'))})
        if policy.get('topology_requirement') == 'HEX_ONLY':
            violations = []
            if abs(min_hex - 100.0) > MESH_TOPOLOGY_TOLERANCE:
                violations.append('min_hex_pct must equal 100')
            if abs(max_non_hex) > MESH_TOPOLOGY_TOLERANCE:
                violations.append('max_non_hex_pct must equal 0')
            forbidden = sorted(set([
                str(candidate.get('recipe_id', ''))
                for candidate in policy['candidates']
                if (candidate.get('recipe_id') in ('FREE_TET', 'HEX_DOMINATED') or
                    candidate.get('control_strategy') in
                    ('TET_FREE', 'HEX_DOMINATED'))]))
            if forbidden:
                violations.append('forbidden recipe(s): %s' % ', '.join(forbidden))
            if violations:
                out.append({
                    'level': 'error', 'code': 'mesh_hex_only_contract',
                    'msg': '%s HEX_ONLY contract violated: %s.' %
                           (part, '; '.join(violations))})
    if not cfg:
        out.append({'level': 'info', 'code': 'mesh_defaults_applied',
                    'msg': 'No mesh block supplied; HEX_CERTIFIED defaults are used.'})
    return out


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def evaluate_mesh_quality(part, metrics, policy):
    """Score one realised mesh from 0..100 and apply non-negotiable gates."""
    metrics = metrics or {}
    policy = policy or {}
    targets = policy.get('targets', {}) or {}
    budgets = policy.get('budgets', {}) or {}
    elements = int(_number(metrics.get('elements', 0), 0))
    failed = int(_number(metrics.get('failed', 0), 0))
    components = int(_number(metrics.get('components', 0), 0))
    warnings = int(_number(metrics.get('warnings', 0), 0))
    hex_pct = max(0.0, min(100.0, _number(metrics.get('hex_pct', 0.0), 0.0)))
    non_hex_pct = max(0.0, min(100.0, _number(
        metrics.get('non_hex_pct', 100.0 - hex_pct), 100.0 - hex_pct)))
    non_hex_count = int(_number(metrics.get('non_hex_count', 0), 0))
    hex_count = int(_number(
        metrics.get('hex_count', max(0, elements - non_hex_count)), 0))
    histogram_count = int(_number(metrics.get('histogram_count', elements), 0))
    topology = str(policy.get(
        'topology_requirement', 'MIXED_ALLOWED')).strip().upper()
    max_non_hex = _number(targets.get('max_non_hex_pct', 100.0), 100.0)
    bulk_ar = _number(metrics.get('ar_bulk_worst',
                                  metrics.get('ar_worst', 0.0)), 0.0)
    repairs = int(_number(metrics.get('repairs', 0), 0))
    hard_budget = int(_number(budgets.get('hard_elements', 0), 0))
    soft_budget = int(_number(budgets.get('soft_elements', 0), 0))
    fillet_expected = bool(policy.get('fillet_expected', False))
    fillet_arc_count = int(_number(metrics.get('fillet_arc_count', 0), 0))
    fillet_band_count = int(_number(metrics.get('fillet_band_count', 0), 0))
    fillet_detected = bool(metrics.get('fillet_detected',
                                       fillet_arc_count > 0))

    hard_reasons = []
    if elements <= 0:
        hard_reasons.append('mesh has no elements')
    if failed > 0:
        hard_reasons.append('%d failed element(s)' % failed)
    if components != 1:
        hard_reasons.append('expected one connected component, found %d' % components)
    if fillet_expected and not fillet_detected:
        hard_reasons.append('expected fillet refinement was not detected')
    if hard_budget > 0 and elements > hard_budget:
        hard_reasons.append('element hard budget exceeded (%d > %d)' %
                            (elements, hard_budget))
    if metrics.get('reproduction_ok') is False:
        hard_reasons.append('selected recipe was not reproducible within declared tolerances')
    if histogram_count != elements:
        hard_reasons.append(
            'element histogram count mismatch (%d != %d)' %
            (histogram_count, elements))
    if hex_count + non_hex_count != elements:
        hard_reasons.append(
            'hex/non-hex count mismatch (%d + %d != %d)' %
            (hex_count, non_hex_count, elements))
    if topology not in MESH_TOPOLOGY_REQUIREMENTS:
        hard_reasons.append('unsupported topology requirement %s' % topology)
    elif topology == 'HEX_ONLY' and (
            non_hex_count > 0 or non_hex_pct > MESH_TOPOLOGY_TOLERANCE):
        hard_reasons.append(
            'HEX_ONLY forbids non-hexahedral elements (%d, %.9f%%)' %
            (non_hex_count, non_hex_pct))
    elif topology == 'HYBRID_HEX':
        if hex_count < 1:
            hard_reasons.append(
                'HYBRID_HEX requires at least one hexahedron per piece')
        if non_hex_pct - max_non_hex > MESH_TOPOLOGY_TOLERANCE:
            hard_reasons.append(
                'HYBRID_HEX non-hex %.3f%% exceeds maximum %.3f%%' %
                (non_hex_pct, max_non_hex))
        min_hex_hard = _number(targets.get('min_hex_pct', 0.0), 0.0)
        if min_hex_hard - hex_pct > MESH_TOPOLOGY_TOLERANCE:
            hard_reasons.append(
                'HYBRID_HEX hex %.3f%% is below minimum %.3f%%' %
                (hex_pct, min_hex_hard))

    score = 100.0
    penalties = []

    def penalise(code, amount, detail):
        nonlocal_holder[0] -= max(0.0, float(amount))
        penalties.append({'code': code, 'points': round(max(0.0, float(amount)), 2),
                          'detail': detail})

    # A one-item list keeps this Python 2.7 compatible (no ``nonlocal`` keyword).
    nonlocal_holder = [score]
    min_hex = _number(targets.get('min_hex_pct', 0.0), 0.0)
    if min_hex > 0 and hex_pct < min_hex:
        penalise('hex_below_target', min(25.0, 25.0 * (min_hex - hex_pct) / min_hex),
                 'hex %.1f%% < target %.1f%%' % (hex_pct, min_hex))
    max_warnings = int(_number(targets.get('max_warnings', 0), 0))
    if warnings > max_warnings:
        penalise('warnings_above_target', min(15.0, (warnings - max_warnings) * 0.75),
                 '%d warnings > target %d' % (warnings, max_warnings))
    max_ar = _number(targets.get('max_bulk_ar', 0.0), 0.0)
    if max_ar > 0 and bulk_ar > max_ar:
        penalise('bulk_ar_above_target', min(25.0, 25.0 * (bulk_ar - max_ar) / max_ar),
                 'bulk AR %.2f > target %.2f' % (bulk_ar, max_ar))
    if soft_budget > 0 and elements > soft_budget:
        penalise('soft_budget_exceeded',
                 min(12.0, 12.0 * (elements - soft_budget) / float(soft_budget)),
                 '%d elements > soft budget %d' % (elements, soft_budget))
    max_repairs = int(_number(targets.get('max_repairs', 0), 0))
    if repairs > max_repairs:
        penalise('repairs_above_target', min(10.0, 2.5 * (repairs - max_repairs)),
                 '%d repairs > target %d' % (repairs, max_repairs))
    if fillet_expected and fillet_detected:
        arc_min = int(_number(targets.get('fillet_arc_min', 0), 0))
        band_min = int(_number(targets.get('fillet_band_min', 0), 0))
        if fillet_arc_count < arc_min:
            penalise('fillet_arcs_below_target', 8.0,
                     '%d fillet arcs < target %d' % (fillet_arc_count, arc_min))
        if fillet_band_count < band_min:
            penalise('fillet_bands_below_target', 8.0,
                     '%d fillet bands < target %d' % (fillet_band_count, band_min))
    score = max(0.0, min(100.0, nonlocal_holder[0]))
    hard_passed = not hard_reasons
    if hard_reasons:
        score = min(score, 39.0)
        status = 'FAIL'
    elif score >= _number(targets.get('pass_score', 75.0), 75.0):
        status = 'PASS'
    elif score >= _number(targets.get('warn_score', 50.0), 50.0):
        status = 'WARN'
    else:
        status = 'FAIL'
    return {
        'part': part,
        'status': status,
        'score': round(score, 2),
        'hard_passed': hard_passed,
        'admissible': hard_passed,
        'hard_reasons': hard_reasons,
        'penalties': penalties,
        'metrics': {
            'nodes': int(_number(metrics.get('nodes', 0), 0)),
            'elements': elements, 'failed': failed, 'warnings': warnings,
            'components': components, 'hex_pct': round(hex_pct, 3),
            'hex_count': hex_count,
            'histogram_count': histogram_count,
            'non_hex_pct': round(non_hex_pct, 9),
            'non_hex_count': non_hex_count,
            'topology_requirement': topology,
            'ar_worst': round(_number(metrics.get('ar_worst', 0.0), 0.0), 3),
            'ar_bulk_worst': round(bulk_ar, 3), 'repairs': repairs,
            'seconds': round(_number(metrics.get('seconds', 0.0), 0.0), 3),
            'fillet_expected': fillet_expected,
            'fillet_detected': fillet_detected,
            'fillet_arc_count': fillet_arc_count,
            'fillet_band_count': fillet_band_count,
            'reproduction_ok': metrics.get('reproduction_ok'),
            'warning_pct': round(100.0 * warnings / max(1, elements), 3)
        },
        'thresholds': dict(_json_clone(targets),
                           topology_requirement=topology,
                           max_non_hex_pct=max_non_hex),
        'budgets': _json_clone(budgets)
    }


def mesh_candidate_rank(attempt, index=0):
    """Comparable tuple with a stable recipe-order tie break.

    Measured wall-clock time is retained for audit/cost reporting but is never a
    selection criterion: scheduler noise must not change the winning recipe.
    """
    quality = attempt.get('quality', {}) or {}
    metrics = quality.get('metrics', attempt.get('metrics', {})) or {}
    status_rank = {'FAIL': 0, 'WARN': 1, 'PASS': 2}.get(
        str(quality.get('status', 'FAIL')).upper(), 0)
    ar_value = _number(metrics.get('ar_bulk_worst',
                                   metrics.get('ar_worst', 1.0e30)), 1.0e30)
    return (
        1 if bool(quality.get('hard_passed', False)) else 0,
        status_rank,
        _number(quality.get('score', 0.0), 0.0),
        _number(metrics.get('hex_pct', 0.0), 0.0),
        -int(_number(metrics.get('warnings', 0), 0)),
        -ar_value,
        -int(_number(metrics.get('elements', 0), 0)),
        -int(index))


def select_best_mesh_candidate(attempts):
    """Select the best measured candidate and explain the deterministic choice."""
    if not attempts:
        raise ValueError('At least one mesh attempt is required for selection.')
    best_index = 0
    best_rank = mesh_candidate_rank(attempts[0], 0)
    for index in range(1, len(attempts)):
        rank = mesh_candidate_rank(attempts[index], index)
        if rank > best_rank:
            best_index, best_rank = index, rank
    selected = attempts[best_index]
    quality = selected.get('quality', {}) or {}
    recipe = selected.get('recipe', {}) or {}
    return {
        'selected_index': best_index,
        'selected_recipe': recipe.get('recipe_id', selected.get('recipe_id', '')),
        'admissible': bool(quality.get('hard_passed', False)),
        'status': quality.get('status', 'FAIL'),
        'score': _number(quality.get('score', 0.0), 0.0),
        'selection_reason': (
            'hard gates -> status -> score -> hex%% -> warnings -> bulk AR -> '
            'element count -> deterministic recipe-order tie break'),
        'rank': list(best_rank)
    }


def aggregate_mesh_quality(part_quality, fail_on_quality=True):
    """Aggregate by worst piece so averages can never hide a failed mesh."""
    names = sorted(part_quality.keys())
    evaluations = [part_quality[name] for name in names]
    statuses = [str(item.get('status', 'FAIL')).upper() for item in evaluations]
    hard_passed = all(bool(item.get('hard_passed', False)) for item in evaluations)
    if 'FAIL' in statuses:
        status = 'FAIL'
    elif 'WARN' in statuses:
        status = 'WARN'
    else:
        status = 'PASS'
    score = min([_number(item.get('score', 0.0), 0.0)
                 for item in evaluations]) if evaluations else 0.0
    passed = hard_passed and (status != 'FAIL' or not bool(fail_on_quality))
    reasons = []
    for name in names:
        item = part_quality[name]
        if item.get('hard_reasons'):
            reasons.append('%s: %s' % (name, '; '.join(item['hard_reasons'])))
        elif str(item.get('status', 'FAIL')).upper() == 'FAIL':
            reasons.append('%s: quality score %.2f below warning threshold' %
                           (name, _number(item.get('score', 0.0), 0.0)))
    return {
        'status': status, 'score': round(score, 2),
        'hard_passed': hard_passed, 'passed': passed,
        'fail_on_quality': bool(fail_on_quality),
        'parts': names, 'reasons': reasons
    }


# =============================================================== parameters
def default_params():
    """Validated D40 design. Every value can be overridden from JSON."""
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {"language": "es"},
        "model_name": "PARAM_MODEL",
        "output_dir": "",
        "save_cae": True,
        "make_preview": True,

        # Configured solid element families:
        #   linear    -> configured C3D8-family hex with optional C3D4 fallback
        #   quadratic -> configured C3D20/C3D20R hex with policy-controlled fallback
        "element_order": "quadratic",     # linear | quadratic
        "linear_hex_code": "C3D8",        # C3D8 | C3D8I | legacy C3D8R
        "quadratic_hex_code": "C3D20R",   # C3D20 | C3D20R

        # Under fallback-capable policies, bad cells may be re-meshed as tets.
        # HEX_ONLY never degrades: empty or repair-requiring cells fail loudly.
        "ar_repair_threshold": 25.0,

        # Versioned automatic mesh policy.  The selected template defines the
        # candidate recipes, topology contract and thresholds; these optional
        # maps only override individual targets/budgets.
        "mesh": {
            "template": "HEX_CERTIFIED",
            "selection": "auto",          # auto | fixed
            "algorithm_version": MESH_ALGORITHM_VERSION,
            "max_attempts": 3,
            "fixed_recipe": "",           # recipe id when selection=fixed
            "fail_on_quality": True,
            "targets": {},                 # global threshold overrides
            "budgets": {},                 # soft_elements / hard_elements
            "parts": {}                    # per-piece targets/budgets/seed_scale
        },

        "compliance_mode": "normative",  # normative | user_override
        "key_form": "A",                  # implemented: A | B | AB
        "groove_form": "N1",              # N1 | N2 | N3 (current solid: N1)
        "hub_type": "cylindrical",        # cylindrical | tapered

        "shaft": {
            # ``diameter_mm`` is the schema-6 canonical name. ``D`` remains a
            # synchronized deprecated backend alias for 4.1/Abaqus scripts.
            "diameter_mm": 40.0,
            "D": 40.0,                    # DEPRECATED ALIAS of diameter_mm
            "L_over_D": 3.0,              # L = 3 * D
            "dz": 38.0,                   # USER, distance between arc centres
            "z0_offset": 5.0,             # z_0 = R_cap + 5
            "R_cap": 0.0,                 # USER, 0 = auto (b/2, end-mill radius)
            "r2": 0.25,                   # USER, keyway root fillet
            "slot_clearance": 0.0,        # width added to the shaft keyway (b + this)
            "seed": 0.0                   # 0 = auto (D/32)
        },
        "key": {
            "l": 0.0,                     # USER, 0 = auto from form
            "c": 0.8,                     # USER, 45 deg corner chamfer
            "chamfer_angle": 45.0,
            "snap_length_to_din": True,   # largest standard l that fits
            "seed": 0.0                   # 0 = auto (b/20)
        },
        "hub": {
            "L_hub": 38.0,                # USER
            # FVA/DIN convention Q_A=d_w/D_outer is canonical in schema 6.
            "QA_shaft_over_outer": 0.5,
            "hub_outer_over_shaft": 2.0,  # DEPRECATED reciprocal backend alias
            "r1": 0.25,                   # USER, hub keyway roof fillet
            "groove_clearance": 0.0215,   # total width clearance in the hub slot
            "seed": 0.0                   # 0 = auto (d_a/80)
        },

        # ---- LOCAL NOTCH REFINEMENT (v3) ----------------------------------
        # A refinement band is PARTITIONED around the keyway root corner, so the
        # notch can be seeded finely without the slender elements that plain arc
        # seeding produced in v2 (there only the tangential size shrank).
        # Inside the band the in-plane size is s_notch = arc_length / arc_elems
        # in BOTH directions; the long axial edges keep the global seed, which is
        # what keeps the element count and the aspect ratio under control.
        # method 'bias' grades the band edges from s_notch at the fillet out to
        # the global seed, so there is no abrupt size jump at the band boundary.
        "notch": {
            "enabled": True,
            "arc_elems": 6,               # divisions on the quarter-circle arc
            "band_factor": 6.0,           # band half-width = this * fillet radius
            "method": "bias",             # bias (graded) | size (uniform)
            # 'band' seeds only the fillet arcs that sit inside a refinement
            # band. 'all' also seeds the arcs on the keyway END CAPS, where no
            # band can be built with principal planes, so only the tangential
            # size shrinks there and the elements become slender - measured on
            # D40: 3.7 k extra elements above the aspect-ratio threshold.
            "arc_scope": "band",          # band (recommended) | all
            "band_max_factor": 3.0,       # coarse end of the band = band / this
            "apply_to_hub": True,         # same treatment on the hub roof fillet
            "axial_factor": 0.0           # >0 also refines axially (expensive)
        },

        # ---- OPTIONAL ANALYSIS STAGE (v3) --------------------------------
        # Default OFF: the model stays NOJOB exactly as before. Switch it on and
        # the builder adds contact, a torsion step, the job, and (if solved)
        # reports the stress concentration factor measured on THIS mesh.
        "analysis": {
            "enabled": False,
            "T_apply": 200.0,             # applied torque [N m]
            "friction": 0.15,             # Coulomb friction, <0 = frictionless
            "nlgeom": False,
            "hold": "hub_outer",          # hub_outer | hub_faces
            "stabilize": True,            # automatic contact stabilisation
            "max_num_inc": 200,
            "initial_inc": 0.1,
            "min_inc": 1e-08,
            "create_job": True,
            "submit": False,              # run the solver right away
            "cpus": 1,
            "post_process": True          # read the ODB and report the SCF
        },

        # ---- MESH DENSITY / QUALITY STUDY --------------------------------
        # Re-meshes the SAME geometry at several seed scales and reports notch
        # size, quality and DOF.  Without solving every scale this is NOT stress
        # or Kt convergence evidence; inadmissible scales are labelled FAIL.
        "study": {
            "enabled": False,
            "seed_scales": [1.6, 1.2, 1.0, 0.8],
            "csv": True
        },

        "preview": {
            "views": ["Iso", "Front", "Right"],
            "notch_zoom": True,
            "width": 1600,
            "height": 1200
        },
        "audit": {"text": True, "json": True},

        # Standards are selectable, but the registry states exactly whether a
        # complete calculation/backend exists. No licensed DIN tables are
        # bundled or silently approximated.
        "standards": {
            "registry_version": din6892.ENGINE_VERSION,
            "selected": {
                "geometry": "DIN_6885_1_2021",
                "strength": "DIN_6892",
                "fatigue": "DIN_743",
                "fit": "DIN_EN_ISO_286",
                "hardness": "DIN_EN_ISO_18265",
                "friction_closure": "DIN_7190_1",
                "key_material": "DIN_6880"
            },
            "registry": din6892.standard_registry()
        },

        # One calculation source for DIN 6892 A/B/C and the FVA 2025 Method-B
        # proposal. Values tied to licensed diagrams remain explicit inputs.
        "din6892": {
            "enabled": True,
            "method": din6892.METHOD_B_CURRENT,
            "variant_id": "VB1",
            "apply_variant_geometry": False,
            "material_pair": "C45N_C45N",
            "use_fva_material_data": True,
            "load_cycles": 10000,
            "load_ratio_R": 0.0,
            # DIN 6892 equation 3 is driven by N_W, the number of LOAD DIRECTION
            # reversals, not by the load cycle count: f_W penalises the key
            # alternately bearing on both keyway flanks. null derives N_W from
            # load_ratio_R (R >= 0 pulsating -> no reversal -> f_W = 1).
            "N_W": None,
            "key_count": 1,
            "phi": 1.0,
            # K_lambda is read from a DIN 6892 diagram (range 1.0 .. 2.0) and has
            # no closed form, so 1.0 stays an explicit placeholder.
            "K_lambda": 1.0,
            # K_R = 1 is the FVA 600 III corrected value: a superposed
            # interference fit does not raise the quasi-static torque.
            "K_R": 1.0,
            # null lets DIN 6892 Table 2 supply f_S/f_H from the material class.
            "f_H": None,
            "f_S": None,
            "safety_factor": 1.2,
            "UPF_um": 18.0,
            "xi_per_mille": 0.0,
            # DIN 6892 equation 9 subtracts the chamfer s1 from the effective
            # bearing depth. null means "take the chamfer the geometry actually
            # has"; a number overrides it. Leaving it at 0 silently overstates
            # t1tr and therefore every Method B/C torque.
            "chamfer_s1_mm": None,
            # Chamfer bounding the HUB keyway flank; null takes the key chamfer.
            "chamfer_s2_mm": None,
            # Which effective shaft bearing depth the pressure checks use.
            # EQUATION_9 keeps the transcribed standard, GEOMETRIC uses the
            # independent flank height and CONSERVATIVE takes the smaller value.
            "bearing_depth_policy": din6892.DEPTH_POLICY_EQUATION_9,
            "v": 0.5,
            # DIN 6892 Table 2 material classes per component. They resolve f_S
            # and f_H from the standard's own table instead of a neutral 1.0.
            "material_classes": {
                "shaft": din6892.DEFAULT_MATERIAL_CLASS,
                "hub": din6892.DEFAULT_MATERIAL_CLASS,
                "key": din6892.DEFAULT_MATERIAL_CLASS
            },
            # DIN 6892 requires the smaller tabulated f_S when the material is
            # not known with certainty.
            "f_S_bound": "lower",
            # Peak-load branch of DIN 6892 Method B: p_max,zul = f_L * p_zul.
            # null disables the branch.
            "f_L": None,
            # Applied equivalent torque; enables the safety S_Feq of equation 1.
            "torque_applied_Nm": None,
            # Application factor of the driven machine: M_teq = K_A * M_t,nom.
            # Supplying torque_nominal_Nm builds the equivalent torque instead
            # of requiring the user to multiply by hand.
            "K_A": 1.0,
            "torque_nominal_Nm": None,
            # Rare peak torque, checked against p_max,zul = f_L * p_zul.
            "torque_peak_applied_Nm": None,
            # Method C sizing target; null reuses torque_applied_Nm.
            "torque_required_Nm": None,
            # Which of the three DIN 6892 K_lambda diagrams the reading came
            # from, and optionally the load derivation distance a_0.
            "load_derivation_position": din6892.LOAD_DERIVATION_REAR,
            "a0_mm": None,
            # Method C allowable pressure variant: the published DIN 0.9*Re_min
            # or the FVA 600 III equation 32 proposal without the reduction.
            "method_c_variant": din6892.METHOD_C_VARIANT_DIN,
            # DIN 7190-1 minimum slip torque, used by equation 12 for K_Req.
            "slip_torque_min_Nm": None,
            "apply_fva_friction_correction": True,
            # The analytical methods are cheap and mutually informative, so they
            # are always evaluated next to the selected primary method. Method A
            # is never a companion because it needs solved FE evidence.
            "companion_methods": list(din6892.ANALYTICAL_METHOD_IDS),
            # A licensed factor left at the neutral value 1.0 is a placeholder.
            # Set this to True only after the licensed values were reviewed.
            "factors_acknowledged": False,
            "factor_provenance": {
                "K_lambda": EVIDENCE_USER_INPUT,
                "K_R": EVIDENCE_FVA_RESEARCH,
                "f_H": EVIDENCE_DIN_METHOD,
                "f_S": EVIDENCE_DIN_METHOD,
                "phi": EVIDENCE_DIN_METHOD
            },
            "method_a": {
                "delta_volume_mm3": None,
                "cycles": 0,
                "minimum_cycles": 10,
                "unloaded_frame_verified": False,
                "source_frame_identified": False,
                "coverage_within_2_percent": False,
                "invariants_revalidated": False,
                "provenance_hash_verified": False,
                "matching_mesh_verified": False,
                "mesh_convergence_verified": False,
                "equilibrium_verified": False,
                "contact_verified": False,
                "din743_verified": False,
                "trials": [],
                "postprocess": None
            }
        },

        # Fast engineering screening retained for compatibility with 4.1.
        "design_check": {
            "enabled": True,
            "evidence_badge": EVIDENCE_CORE_SCREENING,
            "method_label": "Uniform-bearing pressure screening (not DIN 6892 Method B)",
            "T_nom": 200.0,           # nominal torque [N m]
            "T_max": 0.0,             # peak torque [N m], 0 = same as T_nom
            "n_keys": 1,              # number of keys
            "load_distribution": 1.0,  # >1 per DIN 6892 method B; 1.0 = uniform
            "p_perm_shaft": 0.0,      # allowable pressure [MPa], 0 = 1.0*Re
            "p_perm_hub": 0.0
        },

        # legacy tapered variant (only used when hub_type == "tapered")
        "bushing": {
            "length": 38.0,
            "outer_dia_small": 60.0,
            "outer_dia_large": 63.8,
            "seed": 0.9
        },

        # Grade is C45 for all three (documented in the audit; the model itself
        # stays linear elastic, so Re and Rm are reference information only).
        # Rm is required by FVA equation 33 (f_WS = Rm/Re) whenever the discrete
        # FVA material catalogue is switched off; replace both with certified
        # values before quoting a result.
        "materials": {
            MAT_SHAFT: {"grade": "C45", "E": 210000.0, "nu": 0.30,
                        "rho": 7.85e-09, "Re": 430.0, "Rm": 700.0},
            MAT_HUB:   {"grade": "C45", "E": 210000.0, "nu": 0.30,
                        "rho": 7.85e-09, "Re": 430.0, "Rm": 700.0},
            MAT_KEY:   {"grade": "C45", "E": 210000.0, "nu": 0.30,
                        "rho": 7.85e-09, "Re": 430.0, "Rm": 700.0}
        },

        # Dedicated FVA 600 III Method-A workflow.  The default backend builds
        # the connected cylindrical shaft/key/hub model with a verified contact
        # mesh and 20 load cycles, but remains safe NOJOB until explicitly
        # changed.  The immutable one-cycle conical regression backend is still
        # available through its named preset.
        "fva_600_iii": {
            "enabled": False,
            "evidence_badge": EVIDENCE_FVA_RESEARCH,
            "source_id": din6892.SOURCE_FVA,
            "variant_id": "VB1",
            "material_pair": "C45N_C45N",
            "requested_method": din6892.METHOD_A,
            "backend": din6892.BACKEND_METHOD_A_HYBRID_HEX,
            "backend_capability": "METHOD_A_HYBRID_HEX_MATCHED_OPTIONAL_JOB",
            "workflow": "method_a_numerical",
            "method": "din6892_method_a_fva600",
            "is_complete_method_a": False,
            "cycles": 20,
            "method_a_min_cycles": 10,
            "recommended_cycles": 20,
            "recommended_safety_factor": 1.2,
            "v_crit": 0.5,
            "strict_no_job": True,
            "torque_Nm": 1256.0,
            "density_tonne_per_mm3": 7.85e-09,
            "mesh_matching": {
                "required": True,
                "target_size_mm": 0.8,
                "tolerance_mm": 1.0e-6,
                "coordinate_decimals": 6,
                "interfaces": [
                    "SHAFT_KEY_LEFT", "SHAFT_KEY_RIGHT",
                    "HUB_KEY_LEFT", "HUB_KEY_RIGHT", "SHAFT_HUB"
                ],
                "verify_after_meshing": True
            },
            "material_models": {
                "shaft": din6892.SHAFT_MODEL_COMBINED,
                "hub": din6892.HUB_MODEL_UML,
                "key": din6892.MODEL_ELASTIC_IDEAL_PLASTIC
            },
            "execution": {
                "create_job": False,
                "submit_solver": False,
                "job_name": "",
                "cpus": 1,
                "precision": "SINGLE"
            },
            "contact": {
                "interference_total_mm": 0.018,
                "interference_per_flank_mm": 0.009,
                "interference_distribution": "HALF_PER_FLANK",
                "interference_ramp": True,
                "friction_fit": 0.0001,
                "friction_service": 0.2,
                "elastic_slip_mm": 0.001,
                "normal_stiffness_N_per_mm3": 1.0e7,
                "finite_sliding": True
            },
            "steps": {
                "contact_time_s": 1.0,
                "contact_increment_s": 0.05,
                "friction_time_s": 1.0,
                "cycle_period_s": 2.0,
                "cycle_time_s": 2.0
            },
            # Explicit values retained solely for the immutable legacy backend.
            "materials": {
                "shaft": {"E_MPa": 187000.0, "nu": 0.30,
                          "Re_MPa": 378.0, "Qinf_MPa": 32.74,
                          "b_iso": 249.8, "C1_MPa": 15260.0,
                          "gamma1": 50.8},
                "hub": {"E_MPa": 196000.0, "nu": 0.30,
                        "Re_MPa": 279.0743851, "Rm_MPa": 579.0,
                        "K_prime_MPa": 955.0, "n_prime": 0.15,
                        "intervals": 150},
                "key": {"E_MPa": 210000.0, "nu": 0.30,
                        "yield_MPa": 928.0}
            }
        },

        # Optional companion for exchange with MATLAB. Python remains the
        # authoritative postprocessor; RUN is opt-in and never uses a shell.
        "matlab": {
            "mode": "OFF",
            "executable": "matlab",
            "timeout_s": 300,
            "bundle_dir": "",
            "entry_function": "fva600_method_a_bundle",
            "keep_bundle": True
        }
    }


PRESETS = {
    "D25 - small joint":      {"shaft": {"D": 25.0, "dz": 24.0}, "hub": {"L_hub": 25.0}},
    "D40 - validated default": {"mesh": {"template": "HEX_CERTIFIED",
                                              "selection": "auto", "max_attempts": 3,
                                              "fail_on_quality": True},
                                  "element_order": "quadratic",
                                  "quadratic_hex_code": "C3D20R"},
    "Mesh - hex certified": {"mesh": {"template": "HEX_CERTIFIED",
                                             "selection": "auto", "max_attempts": 3,
                                             "fail_on_quality": True},
                                  "element_order": "quadratic",
                                  "quadratic_hex_code": "C3D20R"},
    "Mesh - FVA Method A hybrid": {"mesh": {"template": "FVA_METHOD_A_HYBRID",
                                                   "selection": "fixed", "max_attempts": 1,
                                                   "fail_on_quality": True},
                                        "element_order": "quadratic",
                                        "quadratic_hex_code": "C3D20R"},
    "Mesh - automatic balanced": {"mesh": {"template": "AUTO_BALANCED",
                                                "selection": "auto", "max_attempts": 4,
                                                "fail_on_quality": True}},
    "Mesh - quality critical": {"mesh": {"template": "QUALITY_CRITICAL",
                                              "selection": "auto", "max_attempts": 5,
                                              "fail_on_quality": True}},
    "Mesh - fast preview": {"mesh": {"template": "FAST_PREVIEW",
                                          "selection": "auto", "max_attempts": 2,
                                          "fail_on_quality": False}},
    "Mesh - hex dominant": {"mesh": {"template": "HEX_DOMINANT",
                                          "selection": "auto", "max_attempts": 5,
                                          "fail_on_quality": True}},
    "Mesh - quadratic accuracy": {"mesh": {"template": "QUADRATIC_ACCURACY",
                                                "selection": "auto", "max_attempts": 4,
                                                "fail_on_quality": True}},
    "Mesh - robust fallback": {"mesh": {"template": "ROBUST_FALLBACK",
                                             "selection": "fixed", "max_attempts": 1,
                                             "fail_on_quality": True}},
    "D50 - next DIN band":    {"shaft": {"D": 50.0, "dz": 48.0},
                                 "hub": {"L_hub": 48.0, "r1": 0.40}},
    "D40 quadratic (C3D20)":  {"element_order": "quadratic",
                               "quadratic_hex_code": "C3D20",
                               "shaft": {"seed": 2.0}, "hub": {"seed": 2.0},
                               "key": {"seed": 1.0}},
    "D40 + torsion analysis": {"analysis": {"enabled": True, "submit": False}},
    "FVA 600 III research - D40 pre-solve - 1 LW - NOJOB": {
        "model_name": "D40_FVA600_RESEARCH_PRESOLVE_1LW_NOJOB",
        "hub_type": "tapered",
        "element_order": "quadratic",
        "key": {"l": 38.0, "snap_length_to_din": False},
        "hub": {"hub_outer_over_shaft": 2.0},
        "analysis": {"enabled": False, "create_job": False,
                     "submit": False},
        "study": {"enabled": False},
        "din6892": {"enabled": True, "method": din6892.METHOD_A,
                     "variant_id": "VB1", "material_pair": "C45N_C45N"},
        "fva_600_iii": {
            "enabled": True, "cycles": 1,
            "backend": din6892.BACKEND_LEGACY_D40,
            "backend_capability": "LEGACY_PARTIAL_VB1_C45_1LW_NOJOB",
            "workflow": "pre_solve_regression",
            "method": "research_method_a_setup",
            "variant_id": "VB1", "material_pair": "C45N_C45N",
            "requested_method": din6892.METHOD_A,
            "strict_no_job": True,
            "execution": {"create_job": False, "submit_solver": False}
        }
    },
    "FVA 600 III Method A - D40 matched - 20 LW - NOJOB": {
        "model_name": "D40_FVA600_METHOD_A_20LW_MATCHED_NOJOB",
        "hub_type": "cylindrical",
        "element_order": "quadratic",
        "quadratic_hex_code": "C3D20R",
        "mesh": {"template": "FVA_METHOD_A_HYBRID",
                 "selection": "fixed", "fixed_recipe": "HEX_DOMINATED",
                 "algorithm_version": MESH_ALGORITHM_VERSION,
                 "max_attempts": 1, "fail_on_quality": True},
        "key_form": "A",
        "shaft": {"diameter_mm": 40.0, "D": 40.0, "dz": 38.0,
                  "R_cap": 0.0},
        "key": {"l": 50.0, "snap_length_to_din": False, "seed": 0.8},
        "hub": {"L_hub": 38.0, "QA_shaft_over_outer": 0.5,
                "hub_outer_over_shaft": 2.0, "seed": 0.8},
        "analysis": {"enabled": False, "create_job": False,
                     "submit": False},
        "study": {"enabled": False},
        "din6892": {"enabled": True, "method": din6892.METHOD_A,
                     "variant_id": "VB1", "material_pair": "C45N_C45N",
                     "apply_variant_geometry": True, "load_ratio_R": 0.0},
        "fva_600_iii": {
            "enabled": True, "cycles": 20,
            "backend": din6892.BACKEND_METHOD_A_HYBRID_HEX,
            "backend_capability": "METHOD_A_HYBRID_HEX_MATCHED_OPTIONAL_JOB",
            "workflow": "method_a_numerical",
            "method": "din6892_method_a_fva600",
            "variant_id": "VB1", "material_pair": "C45N_C45N",
            "requested_method": din6892.METHOD_A,
            "strict_no_job": True,
            "mesh_matching": {"required": True, "target_size_mm": 0.8,
                              "tolerance_mm": 1.0e-6,
                              "verify_after_meshing": True},
            "execution": {"create_job": False, "submit_solver": False}
        }
    },
}


def deep_update(base, extra):
    """Recursive dict update; lists and scalars are replaced, dicts merged."""
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _json_clone(value):
    """Dependency-free deep copy that is identical on Python 2.7 and 3."""
    return json.loads(json.dumps(value))


def _migration_record(params, source_schema, actions):
    params["_migration"] = {
        "source_schema": int(source_schema),
        "target_schema": SCHEMA_VERSION,
        "applied": int(source_schema) != SCHEMA_VERSION,
        "actions": list(actions),
        "aliases_are_deprecated": True,
    }


def migrate_params(payload):
    """Migrate a raw parameter document to schema 6 before defaults are mixed in.

    The original schema is inspected first. Future schemas and pre-4.1 schemas
    are rejected rather than being relabelled as current. The function is
    idempotent: applying it to schema 6 preserves values and records no schema
    transition.
    """
    if not isinstance(payload, dict):
        raise ValueError("Parameter document must be a JSON object.")
    if "schema_version" not in payload:
        raise ValueError("Parameter schema_version is required; expected 5 or 6.")
    try:
        source_schema = int(payload.get("schema_version"))
    except (TypeError, ValueError):
        raise ValueError("Parameter schema_version must be an integer.")
    if source_schema > SCHEMA_VERSION:
        raise ValueError(
            "Unsupported future parameter schema %d; this builder supports schema %d."
            % (source_schema, SCHEMA_VERSION))
    if source_schema < PREVIOUS_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported legacy parameter schema %d; migrate it with Model Builder 4.1 first."
            % source_schema)
    migrated = _json_clone(payload)
    migrated.pop("_derived", None)
    migrated.pop("_mesh_plan", None)
    actions = []
    if source_schema == PREVIOUS_SCHEMA_VERSION:
        project = migrated.setdefault("project", {})
        if not project.get("language"):
            project["language"] = "es"
            actions.append("project.language=es")

        shaft = migrated.setdefault("shaft", {})
        if "D" in shaft and "diameter_mm" not in shaft:
            shaft["diameter_mm"] = shaft["D"]
            actions.append("shaft.D -> shaft.diameter_mm (deprecated alias retained)")

        hub = migrated.setdefault("hub", {})
        legacy_outer = None
        if "hub_outer_over_shaft" in hub:
            legacy_outer = hub.get("hub_outer_over_shaft")
        elif "QA" in hub:
            # In 4.1 QA meant D_outer/d_w, opposite to FVA's Q_A convention.
            legacy_outer = hub.get("QA")
            hub["hub_outer_over_shaft"] = legacy_outer
            actions.append("hub.QA -> hub.hub_outer_over_shaft (4.1 convention)")
        if legacy_outer is not None:
            outer = float(legacy_outer)
            if outer <= 0.0:
                raise ValueError("hub_outer_over_shaft must be positive during migration.")
            hub["QA_shaft_over_outer"] = 1.0 / outer
            actions.append(
                "reciprocal hub ratio -> hub.QA_shaft_over_outer (FVA/DIN convention)")

        fva = migrated.get("fva_600_iii") or {}
        if fva:
            fva.setdefault("variant_id", "VB1")
            fva.setdefault("material_pair", "C45N_C45N")
            fva.setdefault("requested_method", din6892.METHOD_A)
            # Schema-5 FVA documents referred only to the immutable conical
            # one-cycle route.  Preserve that meaning explicitly instead of
            # inheriting the new schema-6 default backend.
            fva.setdefault("backend", din6892.BACKEND_LEGACY_D40)
            fva.setdefault("backend_capability", "LEGACY_PARTIAL_VB1_C45_1LW_NOJOB")
            fva.setdefault("workflow", "pre_solve_regression")
            fva.setdefault("strict_no_job", True)
            fva.setdefault("execution", {"create_job": False,
                                         "submit_solver": False})
            if bool(fva.get("enabled", False)):
                din_cfg = migrated.setdefault("din6892", {})
                din_cfg.setdefault("enabled", True)
                din_cfg.setdefault("method", din6892.METHOD_A)
                din_cfg.setdefault("variant_id", fva["variant_id"])
                din_cfg.setdefault("material_pair", fva["material_pair"])
                actions.append("legacy FVA selection mapped to DIN 6892 Method A")
            actions.append("FVA legacy route labelled VB1/C45/partial backend")
        migrated["schema_version"] = SCHEMA_VERSION
    existing_migration = migrated.get("_migration")
    if not (source_schema == SCHEMA_VERSION and
            isinstance(existing_migration, dict) and
            int(existing_migration.get("target_schema", -1)) == SCHEMA_VERSION):
        _migration_record(migrated, source_schema, actions)
    return migrated


def _synchronize_geometry_aliases(params):
    """Synchronize schema-6 canonical geometry names and legacy backend aliases.

    A conflict is only auto-resolved when one side still equals the documented
    default, which identifies a single legacy/canonical override. Two genuinely
    different non-default values are rejected instead of silently choosing one.
    """
    actions = []
    shaft = params.setdefault("shaft", {})
    canonical_d = shaft.get("diameter_mm")
    legacy_d = shaft.get("D")
    if canonical_d is None and legacy_d is None:
        canonical_d = legacy_d = 40.0
        actions.append("shaft diameter defaulted to 40 mm")
    elif canonical_d is None:
        canonical_d = legacy_d
        actions.append("shaft.D promoted to shaft.diameter_mm")
    elif legacy_d is None:
        legacy_d = canonical_d
        actions.append("shaft.D backend alias generated")
    canonical_d = float(canonical_d)
    legacy_d = float(legacy_d)
    if abs(canonical_d - legacy_d) > 1e-12:
        if abs(canonical_d - 40.0) <= 1e-12:
            canonical_d = legacy_d
            actions.append("shaft.D legacy override promoted")
        elif abs(legacy_d - 40.0) <= 1e-12:
            legacy_d = canonical_d
            actions.append("shaft.D synchronized from canonical diameter_mm")
        else:
            raise ValueError(
                "Conflicting shaft.diameter_mm=%r and deprecated shaft.D=%r."
                % (canonical_d, legacy_d))
    shaft["diameter_mm"] = canonical_d
    shaft["D"] = canonical_d

    hub = params.setdefault("hub", {})
    canonical_q = hub.get("QA_shaft_over_outer")
    legacy_outer = hub.get("hub_outer_over_shaft")
    if legacy_outer is None and hub.get("QA") is not None:
        legacy_outer = hub.get("QA")
        actions.append("hub.QA interpreted with 4.1 outer/shaft convention")
    if canonical_q is None and legacy_outer is None:
        canonical_q, legacy_outer = 0.5, 2.0
        actions.append("hub ratio defaulted to Q_A=0.5")
    elif canonical_q is None:
        legacy_outer = float(legacy_outer)
        if legacy_outer <= 0.0:
            raise ValueError("hub_outer_over_shaft must be positive.")
        canonical_q = 1.0 / legacy_outer
        actions.append("legacy hub ratio converted to Q_A=d_w/D_outer")
    elif legacy_outer is None:
        canonical_q = float(canonical_q)
        if canonical_q <= 0.0:
            raise ValueError("QA_shaft_over_outer must be positive.")
        legacy_outer = 1.0 / canonical_q
        actions.append("hub backend ratio generated from canonical Q_A")
    canonical_q = float(canonical_q)
    legacy_outer = float(legacy_outer)
    if canonical_q <= 0.0 or legacy_outer <= 0.0:
        raise ValueError("Hub diameter ratios must be positive.")
    reciprocal = 1.0 / legacy_outer
    if abs(canonical_q - reciprocal) > 1e-12:
        if abs(canonical_q - 0.5) <= 1e-12:
            canonical_q = reciprocal
            actions.append("legacy hub_outer_over_shaft override promoted")
        elif abs(legacy_outer - 2.0) <= 1e-12:
            legacy_outer = 1.0 / canonical_q
            actions.append("backend hub ratio synchronized from canonical Q_A")
        else:
            raise ValueError(
                "Conflicting hub.QA_shaft_over_outer=%r and deprecated "
                "hub.hub_outer_over_shaft=%r."
                % (canonical_q, legacy_outer))
    hub["QA_shaft_over_outer"] = canonical_q
    hub["hub_outer_over_shaft"] = 1.0 / canonical_q
    params["_alias_provenance"] = {
        "canonical": ["shaft.diameter_mm", "hub.QA_shaft_over_outer"],
        "deprecated": ["shaft.D", "hub.hub_outer_over_shaft", "hub.QA"],
        "actions": actions,
    }
    return params


def normalize_params(payload, base=None):
    """Return one complete schema-6 document after explicit migration."""
    migrated = migrate_params(payload)
    defaults = _json_clone(base if base is not None else default_params())
    if int(defaults.get("schema_version", -1)) != SCHEMA_VERSION:
        raise ValueError("Normalization base must use schema %d." % SCHEMA_VERSION)
    deep_update(defaults, migrated)
    defaults["schema_version"] = SCHEMA_VERSION
    _synchronize_geometry_aliases(defaults)
    return to_str(defaults)


def to_str(obj):
    """JSON gives unicode; the Abaqus 2.7 API rejects it for name arguments."""
    if isinstance(obj, dict):
        return dict((to_str(k), to_str(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return type(obj)(to_str(x) for x in obj)
    try:
        uni = unicode           # noqa: F821  (Python 2 only)
    except NameError:
        uni = None
    if uni is not None and isinstance(obj, uni):
        try:
            return obj.encode('ascii')
        except UnicodeEncodeError:
            return obj.encode('utf-8')
    return obj


# keep the old private name working for anything that imported it
_to_str = to_str


def read_json(path):
    f = open(path, 'r')
    try:
        return json.load(f)
    finally:
        f.close()


def write_json(path, obj):
    f = open(path, 'w')
    try:
        json.dump(obj, f, indent=2, sort_keys=True)
    finally:
        f.close()
    return path


def params_from_json(path, base=None):
    """Read the raw JSON schema first, then migrate and merge defaults."""
    if path and os.path.isfile(path):
        return normalize_params(read_json(path), base=base)
    if base is not None:
        return normalize_params(base)
    return normalize_params(default_params())


# =============================================================== derive
def _auto_seed(value, auto):
    """0 or negative means 'let the builder choose'."""
    try:
        v = float(value or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    return (v, False) if v > 0 else (float(auto), True)


def _derive_din6892(params, d):
    """Build one requested/derived/realized DIN 6892 evidence record."""
    cfg = params.get('din6892', {}) or {}
    fva_cfg = params.get('fva_600_iii', {}) or {}
    method_id = str(cfg.get('method', din6892.METHOD_B_CURRENT)).strip().upper()
    record = {
        'enabled': bool(cfg.get('enabled', False)),
        'engine_version': din6892.ENGINE_VERSION,
        'requested': {
            'method': method_id,
            'variant_id': str(cfg.get('variant_id', 'VB1')).strip().upper(),
            'material_pair': str(cfg.get('material_pair', 'C45N_C45N')).strip().upper(),
            'use_fva_material_data': bool(cfg.get('use_fva_material_data', True)),
            'load_ratio_R': float(cfg.get('load_ratio_R', 0.0) or 0.0),
            'UPF_um': float(cfg.get('UPF_um', 18.0) or 0.0),
            'xi_per_mille': float(cfg.get('xi_per_mille', 0.0) or 0.0),
            'backend': str(fva_cfg.get(
                'backend', din6892.BACKEND_METHOD_A_HYBRID_HEX)),
            'cycles': int(fva_cfg.get('cycles', 0) or 0),
            'material_models': _json_clone(
                fva_cfg.get('material_models', din6892.DEFAULT_MATERIAL_MODELS)),
            'mesh_matching': _json_clone(fva_cfg.get('mesh_matching', {})),
            'execution': _json_clone(fva_cfg.get('execution', {})),
            'matlab': _json_clone(params.get('matlab', {})),
            'standards': _json_clone((params.get('standards', {}) or {}).get('selected', {})),
        },
        'derived': {'geometry_trend': din6892.geometry_trend_table()},
        'realized': din6892.assess_backend_request(fva_cfg),
        'calculation': None,
        'issues': [],
    }
    if not record['enabled']:
        record['status'] = 'DISABLED'
        return record
    try:
        variant_data = din6892.derive_variant(
            record['requested']['variant_id'], d['b'], cfg.get('UPF_um', 18.0),
            fva_cfg.get('torque_Nm', cfg.get('torque_max_Nm', 1256.0)))
        record['derived']['variant'] = variant_data
    except (TypeError, ValueError, KeyError) as exc:
        record['issues'].append({'level': 'error', 'code': 'fva_variant_invalid',
                                 'msg': str(exc)})
        variant_data = None

    # DIN 6892 equation 9 subtracts the chamfer s1 from the effective bearing
    # depth. The geometry actually carries the key chamfer c, so defaulting s1 to
    # zero overstates t1tr and inflates every Method B/C torque. null in the
    # parameters therefore means "use the chamfer this joint really has".
    raw_chamfer = cfg.get('chamfer_s1_mm')
    if raw_chamfer in (None, ''):
        chamfer_s1 = float(d.get('c', 0.0) or 0.0)
        chamfer_source = 'GEOMETRY_KEY_CHAMFER'
    else:
        chamfer_s1 = float(raw_chamfer)
        chamfer_source = 'EXPLICIT_INPUT'
    record['derived']['chamfer_s1_mm'] = chamfer_s1
    record['derived']['chamfer_s1_source'] = chamfer_source
    if chamfer_source == 'EXPLICIT_INPUT' and chamfer_s1 <= 0.0 < float(
            d.get('c', 0.0) or 0.0):
        record['issues'].append({
            'level': 'warn', 'code': 'din6892_chamfer_s1_ignored',
            'msg': ('Equation 9 is being evaluated with s1 = 0 although the key '
                    'carries a %.3f mm chamfer; the effective bearing depth t1tr '
                    'and every derived torque are overstated.'
                    % float(d.get('c', 0.0) or 0.0))})
    effective = None
    try:
        effective = din6892.effective_bearing_depth(
            d['t1'], d['D'], d['b'], d['r2'], chamfer_s1)
        record['derived']['effective_bearing_depth'] = effective
    except (TypeError, ValueError, KeyError) as exc:
        record['issues'].append({'level': 'error', 'code': 'din6892_t1tr_invalid',
                                 'msg': str(exc)})

    # DIN 6892 checks the HUB keyway flank on its own bearing depth t2tr. The
    # hub keyway sits in a concave bore and is bounded by the roof fillet r1, the
    # key top chamfer and the radial top clearance g_c = t1 + t2 - h. Without
    # this value the hub would be checked with the shaft depth t1tr, which
    # overstates the hub bearing area because DIN 6885 gives t2 < t1.
    hub_effective = None
    raw_chamfer_s2 = cfg.get('chamfer_s2_mm')
    if raw_chamfer_s2 in (None, ''):
        chamfer_s2 = float(d.get('c', 0.0) or 0.0)
        chamfer_s2_source = 'GEOMETRY_KEY_CHAMFER'
    else:
        chamfer_s2 = float(raw_chamfer_s2)
        chamfer_s2_source = 'EXPLICIT_INPUT'
    record['derived']['chamfer_s2_mm'] = chamfer_s2
    record['derived']['chamfer_s2_source'] = chamfer_s2_source
    try:
        hub_effective = din6892.hub_effective_bearing_depth(
            d['t2'], d['D'], d['b'], d['r1'], chamfer_s2,
            max(0.0, float(d.get('g_c', 0.0) or 0.0)))
        record['derived']['hub_effective_bearing_depth'] = hub_effective
    except (TypeError, ValueError, KeyError) as exc:
        record['issues'].append({
            'level': 'warn', 'code': 'din6892_t2tr_invalid',
            'msg': ('The hub bearing depth t2tr could not be evaluated (%s), so '
                    'the hub keyway falls back to the shaft depth t1tr and its '
                    'result is optimistic.' % exc)})

    material = None
    if bool(cfg.get('use_fva_material_data', True)):
        try:
            material = din6892.material_properties(
                record['requested']['material_pair'], d['D'])
        except (TypeError, ValueError, KeyError) as exc:
            level = 'error' if method_id == din6892.METHOD_B_FVA else 'warn'
            record['issues'].append({
                'level': level, 'code': 'fva_material_point_unavailable',
                'msg': str(exc)})
    if material is None:
        # The FVA reformulation was calibrated on the discrete FVA material
        # catalogue, but refusing to fall back left it returning INVALID_INPUT
        # with no issue at all. Falling back and saying so is honest; staying
        # silent is not.
        mats = params.get('materials', {}) or {}
        shaft = mats.get(MAT_SHAFT, {}) or {}
        hub = mats.get(MAT_HUB, {}) or {}
        key = mats.get(MAT_KEY, {}) or {}
        material = {
            'pair_id': 'MODEL_MATERIAL_INPUTS',
            'label': 'Model material inputs (not FVA table data)',
            'shaft': {'Re_MPa': float(shaft.get('Re', 0.0) or 0.0),
                      'Rm_MPa': float(shaft.get('Rm', 0.0) or 0.0)},
            'hub': {'Re_MPa': float(hub.get('Re', 0.0) or 0.0),
                    'Rm_MPa': float(hub.get('Rm', 0.0) or 0.0)},
            'key': {'yield_MPa': float(key.get('Re', 0.0) or 0.0)},
            'badge': EVIDENCE_USER_INPUT,
            'source_id': 'MODEL_MATERIAL_INPUTS',
            'interpolated': False,
        }
    record['derived']['material'] = material
    record['derived']['material_source'] = (
        (material or {}).get('source_id') or 'UNRESOLVED')
    if (method_id == din6892.METHOD_B_FVA and material is not None and
            str((material or {}).get('source_id')) != din6892.SOURCE_FVA):
        record['issues'].append({
            'level': 'warn', 'code': 'din6892_material_source_not_fva',
            'msg': ('The FVA 600 III Method-B reformulation is being evaluated '
                    'with %s instead of the discrete FVA material catalogue it '
                    'was calibrated on.' % (material.get('label') or 'other data'))})
    if (bool(fva_cfg.get('enabled', False)) and
            str(fva_cfg.get('backend', '')) in (
                din6892.BACKEND_METHOD_A_CONNECTED,
                din6892.BACKEND_METHOD_A_HYBRID_HEX)):
        try:
            intervals = int(((fva_cfg.get('materials', {}) or {}).get(
                'hub', {}) or {}).get('intervals', 150) or 150)
            record['derived']['material_model_bundle'] = \
                din6892.material_model_bundle(
                    record['requested']['material_pair'], d['D'],
                    fva_cfg.get('material_models', {}), intervals)
        except (TypeError, ValueError, KeyError) as exc:
            record['issues'].append({
                'level': 'error', 'code': 'fva_material_model_invalid',
                'msg': str(exc)})
    if effective is None or material is None:
        missing = []
        if effective is None:
            missing.append('effective bearing depth t1tr')
        if material is None:
            missing.append('material strengths')
        record['issues'].append({
            'level': 'error', 'code': 'din6892_calculation_invalid',
            'msg': ('%s could not be resolved, so no DIN 6892 result exists for '
                    'this configuration.' % ' and '.join(missing))})
        record['status'] = 'INVALID_INPUT'
        return record

    shaft_re = float((material.get('shaft') or {}).get('Re_MPa', 0.0) or 0.0)
    hub_re = float((material.get('hub') or {}).get('Re_MPa', 0.0) or 0.0)
    key_re = float((material.get('key') or {}).get(
        'yield_MPa', (material.get('key') or {}).get('Re_MPa', 0.0)) or 0.0)
    positive_yields = [value for value in (shaft_re, hub_re, key_re) if value > 0.0]
    re_min = min(positive_yields) if positive_yields else 0.0
    # DIN 6892 checks the shaft keyway, the hub keyway and the key separately.
    # Each component carries its OWN yield and tensile strength so that FVA
    # equation 33 (f_WS = Rm/Re) can never divide one part's Rm by another
    # part's Re.  A hardness-derived Rm estimate is deliberately NOT promoted to
    # a tensile strength; components without an explicit Rm are reported as
    # skipped by the equation-33 chain instead of being silently paired.
    components = []
    for name, yield_value in (('shaft', shaft_re), ('hub', hub_re),
                              ('key', key_re)):
        if yield_value <= 0.0:
            continue
        row = {'name': name, 'Re_MPa': yield_value}
        try:
            tensile = float((material.get(name) or {}).get('Rm_MPa', 0.0) or 0.0)
        except (TypeError, ValueError):
            tensile = 0.0
        if tensile > 0.0:
            row['Rm_MPa'] = tensile
        components.append(row)
    common = {
        'd_w_mm': d['D'],
        'ltr_mm': d['load_bearing_length'],
        't1tr_mm': effective['t1tr_mm'],
        # Independent flank-height cross-check of equation 9 and the policy that
        # decides which of the two values the pressure checks use.
        't1tr_geometric_mm': effective.get('t1tr_geometric_mm'),
        'bearing_depth_policy': cfg.get(
            'bearing_depth_policy', din6892.DEPTH_POLICY_EQUATION_9),
        # Hub keyway bearing depth; None makes the hub fall back to t1tr and the
        # engine reports that fallback as optimistic.
        't2tr_mm': (None if hub_effective is None
                    else hub_effective['t2tr_mm']),
        'key_count': int(cfg.get('key_count', 1) or 1),
        'phi': cfg.get('phi'),
        'load_cycles': cfg.get('load_cycles', 10000),
        # Equation 3 counts load DIRECTION reversals, not load cycles. N_W = null
        # lets the engine derive the count from the load ratio.
        'load_ratio_R': cfg.get('load_ratio_R', 0.0),
        'N_W': cfg.get('N_W'),
        'K_lambda': cfg.get('K_lambda'),
        'K_R': cfg.get('K_R'),
        'f_H': cfg.get('f_H', 1.0),
        'f_S': cfg.get('f_S', 1.0),
        'safety_factor': cfg.get('safety_factor', 1.2),
        'v': cfg.get('v', 0.5),
        'Re_MPa': re_min,
        'Re_min_MPa': re_min,
        'Rm_MPa': float((material.get('shaft') or {}).get('Rm_MPa', 0.0) or 0.0),
        'components': components,
        'factor_provenance': _json_clone(cfg.get('factor_provenance', {}) or {}),
        'factors_acknowledged': bool(cfg.get('factors_acknowledged', False)),
        'material_classes': _json_clone(cfg.get('material_classes', {}) or {}),
        'f_S_bound': cfg.get('f_S_bound', 'lower'),
        'f_L': cfg.get('f_L'),
        'torque_applied_Nm': cfg.get('torque_applied_Nm'),
        # Application factor chain: M_teq = K_A * M_t,nom.
        'K_A': cfg.get('K_A', 1.0),
        'torque_nominal_Nm': cfg.get('torque_nominal_Nm'),
        'torque_peak_applied_Nm': cfg.get('torque_peak_applied_Nm'),
        'torque_required_Nm': cfg.get('torque_required_Nm'),
        # K_lambda diagram bounds: Q_A = d_w/D and the load derivation position.
        'hub_diameter_mm': d.get('d_a'),
        'load_derivation_position': cfg.get(
            'load_derivation_position', din6892.LOAD_DERIVATION_REAR),
        'a0_mm': cfg.get('a0_mm'),
        'method_c_variant': cfg.get(
            'method_c_variant', din6892.METHOD_C_VARIANT_DIN),
        'h_mm': d['h'],
        't1_mm': d['t1'],
        't2_mm': d['t2'],
        'b_mm': d['b'],
        'key_form': d.get('form', 'A'),
        'UPF_um': cfg.get('UPF_um', 18.0),
        'v_crit': cfg.get('v_crit', 0.5),
    }
    # DIN 6892 equation 12: the friction-closure factor is computable once the
    # DIN 7190-1 minimum slip torque is known. Without it K_R stays the explicit
    # input, which for the FVA correction is exactly 1.0.
    slip_torque = cfg.get('slip_torque_min_Nm')
    if slip_torque not in (None, ''):
        try:
            closure = din6892.friction_closure_factor(
                float(fva_cfg.get('torque_Nm', cfg.get('torque_max_Nm', 1256.0))),
                slip_torque,
                apply_fva_correction=bool(
                    cfg.get('apply_fva_friction_correction', True)))
            record['derived']['friction_closure'] = closure
            common['K_R'] = closure['K_R']
        except (TypeError, ValueError, KeyError) as exc:
            record['issues'].append({
                'level': 'warn', 'code': 'din6892_friction_closure_invalid',
                'msg': str(exc)})
    if method_id == din6892.METHOD_A:
        method_a = _json_clone(cfg.get('method_a', {}) or {})
        # For the connected numerical backend the CAE cycle count is the
        # authoritative Method-A evidence until solved postprocess metadata is
        # persisted.  Keeping the schema default ``method_a.cycles=0`` here
        # produced a false warning even though the preset builds 20 cycles.
        if (bool(fva_cfg.get('enabled', False)) and
                str(fva_cfg.get('backend', '')) in (
                    din6892.BACKEND_METHOD_A_CONNECTED,
                    din6892.BACKEND_METHOD_A_HYBRID_HEX)):
            method_a['cycles'] = int(fva_cfg.get(
                'cycles', method_a.get('cycles', 0)) or 0)
        post = method_a.get('postprocess')
        if isinstance(post, dict):
            integration = post.get('integration') or {}
            if method_a.get('delta_volume_mm3') in (None, ''):
                method_a['delta_volume_mm3'] = integration.get('delta_volume_mm3')
            method_a['cycles'] = int(post.get('cycles', method_a.get('cycles', 0)) or 0)
            method_a['unloaded_frame_verified'] = bool(
                post.get('unloaded_frame_verified',
                         method_a.get('unloaded_frame_verified', False)))
            method_a['source_frame_identified'] = bool(
                post.get('source_frame_identified',
                         method_a.get('source_frame_identified', False)))
            method_a['coverage_within_2_percent'] = bool(
                (post.get('coverage') or {}).get('within_2_percent', False))
            method_a['invariants_revalidated'] = bool(
                (post.get('attached_invariants_verified') or {}).get(
                    'verified', False))
            method_a['provenance_hash_verified'] = bool(
                (post.get('provenance_verification') or {}).get(
                    'verified', False))
            persisted_inputs = ((post.get('volume') or {}).get('inputs') or {})
            persisted_invariants = post.get('invariants') or {}
            required_invariants = ('ltr_mm', 't1tr_mm', 'UPF_um')
            missing_invariants = [name for name in required_invariants
                                  if name not in persisted_invariants or
                                  name not in persisted_inputs]
            if missing_invariants:
                record['issues'].append({
                    'level': 'error',
                    'code': 'method_a_postprocess_invariants_missing',
                    'msg': ('Persisted Method-A invariants/volume inputs are '
                            'incomplete: %s.' % ', '.join(missing_invariants))})
            normalized_invariants = {}
            for name in required_invariants:
                if name in persisted_invariants:
                    normalized_invariants[name] = float(
                        persisted_invariants[name])
            if (len(normalized_invariants) == len(required_invariants) and
                    post.get('invariants_sha256') !=
                    _sha256_json(normalized_invariants)):
                record['issues'].append({
                    'level': 'error',
                    'code': 'method_a_postprocess_invariant_hash_mismatch',
                    'msg': 'Persisted Method-A invariant hash is invalid.'})
            if not ((post.get('coverage') or {}).get('within_2_percent') is True):
                record['issues'].append({
                    'level': 'error',
                    'code': 'method_a_postprocess_coverage_incomplete',
                    'msg': ('Method-A opening grid does not pass the mandatory '
                            '2 percent bounds/coverage gate.')})
            provenance = post.get('provenance') or {}
            verification = post.get('provenance_verification') or {}
            source_hash = str(provenance.get('sha256') or '').lower()
            if (len(source_hash) != 64 or
                    any(char not in '0123456789abcdef' for char in source_hash) or
                    verification.get('verified') is not True):
                record['issues'].append({
                    'level': 'error',
                    'code': 'method_a_postprocess_provenance_unverified',
                    'msg': ('Method-A source SHA-256 must have been reverified '
                            'successfully at attachment.')})
            comparisons = (
                ('ltr_mm', d['load_bearing_length']),
                ('t1tr_mm', effective['t1tr_mm']),
                ('UPF_um', cfg.get('UPF_um', 18.0)),
            )
            for field, current in comparisons:
                previous = persisted_invariants.get(field)
                volume_previous = persisted_inputs.get(field)
                if (previous is None or volume_previous is None or
                        abs(float(previous) - float(current)) > 1e-9 or
                        abs(float(volume_previous) - float(current)) > 1e-9):
                    record['issues'].append({
                        'level': 'error',
                        'code': 'method_a_postprocess_geometry_mismatch',
                        'msg': ('Persisted Method-A %s values %r/%r differ from '
                                'current value %.12g; reprocess the evidence.' %
                                (field, previous, volume_previous,
                                 float(current)))})
        common.update(method_a)
    record['derived']['calculation_inputs'] = _json_clone(common)
    try:
        record['calculation'] = din6892.evaluate(method_id, common)
        record['issues'].extend(din6892.validate_configuration(method_id, common))
        record['status'] = record['calculation'].get('status', 'CALCULATED')
    except (TypeError, ValueError, KeyError) as exc:
        record['issues'].append({'level': 'error',
                                 'code': 'din6892_calculation_invalid',
                                 'msg': str(exc)})
        record['status'] = 'INVALID_INPUT'
    # Method A needs a solved ODB while Methods B and C are closed-form, so the
    # analytical methods are always evaluated for the same joint.  This gives an
    # A-vs-B comparison in one run without weakening the rule that the FVA CAE
    # route itself must request Method A.
    companion_ids = cfg.get('companion_methods')
    if companion_ids is None:
        companion_ids = list(din6892.ANALYTICAL_METHOD_IDS)
    companions = din6892.companion_evaluations(method_id, common, companion_ids)
    record['companions'] = companions
    record['issues'].extend(companions.get('issues') or [])
    return record


def derive(params, verbose=False):
    """Compute every derived quantity from the USER parameters.

    Stores the result in params['_derived'] and returns it.
    """
    if not isinstance(params, dict):
        raise ValueError("Parameters must be a dictionary.")
    try:
        input_schema = int(params.get("schema_version"))
    except (TypeError, ValueError):
        raise ValueError("Parameter schema_version is required and must be an integer.")
    if input_schema != SCHEMA_VERSION:
        normalized = normalize_params(params)
        params.clear()
        params.update(normalized)
    else:
        _synchronize_geometry_aliases(params)

    sh = params.get('shaft', {})
    ky = params.get('key', {})
    hu = params.get('hub', {})
    nt = params.get('notch', {}) or {}

    D = float(sh.get('diameter_mm', sh.get('D', 40.0)))
    sh['diameter_mm'] = D
    sh['D'] = D
    row = din6885_row(D)
    form = normalize_key_form(params.get('key_form', 'A'))
    params['key_form'] = form
    qa_shaft_over_outer = float(hu.get('QA_shaft_over_outer', 0.5))
    if qa_shaft_over_outer <= 0.0:
        raise ValueError('hub.QA_shaft_over_outer must be positive.')
    ratio = 1.0 / qa_shaft_over_outer
    hu['QA_shaft_over_outer'] = qa_shaft_over_outer
    hu['hub_outer_over_shaft'] = ratio
    d = {}
    d['schema_version'] = SCHEMA_VERSION
    d['builder_version'] = BUILDER_VERSION
    d['shaft_diameter_mm'] = D
    d['shaft_radius_mm'] = D / 2.0
    d['hub_ratio_QA_shaft_over_outer'] = qa_shaft_over_outer
    d['deprecated_aliases'] = _json_clone(params.get('_alias_provenance', {}))

    # ---- shaft ----------------------------------------------------------
    d['D'] = D
    d['R'] = D / 2.0
    d['L_over_D'] = float(sh.get('L_over_D', 3.0))
    d['L'] = d['L_over_D'] * D
    d['b'] = row['b']
    d['h'] = row['h']
    d['t1'] = row['t1']
    d['t2'] = row['t2']
    d['t1_tol_plus'] = row['t1_tol_plus']
    d['din_d2_add'] = row['d2_add']
    d['din_d2_ref'] = row['d2_ref']
    d['din_badge'] = EVIDENCE_NORMATIVE
    d['din_source_id'] = row['source_id']
    d['din_band'] = (row['D_from'], row['D_upto'])
    d['din_in_table'] = row['in_table']
    rc_user = float(sh.get('R_cap') or 0.0)
    d['R_cap'] = rc_user if rc_user > 0 else d['b'] / 2.0
    d['R_cap_auto'] = (rc_user <= 0)
    d['z0_offset'] = float(sh.get('z0_offset', 5.0))
    d['z0'] = d['R_cap'] + d['z0_offset']
    d['dz'] = float(sh.get('dz', 38.0))
    d['z1'] = d['z0'] + 2.0 * d['R_cap'] + d['dz']
    d['c1'] = d['z0'] + d['R_cap']          # first arc centre
    d['c2'] = d['c1'] + d['dz']             # second arc centre
    d['z_mid'] = 0.5 * (d['z0'] + d['z1'])
    d['keyway_span'] = d['z1'] - d['z0']
    d['r2'] = float(sh.get('r2', 0.25))
    d['slot_clearance'] = float(sh.get('slot_clearance', 0.0) or 0.0)
    d['slot_w'] = d['b'] + d['slot_clearance']
    d['yF'] = d['R'] - d['t1']
    d['x_w'] = d['b'] / 2.0
    d['x_slot'] = d['slot_w'] / 2.0
    d['y_min'] = d['yF']
    d['y_max'] = d['y_min'] + d['h']
    fr = din_fillet_range(d['b'])
    d['r2_din_range'] = fr
    d['r2_in_din'] = (fr is None) or (fr[0] - 1e-9 <= d['r2'] <= fr[1] + 1e-9)

    # ---- key ------------------------------------------------------------
    d['form'] = form
    l_user = float(ky.get('l') or 0.0)
    d['slot_total_length'] = d['keyway_span']
    if d['form'] == 'A':
        d['l_max'] = d['slot_total_length']
    elif d['form'] == 'B':
        d['l_max'] = d['dz']
    else:  # AB: one rounded end, one straight end
        d['l_max'] = d['dz'] + d['b'] / 2.0
    l = l_user if l_user > 0 else d['l_max']
    d['l_auto'] = (l_user <= 0)
    if bool(ky.get('snap_length_to_din', False)):
        snapped = nearest_standard_length(l)
        d['l_snapped_from'] = l
        d['l_snapped'] = True
        l = snapped
    else:
        d['l_snapped'] = False
    d['l'] = l                         # legacy geometry alias
    d['key_nominal_length'] = l
    if d['form'] == 'A':
        d['load_bearing_length'] = max(0.0, l - d['b'])
    elif d['form'] == 'AB':
        d['load_bearing_length'] = max(0.0, l - d['b'] / 2.0)
    else:
        d['load_bearing_length'] = l
    d['key_axial_center_offset'] = d['b'] / 4.0 if d['form'] == 'AB' else 0.0
    d['key_ab_round_end'] = 'positive_z' if d['form'] == 'AB' else None
    d['key_length_is_standard'] = any(
        abs(l - float(v)) <= 1e-9 for v in DIN6885_LENGTHS)
    d['key_designation'] = 'DIN 6885-1 Form %s %.0f x %.0f x %g' % (
        d['form'], d['b'], d['h'], l)
    d['key_length_badge'] = (EVIDENCE_NORMATIVE if d['key_length_is_standard']
                             else EVIDENCE_USER_OVERRIDE)
    d['c'] = float(ky.get('c', 0.8))
    d['chamfer_angle'] = float(ky.get('chamfer_angle', 45.0))

    # ---- hub ------------------------------------------------------------
    d['L_hub'] = float(hu.get('L_hub', 38.0))
    d['hub_outer_over_shaft'] = float(hu.get('hub_outer_over_shaft', ratio))
    d['shaft_over_hub'] = qa_shaft_over_outer
    d['QA_shaft_over_outer'] = qa_shaft_over_outer
    d['hub_ratio_QA_shaft_over_outer'] = qa_shaft_over_outer
    d['QA'] = qa_shaft_over_outer             # schema-6 FVA/DIN convention
    d['QA_legacy_outer_over_shaft'] = d['hub_outer_over_shaft']
    d['d_i'] = D
    d['d_a'] = D * d['hub_outer_over_shaft']
    d['r1'] = float(hu.get('r1', 0.25))
    d['groove_clearance'] = float(hu.get('groove_clearance', 0.0) or 0.0)
    d['groove_w'] = d['b'] + d['groove_clearance']
    d['groove_roof'] = d['R'] + d['t2']
    d['g_c'] = d['t1'] + d['t2'] - d['h']
    d['hub_wall_left'] = d['d_a'] / 2.0 - d['groove_roof']

    # ---- why is c what it is? -------------------------------------------
    # The bottom corner chamfer of the key must clear the keyway ROOT FILLET r2
    # in the shaft. The fillet centre sits at (x_w - r2, y_F + r2); both of its
    # tangent points give y - x = y_F - x_w + r2, while the chamfer face is the
    # line y - x = y_min - (x_w - c). With y_min = y_F this reduces to the clean
    # condition   c >= r2   and   perpendicular clearance = (c - r2)/sqrt(2).
    root2 = math.sqrt(2.0)
    d['c_min_bottom'] = d['r2']
    d['clear_bottom'] = (d['c'] - d['r2']) / root2
    top_limit = d['groove_w'] / 2.0 + d['groove_roof'] - d['r1']
    top_line = (d['x_w'] - d['c']) + d['y_max']
    d['clear_top'] = (top_limit - top_line) / root2
    d['flank_in_shaft'] = max(0.0, (d['R'] - d['y_min']) - d['c'])
    d['flank_total'] = max(0.0, d['h'] - 2.0 * d['c'])

    # ---- notch refinement band ------------------------------------------
    d['notch_on'] = bool(nt.get('enabled', True))
    d['notch_arc_elems'] = max(0, int(nt.get('arc_elems', 6) or 0))
    d['notch_band_factor'] = float(nt.get('band_factor', 6.0) or 6.0)
    d['notch_method'] = str(nt.get('method', 'bias')).strip().lower()
    d['notch_arc_scope'] = str(nt.get('arc_scope', 'band')).strip().lower()
    d['notch_axial_factor'] = float(nt.get('axial_factor', 0.0) or 0.0)
    d['notch_hub'] = bool(nt.get('apply_to_hub', True))
    d['arc_len_shaft'] = math.pi * d['r2'] / 2.0
    d['arc_len_hub'] = math.pi * d['r1'] / 2.0
    n = max(1, d['notch_arc_elems'])
    d['s_notch_shaft'] = d['arc_len_shaft'] / n if d['r2'] > 0 else 0.0
    d['s_notch_hub'] = d['arc_len_hub'] / n if d['r1'] > 0 else 0.0
    d['notch_band_max_factor'] = float(nt.get('band_max_factor', 3.0) or 3.0)
    d['band_shaft'] = d['notch_band_factor'] * d['r2']
    d['band_hub'] = d['notch_band_factor'] * d['r1']

    # ---- mesh seeds (0 = auto) ------------------------------------------
    # The auto seed depends on whether the LOCAL notch refinement is active.
    # With the band switched on, the global seed no longer has to resolve the
    # fillet, so a coarser mesh is both cheaper and more accurate at the notch.
    # Measured on D40 (shaft only, linear C3D8):
    #    notch off, seed D/32 = 1.25 mm -> 70 100 elements, notch element 0.196 mm
    #    notch on,  seed D/16 = 2.50 mm -> 39 983 elements, notch element 0.065 mm
    # i.e. 43 % fewer elements and a 3x better resolved notch.
    d['seed_rule_shaft'] = 'D/16' if d['notch_on'] else 'D/32'
    d['seed_shaft'], d['seed_shaft_auto'] = _auto_seed(
        sh.get('seed'), D / (16.0 if d['notch_on'] else 32.0))
    d['seed_key'], d['seed_key_auto'] = _auto_seed(ky.get('seed'), d['b'] / 20.0)
    d['seed_rule_hub'] = 'd_a/40' if (d['notch_on'] and d['notch_hub']) else 'd_a/80'
    d['seed_hub'], d['seed_hub_auto'] = _auto_seed(
        hu.get('seed'),
        d['d_a'] / (40.0 if (d['notch_on'] and d['notch_hub']) else 80.0))
    bp = params.get('bushing', {}) or {}
    d['seed_bushing'], d['seed_bushing_auto'] = _auto_seed(bp.get('seed'), D / 44.0)

    # what the refinement will cost / achieve, before anything is built
    d['ar_notch_expect'] = (d['seed_shaft'] / d['s_notch_shaft']
                            if d['s_notch_shaft'] > 0 else 0.0)

    # ---- analytical design check ----------------------------------------
    dc = params.get('design_check', {}) or {}
    d['dc_on'] = bool(dc.get('enabled', False))
    if d['dc_on']:
        T = float(dc.get('T_nom', 0.0)) * 1000.0            # N m -> N mm
        Tmax = float(dc.get('T_max', 0.0)) * 1000.0
        if Tmax <= 0:
            Tmax = T
        nk = max(1, int(dc.get('n_keys', 1)))
        phi = float(dc.get('load_distribution', 1.0)) or 1.0
        d['n_keys'] = nk
        d['phi'] = phi
        # nominal torsional stress of the plain shaft, tau = T / Wt, Wt = pi d^3/16
        d['Wt'] = math.pi * D ** 3 / 16.0
        d['T_nom'] = T
        d['T_max'] = Tmax
        d['tau_nom'] = T / d['Wt'] if d['Wt'] > 0 else 0.0
        # peak stresses ESTIMATED with published SCFs - not computed here
        d['tau_peak_lit'] = KTS_SHAFT_LIT * d['tau_nom']
        d['tau_peak_hub_lit'] = KTS_HUB_LIT * d['tau_nom']
        # Uniform-bearing pressure SCREENING.  This is intentionally labelled
        # CORE-SCREENING and is not a complete DIN 6892 Method B calculation.
        d['design_check_badge'] = EVIDENCE_CORE_SCREENING
        d['design_check_method'] = dc.get(
            'method_label', 'Uniform-bearing pressure screening')
        d['h_bear_shaft'] = max(0.0, d['t1'] - d['c'])
        d['h_bear_hub'] = max(0.0, d['h'] - d['t1'] - d['c'])
        d['l_tr'] = d['load_bearing_length']  # legacy formula/report alias

        def _p(hb):
            den = D * hb * d['l_tr'] * nk
            return (2.0 * Tmax * phi / den) if den > 0 else float('inf')

        d['p_shaft'] = _p(d['h_bear_shaft'])
        d['p_hub'] = _p(d['h_bear_hub'])
        mats = params.get('materials', {}) or {}
        Re_s = float((mats.get(MAT_SHAFT, {}) or {}).get('Re', 0.0) or 0.0)
        Re_h = float((mats.get(MAT_HUB, {}) or {}).get('Re', 0.0) or 0.0)
        d['p_perm_shaft'] = float(dc.get('p_perm_shaft', 0.0) or 0.0) or Re_s
        d['p_perm_hub'] = float(dc.get('p_perm_hub', 0.0) or 0.0) or Re_h
        d['util_shaft'] = (d['p_shaft'] / d['p_perm_shaft']) if d['p_perm_shaft'] > 0 else None
        d['util_hub'] = (d['p_hub'] / d['p_perm_hub']) if d['p_perm_hub'] > 0 else None

        def _T(hb, pp):
            return pp * D * hb * d['l_tr'] * nk / (2.0 * phi) / 1000.0   # -> N m

        d['T_perm_shaft'] = _T(d['h_bear_shaft'], d['p_perm_shaft'])
        d['T_perm_hub'] = _T(d['h_bear_hub'], d['p_perm_hub'])
        d['T_perm'] = min(d['T_perm_shaft'], d['T_perm_hub'])
        # Unambiguous wall ratios (the legacy literature symbol is retained).
        d['shaft_over_hub'] = d['d_i'] / d['d_a'] if d['d_a'] > 0 else None
        d['hub_outer_over_shaft'] = d['d_a'] / d['d_i'] if d['d_i'] > 0 else None
        d['d_over_D1'] = d['shaft_over_hub']  # legacy literature alias
        d['thick_walled'] = (d['shaft_over_hub'] is not None
                             and d['shaft_over_hub'] < D_OVER_D1_THICK)

    # ---- DIN 6892 / FVA calculation evidence ---------------------------
    d['standards_registry'] = din6892.standard_registry()
    d['din6892'] = _derive_din6892(params, d)
    din_calc = d['din6892'].get('calculation') or {}
    d['din6892_method'] = d['din6892'].get('requested', {}).get('method')
    d['M_t_zul_Nm'] = din_calc.get('torque_allowable_Nm')
    d['M_t_design_Nm'] = din_calc.get('torque_design_Nm')
    d['din6892_governing_component'] = din_calc.get('governing_component')
    d['din6892_factor_audit'] = _json_clone(din_calc.get('factor_audit') or {})
    d['din6892_companions'] = dict(
        (name, {'status': item.get('status'),
                'badge': item.get('badge'),
                'governing_component': item.get('governing_component'),
                'M_t_zul_Nm': item.get('torque_allowable_Nm'),
                'M_t_design_Nm': item.get('torque_design_Nm'),
                'equations': item.get('equations')})
        for name, item in ((d['din6892'].get('companions') or {}).get(
            'results') or {}).items())
    d['execution_trace'] = {
        'requested': _json_clone(d['din6892'].get('requested', {})),
        'derived': {
            'method_status': d['din6892'].get('status'),
            'M_t_zul_Nm': d['M_t_zul_Nm'],
            'M_t_design_Nm': d['M_t_design_Nm'],
        },
        'realized': _json_clone(d['din6892'].get('realized', {}).get(
            'realized', {'status': 'NOT_REQUESTED'})),
    }

    # ---- analysis --------------------------------------------------------
    an = params.get('analysis', {}) or {}
    d['an_on'] = bool(an.get('enabled', False))
    d['T_apply'] = float(an.get('T_apply', 0.0) or 0.0)          # N m
    d['T_apply_Nmm'] = d['T_apply'] * 1000.0
    d['tau_nom_apply'] = (d['T_apply_Nmm'] / (math.pi * D ** 3 / 16.0)
                          if D > 0 else 0.0)

    d['compliance_mode'] = str(params.get('compliance_mode', 'normative')).lower()
    d['groove_form'] = str(params.get('groove_form', 'N1')).upper()
    d['roughness_rz_max_um'] = 16.0
    radii = din6885_radii(d['b'])
    d['r1_din_range'] = (radii['r1_min'], radii['r1_max'])
    d['r2_din_range'] = (radii['r2_min'], radii['r2_max'])
    d['r1_in_din'] = (d['r1_din_range'][0] - 1e-9 <= d['r1'] <=
                      d['r1_din_range'][1] + 1e-9)
    d['normative_geometry'] = (
        d['form'] in KEY_FORMS_IMPLEMENTED and
        abs(d['R_cap'] - d['b'] / 2.0) <= 1e-9 and
        d['key_length_is_standard'] and d['r1_in_din'] and d['r2_in_din'] and
        d['groove_form'] == 'N1')
    d['geometry_badge'] = (EVIDENCE_NORMATIVE if d['normative_geometry']
                           else EVIDENCE_USER_OVERRIDE)
    d['provenance'] = traceability_manifest()

    # Resolve the mesh policy after all geometry-dependent expectations are
    # known.  Invalid configuration is reported by validate(); derive remains
    # usable by the GUI so it can display the offending input.
    try:
        mesh_plan = resolve_mesh_plan(params, d)
        params['_mesh_plan'] = mesh_plan
        d['mesh_template'] = mesh_plan['template']
        d['mesh_template_label'] = mesh_plan['template_label']
        d['mesh_algorithm_version'] = mesh_plan['algorithm_version']
        d['mesh_selection'] = mesh_plan['selection']
        d['mesh_effective_order'] = mesh_plan['element_order']
        d['mesh_effective_hex_code'] = mesh_plan['linear_hex_code']
        d['mesh_plan_error'] = ''
    except (TypeError, ValueError, KeyError) as exc:
        params.pop('_mesh_plan', None)
        d['mesh_template'] = str((params.get('mesh', {}) or {}).get(
            'template', 'AUTO_BALANCED')).strip().upper()
        d['mesh_template_label'] = d['mesh_template']
        d['mesh_algorithm_version'] = str((params.get('mesh', {}) or {}).get(
            'algorithm_version', ''))
        d['mesh_selection'] = str((params.get('mesh', {}) or {}).get(
            'selection', 'auto')).lower()
        d['mesh_effective_order'] = str(params.get('element_order', 'linear')).lower()
        d['mesh_effective_hex_code'] = str(params.get('linear_hex_code', 'C3D8')).upper()
        d['mesh_plan_error'] = str(exc)

    params['_derived'] = d
    if verbose:
        print('[derive] D=%.1f R=%.1f L=%.1f | DIN b=%.1f h=%.1f t1=%.1f t2=%.1f'
              % (D, d['R'], d['L'], d['b'], d['h'], d['t1'], d['t2']))
        print('[derive] R_cap=%.2f z0=%.2f z1=%.2f (dz=%.1f) yF=%.2f'
              % (d['R_cap'], d['z0'], d['z1'], d['dz'], d['yF']))
        print('[derive] key Form %s l=%.2f c=%.2f | hub d_i=%.1f d_a=%.1f roof=%.2f g_c=%.3f'
              % (d['form'], d['l'], d['c'], d['d_i'], d['d_a'],
                 d['groove_roof'], d['g_c']))
        print('[derive] seeds shaft=%.3f%s key=%.3f%s hub=%.3f%s'
              % (d['seed_shaft'], '(auto)' if d['seed_shaft_auto'] else '',
                 d['seed_key'], '(auto)' if d['seed_key_auto'] else '',
                 d['seed_hub'], '(auto)' if d['seed_hub_auto'] else ''))
    return d


# =============================================================== validation
def _issue(level, code, msg):
    return {'level': level, 'code': code, 'msg': msg,
            'canonical_message': msg}


def validate(params, d=None):
    """Check the parameter set BEFORE anything is built.

    Returns a list of {'level': 'error'|'warn'|'info', 'code':..., 'msg':...}.
    An 'error' means the build cannot produce a valid model and must stop.
    """
    if d is None:
        d = params.get('_derived') or derive(params)
    out = []
    E = lambda c, m: out.append(_issue('error', c, m))   # noqa: E731
    W = lambda c, m: out.append(_issue('warn', c, m))    # noqa: E731
    I = lambda c, m: out.append(_issue('info', c, m))    # noqa: E731

    tapered = str(params.get('hub_type', 'cylindrical')).strip().lower() == 'tapered'

    # ---- shaft ----------------------------------------------------------
    if d['D'] <= 0:
        E('D_nonpositive', 'Shaft diameter D must be positive.')
    if not (DIN_D_MIN < d['D'] <= DIN_D_MAX):
        E('D_outside_normative_range', 'DIN 6885-1 requires 6 < d1 <= 500 mm; '
          'no row is extrapolated.')
    if d['L'] <= 0:
        E('L_nonpositive', 'Shaft length L must be positive (L = L_over_D * D).')
    if d['z0'] < 0:
        E('z0_negative', 'z0 = %.3f is negative: the keyway would start before the '
          'shaft. Raise z0_offset.' % d['z0'])
    if d['z1'] > d['L'] + 1e-9:
        E('keyway_off_shaft', 'The keyway ends at z1 = %.2f but the shaft is only '
          'L = %.2f long. Increase L_over_D or reduce dz / z0_offset.'
          % (d['z1'], d['L']))
    elif d['L'] - d['z1'] < d['D'] * 0.25:
        W('keyway_near_end', 'Only %.2f mm of plain shaft is left after the keyway '
          '(< D/4). Saint-Venant needs room: the end boundary condition will '
          'pollute the notch stress.' % (d['L'] - d['z1']))
    if d['dz'] <= 0:
        E('dz_nonpositive', 'dz (distance between the keyway arc centres) must be '
          'positive.')
    if d['t1'] >= d['R']:
        E('t1_too_deep', 'Keyway depth t1 = %.2f reaches the shaft axis (R = %.2f).'
          % (d['t1'], d['R']))
    if d['r2'] < 0:
        E('r2_negative', 'The keyway root fillet r2 cannot be negative.')
    if d['r2'] >= min(d['t1'], d['x_w']) - 1e-9:
        E('r2_too_big', 'r2 = %.3f does not fit in the keyway (needs r2 < min(t1, b/2) '
          '= %.3f).' % (d['r2'], min(d['t1'], d['x_w'])))
    if d['r2'] == 0:
        W('r2_zero', 'r2 = 0 leaves a sharp keyway corner: the stress there is '
          'singular and no mesh will converge.')
    if d['r2_din_range'] and not d['r2_in_din']:
        W('r2_outside_din', 'r2 = %.3f is outside the DIN 6885-1 range %.2f..%.2f mm '
          'for b = %.0f.' % (d['r2'], d['r2_din_range'][0], d['r2_din_range'][1], d['b']))
    if d['slot_clearance'] < 0:
        E('slot_clearance_negative', 'The shaft keyway width clearance cannot be '
          'negative (the key would not fit).')

    # ---- key ------------------------------------------------------------
    if d['form'] not in KEY_FORMS_IMPLEMENTED:
        E('bad_form', "Implemented key forms are A, B and AB.")
    if d['groove_form'] != 'N1':
        E('groove_form_unimplemented', 'Groove form %s is not yet generated by the '
          'solid backend; N2/N3 require their own cutter geometry. Choose N1.'
          % d['groove_form'])
    if abs(d['R_cap'] - d['b'] / 2.0) > 1e-9:
        W('R_cap_user_override', 'R_cap = %.3f differs from normative b/2 = %.3f; '
          'the geometry is labelled USER-OVERRIDE.' % (d['R_cap'], d['b'] / 2.0))
    if not d['key_length_is_standard']:
        W('nonstandard_key_length', 'Key nominal length %.3f mm is not in the DIN '
          'length series; enable snap_length_to_din for a NORMATIVE designation.'
          % d['key_nominal_length'])
    if d['l'] <= 0:
        E('l_nonpositive', 'Key length l must be positive.')
    if d['form'] == 'A' and d['l'] <= d['b'] + 1e-9:
        E('formA_too_short', 'A Form A key needs l > b (= %.2f); l = %.2f leaves no '
          'straight portion between the two end radii.' % (d['b'], d['l']))
    if d['form'] == 'AB' and d['l'] <= d['b'] / 2.0 + 1e-9:
        E('formAB_too_short', 'A Form AB key needs l > b/2 (= %.2f); l = %.2f leaves '
          'no straight portion beside its rounded end.' % (d['b'] / 2.0, d['l']))
    if d['l'] > d['l_max'] + 1e-6:
        E('l_too_long', 'Key length l = %.2f exceeds the keyway (max %.2f for Form %s).'
          % (d['l'], d['l_max'], d['form']))
    if d['c'] < 0:
        E('c_negative', 'The corner chamfer c cannot be negative.')
    if d['c'] + 1e-9 < d['r2']:
        E('c_below_r2', 'c = %.3f is smaller than the root fillet r2 = %.3f, so the '
          'key corner would bite into the fillet. Need c >= r2.' % (d['c'], d['r2']))
    if d['c'] >= d['h'] / 2.0 - 1e-9:
        E('c_too_big', 'Chamfer c = %.3f removes the whole key height (h = %.2f). '
          'Need c < h/2.' % (d['c'], d['h']))
    if d['flank_total'] <= 0:
        E('no_flank', 'No straight flank is left on the key (h - 2c = %.3f), so no '
          'torque could be transferred.' % d['flank_total'])
    if abs(d['chamfer_angle'] - 45.0) > 1e-6:
        W('chamfer_angle', 'chamfer_angle = %.1f deg was requested, but the symmetric '
          'Chamfer(length=..) used by the builder is 45 deg by construction; the '
          'model will be built with 45 deg.' % d['chamfer_angle'])
    if d.get('l_snapped'):
        I('l_snapped', 'Key length snapped down to the DIN 6885 series: %.2f -> %.2f mm.'
          % (d.get('l_snapped_from', d['l']), d['l']))

    # ---- hub ------------------------------------------------------------
    if d['hub_outer_over_shaft'] <= 1.0:
        E('hub_ratio_too_small', 'hub_outer_over_shaft = %.3f gives an outer diameter '
          '%.2f that does not exceed the bore %.2f.'
          % (d['hub_outer_over_shaft'], d['d_a'], d['d_i']))
    if d['hub_wall_left'] <= 0:
        E('hub_wall', 'The hub keyway breaks through the hub wall: only %.3f mm is '
          'left above the groove roof. Raise Q_A.' % d['hub_wall_left'])
    elif d['hub_wall_left'] < 2.0 * d['t2']:
        W('hub_wall_thin', 'Only %.2f mm of hub wall is left above the keyway '
          '(< 2*t2 = %.2f).' % (d['hub_wall_left'], 2.0 * d['t2']))
    if d['g_c'] < -1e-9:
        E('gc_negative', 'Top clearance g_c = t1 + t2 - h = %.3f is negative: the key '
          'is taller than the two keyway depths together.' % d['g_c'])
    if d['r1'] < 0:
        E('r1_negative', 'The hub roof fillet r1 cannot be negative.')
    if d['r1'] >= min(d['t2'], d['groove_w'] / 2.0) - 1e-9:
        E('r1_too_big', 'r1 = %.3f does not fit in the hub keyway (needs r1 < '
          'min(t2, groove_w/2) = %.3f).'
          % (d['r1'], min(d['t2'], d['groove_w'] / 2.0)))
    if not d.get('r1_in_din', False):
        W('r1_outside_din', 'r1 = %.3f is outside the DIN 6885-1 range %.2f..%.2f mm '
          'for b = %.0f; geometry is labelled USER-OVERRIDE.' % (
              d['r1'], d['r1_din_range'][0], d['r1_din_range'][1], d['b']))
    if d['clear_top'] < -1e-9:
        W('clear_top', 'The key top chamfer overlaps the hub roof fillet by %.4f mm.'
          % (-d['clear_top']))
    if d['groove_clearance'] < 0:
        E('groove_clearance_negative', 'The hub groove width clearance cannot be '
          'negative.')
    if d['L_hub'] <= 0:
        E('Lhub_nonpositive', 'Hub length L_hub must be positive.')
    if d['L_hub'] > d['keyway_span'] + 1e-9:
        I('hub_longer_than_keyway', 'The hub (%.2f) is longer than the keyway span '
          '(%.2f); it overhangs the keyway, which is normal but means the hub '
          'contacts plain shaft at both ends.' % (d['L_hub'], d['keyway_span']))
    if d['L_hub'] < d['l'] - 1e-9:
        I('hub_shorter_than_key', 'The hub (%.2f) is shorter than the key (%.2f), so '
          'the key ends stand outside the hub and carry no hub load. This may be '
          'intentional; note [3]: the peak shear sits at the keyway end.'
          % (d['L_hub'], d['l']))

    # ---- mesh -----------------------------------------------------------
    # Configuration validation is pure Python and therefore identical in the
    # GUI and Abaqus runtimes.  Runtime mesh quality is evaluated separately
    # after each candidate has actually been generated.
    mesh_issues = validate_mesh_configuration(params)
    for issue in mesh_issues:
        issue.setdefault('canonical_message', issue.get('msg', ''))
    out.extend(mesh_issues)
    for tag, s in (('shaft', d['seed_shaft']), ('key', d['seed_key']),
                   ('hub', d['seed_hub'])):
        if s <= 0:
            E('seed_nonpositive', 'The %s mesh seed must be positive.' % tag)
    if d['seed_key'] > d['b'] / 3.0:
        W('key_seed_coarse', 'The key seed (%.3f) is coarser than b/3 = %.3f: fewer '
          'than 3 elements across the key width.' % (d['seed_key'], d['b'] / 3.0))
    notch_refinement_active = d['notch_on'] and not tapered
    if notch_refinement_active and d['notch_arc_elems'] < 4:
        W('arc_elems_low', 'notch.arc_elems = %d: fewer than 4 elements on the fillet '
          'arc is not enough to quote a stress concentration factor.'
          % d['notch_arc_elems'])
    if d['notch_on'] and d['band_shaft'] >= min(d['t1'], d['x_w']) * 0.9:
        W('band_too_wide', 'The notch refinement band (%.3f mm) is nearly as wide as '
          'the keyway itself; lower notch.band_factor.' % d['band_shaft'])
    if d['notch_on'] and d['band_shaft'] <= d['r2']:
        W('band_too_narrow', 'The notch band (%.3f mm) is not wider than the fillet '
          'itself (r2 = %.3f); raise notch.band_factor to at least 2.'
          % (d['band_shaft'], d['r2']))
    if notch_refinement_active and d['ar_notch_expect'] > 30.0:
        W('ar_notch_expect', 'The notch elements will be about %.0f times longer '
          'axially than in-plane (global seed %.2f vs notch size %.4f mm). Either '
          'lower the shaft seed or lower notch.arc_elems.'
          % (d['ar_notch_expect'], d['seed_shaft'], d['s_notch_shaft']))
    if tapered and d['notch_on']:
        I('tapered_notch_seeding_disabled', 'The legacy tapered route keeps the shaft '
          'fillet geometry but does not apply the dedicated local notch seeding or '
          'its expected axial-aspect-ratio estimate; reported fillet resolution is '
          'measured from the selected global mesh candidate.')
    if str(params.get('element_order', 'linear')).lower() == 'quadratic' and \
            d['seed_shaft'] < d['D'] / 40.0:
        W('quadratic_cost', 'Quadratic elements with a %.2f mm shaft seed will produce '
          'a very large model; consider a coarser seed.' % d['seed_shaft'])
    hexc = str(params.get('linear_hex_code', 'C3D8')).upper()
    if hexc == 'C3D8R':
        W('reduced_integration', 'linear_hex_code = C3D8R is REDUCED integration; the '
          'design brief asks for fully integrated elements (C3D8 or C3D8I).')

    # ---- analysis --------------------------------------------------------
    if d['an_on']:
        an = params.get('analysis', {}) or {}
        if d['T_apply'] <= 0:
            E('T_apply', 'analysis.T_apply must be positive when the analysis stage '
              'is enabled.')
        if tapered:
            W('analysis_tapered', 'The analysis stage was written and verified for the '
              'cylindrical hub; with hub_type = tapered it is untested.')
        if float(an.get('friction', 0.15)) < 0:
            W('frictionless', 'Frictionless contact was requested: the key alone must '
              'carry the whole torque, which is conservative but not what DIN 6892 '
              'assumes.')
        if d['g_c'] > 0 and d['notch_on'] is False:
            I('gc_gap', 'The key top has a %.3f mm gap to the hub roof, so that pair '
              'starts open, as intended.' % d['g_c'])
        if bool(an.get('submit', False)) and d['seed_shaft'] < d['D'] / 40.0:
            W('submit_expensive', 'Submitting with a %.2f mm shaft seed can take a '
              'long time; consider a coarser seed for a first run.' % d['seed_shaft'])
    # ---- study -----------------------------------------------------------
    st = params.get('study', {}) or {}
    if bool(st.get('enabled', False)):
        scales = st.get('seed_scales') or []
        if not scales:
            E('study_no_scales', 'study.enabled is true but study.seed_scales is empty.')
        elif min([float(s) for s in scales]) <= 0:
            E('study_bad_scale', 'study.seed_scales must all be positive.')

    # ---- standards / DIN 6892 -------------------------------------------
    standards = params.get('standards', {}) or {}
    registry = din6892.standard_registry()
    for role, standard_id in sorted((standards.get('selected', {}) or {}).items()):
        if standard_id not in registry:
            E('standard_selection_unknown',
              'Unknown standard selection %r for role %s.' % (standard_id, role))
            continue
        implementation = registry[standard_id].get('implementation', '')
        if implementation == 'NOT_IMPLEMENTED':
            E('standard_not_implemented',
              '%s was selected for %s, but its procedure/geometry is not implemented.' %
              (standard_id, role))
        elif implementation == 'REFERENCE_ONLY':
            I('standard_not_implemented',
              '%s is selectable for traceability but remains reference-only.' % standard_id)
        elif implementation in ('EXTERNAL_RESULT_REQUIRED', 'USER_INPUT'):
            I('standard_external_input',
              '%s requires explicit user input or independent verification.' % standard_id)

    din_record = d.get('din6892', {}) or {}
    for issue in din_record.get('issues', []) or []:
        level = str(issue.get('level', 'error')).lower()
        code = issue.get('code', 'din6892_issue')
        message = issue.get('msg', '')
        if level == 'warn':
            W(code, message)
        elif level == 'info':
            I(code, message)
        else:
            E(code, message)
    din_cfg = params.get('din6892', {}) or {}
    if bool(din_cfg.get('enabled', False)) and bool(din_cfg.get('apply_variant_geometry', False)):
        try:
            requested_variant = din6892.variant(din_cfg.get('variant_id', 'VB1'))
            if abs(d['D'] - requested_variant['d_w_mm']) > 1e-9:
                E('fva_variant_diameter_mismatch',
                  'Requested %s requires d_w=%.3f mm; geometry has %.3f mm.' %
                  (requested_variant['variant_id'], requested_variant['d_w_mm'], d['D']))
            ratio_now = d['load_bearing_length'] / d['D'] if d['D'] > 0 else 0.0
            if abs(ratio_now - requested_variant['ltr_over_dw']) > 1e-6:
                E('fva_variant_length_mismatch',
                  'Requested %s requires l_tr/d_w=%.3f; geometry has %.6f.' %
                  (requested_variant['variant_id'], requested_variant['ltr_over_dw'],
                   ratio_now))
            if abs(d['QA_shaft_over_outer'] -
                   requested_variant['QA_shaft_over_hub']) > 1e-9:
                E('fva_variant_hub_ratio_mismatch',
                  'Requested %s requires Q_A=d_w/D_outer=%.3f; geometry has %.6f.' %
                  (requested_variant['variant_id'],
                   requested_variant['QA_shaft_over_hub'],
                   d['QA_shaft_over_outer']))
            if d['form'] != requested_variant['key_form']:
                E('fva_variant_key_form_mismatch',
                  'Requested %s requires key Form %s; geometry uses Form %s.' %
                  (requested_variant['variant_id'], requested_variant['key_form'],
                   d['form']))
        except (TypeError, ValueError, KeyError) as exc:
            E('fva_variant_invalid', str(exc))

    backend_assessment = din_record.get('realized') or \
        din6892.assess_backend_request(params.get('fva_600_iii', {}) or {})
    for issue in backend_assessment.get('issues', []) or []:
        E(issue.get('code', 'fva_backend_blocked'), issue.get('msg', ''))
    fva_request = params.get('fva_600_iii', {}) or {}
    if bool(fva_request.get('enabled', False)):
        backend_id = str(fva_request.get('backend', ''))
        din_variant = str(din_cfg.get('variant_id', '')).upper()
        fva_variant = str(fva_request.get('variant_id', '')).upper()
        if din_variant != fva_variant:
            E('fva_request_variant_mismatch',
              'DIN calculation requests %s but CAE backend requests %s.' %
              (din_variant, fva_variant))
        din_material = str(din_cfg.get('material_pair', '')).upper()
        fva_material = str(fva_request.get('material_pair', '')).upper()
        if din_material != fva_material:
            E('fva_request_material_mismatch',
              'DIN calculation requests %s but CAE backend requests %s.' %
              (din_material, fva_material))
        if str(din_cfg.get('method', '')).upper() != din6892.METHOD_A:
            E('fva_request_method_mismatch',
              'The FVA CAE route realizes only DIN 6892 Method A; select %s.' %
              din6892.METHOD_A)

        if backend_id == din6892.BACKEND_LEGACY_D40:
            geometry_mismatches = []
            if abs(d['D'] - 40.0) > 1e-9:
                geometry_mismatches.append('d_w=40 mm')
            if d['form'] != 'A':
                geometry_mismatches.append('key Form A')
            if str(params.get('hub_type', '')).lower() != 'tapered':
                geometry_mismatches.append('hub_type=tapered')
            if str(params.get('element_order', '')).lower() != 'quadratic':
                geometry_mismatches.append('element_order=quadratic')
            if abs(d['key_nominal_length'] - 38.0) > 1e-9:
                geometry_mismatches.append('legacy key length=38 mm')
            if geometry_mismatches:
                E('fva_backend_geometry_contract_mismatch',
                  'Locked FVA backend would ignore incompatible requested geometry; '
                  'required: %s.' % ', '.join(geometry_mismatches))
        elif backend_id in (
                din6892.BACKEND_METHOD_A_CONNECTED,
                din6892.BACKEND_METHOD_A_HYBRID_HEX):
            connected_mismatches = []
            try:
                requested_variant = din6892.variant(fva_variant)
                ratio_now = (d['load_bearing_length'] / d['D']
                             if d['D'] > 0.0 else 0.0)
                if abs(d['D'] - requested_variant['d_w_mm']) > 1e-9:
                    connected_mismatches.append('d_w=%.3f mm' %
                                                requested_variant['d_w_mm'])
                if abs(ratio_now - requested_variant['ltr_over_dw']) > 1e-6:
                    connected_mismatches.append('l_tr/d_w=%.3f' %
                                                requested_variant['ltr_over_dw'])
                if abs(d['QA_shaft_over_outer'] -
                       requested_variant['QA_shaft_over_hub']) > 1e-9:
                    connected_mismatches.append('Q_A=%.3f' %
                                                requested_variant['QA_shaft_over_hub'])
                if d['form'] != requested_variant['key_form']:
                    connected_mismatches.append('key Form %s' %
                                                requested_variant['key_form'])
                if abs(d['L_hub'] - d['load_bearing_length']) > 1e-6:
                    connected_mismatches.append('L_hub=l_tr')
            except (TypeError, ValueError, KeyError) as exc:
                E('fva_variant_invalid', str(exc))
            if str(params.get('hub_type', '')).lower() != 'cylindrical':
                connected_mismatches.append('hub_type=cylindrical')
            if connected_mismatches:
                E('fva_connected_geometry_mismatch',
                  'Connected Method-A backend requires the selected FVA variant '
                  'geometry: %s.' % ', '.join(connected_mismatches))

            if backend_id == din6892.BACKEND_METHOD_A_HYBRID_HEX:
                mesh_plan = params.get('_mesh_plan') or resolve_mesh_plan(params, d)
                hybrid_mismatches = []
                if mesh_plan.get('template') != 'FVA_METHOD_A_HYBRID':
                    hybrid_mismatches.append('mesh.template=FVA_METHOD_A_HYBRID')
                if mesh_plan.get('selection') != 'fixed':
                    hybrid_mismatches.append('mesh.selection=fixed')
                if mesh_plan.get('topology_requirement') != 'HYBRID_HEX':
                    hybrid_mismatches.append('topology_requirement=HYBRID_HEX')
                if mesh_plan.get('element_order') != 'quadratic':
                    hybrid_mismatches.append('element_order=quadratic')
                if mesh_plan.get('quadratic_hex_code') != 'C3D20R':
                    hybrid_mismatches.append('quadratic_hex_code=C3D20R')
                expected_profile = ['C3D20R', 'C3D15', 'C3D10']
                if mesh_plan.get('element_profile', {}).get(
                        'allowed_types') != expected_profile:
                    hybrid_mismatches.append(
                        'allowed element profile C3D20R/C3D15/C3D10')
                if hybrid_mismatches:
                    E('fva_hybrid_mesh_contract_mismatch',
                      'Hybrid Method-A backend requires: %s.' %
                      ', '.join(hybrid_mismatches))

            contact = fva_request.get('contact', {}) or {}
            total = float(contact.get('interference_total_mm', 0.0) or 0.0)
            half = float(contact.get('interference_per_flank_mm', 0.0) or 0.0)
            if total < 0.0 or half < 0.0:
                E('fva_interference_negative',
                  'Contact interference values cannot be negative.')
            if abs(total - 2.0 * half) > 1.0e-9:
                E('fva_interference_distribution_invalid',
                  'interference_per_flank_mm must equal half of '
                  'interference_total_mm.')
            if not bool(contact.get('finite_sliding', True)):
                E('fva_finite_sliding_required',
                  'FVA Method-A contact requires finite sliding.')
            if not bool(contact.get('interference_ramp', True)):
                E('fva_interference_ramp_required',
                  'The insertion interference must be ramped gradually.')
            if float(contact.get('friction_fit', 0.0001)) < 0.0 or \
                    float(contact.get('friction_service', 0.2)) < 0.0:
                E('fva_friction_negative', 'FVA friction coefficients cannot be negative.')
            if float(contact.get('elastic_slip_mm', 0.001) or 0.0) <= 0.0:
                E('fva_elastic_slip_invalid', 'elastic_slip_mm must be positive.')
            if float(contact.get('normal_stiffness_N_per_mm3', 1.0e7) or 0.0) <= 0.0:
                E('fva_contact_stiffness_invalid',
                  'normal_stiffness_N_per_mm3 must be positive.')

        # A dedicated FVA backend and the generic torsion backend may not be
        # active together; their steps, BCs and interactions would conflict.
        generic_analysis = params.get('analysis', {}) or {}
        forbidden = [name for name in ('enabled', 'create_job', 'submit')
                     if bool(generic_analysis.get(name, False))]
        if forbidden:
            E('fva_generic_analysis_forbidden',
              'Generic analysis/job switches are incompatible with the dedicated '
              'FVA backend: %s.' % ', '.join(forbidden))
        if bool((params.get('study', {}) or {}).get('enabled', False)):
            E('fva_mesh_study_forbidden',
              'The generic mesh study cannot remesh a verified matching interface.')

    # ---- FVA 600 III research workflow ----------------------------------
    fva = params.get('fva_600_iii', {}) or {}
    if bool(fva.get('enabled', False)):
        backend_id = str(fva.get('backend', ''))
        cycles = int(fva.get('cycles', 0) or 0)
        minimum_cycles = int(fva.get('method_a_min_cycles', 10) or 10)
        if cycles < minimum_cycles and backend_id == din6892.BACKEND_LEGACY_D40:
            I('fva_presolve_only', 'The FVA workflow uses %d LW; the supplied 2025 '
              'research report proposes at least 10 LW for Method A. This run is '
              'labelled PRE-SOLVE/REGRESSION, not complete Method A.' % cycles)
        if abs(float(fva.get('v_crit', 0.5)) - 0.5) > 1e-12:
            W('fva_vcrit_override', 'v_crit differs from the supplied research '
              'criterion 0.5 and is labelled USER-OVERRIDE.')
        if backend_id == din6892.BACKEND_LEGACY_D40:
            if not bool(fva.get('strict_no_job', False)):
                E('fva_nojob_required', 'The locked one-cycle FVA pre-solve backend '
                  'requires strict_no_job=true.')
            if not bool(params.get('make_preview', True)):
                E('fva_preview_required',
                  'Visual evidence is mandatory for the locked FVA legacy backend.')
        trend = din6892.geometry_trend_table()
        if trend.get('narrative_table_conflict'):
            W('fva_table11_narrative_conflict', trend.get('warning', ''))

        matlab = params.get('matlab', {}) or {}
        matlab_mode = str(matlab.get('mode', 'OFF')).strip().upper()
        if matlab_mode not in ('OFF', 'EXPORT', 'RUN'):
            E('matlab_mode_invalid', 'matlab.mode must be OFF, EXPORT or RUN.')
        if matlab_mode == 'RUN' and not str(matlab.get('executable', '')).strip():
            E('matlab_executable_required',
              'matlab.executable is required when matlab.mode=RUN.')
        if int(matlab.get('timeout_s', 300) or 0) <= 0:
            E('matlab_timeout_invalid', 'matlab.timeout_s must be positive.')

    if tapered:
        I('tapered', 'hub_type = tapered selects the legacy bushing + conical hub '
          'variant; the cylindrical hub is the reviewed default.')
    return out


def errors(issues):
    return [i for i in issues if i['level'] == 'error']


def warnings_(issues):
    return [i for i in issues if i['level'] == 'warn']


def format_issues(issues, indent='   '):
    lines = []
    order = {'error': 0, 'warn': 1, 'info': 2}
    for i in sorted(issues, key=lambda x: order.get(x['level'], 9)):
        lines.append('%s[%-5s] %-24s %s' % (indent, i['level'].upper(),
                                            i['code'], i['msg']))
    return lines


def fva600_research_factors(v, d_w, rm, re_value, load_bearing_length):
    """Backward-compatible wrapper around :mod:`din6892_methods`."""
    f_sv = din6892.volume_support_factor(v)
    k_d = din6892.size_factor(d_w)
    f_ws = din6892.strength_support_factor(rm, re_value)
    f_ltr = din6892.length_support_factor_fva(load_bearing_length, d_w)
    return {
        'badge': EVIDENCE_FVA_RESEARCH,
        'v': float(v), 'v_crit': 0.5, 'below_research_critical': float(v) <= 0.5,
        'f_sv': f_sv['f_Sv'], 'K_d': k_d['K_d'], 'f_WS': f_ws['f_WS'],
        'f_S_ltr': f_ltr['f_S_ltr'],
        'f_S_ges': f_ws['f_WS'] + f_ltr['f_S_ltr'],
        'source_id': din6892.SOURCE_FVA,
    }


def fva600_relative_opening_volume(delta_volume, load_bearing_length,
                                   effective_depth, contact_perimeter):
    """Deprecated wrapper; ``contact_perimeter`` is the old U_PF value in mm."""
    result = din6892.relative_opening_volume(
        delta_volume, load_bearing_length, effective_depth,
        float(contact_perimeter) * 1000.0, 0.5)
    return {'badge': EVIDENCE_FVA_RESEARCH,
            'delta_volume': result['delta_volume_mm3'],
            'theoretical_volume': result['V_theo_mm3'], 'v': result['v'],
            'v_crit': result['v_crit'], 'source_id': din6892.SOURCE_FVA}


# =============================================================== fit checks
def fit_checks(d, tapered=False):
    """The clearance / fit table printed in the audit.

    Each row is (label, value_mm, lower_bound_or_None, note). A value below the
    lower bound is a FAIL; a None bound means the row is informative.
    """
    rows = []
    if not tapered:
        rows.append(('shaft OD vs hub bore', d['d_i'] / 2.0 - d['R'], 0.0,
                     'gap>=0 (0 = line-to-line seat)'))
    rows.append(('key base vs keyway floor', d['y_min'] - d['yF'], None,
                 'should be ~0'))
    rows.append(('shaft keyway flank/side', (d['slot_w'] - d['b']) / 2.0, 0.0,
                 '>=0 (0 = tight fit, DIN P9/h9)'))
    rows.append(('hub groove flank/side', (d['groove_w'] - d['b']) / 2.0, 0.0, '>=0'))
    rows.append(('key top vs groove roof (g_c)', d['g_c'], 0.0, 'gap>=0'))
    rows.append(('key length vs keyway (Form %s)' % d['form'], d['l_max'] - d['l'],
                 0.0, 'l <= %.2f' % d['l_max']))
    rows.append(('hub length vs keyway span', d['keyway_span'] - d['L_hub'], None,
                 'info only'))
    rows.append(('plain shaft after keyway', d['L'] - d['z1'], 0.0,
                 'room for the end BC (want >= D/4 = %.2f)' % (d['D'] / 4.0)))
    rows.append(('chamfer c vs root fillet r2', d['c'] - d['c_min_bottom'], 0.0,
                 'need c >= r2 = %.3f' % d['c_min_bottom']))
    rows.append(('  -> bottom chamfer clearance', d['clear_bottom'], 0.0,
                 '= (c - r2)/sqrt(2)'))
    rows.append(('  -> top chamfer clearance', d['clear_top'], 0.0,
                 'vs hub roof fillet r1'))
    rows.append(('straight flank left on key', d['flank_total'], 0.0,
                 '= h - 2c, load-carrying height'))
    rows.append(('hub wall left above keyway', d['hub_wall_left'], 0.0,
                 '= d_a/2 - (R + t2); raise Q_A if <= 0'))
    return rows


# =============================================================== GUI helpers
def format_derived_text(d, issues=None):
    """The read-only 'Derived' panel shown by the GUI."""
    txt = (
        "R = D/2 = %.3f      L = %.1f x D = %.3f\n"
        "DIN 6885 (band %.0f..%.0f mm):  b = %.2f   h = %.2f   t1 = %.2f   t2 = %.2f\n"
        "R_cap = %.2f %s   z0 = R_cap+%.1f = %.2f   z1 = z0+2R_cap+dz = %.2f\n"
        "y_F = R-t1 = %.3f   y_max = R-t1+h = %.3f   x_w = b/2 = %.2f\n"
        "key Form %s  l = %.2f %s (max %.2f)   phi_c = 45 deg\n"
        "hub: d_i = %.2f   d_a = D*Q_A = %.2f   roof = R+t2 = %.3f   g_c = %.3f\n"
        "why c: need c >= r2 = %.3f -> clearance (c-r2)/sqrt2 = %.4f | top %.4f\n"
        "flank left h-2c = %.3f      hub wall left = %.3f\n"
        "seeds: shaft %.3f%s  key %.3f%s  hub %.3f%s\n"
        "notch: %s  arc %d elem -> %.4f mm in-plane, band %.3f mm, axial AR ~%.0f"
        % (d['R'], d['L_over_D'], d['L'],
           d['din_band'][0], d['din_band'][1], d['b'], d['h'], d['t1'], d['t2'],
           d['R_cap'], "(auto b/2)" if d['R_cap_auto'] else "(user)",
           d['z0_offset'], d['z0'], d['z1'],
           d['yF'], d['y_max'], d['x_w'],
           d['form'], d['l'], "(auto)" if d['l_auto'] else "(user)", d['l_max'],
           d['d_i'], d['d_a'], d['groove_roof'], d['g_c'],
           d['r2'], d['clear_bottom'], d['clear_top'],
           d['flank_total'], d['hub_wall_left'],
           d['seed_shaft'], "*" if d['seed_shaft_auto'] else " ",
           d['seed_key'], "*" if d['seed_key_auto'] else " ",
           d['seed_hub'], "*" if d['seed_hub_auto'] else " ",
           "ON" if d['notch_on'] else "off", d['notch_arc_elems'],
           d['s_notch_shaft'], d['band_shaft'], d['ar_notch_expect']))
    if d['dc_on']:
        txt += ("\ndesign: tau_nom = %.2f MPa   p_shaft = %.1f   p_hub = %.1f MPa"
                "   T_perm = %.0f N m"
                % (d['tau_nom'], d['p_shaft'], d['p_hub'], d['T_perm']))
    if issues:
        errs = errors(issues)
        wrns = warnings_(issues)
        if errs:
            txt += "\n\n!! %d ERROR(S) - the build would fail:" % len(errs)
            for i in errs:
                txt += "\n   - %s" % i['msg']
        if wrns:
            txt += "\n\n!  %d warning(s):" % len(wrns)
            for i in wrns:
                txt += "\n   - %s" % i['msg']
    return txt


def summary_line(d):
    return ('D%.0f Form %s | %s hub QA=%.2f | %s %s | seeds %.2f/%.2f/%.2f'
            % (d['D'], d['form'], 'cyl', d['QA'],
               d.get('builder_version', BUILDER_VERSION),
               'notch ON' if d['notch_on'] else 'notch off',
               d['seed_shaft'], d['seed_key'], d['seed_hub']))


if __name__ == '__main__':
    # Self-test without Abaqus: derive + validate the defaults and a few variants.
    def _show(title, over):
        p = default_params()
        if over:
            deep_update(p, over)
        d = derive(p)
        iss = validate(p, d)
        ne = len(errors(iss))
        nw = len(warnings_(iss))
        print('%-34s D=%-6.1f b=%-4.1f l=%-6.2f errors=%d warnings=%d'
              % (title, d['D'], d['b'], d['l'], ne, nw))
        for line in format_issues(iss):
            print(line)

    _show('defaults (D40 Form A)', None)
    _show('D50', {'shaft': {'D': 50.0, 'dz': 48.0}})
    _show('Form B', {'key_form': 'B'})
    _show('bad: c < r2', {'key': {'c': 0.2}})
    _show('bad: QA too small', {'hub': {'QA': 1.1}})
    _show('bad: keyway off shaft', {'shaft': {'dz': 200.0}})
    _show('bad: Form A too short', {'key': {'l': 8.0}})
    _show('snap l to DIN', {'key': {'snap_length_to_din': True}})
