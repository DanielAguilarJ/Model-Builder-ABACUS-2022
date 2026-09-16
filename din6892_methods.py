# -*- coding: utf-8 -*-
"""DIN 6892 and FVA 600 III calculation engine for Model Builder.

Pure Python 2.7/3.x: no Abaqus imports and no third-party dependencies.

The module intentionally separates four evidence levels:

* ``DIN-METHOD``: equations transcribed from the licensed/user-supplied
  DIN 6892 context. Diagram/table factors that are not available as equations
  remain explicit user inputs.
* ``FVA-RESEARCH``: equations and material data transcribed from the supplied
  FVA 600 III final report (FVA booklet 1686, 2025).
* ``USER-INPUT``: values that need a licensed standard, test certificate or
  engineering decision (for example K_lambda or a DIN 743 result).
* ``NOT-IMPLEMENTED``: a related standard is visible in the registry, but the
  application must not claim that its complete procedure is implemented.

Nothing in this module constitutes certification or replaces licensed
standards and engineering review.
"""
from __future__ import print_function, division

import json
import math

ENGINE_VERSION = "din6892-methods-1.0"
SOURCE_FVA = "FVA600_III_1686_2025"
SOURCE_DIN6892 = "DIN6892_USER_LICENSED_CONTEXT"
BADGE_DIN_METHOD = "DIN-METHOD"
BADGE_FVA_RESEARCH = "FVA-RESEARCH"
BADGE_USER_INPUT = "USER-INPUT"
BADGE_NOT_IMPLEMENTED = "NOT-IMPLEMENTED"

METHOD_A = "A_FE_VOLUME"
METHOD_B_CURRENT = "B_DIN_CURRENT"
METHOD_B_FVA = "B_FVA_2025"
METHOD_C = "C_PRELIMINARY"
METHOD_IDS = (METHOD_A, METHOD_B_CURRENT, METHOD_B_FVA, METHOD_C)

BACKEND_LEGACY_D40 = "d40_v3_refined_hex_nojob"
BACKEND_METHOD_A_CONNECTED = "method_a_connected_mesh_v1"
BACKEND_METHOD_A_HYBRID_HEX = "method_a_hybrid_hex_v2"

SHAFT_MODEL_COMBINED = "CHABOCHE_LEMAITRE_COMBINED"
HUB_MODEL_UML = "UML_RAMBERG_OSGOOD"
MODEL_ELASTIC_IDEAL_PLASTIC = "ELASTIC_IDEAL_PLASTIC"
MODEL_LINEAR_ELASTIC = "LINEAR_ELASTIC"
DEFAULT_MATERIAL_MODELS = {
    "shaft": SHAFT_MODEL_COMBINED,
    "hub": HUB_MODEL_UML,
    "key": MODEL_ELASTIC_IDEAL_PLASTIC,
}

BACKEND_CAPABILITIES = {
    BACKEND_LEGACY_D40: {
        "label": "Legacy D40 refined-hex pre-solve backend",
        "implementation": "LEGACY_PARTIAL",
        "supported_methods": [METHOD_A],
        "supported_variants": ["VB1"],
        "supported_material_pairs": ["C45N_C45N"],
        "supported_cycles": [1],
        "minimum_cycles": 1,
        "recommended_cycles": 1,
        "creates_job": False,
        "submits_solver": False,
        "complete_method_a": False,
        "strict_no_job_required": True,
        "matching_status": "NOT_VERIFIED",
        "geometry_status": "AUDITED_ADAPTATION_NOT_EXACT_FVA_SPECIMEN",
        "supported_material_models": {},
        "limitations": [
            "Locked D40 geometry adapted from the existing conical V3 model",
            "One load cycle is regression evidence, below Method-A minimum",
            "No job, input deck, solve or ODB is created",
            "VB2..VB8 and 42CrMoS4+QT are not realized by this backend",
        ],
    },
    BACKEND_METHOD_A_CONNECTED: {
        "label": "DIN 6892 Method-A connected cylindrical backend",
        "implementation": "METHOD_A_NUMERICAL_SETUP",
        "supported_methods": [METHOD_A],
        "supported_variants": ["VB%d" % index for index in range(1, 9)],
        "supported_material_pairs": ["C45N_C45N", "42CRMO4QT_42CRMO4QT"],
        "supported_cycles": None,
        "minimum_cycles": 10,
        "recommended_cycles": 20,
        "creates_job": True,
        "submits_solver": True,
        "complete_method_a": False,
        "strict_no_job_required": False,
        "matching_status": "VERIFY_AT_BUILD",
        "geometry_status": "PARAMETRIC_CYLINDRICAL_SHAFT_KEY_HUB",
        "supported_material_models": {
            "shaft": [SHAFT_MODEL_COMBINED, MODEL_ELASTIC_IDEAL_PLASTIC,
                      MODEL_LINEAR_ELASTIC],
            "hub": [HUB_MODEL_UML, MODEL_ELASTIC_IDEAL_PLASTIC,
                    MODEL_LINEAR_ELASTIC],
            "key": [MODEL_ELASTIC_IDEAL_PLASTIC, MODEL_LINEAR_ELASTIC],
        },
        "limitations": [
            "Creates the cyclic Method-A model and verification sets but does not solve by default",
            "Complete Method-A evidence still requires a solved unloaded frame and volume post-processing",
            "DIN 743 fatigue verification remains independent",
        ],
    },
}

# The v2 backend shares the connected physics/material capability but replaces
# the all-tetrahedral volume fill with a quadratic, bounded hybrid-hex policy.
BACKEND_CAPABILITIES[BACKEND_METHOD_A_HYBRID_HEX] = json.loads(json.dumps(
    BACKEND_CAPABILITIES[BACKEND_METHOD_A_CONNECTED]))
BACKEND_CAPABILITIES[BACKEND_METHOD_A_HYBRID_HEX].update({
    "label": "DIN 6892 Method-A hybrid-hex cylindrical backend",
    "implementation": "METHOD_A_HYBRID_HEX_SETUP",
    "matching_status": "VERIFY_AT_BUILD",
    "geometry_status": "PARAMETRIC_CYLINDRICAL_SHAFT_KEY_HUB_HYBRID_HEX",
    "limitations": [
        "Quadratic hex-dominated volume mesh with bounded C3D15/C3D10 transitions",
        "Interface patterns, <=1 mm edge limit and rectangular opening grid are verified at build",
        "Complete Method-A evidence still requires a solved unloaded frame and independent DIN 743 review",
    ],
})


# Registry shown to the user. It provides freedom to select the governing
# workflow while making implementation limits machine-readable.
STANDARD_REGISTRY = {
    "DIN_6885_1_2021": {
        "title": "Parallel keys, geometry and tolerances",
        "role": "geometry",
        "implementation": "IMPLEMENTED",
        "badge": "NORMATIVE",
        "notes": "Numeric DIN 6885-1 bands/forms implemented by keyjoint_core",
    },
    "DIN_6892": {
        "title": "Parallel-key load-carrying capacity",
        "role": "strength",
        "implementation": "METHODS_A_B_C",
        "badge": BADGE_DIN_METHOD,
        "notes": "A/B/C workflows; licensed diagram factors remain user inputs",
    },
    "DIN_743": {
        "title": "Shaft fatigue strength",
        "role": "fatigue",
        "implementation": "EXTERNAL_RESULT_REQUIRED",
        "badge": BADGE_USER_INPUT,
        "notes": "Required independent fatigue verification; no bundled DIN tables",
    },
    "DIN_EN_ISO_286": {
        "title": "Limits and fits",
        "role": "fit",
        "implementation": "USER_INPUT",
        "badge": BADGE_USER_INPUT,
        "notes": "Fit/interference may be entered; complete licensed tolerance tables are not bundled",
    },
    "DIN_EN_ISO_18265": {
        "title": "Hardness conversion",
        "role": "material",
        "implementation": "REPORT_DATA_ONLY",
        "badge": "FVA-RESEARCH",
        "notes": "FVA Table 6 estimates are available; no general conversion table is bundled",
    },
    "DIN_7190_1": {
        "title": "Interference fits / minimum friction torque",
        "role": "friction_closure",
        "implementation": "USER_INPUT",
        "badge": BADGE_USER_INPUT,
        "notes": "M_Rmin or K_R must be supplied; FVA recommendation K_R=1 is separately labelled",
    },
    "DIN_6880": {
        "title": "Key stock",
        "role": "key_material",
        "implementation": "REFERENCE_ONLY",
        "badge": BADGE_NOT_IMPLEMENTED,
        "notes": "Material/product reference only",
    },
    "DIN_6888": {
        "title": "Woodruff keys",
        "role": "alternative_geometry",
        "implementation": "NOT_IMPLEMENTED",
        "badge": BADGE_NOT_IMPLEMENTED,
        "notes": "Visible choice, but no Woodruff-key solid backend is implemented",
    },
}

METHOD_CATALOG = {
    METHOD_A: {
        "badge": BADGE_FVA_RESEARCH,
        "source_id": SOURCE_FVA,
        "scope": "FE verification using relative plastic keyway-opening volume",
        "requires_solver_result": True,
        "creates_solver": False,
        "minimum_cycles": 10,
    },
    METHOD_B_CURRENT: {
        "badge": BADGE_DIN_METHOD,
        "source_id": SOURCE_DIN6892,
        "scope": "Analytical Method B using equivalent pressure and explicit factors",
        "requires_solver_result": False,
        "creates_solver": False,
    },
    METHOD_B_FVA: {
        "badge": BADGE_FVA_RESEARCH,
        "source_id": SOURCE_FVA,
        "scope": "FVA 600 III proposed Method-B reformulation, equation 36",
        "requires_solver_result": False,
        "creates_solver": False,
    },
    METHOD_C: {
        "badge": BADGE_DIN_METHOD,
        "source_id": SOURCE_DIN6892,
        "scope": "Preliminary sizing with constant allowable pressure",
        "requires_solver_result": False,
        "creates_solver": False,
    },
}

# Table 4. Variants are discrete research configurations. They are not a
# continuous validity domain and are not automatically executable by Abaqus.
FVA_VARIANTS = {
    "VB1": {"d_w_mm": 40.0, "ltr_over_dw": 0.95, "QA_shaft_over_hub": 0.5,
            "xi_per_mille": 0.0, "load_ratio_R": 0.0, "key_form": "A"},
    "VB2": {"d_w_mm": 20.0, "ltr_over_dw": 0.95, "QA_shaft_over_hub": 0.5,
            "xi_per_mille": 0.0, "load_ratio_R": 0.0, "key_form": "A"},
    "VB3": {"d_w_mm": 60.0, "ltr_over_dw": 0.95, "QA_shaft_over_hub": 0.5,
            "xi_per_mille": 0.0, "load_ratio_R": 0.0, "key_form": "A"},
    "VB4": {"d_w_mm": 40.0, "ltr_over_dw": 0.5, "QA_shaft_over_hub": 0.5,
            "xi_per_mille": 0.0, "load_ratio_R": 0.0, "key_form": "A"},
    "VB5": {"d_w_mm": 40.0, "ltr_over_dw": 0.95, "QA_shaft_over_hub": 0.7,
            "xi_per_mille": 0.0, "load_ratio_R": 0.0, "key_form": "A"},
    "VB6": {"d_w_mm": 40.0, "ltr_over_dw": 0.95, "QA_shaft_over_hub": 0.5,
            "xi_per_mille": 0.5, "load_ratio_R": 0.0, "key_form": "A"},
    "VB7": {"d_w_mm": 40.0, "ltr_over_dw": 0.95, "QA_shaft_over_hub": 0.5,
            "xi_per_mille": 0.0, "load_ratio_R": 0.0, "key_form": "B"},
    "VB8": {"d_w_mm": 40.0, "ltr_over_dw": 0.95, "QA_shaft_over_hub": 0.5,
            "xi_per_mille": 0.0, "load_ratio_R": -1.0, "key_form": "A"},
}

# Table 5 (quasi-static tests), Table 6 (hardness estimates), Table 8
# (shaft cyclic plasticity), and Table 9 (hub UML). Values are only supplied
# for the measured diameters. No interpolation is performed.
MATERIAL_CATALOG = {
    "C45N_C45N": {
        "label": "C45+N / C45+N; key C45+QT",
        "shaft_grade": "C45+N", "hub_grade": "C45+N", "key_grade": "C45+QT",
        "diameters": {
            20: {"shaft": {"Re_MPa": 368.0, "Rm_MPa": 670.0, "E_MPa": 199000.0},
                 "hub": {"Re_MPa": 283.0, "Rm_MPa": 527.0, "E_MPa": 185000.0},
                 "hardness_Rm_shaft_MPa": 716.0, "hub_K_prime_MPa": 868.0},
            40: {"shaft": {"Re_MPa": 377.0, "Rm_MPa": 676.0, "E_MPa": 187000.0},
                 "hub": {"Re_MPa": 279.0, "Rm_MPa": 579.0, "E_MPa": 196000.0},
                 "hardness_Rm_shaft_MPa": 716.0, "hub_K_prime_MPa": 955.0},
            60: {"shaft": {"Re_MPa": 363.0, "Rm_MPa": 650.0, "E_MPa": 190000.0},
                 "hub": {"Re_MPa": 282.0, "Rm_MPa": 584.0, "E_MPa": 194000.0},
                 "hardness_Rm_shaft_MPa": 748.0, "hub_K_prime_MPa": 963.0},
        },
        "shaft_cyclic": {"Q_inf_MPa": 32.74, "b_iso": 249.8,
                          "C_i_MPa": [15260.0], "gamma_i": [50.8]},
        "hub_n_prime": 0.15,
    },
    "42CRMO4QT_42CRMO4QT": {
        "label": "42CrMoS4+QT / 42CrMoS4+QT; key C45+QT",
        "shaft_grade": "42CrMoS4+QT", "hub_grade": "42CrMoS4+QT",
        "key_grade": "C45+QT",
        "diameters": {
            20: {"shaft": {"Re_MPa": 767.0, "Rm_MPa": 908.0, "E_MPa": 193000.0},
                 "hub": {"Re_MPa": 580.0, "Rm_MPa": 774.0, "E_MPa": None},
                 "hardness_Rm_shaft_MPa": 1250.0, "hub_K_prime_MPa": 1278.0},
            40: {"shaft": {"Re_MPa": 849.0, "Rm_MPa": 969.0, "E_MPa": 198000.0},
                 "hub": {"Re_MPa": 592.0, "Rm_MPa": 789.0, "E_MPa": 203000.0},
                 "hardness_Rm_shaft_MPa": 1189.0, "hub_K_prime_MPa": 1302.0},
            60: {"shaft": {"Re_MPa": 881.0, "Rm_MPa": 969.0, "E_MPa": 210000.0},
                 "hub": {"Re_MPa": 607.0, "Rm_MPa": 810.0, "E_MPa": 182000.0},
                 "hardness_Rm_shaft_MPa": 1250.0, "hub_K_prime_MPa": 1367.0},
        },
        "shaft_cyclic": {"Q_inf_MPa": -330.0, "b_iso": 2.0,
                          "C_i_MPa": [1134.0, 179.0, 119.0],
                          "gamma_i": [197.0, 187.0, 2318.0]},
        "hub_n_prime": 0.15,
    },
}
KEY_MATERIAL = {"grade": "C45+QT", "E_MPa": 210000.0, "nu": 0.30,
                "yield_MPa": 928.0, "hardness_Rm_MPa": 877.0,
                "model": "elastic_ideal_plastic"}

# FVA 600 III, Table 11.  Preserve the tabulated values literally.  The
# accompanying narrative says t1/b rises with diameter, while the table gives
# 0.583, 0.5, 0.5; callers therefore receive an explicit inconsistency flag
# instead of an invented monotonic correction.
FVA_TABLE11_GEOMETRY = {
    20: {"max_relative_interference_per_mille": 1.24, "t1_over_b": 0.583},
    40: {"max_relative_interference_per_mille": 0.80, "t1_over_b": 0.500},
    60: {"max_relative_interference_per_mille": 0.53, "t1_over_b": 0.500},
}


# FVA 600 III reference results. These are MEASURED support factors and torques
# from the report, kept so an implementation can be compared against the source
# instead of only against itself. They are evidence, not equations: the analytic
# chain needs K_lambda from a licensed diagram to reproduce the torques, so only
# the dimensionless identities below are self-checkable.
FVA_REFERENCE_RESULTS = {
    "VB1": {
        "C45N_C45N": {"f_S_experiment": 1.72, "f_S_simulation": 2.06,
                      "torque_experiment_Nm": 1440.0,
                      "simulation_overestimate_percent": 19.0,
                      "relative_capacity": 1.00},
        "42CRMO4QT_42CRMO4QT": {"f_S_experiment": 1.18, "f_S_simulation": 1.34,
                                "simulation_overestimate_percent": 13.0,
                                "relative_capacity": 1.00},
    },
    "VB2": {"C45N_C45N": {"f_S_experiment": 1.27, "torque_experiment_Nm": 199.0,
                          "relative_capacity": 0.85}},
    "VB3": {"C45N_C45N": {"f_S_experiment": 1.67, "torque_experiment_Nm": 4479.0,
                          "relative_capacity": 0.96}},
    "VB4": {"C45N_C45N": {"f_S_experiment": 1.78, "torque_experiment_Nm": 826.0,
                          "estimated": True, "relative_capacity": 1.08}},
    "VB5": {"C45N_C45N": {"f_S_simulation": 1.93, "relative_capacity": 0.94}},
    "VB6": {"C45N_C45N": {"f_S_experiment": 1.06, "torque_experiment_Nm": 1404.0,
                          "K_R_din": 0.56, "f_S_corrected": 1.89,
                          "torque_corrected_Nm": 1582.0, "K_R_corrected": 1.0,
                          "relative_capacity": 0.98}},
    "VB7": {"C45N_C45N": {"f_S_experiment": 1.66, "torque_experiment_Nm": 1381.0,
                          "relative_capacity": 0.94}},
    "VB8": {"C45N_C45N": {"f_S_experiment": 1.14, "torque_experiment_Nm": 867.0,
                          "relative_capacity": 0.90}},
}
# Support factors measured at the two evaluated criticality levels. The ratio
# between them must reproduce the volume support factor of equation 26.
FVA_VOLUME_CALIBRATION = {
    "C45N_C45N": {"f_S_at_v_0_5": 1.72, "f_S_at_v_1_0": 2.36},
    "42CRMO4QT_42CRMO4QT": {"f_S_at_v_0_5": 1.17, "f_S_at_v_1_0": 1.62},
}
# DIN 6892 Method B reference torque for d_w = 40 mm, l_tr/d_w = 0.5, C45+N.
FVA_DIN_REFERENCE_TORQUE_NM = 626.0


def _clone(value):
    return json.loads(json.dumps(value))


def volume_support_factor_calibration(tolerance_percent=2.0):
    """Check equation 26 against the report's own measured support factors.

    f_Sv is normalised at v = 0.5, so f_Sv(1.0)/f_Sv(0.5) must equal the measured
    ratio f_S(v=1)/f_S(v=0.5) for both material pairs. This is the one part of
    the FVA reformulation that can be validated without a licensed K_lambda
    diagram.
    """
    predicted = (volume_support_factor(1.0)["f_Sv"] /
                 volume_support_factor(0.5)["f_Sv"])
    limit = _number(tolerance_percent, "tolerance_percent", positive=True)
    rows = []
    worst = 0.0
    for pair in sorted(FVA_VOLUME_CALIBRATION):
        data = FVA_VOLUME_CALIBRATION[pair]
        measured = data["f_S_at_v_1_0"] / data["f_S_at_v_0_5"]
        deviation = abs(measured - predicted) / predicted * 100.0
        worst = max(worst, deviation)
        rows.append({"material_pair": pair, "measured_ratio": measured,
                     "predicted_ratio": predicted,
                     "deviation_percent": deviation,
                     "within_tolerance": deviation <= limit})
    return {"equation": 26, "source_id": SOURCE_FVA,
            "badge": BADGE_FVA_RESEARCH,
            "predicted_ratio": predicted, "rows": rows,
            "tolerance_percent": limit,
            "worst_deviation_percent": worst,
            "validated": worst <= limit,
            "note": ("f_Sv = 0.74*v + 0.63 equals 1.0 at the research criterion "
                     "v_krit = 0.5, so the factor is a ratio relative to that "
                     "criticality level.")}


def reference_results(variant_id=None, material_pair=None):
    """Measured FVA 600 III support factors and torques for comparison."""
    data = _clone(FVA_REFERENCE_RESULTS)
    if variant_id is None:
        return {"rows": data, "source_id": SOURCE_FVA,
                "badge": BADGE_FVA_RESEARCH, "source_tables": [4],
                "din_reference_torque_Nm": FVA_DIN_REFERENCE_TORQUE_NM}
    key = str(variant_id).strip().upper()
    if key not in data:
        raise ValueError("No FVA reference result for %r" % variant_id)
    row = data[key]
    if material_pair is None:
        return {"variant_id": key, "rows": row, "source_id": SOURCE_FVA,
                "badge": BADGE_FVA_RESEARCH}
    pair = str(material_pair).strip().upper()
    if pair not in row:
        raise ValueError("No FVA reference result for %s / %s"
                         % (key, material_pair))
    result = dict(row[pair])
    result.update({"variant_id": key, "material_pair": pair,
                   "source_id": SOURCE_FVA, "badge": BADGE_FVA_RESEARCH})
    return result


def _number(value, name, positive=False, allow_zero=False):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be numeric; received %r" % (name, value))
    if hasattr(math, "isfinite"):
        finite = math.isfinite(result)
    else:
        finite = not (math.isinf(result) or math.isnan(result))
    if not finite:
        raise ValueError("%s must be finite" % name)
    if positive and (result < 0.0 if allow_zero else result <= 0.0):
        relation = ">= 0" if allow_zero else "> 0"
        raise ValueError("%s must be %s" % (name, relation))
    return result


def standard_registry():
    return _clone(STANDARD_REGISTRY)


def method_catalog():
    return _clone(METHOD_CATALOG)


def variant_catalog():
    out = _clone(FVA_VARIANTS)
    for key in out:
        out[key]["variant_id"] = key
        out[key]["badge"] = BADGE_FVA_RESEARCH
        out[key]["source_id"] = SOURCE_FVA
        out[key]["source_table"] = 4
    return out


def variant(variant_id):
    key = str(variant_id or "").strip().upper()
    if key not in FVA_VARIANTS:
        raise ValueError("Unknown FVA variant %r; expected VB1..VB8" % variant_id)
    result = _clone(FVA_VARIANTS[key])
    result.update({"variant_id": key, "badge": BADGE_FVA_RESEARCH,
                   "source_id": SOURCE_FVA, "source_table": 4})
    return result


def backend_capabilities():
    return _clone(BACKEND_CAPABILITIES)


def assess_backend_request(config):
    """Return a machine-readable requested/derived/realized CAE verdict.

    Capability and user intent are kept separate.  In particular, a backend
    that *can* create/submit a job still reports both actions as false unless
    they were explicitly requested.  This makes the default Method-A route a
    safe model-only workflow.
    """
    cfg = config or {}
    execution = cfg.get("execution", {}) or {}
    matching = cfg.get("mesh_matching", {}) or {}
    models = cfg.get("material_models", {}) or {}
    requested = {
        "enabled": bool(cfg.get("enabled", False)),
        "backend": str(cfg.get("backend", BACKEND_METHOD_A_HYBRID_HEX) or ""),
        "method": str(cfg.get("requested_method", METHOD_A) or "").upper(),
        "variant_id": str(cfg.get("variant_id", "VB1") or "").upper(),
        "material_pair": str(cfg.get("material_pair", "C45N_C45N") or "").upper(),
        "cycles": int(cfg.get("cycles", 0) or 0),
        "strict_no_job": bool(cfg.get("strict_no_job", False)),
        "create_job": bool(execution.get("create_job", False)),
        "submit_solver": bool(execution.get("submit_solver", False)),
        "material_models": dict((name, str(models.get(
            name, DEFAULT_MATERIAL_MODELS[name]) or "").upper())
            for name in ("shaft", "hub", "key")),
        "matching_required": bool(matching.get("required", True)),
        "matching_verify_after_meshing": bool(
            matching.get("verify_after_meshing", True)),
        "matching_interfaces": list(matching.get("interfaces") or [
            "SHAFT_KEY_LEFT", "SHAFT_KEY_RIGHT", "HUB_KEY_LEFT",
            "HUB_KEY_RIGHT", "SHAFT_HUB"]),
        "matching_target_size_mm": float(matching.get("target_size_mm", 1.0) or 0.0),
        "matching_tolerance_mm": float(matching.get("tolerance_mm", 1.0e-6) or 0.0),
    }
    if not requested["enabled"]:
        return {
            "requested": requested,
            "derived": {"capability": None},
            "realized": {"status": "NOT_REQUESTED", "matching": "NOT_APPLICABLE",
                         "creates_job": False, "submits_solver": False,
                         "complete_method_a": False},
            "executable": True,
            "issues": [],
        }
    capability = BACKEND_CAPABILITIES.get(requested["backend"])
    if capability is None:
        return {
            "requested": requested,
            "derived": {"capability": None},
            "realized": {"status": "BLOCKED", "matching": "NOT_VERIFIED",
                         "creates_job": False, "submits_solver": False,
                         "complete_method_a": False},
            "executable": False,
            "issues": [{"level": "error", "code": "fva_backend_unknown",
                        "msg": "Unknown FVA CAE backend %r." % requested["backend"]}],
        }
    issues = []

    def reject(code, message):
        issues.append({"level": "error", "code": code, "msg": message})

    if requested["method"] not in capability["supported_methods"]:
        reject("fva_backend_method_unsupported",
               "Backend %s cannot realize method %s." %
               (requested["backend"], requested["method"]))
    if requested["variant_id"] not in capability["supported_variants"]:
        reject("fva_backend_variant_unsupported",
               "Backend %s realizes only %s, not %s." %
               (requested["backend"], ", ".join(capability["supported_variants"]),
                requested["variant_id"]))
    if requested["material_pair"] not in capability["supported_material_pairs"]:
        reject("fva_backend_material_unsupported",
               "Backend %s does not realize material pair %s." %
               (requested["backend"], requested["material_pair"]))
    supported_cycles = capability.get("supported_cycles")
    minimum_cycles = int(capability.get("minimum_cycles", 1) or 1)
    if supported_cycles is not None and requested["cycles"] not in supported_cycles:
        reject("fva_backend_cycles_unsupported",
               "Backend %s is locked to %s cycle(s), not %d." %
               (requested["backend"], supported_cycles, requested["cycles"]))
    elif supported_cycles is None and requested["cycles"] < minimum_cycles:
        reject("fva_backend_cycles_unsupported",
               "Backend %s requires at least %d cycles, not %d." %
               (requested["backend"], minimum_cycles, requested["cycles"]))
    if capability["strict_no_job_required"] and not requested["strict_no_job"]:
        reject("fva_backend_nojob_required",
               "Backend %s requires strict_no_job=true." % requested["backend"])
    if requested["submit_solver"] and not requested["create_job"]:
        reject("fva_backend_submit_requires_job",
               "Solver submission requires execution.create_job=true.")
    if requested["strict_no_job"] and (requested["create_job"] or
                                        requested["submit_solver"]):
        reject("fva_backend_strict_nojob_conflict",
               "strict_no_job=true conflicts with job creation or solver submission.")
    if requested["create_job"] and not capability.get("creates_job", False):
        reject("fva_backend_job_unsupported",
               "Backend %s cannot create a job." % requested["backend"])
    if requested["submit_solver"] and not capability.get("submits_solver", False):
        reject("fva_backend_solver_unsupported",
               "Backend %s cannot submit the solver." % requested["backend"])

    supported_models = capability.get("supported_material_models") or {}
    for component in ("shaft", "hub", "key"):
        allowed = supported_models.get(component) or []
        if allowed and requested["material_models"][component] not in allowed:
            reject("fva_backend_material_model_unsupported",
                   "Backend %s does not support %s model %s (allowed: %s)." %
                   (requested["backend"], component,
                    requested["material_models"][component], ", ".join(allowed)))

    if requested["backend"] in (
            BACKEND_METHOD_A_CONNECTED, BACKEND_METHOD_A_HYBRID_HEX):
        if not requested["matching_required"]:
            reject("fva_backend_matching_required",
                   "The connected Method-A backend requires mesh matching verification.")
        if not requested["matching_verify_after_meshing"]:
            reject("fva_backend_matching_after_mesh_required",
                   "Method-A matching must be verified after actual meshing.")
        required_interfaces = [
            "SHAFT_KEY_LEFT", "SHAFT_KEY_RIGHT", "HUB_KEY_LEFT",
            "HUB_KEY_RIGHT", "SHAFT_HUB"]
        if requested["matching_interfaces"] != required_interfaces:
            reject("fva_backend_matching_interfaces_invalid",
                   "Method-A requires exactly five ordered matching interfaces: %s." %
                   ", ".join(required_interfaces))
        if requested["matching_target_size_mm"] <= 0.0:
            reject("fva_matching_target_invalid",
                   "mesh_matching.target_size_mm must be positive.")
        elif requested["matching_target_size_mm"] > 1.0 + 1.0e-12:
            reject("fva_matching_target_too_coarse",
                   "FVA Method-A contact mesh target must be <= 1 mm.")
        if requested["matching_tolerance_mm"] <= 0.0:
            reject("fva_matching_tolerance_invalid",
                   "mesh_matching.tolerance_mm must be positive.")

    executable = not issues
    status = capability["implementation"] if executable else "BLOCKED"
    return {
        "requested": requested,
        "derived": {"capability": _clone(capability)},
        "realized": {
            "status": status,
            "matching": capability["matching_status"],
            "creates_job": (requested["create_job"] if executable else False),
            "submits_solver": (requested["submit_solver"] if executable else False),
            "complete_method_a": (capability["complete_method_a"]
                                  if executable else False),
        },
        "executable": executable,
        "issues": issues,
    }


def material_properties(pair_id, diameter_mm):
    key = str(pair_id or "").strip().upper()
    if key not in MATERIAL_CATALOG:
        raise ValueError("Unknown material pair %r" % pair_id)
    diameter = _number(diameter_mm, "diameter_mm", positive=True)
    rounded = int(round(diameter))
    if abs(diameter - rounded) > 1e-9 or rounded not in (20, 40, 60):
        raise ValueError("FVA material data are discrete at d_w = 20, 40 or 60 mm; no interpolation is allowed")
    data = _clone(MATERIAL_CATALOG[key])
    diameter_points = data.pop("diameters")
    point = diameter_points.get(rounded, diameter_points.get(str(rounded)))
    if point is None:
        raise ValueError("No FVA material data at d_w = %s mm" % rounded)
    result = {
        "pair_id": key, "label": data["label"], "diameter_mm": float(rounded),
        "shaft_grade": data["shaft_grade"], "hub_grade": data["hub_grade"],
        "key_grade": data["key_grade"], "shaft": point["shaft"],
        "hub": point["hub"], "shaft_cyclic": data["shaft_cyclic"],
        "hub_uml": {"K_prime_MPa": point["hub_K_prime_MPa"],
                    "n_prime": data["hub_n_prime"]},
        "hardness_Rm_shaft_MPa": point["hardness_Rm_shaft_MPa"],
        "key": _clone(KEY_MATERIAL), "badge": BADGE_FVA_RESEARCH,
        "source_id": SOURCE_FVA,
        "source_tables": [5, 6, 8, 9],
        "interpolated": False,
    }
    return result


def geometry_trend_table():
    """Return the literal Table-11 diameter trend and its consistency checks."""
    rows = []
    for diameter in sorted(FVA_TABLE11_GEOMETRY):
        item = _clone(FVA_TABLE11_GEOMETRY[diameter])
        item["diameter_mm"] = float(diameter)
        rows.append(item)
    interference = [row["max_relative_interference_per_mille"] for row in rows]
    depth_ratio = [row["t1_over_b"] for row in rows]
    return {
        "rows": rows,
        "max_relative_interference_decreases": all(
            interference[index + 1] < interference[index]
            for index in range(len(interference) - 1)),
        "t1_over_b_increases": all(
            depth_ratio[index + 1] > depth_ratio[index]
            for index in range(len(depth_ratio) - 1)),
        "narrative_table_conflict": True,
        "warning": ("FVA Table 11 gives t1/b = 0.583, 0.5, 0.5 for "
                    "d = 20, 40, 60 mm, contradicting the accompanying "
                    "statement that t1/b increases; tabulated values are retained."),
        "badge": BADGE_FVA_RESEARCH,
        "source_id": SOURCE_FVA,
        "source_table": 11,
    }


def uml_plastic_table(re_MPa, rm_MPa, k_prime_MPa, n_prime, intervals=150):
    """Generate the Abaqus stress/plastic-strain table for the FVA UML law."""
    re_value = _number(re_MPa, "Re_MPa", positive=True)
    rm_value = _number(rm_MPa, "Rm_MPa", positive=True)
    k_prime = _number(k_prime_MPa, "K_prime_MPa", positive=True)
    exponent = _number(n_prime, "n_prime", positive=True)
    count = int(intervals)
    if rm_value < re_value:
        raise ValueError("Rm_MPa must be >= Re_MPa for the UML table")
    if count < 2:
        raise ValueError("UML intervals must be at least 2")
    rows = [(re_value, 0.0)]
    for index in range(count + 1):
        fraction = float(index) / float(count)
        stress = re_value + (rm_value - re_value) * fraction
        plastic = (stress / k_prime) ** (1.0 / exponent)
        rows.append((float(stress), float(plastic)))
    return rows


def material_model_bundle(pair_id, diameter_mm, selections=None, intervals=150):
    """Resolve selected shaft/hub/key constitutive laws without Abaqus imports."""
    data = material_properties(pair_id, diameter_mm)
    selected = _clone(DEFAULT_MATERIAL_MODELS)
    if selections:
        for component in ("shaft", "hub", "key"):
            if component in selections:
                selected[component] = str(selections[component]).strip().upper()
    allowed = BACKEND_CAPABILITIES[BACKEND_METHOD_A_CONNECTED][
        "supported_material_models"]
    for component in ("shaft", "hub", "key"):
        if selected[component] not in allowed[component]:
            raise ValueError("Unsupported %s material model %r" %
                             (component, selected[component]))

    shaft = data["shaft"]
    hub = data["hub"]
    key = data["key"]
    bundle = {
        "pair_id": data["pair_id"],
        "diameter_mm": data["diameter_mm"],
        "badge": BADGE_FVA_RESEARCH,
        "source_id": SOURCE_FVA,
        "selected": selected,
        "shaft": {
            "model": selected["shaft"], "grade": data["shaft_grade"],
            "E_MPa": shaft["E_MPa"], "nu": 0.30,
            "yield_MPa": shaft["Re_MPa"],
            "combined": _clone(data["shaft_cyclic"]),
        },
        "hub": {
            "model": selected["hub"], "grade": data["hub_grade"],
            "E_MPa": hub["E_MPa"], "nu": 0.30,
            "yield_MPa": hub["Re_MPa"], "Rm_MPa": hub["Rm_MPa"],
            "uml": _clone(data["hub_uml"]),
        },
        "key": {
            "model": selected["key"], "grade": data["key_grade"],
            "E_MPa": key["E_MPa"], "nu": key["nu"],
            "yield_MPa": key["yield_MPa"],
        },
    }
    if selected["hub"] == HUB_MODEL_UML:
        if hub["E_MPa"] is None:
            raise ValueError("FVA hub E is unavailable for %s at d=%g mm" %
                             (data["pair_id"], data["diameter_mm"]))
        bundle["hub"]["plastic_table"] = uml_plastic_table(
            hub["Re_MPa"], hub["Rm_MPa"],
            data["hub_uml"]["K_prime_MPa"],
            data["hub_uml"]["n_prime"], intervals)
    return bundle


# DIN 6892 Table 2: support factor f_S and hardness factor f_H per component and
# material class. These are TABLE values, not diagram readings, so they are
# implemented instead of being left as neutral placeholders. DIN 6892 states
# explicitly that the SMALLER value must be used whenever the material is not
# known with certainty, so the lower bound is the default.
DIN6892_TABLE2_SUPPORT = {
    "key": {
        "STRUCTURAL_STEEL": {"f_S": (1.1, 1.4), "f_H": 1.0,
                             "standard": "DIN_EN_10025_1"},
        "BRIGHT_STEEL": {"f_S": (1.1, 1.4), "f_H": 1.0,
                         "standard": "DIN_EN_10277"},
        "QUENCHED_TEMPERED_STEEL": {"f_S": (1.1, 1.4), "f_H": 1.0,
                                    "standard": "DIN_EN_10083_1_2"},
        "CASE_HARDENED_STEEL": {"f_S": (1.1, 1.4), "f_H": 1.15,
                                "standard": "DIN_EN_ISO_683_3"},
    },
    "shaft": {
        "STRUCTURAL_STEEL": {"f_S": (1.3, 1.7), "f_H": 1.0,
                             "standard": "DIN_EN_10025_1"},
        "QUENCHED_TEMPERED_STEEL": {"f_S": (1.3, 1.7), "f_H": 1.0,
                                    "standard": "DIN_EN_10083_1_2"},
        "CASE_HARDENED_STEEL": {"f_S": (1.3, 1.7), "f_H": 1.15,
                                "standard": "DIN_EN_ISO_683_3"},
        "NODULAR_CAST_IRON": {"f_S": (1.3, 1.7), "f_H": 1.0,
                              "standard": "DIN_EN_1563"},
        "CAST_STEEL": {"f_S": (1.3, 1.7), "f_H": 1.0,
                       "standard": "DIN_EN_10293"},
        "LAMELLAR_CAST_IRON": {"f_S": (1.1, 1.4), "f_H": None,
                               "standard": "DIN_EN_1561"},
    },
    "hub": {
        "STRUCTURAL_STEEL": {"f_S": (1.5, 1.5), "f_H": 1.0,
                             "standard": "DIN_EN_10025_1"},
        "QUENCHED_TEMPERED_STEEL": {"f_S": (1.5, 1.5), "f_H": 1.0,
                                    "standard": "DIN_EN_10083_1_2"},
        "CASE_HARDENED_STEEL": {"f_S": (1.5, 1.5), "f_H": 1.15,
                                "standard": "DIN_EN_ISO_683_3"},
        "NODULAR_CAST_IRON": {"f_S": (1.5, 1.5), "f_H": 1.0,
                              "standard": "DIN_EN_1563"},
        "CAST_STEEL": {"f_S": (1.5, 1.5), "f_H": 1.0,
                       "standard": "DIN_EN_10293"},
        "LAMELLAR_CAST_IRON": {"f_S": (2.0, 2.0), "f_H": None,
                               "standard": "DIN_EN_1561"},
    },
}
DIN6892_MATERIAL_CLASSES = tuple(sorted(DIN6892_TABLE2_SUPPORT["hub"]))
DEFAULT_MATERIAL_CLASS = "QUENCHED_TEMPERED_STEEL"


def table2_support_factors(component, material_class=None, bound="lower"):
    """DIN 6892 Table 2 support factor f_S and hardness factor f_H.

    ``bound`` selects the lower (standard-conforming default), upper or mid
    value of the tabulated f_S range. DIN 6892 requires the smaller value when
    the material is not known, so "lower" is the safe default.
    """
    name = str(component or "").strip().lower()
    if name not in DIN6892_TABLE2_SUPPORT:
        raise ValueError("DIN 6892 Table 2 covers key, shaft and hub, not %r"
                         % component)
    material = str(material_class or DEFAULT_MATERIAL_CLASS).strip().upper()
    table = DIN6892_TABLE2_SUPPORT[name]
    if material not in table:
        raise ValueError("Unknown %s material class %r; expected one of %s"
                         % (name, material_class, ", ".join(sorted(table))))
    row = table[material]
    low, high = float(row["f_S"][0]), float(row["f_S"][1])
    selector = str(bound or "lower").strip().lower()
    if selector == "upper":
        f_s = high
    elif selector in ("mid", "middle", "mean"):
        f_s = 0.5 * (low + high)
    elif selector == "lower":
        f_s = low
    else:
        raise ValueError("f_S bound must be lower, mid or upper, not %r" % bound)
    hardness = row["f_H"]
    return {"component": name, "material_class": material,
            "f_S": f_s, "f_S_range": [low, high], "f_S_bound": selector,
            "f_H": (None if hardness is None else float(hardness)),
            "f_H_available": hardness is not None,
            "material_standard": row["standard"],
            "equations": [4, 5], "source_table": 2,
            "source_id": SOURCE_DIN6892, "badge": BADGE_DIN_METHOD,
            "note": ("DIN 6892 requires the smaller tabulated f_S whenever the "
                     "material is not known with certainty; f_H is undefined for "
                     "lamellar cast iron.")}


# DIN 6892 equation 10 defines phi only for one and two keys, and the value for
# two keys depends on whether the allowable or the peak pressure is evaluated.
LOAD_TARGET_ALLOWABLE = "p_zul"
LOAD_TARGET_PEAK = "p_max"


def default_load_share_phi(key_count, target=LOAD_TARGET_ALLOWABLE):
    """DIN 6892 equation 10 load share phi.

    phi = 1 for a single key; for two keys phi = 0.75 when the allowable
    pressure is evaluated and phi = 0.9 for the peak pressure. More than two
    keys is outside the scope of equation 10.
    """
    count = int(key_count)
    if count <= 0:
        raise ValueError("key_count must be at least 1")
    which = str(target or LOAD_TARGET_ALLOWABLE).strip().lower()
    if which not in (LOAD_TARGET_ALLOWABLE, LOAD_TARGET_PEAK):
        raise ValueError("target must be %r or %r, not %r"
                         % (LOAD_TARGET_ALLOWABLE, LOAD_TARGET_PEAK, target))
    if count == 1:
        return 1.0
    if count == 2:
        return 0.75 if which == LOAD_TARGET_ALLOWABLE else 0.90
    raise ValueError(
        "DIN 6892 equation 10 defines phi only for i = 1 or i = 2 keys; "
        "i = %d needs an explicit measured load share" % count)


def load_distribution_factor(key_count, phi=None, target=LOAD_TARGET_ALLOWABLE):
    count = int(key_count)
    if phi is None:
        share = default_load_share_phi(count, target)
        provenance = BADGE_DIN_METHOD
    else:
        share = _number(phi, "phi", positive=True)
        provenance = BADGE_USER_INPUT
    if share > 1.0:
        raise ValueError("phi is a load share and cannot exceed 1.0")
    return {"key_count": count, "phi": share, "K_V": 1.0 / (count * share),
            "phi_provenance": provenance, "load_target": str(target),
            "equation": 10, "formula": "K_V = 1/(i*phi)",
            "source_id": SOURCE_DIN6892, "badge": BADGE_DIN_METHOD}


def hub_equivalent_diameter(D1_mm, D2_mm, c_mm, ltr_mm):
    """DIN 6892 equation 11: torsion-equivalent diameter of a shouldered hub."""
    d1 = _number(D1_mm, "D1_mm", positive=True)
    d2 = _number(D2_mm, "D2_mm", positive=True)
    c = _number(c_mm, "c_mm", positive=True, allow_zero=True)
    ltr = _number(ltr_mm, "ltr_mm", positive=True)
    if c > ltr:
        raise ValueError("The flange width c cannot exceed the bearing length l_tr")
    ratio = c / ltr
    radicand = (d2 / d1) ** 4 * (1.0 - ratio) + ratio
    if radicand <= 0.0:
        raise ValueError("Equation 11 has a non-positive fourth-root argument")
    return {"D_ers_mm": d2 / radicand ** 0.25, "D1_mm": d1, "D2_mm": d2,
            "c_mm": c, "ltr_mm": ltr, "c_over_ltr": ratio,
            "equation": 11, "source_id": SOURCE_DIN6892,
            "badge": BADGE_DIN_METHOD}


# DIN 6892 equation 12 friction-closure factor, and the FVA 600 III correction.
FRICTION_REDUCTION_Q_EQ = 0.5
FVA_FRICTION_FACTOR_K_R = 1.0


def friction_closure_factor(torque_eq_Nm, slip_torque_min_Nm,
                           q_eq=FRICTION_REDUCTION_Q_EQ, apply_fva_correction=True):
    """DIN 6892 equation 12 K_Req, plus the FVA 600 III correction K_R = 1.

    The interrupted shaft/hub joint is accounted for by q_eq = 0.5. FVA 600 III
    showed experimentally and numerically that a superposed interference fit does
    NOT raise the quasi-static transmissible torque, and proposes K_R = 1; the
    DIN value is still reported so the difference stays visible.
    """
    torque = _number(torque_eq_Nm, "torque_eq_Nm", positive=True)
    slip = _number(slip_torque_min_Nm, "slip_torque_min_Nm", positive=True,
                   allow_zero=True)
    reduction = _number(q_eq, "q_eq", positive=True, allow_zero=True)
    din_value = (torque - reduction * slip) / torque
    result = {"K_Req_din": din_value, "q_eq": reduction,
              "torque_eq_Nm": torque, "slip_torque_min_Nm": slip,
              "equation": 12, "source_id": SOURCE_DIN6892,
              "slip_torque_source": "DIN_7190_1",
              "fva_recommended_K_R": FVA_FRICTION_FACTOR_K_R,
              "fva_correction_applied": bool(apply_fva_correction),
              "fva_note": ("FVA 600 III: a superposed interference fit does not "
                           "raise the quasi-static transmissible torque, so "
                           "K_R = 1 is recommended for the torque check while the "
                           "press fit still helps the long-term fatigue strength.")}
    if din_value <= 0.0:
        raise ValueError("Equation 12 gives a non-positive K_Req; the minimum "
                         "slip torque exceeds the equivalent torque")
    result["K_R"] = (FVA_FRICTION_FACTOR_K_R if apply_fva_correction
                     else din_value)
    result["badge"] = (BADGE_FVA_RESEARCH if apply_fva_correction
                       else BADGE_DIN_METHOD)
    return result


def _chord_correction_mm(d_w, width):
    """Half the sagitta of the chord of width ``width`` on diameter ``d_w``.

    This is the geometric offset between the cylinder apex and the cylinder
    surface at the keyway edge, i.e. the term 0.5*(d_w - sqrt(d_w^2 - width^2))
    that appears in DIN 6892 equation 9.
    """
    radicand = d_w * d_w - width * width
    if radicand < 0.0:
        raise ValueError("The keyway width exceeds the shaft diameter, so the "
                         "chord correction of equation 9 has no real value")
    return 0.5 * (d_w - math.sqrt(radicand))


# Which effective-bearing-depth value the pressure checks are evaluated with.
DEPTH_POLICY_EQUATION_9 = "EQUATION_9"
DEPTH_POLICY_GEOMETRIC = "GEOMETRIC"
DEPTH_POLICY_CONSERVATIVE = "CONSERVATIVE"
DEPTH_POLICIES = (DEPTH_POLICY_EQUATION_9, DEPTH_POLICY_GEOMETRIC,
                  DEPTH_POLICY_CONSERVATIVE)
DEPTH_AGREEMENT_TOLERANCE_MM = 1.0e-6


def effective_bearing_depth(t1_mm, d_w_mm, b_mm, root_radius_mm=0.0,
                            chamfer_s1_mm=0.0):
    """DIN 6892 equation 9: effective SHAFT-keyway bearing depth t1tr.

    The transcribed equation is evaluated unchanged and reported as
    ``t1tr_mm``.  Next to it an independent closed-form flank height is
    reported as ``t1tr_geometric_mm``.

    Both use the same terms; they differ only in the sign of the chord
    correction.  The shaft keyway sits in a CONVEX surface, so the shaft
    surface at the keyway edge lies BELOW the shaft apex from which the DIN
    6885 depth t1 is measured, and the flank that can actually carry pressure
    is shorter than t1.  DIN 6892 also states in words that the effective depth
    is *reduced* relative to the manufactured depth by the chamfer s1 and the
    fillet r.  The transcribed equation adds the chord correction and therefore
    returns a value larger than t1 for standard geometry.

    Nothing is silently corrected here: both values, their difference and an
    ``agrees`` flag are returned so the discrepancy is visible and the caller
    can choose a policy.  The hub keyway sits in a CONCAVE bore where the same
    algebraic form with a plus sign IS geometrically correct, see
    ``hub_effective_bearing_depth``.
    """
    t1 = _number(t1_mm, "t1_mm", positive=True)
    d_w = _number(d_w_mm, "d_w_mm", positive=True)
    b = _number(b_mm, "b_mm", positive=True)
    radius = _number(root_radius_mm, "root_radius_mm", positive=True, allow_zero=True)
    s1 = _number(chamfer_s1_mm, "chamfer_s1_mm", positive=True, allow_zero=True)
    width = b + 2.0 * s1
    try:
        chord = _chord_correction_mm(d_w, width)
    except ValueError:
        raise ValueError("Equation 9 has a negative square-root argument")
    value = t1 - (radius + s1) + chord
    geometric = t1 - (radius + s1) - chord
    if value <= 0.0:
        raise ValueError("Effective bearing depth t1tr must be positive")
    conservative = min(value, geometric)
    difference = value - geometric
    return {"t1tr_mm": value,
            "t1tr_equation9_mm": value,
            "t1tr_geometric_mm": geometric,
            "t1tr_conservative_mm": conservative,
            "geometric_is_positive": geometric > 0.0,
            "chord_correction_mm": chord,
            "difference_mm": difference,
            "relative_difference_percent": (
                100.0 * difference / value if value > 0.0 else None),
            "agrees": abs(difference) <= DEPTH_AGREEMENT_TOLERANCE_MM,
            "equation": 9, "source_id": SOURCE_DIN6892,
            "surface": "CONVEX_SHAFT",
            "note": ("Equation 9 as transcribed ADDS the chord correction "
                     "0.5*(d_w - sqrt(d_w^2 - (b+2*s1)^2)); the convex shaft "
                     "flank geometry requires SUBTRACTING it. Both values are "
                     "reported and the pressure checks follow the selected "
                     "bearing_depth_policy, which defaults to the transcribed "
                     "equation so no standard is silently overruled."),
            "inputs": {"t1_mm": t1, "d_w_mm": d_w, "b_mm": b,
                       "root_radius_mm": radius, "chamfer_s1_mm": s1}}


def hub_effective_bearing_depth(t2_mm, d_w_mm, b_mm, roof_radius_mm=0.0,
                                chamfer_s2_mm=0.0, top_clearance_mm=0.0):
    """Effective HUB-keyway bearing depth t2tr.

    DIN 6892 checks the hub keyway flank on its own bearing depth t2tr (see the
    geometry figure of the standard), not on the shaft depth t1tr.  Evaluating
    the hub with t1tr overstates the hub bearing area whenever t2 < t1, which is
    the normal DIN 6885 proportion.

    The hub keyway is cut into a CONCAVE bore, so the bore surface at the keyway
    edge lies below the bore apex and the flank is TALLER than the nominal depth
    t2 by the chord correction.  The same algebraic form as equation 9 therefore
    applies with a plus sign, which is derived here from the geometry rather
    than assumed:

        t2tr = t2 - (r1 + s2) + 0.5*(d_w - sqrt(d_w^2 - (b + 2*s2)^2))

    ``top_clearance_mm`` is the radial gap g_c = t1 + t2 - h between the key top
    and the hub keyway roof.  A positive clearance means the key never reaches
    the roof, so it is subtracted from the height that can carry pressure.
    """
    t2 = _number(t2_mm, "t2_mm", positive=True)
    d_w = _number(d_w_mm, "d_w_mm", positive=True)
    b = _number(b_mm, "b_mm", positive=True)
    radius = _number(roof_radius_mm, "roof_radius_mm", positive=True,
                     allow_zero=True)
    s2 = _number(chamfer_s2_mm, "chamfer_s2_mm", positive=True, allow_zero=True)
    clearance = _number(top_clearance_mm, "top_clearance_mm", positive=True,
                        allow_zero=True)
    chord = _chord_correction_mm(d_w, b + 2.0 * s2)
    value = t2 - (radius + s2) - clearance + chord
    if value <= 0.0:
        raise ValueError("Effective hub bearing depth t2tr must be positive; "
                         "check t2, the roof fillet r1, the chamfer s2 and the "
                         "top clearance g_c")
    return {"t2tr_mm": value, "chord_correction_mm": chord,
            "surface": "CONCAVE_HUB_BORE",
            "source_id": SOURCE_DIN6892, "badge": BADGE_DIN_METHOD,
            "note": ("The hub keyway flank is measured in a concave bore, so "
                     "the chord correction is additive; the top clearance "
                     "g_c = t1 + t2 - h is removed because the key top does "
                     "not touch the hub keyway roof."),
            "inputs": {"t2_mm": t2, "d_w_mm": d_w, "b_mm": b,
                       "roof_radius_mm": radius, "chamfer_s2_mm": s2,
                       "top_clearance_mm": clearance}}


# DIN 6892 equation 8: the bearing length depends on the DIN 6885 key form.
KEY_FORM_BEARING_LENGTH = {
    "A": "l_tr = l_PF - b (both ends rounded)",
    "B": "l_tr = l_PF (both ends square)",
    "AB": "l_tr = l_PF - b/2 (one rounded, one square end)",
}


def bearing_length(key_nominal_length_mm, b_mm, key_form="A"):
    """DIN 6892 equation 8: bearing length l_tr from the nominal key length."""
    length = _number(key_nominal_length_mm, "key_nominal_length_mm",
                     positive=True)
    b = _number(b_mm, "b_mm", positive=True)
    form = str(key_form or "A").strip().upper()
    if form not in KEY_FORM_BEARING_LENGTH:
        raise ValueError("DIN 6885 key form must be A, B or AB, not %r" % key_form)
    if form == "A":
        value = length - b
    elif form == "AB":
        value = length - 0.5 * b
    else:
        value = length
    if value <= 0.0:
        raise ValueError("The nominal key length is too short for form %s: the "
                         "bearing length l_tr would be %.3f mm" % (form, value))
    return {"ltr_mm": value, "key_nominal_length_mm": length, "b_mm": b,
            "key_form": form, "formula": KEY_FORM_BEARING_LENGTH[form],
            "equation": 8, "source_id": SOURCE_DIN6892,
            "badge": BADGE_DIN_METHOD}


def nominal_key_length(ltr_mm, b_mm, key_form="A"):
    """Inverse of equation 8: nominal key length for a required l_tr."""
    ltr = _number(ltr_mm, "ltr_mm", positive=True)
    b = _number(b_mm, "b_mm", positive=True)
    form = str(key_form or "A").strip().upper()
    if form not in KEY_FORM_BEARING_LENGTH:
        raise ValueError("DIN 6885 key form must be A, B or AB, not %r" % key_form)
    if form == "A":
        value = ltr + b
    elif form == "AB":
        value = ltr + 0.5 * b
    else:
        value = ltr
    return {"key_nominal_length_mm": value, "ltr_mm": ltr, "b_mm": b,
            "key_form": form, "equation": 8, "source_id": SOURCE_DIN6892,
            "badge": BADGE_DIN_METHOD}


# DIN 6892 equation 3 is driven by N_W, the number of LOAD DIRECTION REVERSALS
# (Lastrichtungswechsel), not by the total number of load cycles: f_W accounts
# for the extra damage caused by the key alternately bearing on both shaft
# keyway flanks. A purely pulsating torque keeps the key on one flank.
REVERSAL_SOURCE_EXPLICIT = "EXPLICIT_N_W"
REVERSAL_SOURCE_DERIVED_ALTERNATING = "DERIVED_FROM_NEGATIVE_LOAD_RATIO"
REVERSAL_SOURCE_DERIVED_PULSATING = "DERIVED_FROM_NON_NEGATIVE_LOAD_RATIO"
REVERSAL_SOURCE_UNKNOWN_DIRECTION = "FALLBACK_LOAD_CYCLES_DIRECTION_UNKNOWN"


def load_reversal_count(load_cycles, load_ratio_R=None, N_W=None):
    """Resolve N_W for equation 3 and report where the value came from.

    * An explicit ``N_W`` always wins.
    * With a known load ratio R < 0 the key changes flank once per cycle, so
      N_W = load_cycles.
    * With a known load ratio R >= 0 the torque only pulsates, the key stays on
      the same flank and there is no load direction reversal, so N_W = 0.
    * With an unknown load ratio the conservative fallback N_W = load_cycles is
      used, because assuming no reversal would raise the allowable pressure.
    """
    cycles = _number(load_cycles, "load_cycles", positive=True, allow_zero=True)
    if N_W not in (None, ""):
        count = _number(N_W, "N_W", positive=True, allow_zero=True)
        return {"N_W": count, "load_cycles": cycles, "load_ratio_R": (
            None if load_ratio_R in (None, "") else float(load_ratio_R)),
            "source": REVERSAL_SOURCE_EXPLICIT, "derived": False,
            "badge": BADGE_USER_INPUT, "reverses": count > 0.0}
    if load_ratio_R in (None, ""):
        return {"N_W": cycles, "load_cycles": cycles, "load_ratio_R": None,
                "source": REVERSAL_SOURCE_UNKNOWN_DIRECTION, "derived": True,
                "badge": BADGE_USER_INPUT, "reverses": cycles > 0.0,
                "note": ("The load direction is unknown, so every load cycle is "
                         "counted as a load direction reversal; supply "
                         "load_ratio_R or N_W to remove this conservative "
                         "fallback.")}
    ratio = _number(load_ratio_R, "load_ratio_R")
    if ratio < 0.0:
        return {"N_W": cycles, "load_cycles": cycles, "load_ratio_R": ratio,
                "source": REVERSAL_SOURCE_DERIVED_ALTERNATING, "derived": True,
                "badge": BADGE_DIN_METHOD, "reverses": cycles > 0.0,
                "note": ("R < 0 alternates the torque, so the key changes "
                         "keyway flank once per cycle and N_W = load cycles.")}
    return {"N_W": 0.0, "load_cycles": cycles, "load_ratio_R": ratio,
            "source": REVERSAL_SOURCE_DERIVED_PULSATING, "derived": True,
            "badge": BADGE_DIN_METHOD, "reverses": False,
            "note": ("R >= 0 is a purely pulsating torque: the key stays on the "
                     "same keyway flank, so there is no load direction reversal "
                     "and f_W = 1. Supply N_W explicitly if the duty cycle does "
                     "contain reversals.")}


def load_reversal_factor(load_direction_reversals):
    """DIN 6892 equation 3: f_W = 2 * N_W^-0.1, capped at one.

    ``load_direction_reversals`` is N_W, the number of LOAD DIRECTION REVERSALS.
    N_W = 0 means the load never reverses, which is the f_W = 1 plateau of the
    standard's diagram.
    """
    cycles = _number(load_direction_reversals, "N_W", positive=True,
                     allow_zero=True)
    if cycles <= 0.0:
        return {"f_W": 1.0, "raw_equation_value": None, "capped_at_one": True,
                "equation": 3, "source_id": SOURCE_DIN6892,
                "load_cycles": cycles, "N_W": cycles,
                "no_reversal": True,
                "note": ("No load direction reversal: f_W stays on the "
                         "plateau f_W = 1 of the DIN 6892 diagram.")}
    raw = 2.0 * cycles ** -0.1
    # Figure/equation 3 defines f_W up to one. Preserve both values so the cap
    # is auditable rather than silently changing the equation.
    return {"f_W": min(1.0, raw), "raw_equation_value": raw,
            "capped_at_one": raw > 1.0, "equation": 3,
            "source_id": SOURCE_DIN6892, "load_cycles": cycles, "N_W": cycles,
            "no_reversal": False}


def equivalent_torque(torque_nominal_Nm, K_A=1.0):
    """DIN 6892 equivalent torque M_teq = K_A * M_t,nom.

    The application factor K_A converts the nominal drive torque into the
    equivalent torque the pressure check is run with. It is a drive-train
    property (see DIN 3990/ISO 6336 for gear drives) and therefore an explicit
    input, never a default derived from the joint geometry.
    """
    nominal = _number(torque_nominal_Nm, "torque_nominal_Nm", positive=True)
    factor = _number(K_A, "K_A", positive=True)
    return {"torque_nominal_Nm": nominal, "K_A": factor,
            "torque_equivalent_Nm": factor * nominal,
            "equation": 7, "source_id": SOURCE_DIN6892,
            "badge": BADGE_DIN_METHOD if factor == 1.0 else BADGE_USER_INPUT,
            "note": ("K_A is the application factor of the driven machine; "
                     "K_A = 1 means the nominal torque is already the "
                     "equivalent torque.")}


def circumferential_force(torque_Nm, d_w_mm):
    """DIN 6892 equation 7 solved for the circumferential force F_eq."""
    torque = _number(torque_Nm, "torque_Nm", positive=True)
    d_w = _number(d_w_mm, "d_w_mm", positive=True)
    return {"F_eq_N": 2000.0 * torque / d_w, "torque_Nm": torque,
            "d_w_mm": d_w, "equation": 7, "source_id": SOURCE_DIN6892,
            "badge": BADGE_DIN_METHOD}


# DIN 6892 supplies three K_lambda diagrams, selected by where the load leaves
# the hub relative to where it enters the key (distance a_0). The position is a
# declaration about the assembly, so it is an explicit choice and the mapping
# from a_0/l_tr to a diagram is NOT invented here.
LOAD_DERIVATION_FRONT = "FRONT"
LOAD_DERIVATION_MIDDLE = "MIDDLE"
LOAD_DERIVATION_REAR = "REAR"
LOAD_DERIVATION_POSITIONS = (LOAD_DERIVATION_FRONT, LOAD_DERIVATION_MIDDLE,
                             LOAD_DERIVATION_REAR)
# Axis ranges of the licensed K_lambda diagrams, used only to detect readings
# that cannot have come from them.
K_LAMBDA_RANGE = (1.0, 2.0)
K_LAMBDA_QA_RANGE = (0.3, 0.9)
K_LAMBDA_LENGTH_RATIO_RANGE = (0.5, 2.0)


def load_distribution_domain(K_lambda, d_w_mm, ltr_mm, hub_diameter_mm=None,
                             position=LOAD_DERIVATION_REAR, a0_mm=None):
    """Plausibility gate for the licensed K_lambda diagram reading.

    K_lambda itself has no closed form and stays a user input. What CAN be
    checked is whether the reading is inside the diagram at all: the diagrams
    span Q_A = d_w/D from 0.3 to 0.9, l_tr/d_w from 0.5 to 2 and K_lambda from
    1.0 to 2.0, and one of three load-derivation diagrams has to be declared.
    A value outside those bounds cannot have been read from the standard.
    """
    k_lambda = _number(K_lambda, "K_lambda", positive=True)
    d_w = _number(d_w_mm, "d_w_mm", positive=True)
    ltr = _number(ltr_mm, "ltr_mm", positive=True)
    place = str(position or LOAD_DERIVATION_REAR).strip().upper()
    if place not in LOAD_DERIVATION_POSITIONS:
        raise ValueError("The load derivation position must be one of %s, not %r"
                         % (", ".join(LOAD_DERIVATION_POSITIONS), position))
    ratio = ltr / d_w
    q_a = None
    if hub_diameter_mm not in (None, ""):
        hub = _number(hub_diameter_mm, "hub_diameter_mm", positive=True)
        if hub <= d_w:
            raise ValueError("The hub outer/equivalent diameter must exceed the "
                             "shaft diameter")
        q_a = d_w / hub
    a0_ratio = None
    if a0_mm not in (None, ""):
        a0 = _number(a0_mm, "a0_mm", positive=True, allow_zero=True)
        a0_ratio = a0 / ltr
    return {
        "K_lambda": k_lambda,
        "load_derivation_position": place,
        "Q_A_shaft_over_hub": q_a,
        "ltr_over_dw": ratio,
        "a0_over_ltr": a0_ratio,
        "K_lambda_range": list(K_LAMBDA_RANGE),
        "Q_A_range": list(K_LAMBDA_QA_RANGE),
        "ltr_over_dw_range": list(K_LAMBDA_LENGTH_RATIO_RANGE),
        "K_lambda_inside_diagram": (
            K_LAMBDA_RANGE[0] - 1.0e-12 <= k_lambda <= K_LAMBDA_RANGE[1] + 1.0e-12),
        "Q_A_inside_diagram": (
            None if q_a is None else
            K_LAMBDA_QA_RANGE[0] - 1.0e-12 <= q_a <= K_LAMBDA_QA_RANGE[1] + 1.0e-12),
        "ltr_over_dw_inside_diagram": (
            K_LAMBDA_LENGTH_RATIO_RANGE[0] - 1.0e-12 <= ratio <=
            K_LAMBDA_LENGTH_RATIO_RANGE[1] + 1.0e-12),
        "source_id": SOURCE_DIN6892, "badge": BADGE_USER_INPUT,
        "note": ("K_lambda must be read from the DIN 6892 diagram for the "
                 "declared load-derivation position; only the diagram bounds "
                 "are checked here, the reading itself is never interpolated "
                 "or invented."),
    }


def strength_support_factor(rm_MPa, re_MPa):
    rm = _number(rm_MPa, "Rm_MPa", positive=True)
    re_value = _number(re_MPa, "Re_MPa", positive=True)
    return {"f_WS": rm / re_value, "equation": 33, "source_id": SOURCE_FVA,
            "Rm_MPa": rm, "Re_MPa": re_value, "badge": BADGE_FVA_RESEARCH}


def length_support_factor_fva(ltr_mm, d_w_mm):
    ltr = _number(ltr_mm, "ltr_mm", positive=True)
    diameter = _number(d_w_mm, "d_w_mm", positive=True)
    ratio = ltr / diameter
    return {"f_S_ltr": -0.17 * ratio + 0.16, "ltr_over_dw": ratio,
            "equation": 34, "source_id": SOURCE_FVA,
            "badge": BADGE_FVA_RESEARCH}


def length_support_factor_legacy(ltr_mm, d_w_mm):
    ltr = _number(ltr_mm, "ltr_mm", positive=True)
    diameter = _number(d_w_mm, "d_w_mm", positive=True)
    ratio = ltr / diameter
    value = 1.3 - ratio if 0.5 <= ratio < 1.3 else 0.0
    return {"f_S_ltr_legacy": value, "ltr_over_dw": ratio,
            "equation": 15, "source_id": SOURCE_DIN6892}


def length_support_factor_domain(ltr_mm, d_w_mm):
    """Validity domain of the length-dependent support factors.

    Equation 34 is a linear fit through test data with l_tr/d_w between 0.5 and
    1.3, and DIN 6892 warns that beyond l_tr/d_w = 1.3 the rear part of the key
    transmits practically no pressure, so the joint should not be longer.
    """
    ltr = _number(ltr_mm, "ltr_mm", positive=True)
    diameter = _number(d_w_mm, "d_w_mm", positive=True)
    ratio = ltr / diameter
    return {"ltr_over_dw": ratio, "fit_min": 0.5, "fit_max": 1.3,
            "design_limit": 1.3,
            "inside_fit_domain": 0.5 - 1.0e-12 <= ratio <= 1.3 + 1.0e-12,
            "exceeds_design_limit": ratio > 1.3 + 1.0e-12,
            "source_id": SOURCE_FVA,
            "note": ("Above l_tr/d_w = 1.3 the rear part of the key carries "
                     "practically no pressure; equations 15 and 34 were fitted "
                     "for 0.5 <= l_tr/d_w <= 1.3.")}


def size_factor(d_w_mm):
    """FVA 600 III equation 29 geometric size factor K_d.

    The report gives the fit K_d = 2.08 * d_w^-0.18 and states that above
    d_w = 100 mm a constant K_d = 0.82 may be assumed as a SIMPLIFICATION
    ("vereinfachend"). Fit and plateau therefore do not meet at 100 mm; both
    values and the step are reported so the simplification stays auditable
    instead of being smoothed away with invented constants.
    """
    diameter = _number(d_w_mm, "d_w_mm", positive=True)
    fitted = 2.08 * diameter ** -0.18
    boundary = 2.08 * 100.0 ** -0.18
    plateau = 0.82
    value = fitted if diameter <= 100.0 else plateau
    step = abs(boundary - plateau)
    return {"K_d": value, "equation": 29, "source_id": SOURCE_FVA,
            "badge": BADGE_FVA_RESEARCH, "d_w_mm": diameter,
            "fitted_value": fitted, "plateau_value": plateau,
            "plateau_applies": diameter > 100.0,
            "plateau_is_documented_simplification": True,
            "boundary_value_at_100mm": boundary,
            "transcription_step_at_100mm": step,
            "transcription_continuous": step <= 1.0e-3,
            "data_domain_mm": [10.0, 450.0],
            "inside_data_domain": 10.0 <= diameter <= 450.0,
            "warning": ("Equation 29 gives K_d = %.4f at d_w = 100 mm while the "
                        "documented large-diameter simplification is %.2f; the "
                        "step is retained rather than interpolated."
                        % (boundary, plateau))}


# Licensed DIN 6892 diagram/table factors. A neutral 1.0 is a placeholder, not
# a measurement, so a result built on untouched placeholders is reported as
# provisional instead of calculated.
LICENSED_FACTORS = ("K_lambda", "K_R", "f_H", "f_S")
NEUTRAL_FACTOR_VALUE = 1.0
STATUS_CALCULATED = "CALCULATED"
STATUS_PROVISIONAL_FACTORS = "PROVISIONAL_FACTORS"


def factor_provenance_audit(inputs, factors=None):
    """Report which licensed factors are still untouched neutral placeholders."""
    provenance = inputs.get("factor_provenance") or {}
    acknowledged = bool(inputs.get("factors_acknowledged", False))
    names = tuple(factors) if factors else LICENSED_FACTORS
    placeholders = []
    resolved = {}
    for name in names:
        raw = inputs.get(name)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        source = str(provenance.get(name, BADGE_USER_INPUT) or BADGE_USER_INPUT)
        resolved[name] = {"value": value, "provenance": source}
        if abs(value - NEUTRAL_FACTOR_VALUE) <= 1.0e-12 and source == BADGE_USER_INPUT:
            placeholders.append(name)
    conclusive = bool(acknowledged or not placeholders)
    return {"licensed_factors": list(names), "resolved": resolved,
            "placeholder_factors": placeholders, "acknowledged": acknowledged,
            "conclusive": conclusive, "badge": BADGE_USER_INPUT,
            "status": STATUS_CALCULATED if conclusive else STATUS_PROVISIONAL_FACTORS,
            "note": ("Licensed DIN 6892 diagram/table factors left at the neutral "
                     "value 1.0 keep the result provisional; supply the licensed "
                     "values or set factors_acknowledged=true after review.")}


def _bearing_components(inputs, require_tensile=False):
    """Resolve the per-component (Re, Rm) rows of a bearing-pressure check.

    DIN 6892 checks the shaft keyway, the hub keyway and the key separately and
    the joint is governed by the weakest of them.  A tensile strength is only
    accepted when it was supplied explicitly for that same component, so
    equation 33 can never pair one part's Rm with another part's Re.
    Callers that pass only the scalar ``Re_MPa``/``Rm_MPa`` keep single
    component behaviour.
    """
    supplied = inputs.get("components") or []
    rows = []
    skipped = []
    for item in supplied:
        name = str((item or {}).get("name") or "component").strip().lower()
        try:
            re_value = _number((item or {}).get("Re_MPa"),
                               "%s Re_MPa" % name, positive=True)
        except ValueError as exc:
            skipped.append({"name": name, "reason": str(exc)})
            continue
        rm_value = None
        raw = (item or {}).get("Rm_MPa")
        if raw not in (None, ""):
            try:
                rm_value = _number(raw, "%s Rm_MPa" % name, positive=True)
            except ValueError:
                rm_value = None
        if require_tensile and rm_value is None:
            skipped.append({
                "name": name,
                "reason": ("no explicit tensile strength Rm for this component; "
                           "equation 33 needs Rm and Re of the same part")})
            continue
        rows.append({"name": name, "Re_MPa": re_value, "Rm_MPa": rm_value})
    if supplied and not rows:
        raise ValueError(
            "No component of the bearing check can be evaluated: %s" %
            "; ".join("%s (%s)" % (item["name"], item["reason"])
                      for item in skipped))
    if not supplied:
        re_value = _number(inputs.get("Re_MPa"), "Re_MPa", positive=True)
        if require_tensile:
            rm_value = _number(inputs.get("Rm_MPa"), "Rm_MPa", positive=True)
        else:
            rm_value = None
            raw = inputs.get("Rm_MPa")
            if raw not in (None, ""):
                try:
                    rm_value = _number(raw, "Rm_MPa", positive=True)
                except ValueError:
                    rm_value = None
        rows = [{"name": "governing", "Re_MPa": re_value, "Rm_MPa": rm_value}]
    return rows, skipped


def _named_component(inputs, name, require_tensile=False):
    """Resolve ONE named component, for checks that target a specific part.

    Used by the FVA reformulation, whose limit-load criterion is the plastic
    opening volume of the shaft keyway, so it must never silently fall back to
    another part's strengths.
    """
    wanted = str(name).strip().lower()
    for item in inputs.get("components") or []:
        if str((item or {}).get("name", "")).strip().lower() != wanted:
            continue
        re_value = _number((item or {}).get("Re_MPa"), "%s Re_MPa" % wanted,
                           positive=True)
        raw = (item or {}).get("Rm_MPa")
        if require_tensile and raw in (None, ""):
            raise ValueError(
                "The %s tensile strength Rm is required by equation 33 and no "
                "value was supplied for that component" % wanted)
        rm_value = (None if raw in (None, "")
                    else _number(raw, "%s Rm_MPa" % wanted, positive=True))
        return {"name": wanted, "Re_MPa": re_value, "Rm_MPa": rm_value}
    re_value = _number(inputs.get("Re_MPa"), "Re_MPa", positive=True)
    rm_value = None
    if require_tensile:
        rm_value = _number(inputs.get("Rm_MPa"), "Rm_MPa", positive=True)
    return {"name": wanted, "Re_MPa": re_value, "Rm_MPa": rm_value}


def _governing_component(rows):
    """The weakest evaluated component decides the joint."""
    if not rows:
        raise ValueError("A bearing check needs at least one evaluated component")
    ordered = sorted(rows, key=lambda item: item["torque_allowable_Nm"])
    return ordered[0]


def volume_support_factor(v):
    value = _number(v, "v", positive=True, allow_zero=True)
    return {"f_Sv": 0.74 * value + 0.63, "v": value, "equation": 26,
            "source_id": SOURCE_FVA, "badge": BADGE_FVA_RESEARCH}


def theoretical_interference_volume(ltr_mm, t1tr_mm, UPF_um):
    ltr = _number(ltr_mm, "ltr_mm", positive=True)
    depth = _number(t1tr_mm, "t1tr_mm", positive=True)
    upf_um = _number(UPF_um, "UPF_um", positive=True)
    upf_mm = upf_um / 1000.0
    return {"V_theo_mm3": ltr * depth * upf_mm, "ltr_mm": ltr,
            "t1tr_mm": depth, "UPF_um": upf_um, "UPF_mm": upf_mm,
            "equation": 17, "source_id": SOURCE_FVA,
            "badge": BADGE_FVA_RESEARCH}


def relative_opening_volume(delta_volume_mm3, ltr_mm, t1tr_mm, UPF_um,
                            v_crit=0.5):
    delta = _number(delta_volume_mm3, "delta_volume_mm3", positive=True,
                    allow_zero=True)
    theoretical = theoretical_interference_volume(ltr_mm, t1tr_mm, UPF_um)
    v = delta / theoretical["V_theo_mm3"]
    limit = _number(v_crit, "v_crit", positive=True)
    return {"delta_volume_mm3": delta, "V_theo_mm3": theoretical["V_theo_mm3"],
            "v": v, "v_crit": limit, "criterion_met": v <= limit,
            "equations": [16, 17, 18], "source_id": SOURCE_FVA,
            "badge": BADGE_FVA_RESEARCH, "inputs": theoretical}


def normalized_amplitude(load_ratio_R, cycles=1):
    ratio = _number(load_ratio_R, "load_ratio_R")
    count = int(cycles)
    if count < 1:
        raise ValueError("cycles must be at least 1")
    if ratio < -1.0 or ratio > 1.0:
        raise ValueError("load_ratio_R must be between -1 and 1")
    points = [(0.0, 0.0)]
    for index in range(count):
        start = float(index) / count
        end = float(index + 1) / count
        if ratio < 0.0:
            points.extend(((start + 0.25 / count, 1.0),
                           (start + 0.75 / count, ratio),
                           (end, 0.0 if index == count - 1 else ratio)))
        else:
            points.extend(((start + 0.5 / count, 1.0), (end, ratio)))
    return {"load_ratio_R": ratio, "cycles": count, "points": points,
            "M_min_over_M_max": ratio, "source_id": SOURCE_FVA,
            "badge": BADGE_FVA_RESEARCH}


def derive_variant(variant_id, b_mm, UPF_um=18.0, torque_max_Nm=1256.0):
    data = variant(variant_id)
    b = _number(b_mm, "b_mm", positive=True)
    diameter = data["d_w_mm"]
    ltr = data["ltr_over_dw"] * diameter
    form = data["key_form"]
    nominal_length = ltr + b if form == "A" else ltr
    hub_outer = diameter / data["QA_shaft_over_hub"]
    xi_diametral = diameter * data["xi_per_mille"] / 1000.0
    torque = _number(torque_max_Nm, "torque_max_Nm", positive=True)
    data.update({
        "ltr_mm": ltr, "key_nominal_length_mm": nominal_length,
        "hub_outer_diameter_mm": hub_outer,
        "hub_outer_over_shaft": hub_outer / diameter,
        "UPF_um": _number(UPF_um, "UPF_um", positive=True),
        "xi_diametral_mm": xi_diametral,
        "xi_convention": "diametral_interference = d_w * xi_per_mille / 1000",
        "torque_max_Nm": torque,
        "torque_min_Nm": data["load_ratio_R"] * torque,
        "amplitude": normalized_amplitude(data["load_ratio_R"], 1),
    })
    return data


# Method C allowable pressure. The published DIN edition keeps a 10 % reduction
# on the yield strength of the weakest part; FVA 600 III equation 32 proposes
# dropping it (f_S = 1) because the measured capacity is consistently higher.
METHOD_C_VARIANT_DIN = "DIN_PUBLISHED"
METHOD_C_VARIANT_FVA = "FVA_2025"
METHOD_C_VARIANTS = {
    METHOD_C_VARIANT_DIN: {
        "f_S": 0.9, "equations": [30, 31], "badge": BADGE_DIN_METHOD,
        "source_id": SOURCE_DIN6892,
        "note": "Published DIN 6892 Method C: p_zul = 0.9 * Re_min",
    },
    METHOD_C_VARIANT_FVA: {
        "f_S": 1.0, "equations": [31, 32], "badge": BADGE_FVA_RESEARCH,
        "source_id": SOURCE_FVA,
        "note": ("FVA 600 III equation 32 proposal: p_zul,neu = f_S * Re_min "
                 "with f_S = 1, i.e. the 10 % reduction is dropped"),
    },
}


def method_c_engaged_height(h_mm, t1_mm, t2_mm=None):
    """The constant flank height h - t1 that Method C equation 31 uses.

    Equation 31 works with the hub-side engagement height h - t1, not with the
    nominal DIN 6885 hub depth t2. The two differ by the radial top clearance
    g_c = t1 + t2 - h, so h - t1 = t2 - g_c is automatically the smaller and
    therefore the conservative value. Both are reported so the clearance stays
    visible instead of looking like a transcription error.
    """
    h = _number(h_mm, "h_mm", positive=True)
    t1 = _number(t1_mm, "t1_mm", positive=True)
    if h <= t1:
        raise ValueError("Method C requires h > t1: the key has to protrude out "
                         "of the shaft keyway to engage the hub")
    engaged = h - t1
    result = {"engaged_height_mm": engaged, "h_mm": h, "t1_mm": t1,
              "formula": "h - t1", "equation": 31,
              "source_id": SOURCE_DIN6892, "badge": BADGE_DIN_METHOD}
    if t2_mm not in (None, ""):
        t2 = _number(t2_mm, "t2_mm", positive=True)
        clearance = t1 + t2 - h
        result.update({
            "t2_mm": t2, "top_clearance_gc_mm": clearance,
            "engaged_equals_t2": abs(clearance) <= 1.0e-9,
            "clearance_is_negative": clearance < -1.0e-9,
            "note": ("g_c = t1 + t2 - h = %.3f mm is the radial gap between the "
                     "key top and the hub keyway roof, so equation 31 works "
                     "with h - t1 = t2 - g_c." % clearance)})
    return result


def method_c_preliminary(inputs):
    """DIN 6892 Method C, equations 30 and 31, with the FVA 600 III variant.

    Evaluated for every supplied component; the weakest one governs, which is
    equivalent to the scalar Re_min form when only that scalar is available.

    Method C is a *sizing* method, so the inverse result is returned as well:
    the bearing length and the DIN 6885 nominal key length a required torque
    needs, plus the utilisation against an applied torque.
    """
    d_w = _number(inputs.get("d_w_mm"), "d_w_mm", positive=True)
    h = _number(inputs.get("h_mm"), "h_mm", positive=True)
    t1 = _number(inputs.get("t1_mm"), "t1_mm", positive=True)
    ltr = _number(inputs.get("ltr_mm"), "ltr_mm", positive=True)
    engaged = method_c_engaged_height(h, t1, inputs.get("t2_mm"))
    height = engaged["engaged_height_mm"]
    key_count = int(inputs.get("key_count", 1))
    distribution = load_distribution_factor(key_count, inputs.get("phi"))
    scoped = dict(inputs)
    if not (inputs.get("components") or []):
        if inputs.get("Re_min_MPa") in (None, ""):
            raise ValueError("Re_min_MPa must be numeric; received None")
        scoped["Re_MPa"] = inputs.get("Re_min_MPa")
    rows, skipped = _bearing_components(scoped)
    variant = str(inputs.get("method_c_variant", METHOD_C_VARIANT_DIN)
                  or METHOD_C_VARIANT_DIN).strip().upper()
    if variant not in METHOD_C_VARIANTS:
        raise ValueError("Method C variant must be one of %s, not %r"
                         % (", ".join(sorted(METHOD_C_VARIANTS)), variant))
    strength_share = METHOD_C_VARIANTS[variant]["f_S"]
    # The torque per unit bearing length is kept explicitly so the inverse
    # sizing below uses exactly the same chain as the forward check.
    evaluated = []
    for row in rows:
        p_zul = strength_share * row["Re_MPa"]
        torque_per_mm = (p_zul * height * (d_w / 2.0) * key_count *
                         distribution["phi"]) / 1000.0
        evaluated.append({"name": row["name"], "Re_MPa": row["Re_MPa"],
                          "p_zul_MPa": p_zul,
                          "torque_per_bearing_mm_Nm": torque_per_mm,
                          "torque_allowable_Nm": torque_per_mm * ltr})
    governing = _governing_component(evaluated)
    safety = _number(inputs.get("safety_factor", 1.0), "safety_factor", positive=True)
    torque = governing["torque_allowable_Nm"]
    result = {"method": METHOD_C, "badge": METHOD_C_VARIANTS[variant]["badge"],
              "source_id": METHOD_C_VARIANTS[variant]["source_id"],
              "status": STATUS_CALCULATED,
              "variant": variant, "variant_f_S": strength_share,
              "variant_note": METHOD_C_VARIANTS[variant]["note"],
              "p_zul_MPa": governing["p_zul_MPa"],
              "torque_allowable_Nm": torque,
              "torque_design_Nm": torque / safety,
              "safety_factor": safety,
              "engaged_height": engaged,
              "engaged_height_mm": height,
              "ltr_mm": ltr, "d_w_mm": d_w,
              "torque_per_bearing_mm_Nm": governing["torque_per_bearing_mm_Nm"],
              "equations": METHOD_C_VARIANTS[variant]["equations"],
              "load_distribution": distribution,
              "components": evaluated, "components_skipped": skipped,
              "governing_component": governing["name"],
              "limitations": [
                  "Preliminary sizing; Method B/A and DIN 743 remain required as applicable",
                  "Equation 31 assumes one constant pressure over h - t1 and ignores the load distribution K_lambda and the shaft flank height",
              ]}
    applied = inputs.get("torque_applied_Nm")
    applied_value = None
    if applied not in (None, ""):
        applied_value = _number(applied, "torque_applied_Nm", positive=True)
        result["torque_applied_Nm"] = applied_value
        result["safety_S_F"] = torque / applied_value
        result["utilisation"] = applied_value / torque
    # Inverse sizing: what bearing length does a required torque need?
    required = inputs.get("torque_required_Nm")
    if required in (None, ""):
        required = applied_value
    if required not in (None, ""):
        try:
            result["sizing"] = method_c_required_length(
                required, governing["torque_per_bearing_mm_Nm"],
                inputs.get("b_mm"), inputs.get("key_form", "A"), safety, d_w)
        except (TypeError, ValueError) as exc:
            result["sizing"] = {"status": "INVALID_INPUT", "reason": str(exc)}
    return result


def method_c_required_length(torque_required_Nm, torque_per_bearing_mm_Nm,
                             b_mm=None, key_form="A", safety_factor=1.0,
                             d_w_mm=None):
    """Bearing length and DIN 6885 nominal key length for a required torque.

    This is what Method C is for: a first length estimate before the Method-B
    check is run. The safety factor is applied to the requirement, so the
    returned length satisfies M_t,design >= M_t,required.
    """
    required = _number(torque_required_Nm, "torque_required_Nm", positive=True)
    per_mm = _number(torque_per_bearing_mm_Nm, "torque_per_bearing_mm_Nm",
                     positive=True)
    safety = _number(safety_factor, "safety_factor", positive=True)
    ltr_required = required * safety / per_mm
    result = {"status": "SIZED", "torque_required_Nm": required,
              "safety_factor": safety,
              "torque_per_bearing_mm_Nm": per_mm,
              "ltr_required_mm": ltr_required,
              "equations": [31], "source_id": SOURCE_DIN6892,
              "badge": BADGE_DIN_METHOD,
              "note": ("Preliminary length only. DIN 6892 warns that above "
                       "l_tr/d_w = 1.3 the rear part of the key transmits "
                       "practically no pressure, so a longer result has to be "
                       "solved with more keys or another joint type.")}
    if d_w_mm not in (None, ""):
        d_w = _number(d_w_mm, "d_w_mm", positive=True)
        ratio = ltr_required / d_w
        result["ltr_over_dw_required"] = ratio
        result["exceeds_design_limit"] = ratio > 1.3 + 1.0e-12
    if b_mm not in (None, ""):
        nominal = nominal_key_length(ltr_required, b_mm, key_form)
        result["key_nominal_length_required_mm"] = nominal[
            "key_nominal_length_mm"]
        result["key_form"] = nominal["key_form"]
        result["b_mm"] = nominal["b_mm"]
    return result


def _component_support_factors(inputs, component):
    """Resolve f_S and f_H for one component from Table 2 or explicit input.

    An explicit user value always wins. Otherwise the DIN 6892 Table 2 entry for
    the declared material class is used with the lower bound of the f_S range,
    which is what the standard demands when the material is not known.
    """
    classes = inputs.get("material_classes") or {}
    bound = inputs.get("f_S_bound", "lower")
    explicit_s = inputs.get("f_S")
    explicit_h = inputs.get("f_H")
    table = None
    if component in DIN6892_TABLE2_SUPPORT and classes.get(component):
        table = table2_support_factors(component, classes.get(component), bound)
    if explicit_s not in (None, ""):
        f_s = _number(explicit_s, "f_S", positive=True)
        s_source = BADGE_USER_INPUT
    elif table is not None:
        f_s = table["f_S"]
        s_source = BADGE_DIN_METHOD
    else:
        f_s = 1.0
        s_source = BADGE_USER_INPUT
    if explicit_h not in (None, ""):
        f_h = _number(explicit_h, "f_H", positive=True)
        h_source = BADGE_USER_INPUT
    elif table is not None and table["f_H_available"]:
        f_h = table["f_H"]
        h_source = BADGE_DIN_METHOD
    elif table is not None:
        raise ValueError(
            "DIN 6892 Table 2 defines no hardness factor f_H for %s made of %s; "
            "supply f_H explicitly" % (component, table["material_class"]))
    else:
        f_h = 1.0
        h_source = BADGE_USER_INPUT
    return {"f_S": f_s, "f_H": f_h, "f_S_provenance": s_source,
            "f_H_provenance": h_source, "table2": table}


def resolve_bearing_depth_policy(inputs):
    """Pick the shaft bearing depth the pressure checks are evaluated with.

    ``t1tr_mm`` is the DIN 6892 equation-9 value and stays the default so the
    transcribed standard is never silently overruled.  ``t1tr_geometric_mm`` is
    the independent flank-height value.  ``bearing_depth_policy`` selects
    between them, or takes the smaller of the two.
    """
    equation9 = _number(inputs.get("t1tr_mm"), "t1tr_mm", positive=True)
    raw_geometric = inputs.get("t1tr_geometric_mm")
    geometric = None
    if raw_geometric not in (None, ""):
        try:
            geometric = _number(raw_geometric, "t1tr_geometric_mm")
        except ValueError:
            geometric = None
    policy = str(inputs.get("bearing_depth_policy", DEPTH_POLICY_EQUATION_9)
                 or DEPTH_POLICY_EQUATION_9).strip().upper()
    if policy not in DEPTH_POLICIES:
        raise ValueError("bearing_depth_policy must be one of %s, not %r"
                         % (", ".join(DEPTH_POLICIES),
                            inputs.get("bearing_depth_policy")))
    usable_geometric = geometric is not None and geometric > 0.0
    if policy == DEPTH_POLICY_GEOMETRIC and usable_geometric:
        value = geometric
    elif policy == DEPTH_POLICY_CONSERVATIVE and usable_geometric:
        value = min(equation9, geometric)
    else:
        value = equation9
    difference = (None if geometric is None else equation9 - geometric)
    return {"t1tr_mm": value, "policy": policy,
            "policy_applied": (policy if (policy == DEPTH_POLICY_EQUATION_9 or
                                          usable_geometric)
                               else DEPTH_POLICY_EQUATION_9),
            "t1tr_equation9_mm": equation9,
            "t1tr_geometric_mm": geometric,
            "geometric_available": usable_geometric,
            "difference_mm": difference,
            "agrees": (difference is not None and
                       abs(difference) <= DEPTH_AGREEMENT_TOLERANCE_MM),
            "source_id": SOURCE_DIN6892}


def _component_bearing_depths(inputs, shaft_depth_mm):
    """Per-component bearing depth: t1tr for the shaft, t2tr for the hub.

    DIN 6892 evaluates the shaft keyway pressure over l_tr * t1tr and the hub
    keyway pressure over l_tr * t2tr.  Checking the hub with the shaft depth
    overstates the hub bearing area whenever t2 < t1, which is the normal
    DIN 6885 proportion, so the hub result would be optimistic.

    The key flank sees the same pressure as the mating keyway flank, so it is
    limited by the SMALLER of the two contact heights.
    """
    hub_raw = inputs.get("t2tr_mm")
    hub_depth = None
    if hub_raw not in (None, ""):
        hub_depth = _number(hub_raw, "t2tr_mm", positive=True)
    depths = {
        "shaft": {"depth_mm": shaft_depth_mm, "symbol": "t1tr",
                  "source": "SHAFT_EQUATION_9_OR_POLICY"},
    }
    if hub_depth is None:
        depths["hub"] = {"depth_mm": shaft_depth_mm, "symbol": "t1tr",
                         "source": "FALLBACK_SHAFT_DEPTH", "fallback": True}
        depths["key"] = {"depth_mm": shaft_depth_mm, "symbol": "t1tr",
                         "source": "FALLBACK_SHAFT_DEPTH", "fallback": True}
    else:
        depths["hub"] = {"depth_mm": hub_depth, "symbol": "t2tr",
                         "source": "HUB_FLANK_GEOMETRY", "fallback": False}
        governing_key = min(shaft_depth_mm, hub_depth)
        depths["key"] = {
            "depth_mm": governing_key,
            "symbol": ("t1tr" if governing_key == shaft_depth_mm else "t2tr"),
            "source": "MIN_OF_SHAFT_AND_HUB", "fallback": False}
    return {"depths": depths, "t1tr_mm": shaft_depth_mm, "t2tr_mm": hub_depth,
            "hub_depth_available": hub_depth is not None,
            "note": ("The hub keyway is checked on t2tr and the key on the "
                     "smaller of the two flank heights; without t2tr the hub "
                     "and key fall back to the shaft depth, which is "
                     "optimistic and reported as such.")}


def method_b_current(inputs):
    """Current analytical Method-B pressure chain, equations 1..12.

    The equivalent-pressure check runs for the shaft keyway, the hub keyway and
    the key, each with

    * its own yield strength,
    * its own DIN 6892 Table 2 support/hardness factors, and
    * its own bearing depth: t1tr on the shaft flank, t2tr on the hub flank and
      the smaller of the two for the key.

    The weakest component governs the transmissible torque.  When ``f_L`` is
    supplied the peak-pressure branch p_max,zul = f_L * p_zul is evaluated as
    well, with the equation-10 load share for the peak pressure.
    """
    d_w = _number(inputs.get("d_w_mm"), "d_w_mm", positive=True)
    ltr = _number(inputs.get("ltr_mm"), "ltr_mm", positive=True)
    depth_policy = resolve_bearing_depth_policy(inputs)
    t1tr = depth_policy["t1tr_mm"]
    depth_map = _component_bearing_depths(inputs, t1tr)
    k_lambda = _number(inputs.get("K_lambda"), "K_lambda", positive=True)
    k_r = _number(inputs.get("K_R"), "K_R", positive=True)
    reversal_count = load_reversal_count(
        inputs.get("load_cycles", 10000.0), inputs.get("load_ratio_R"),
        inputs.get("N_W"))
    reversal = load_reversal_factor(reversal_count["N_W"])
    reversal["count"] = reversal_count
    key_count = int(inputs.get("key_count", 1))
    distribution = load_distribution_factor(
        key_count, inputs.get("phi"), LOAD_TARGET_ALLOWABLE)
    peak_distribution = load_distribution_factor(
        key_count, inputs.get("phi"), LOAD_TARGET_PEAK)
    rows, skipped = _bearing_components(inputs)
    den = 2.0 * distribution["K_V"] * k_lambda * k_r
    peak_den = 2.0 * peak_distribution["K_V"] * k_lambda * k_r
    peak_share = inputs.get("f_L")

    # Applied loading. torque_applied_Nm is the equivalent torque and keeps
    # precedence; otherwise it is built from the nominal torque and K_A.
    application = None
    applied_equivalent = None
    raw_applied = inputs.get("torque_applied_Nm")
    if raw_applied not in (None, ""):
        applied_equivalent = _number(raw_applied, "torque_applied_Nm",
                                     positive=True)
    raw_nominal = inputs.get("torque_nominal_Nm")
    if raw_nominal not in (None, ""):
        application = equivalent_torque(raw_nominal, inputs.get("K_A", 1.0))
        if applied_equivalent is None:
            applied_equivalent = application["torque_equivalent_Nm"]
    applied_peak = None
    raw_peak_applied = inputs.get("torque_peak_applied_Nm")
    if raw_peak_applied not in (None, ""):
        applied_peak = _number(raw_peak_applied, "torque_peak_applied_Nm",
                               positive=True)

    evaluated = []
    for row in rows:
        factors = _component_support_factors(inputs, row["name"])
        depth = depth_map["depths"].get(
            row["name"], {"depth_mm": t1tr, "symbol": "t1tr",
                          "source": "FALLBACK_SHAFT_DEPTH", "fallback": True})
        t_tr = depth["depth_mm"]
        p_zul = factors["f_S"] * factors["f_H"] * row["Re_MPa"]
        p_eq_zul = reversal["f_W"] * p_zul
        area = ltr * t_tr
        item = {
            "name": row["name"], "Re_MPa": row["Re_MPa"],
            "f_S": factors["f_S"], "f_H": factors["f_H"],
            "f_S_provenance": factors["f_S_provenance"],
            "f_H_provenance": factors["f_H_provenance"],
            "f_S_range": (factors["table2"] or {}).get("f_S_range"),
            "material_class": (factors["table2"] or {}).get("material_class"),
            "bearing_depth_mm": t_tr,
            "bearing_depth_symbol": depth["symbol"],
            "bearing_depth_source": depth["source"],
            "bearing_depth_is_fallback": bool(depth.get("fallback", False)),
            "bearing_area_mm2": area,
            "p_zul_MPa": p_zul, "p_eq_zul_MPa": p_eq_zul,
            "torque_allowable_Nm": p_eq_zul * d_w * ltr * t_tr / den / 1000.0}
        if applied_equivalent is not None:
            # Equation 6 with equation 7: p_eq = K_V*K_lambda*K_R*F_eq/(l_tr*t_tr)
            item["p_eq_MPa"] = (distribution["K_V"] * k_lambda * k_r *
                                2000.0 * applied_equivalent / (d_w * area))
            item["utilisation_eq"] = item["p_eq_MPa"] / p_eq_zul
        if peak_share not in (None, ""):
            f_l = _number(peak_share, "f_L", positive=True)
            item["f_L"] = f_l
            item["p_max_zul_MPa"] = f_l * p_zul
            item["torque_peak_allowable_Nm"] = (
                f_l * p_zul * d_w * ltr * t_tr / peak_den / 1000.0)
            if applied_peak is not None:
                item["p_max_MPa"] = (peak_distribution["K_V"] * k_lambda * k_r *
                                     2000.0 * applied_peak / (d_w * area))
                item["utilisation_max"] = item["p_max_MPa"] / item["p_max_zul_MPa"]
        evaluated.append(item)
    governing = _governing_component(evaluated)
    torque = governing["torque_allowable_Nm"]
    safety = _number(inputs.get("safety_factor", 1.0), "safety_factor", positive=True)
    factor_audit = factor_provenance_audit(inputs)
    domain = length_support_factor_domain(ltr, d_w)
    try:
        k_lambda_domain = load_distribution_domain(
            k_lambda, d_w, ltr, inputs.get("hub_diameter_mm"),
            inputs.get("load_derivation_position", LOAD_DERIVATION_REAR),
            inputs.get("a0_mm"))
    except ValueError as exc:
        k_lambda_domain = {"error": str(exc), "K_lambda": k_lambda,
                           "source_id": SOURCE_DIN6892}
    result = {"method": METHOD_B_CURRENT, "badge": BADGE_DIN_METHOD,
              "source_id": SOURCE_DIN6892, "status": factor_audit["status"],
              "p_zul_MPa": governing["p_zul_MPa"],
              "p_eq_zul_MPa": governing["p_eq_zul_MPa"],
              "torque_allowable_Nm": torque, "torque_design_Nm": torque / safety,
              "safety_factor": safety,
              "f_S": governing["f_S"], "f_H": governing["f_H"],
              "f_W": reversal["f_W"], "K_lambda": k_lambda, "K_R": k_r,
              "K_V": distribution["K_V"], "load_distribution": distribution,
              "peak_load_distribution": peak_distribution,
              "load_reversal": reversal,
              "load_reversal_count": reversal_count,
              "bearing_depth_policy": depth_policy,
              "bearing_depths": depth_map,
              "t1tr_mm": t1tr, "t2tr_mm": depth_map["t2tr_mm"],
              "K_lambda_domain": k_lambda_domain,
              "components": evaluated,
              "components_skipped": skipped,
              "governing_component": governing["name"],
              "governing_bearing_depth_mm": governing["bearing_depth_mm"],
              "length_domain": domain,
              "factor_audit": factor_audit, "equations": list(range(1, 13)),
              "limitations": [
                  "K_lambda is read from DIN 6892 diagrams and remains an explicit USER-INPUT",
                  "f_S/f_H come from DIN 6892 Table 2 only when a material class is declared",
                  "Without t2tr the hub and key checks fall back to the shaft depth and are optimistic",
              ]}
    if application is not None:
        result["application"] = application
        result["K_A"] = application["K_A"]
        result["torque_nominal_Nm"] = application["torque_nominal_Nm"]
        result["torque_equivalent_Nm"] = application["torque_equivalent_Nm"]
    if "torque_peak_allowable_Nm" in governing:
        peak = _governing_component(
            [item for item in evaluated if "torque_peak_allowable_Nm" in item])
        result["p_max_zul_MPa"] = peak["p_max_zul_MPa"]
        result["torque_peak_allowable_Nm"] = peak["torque_peak_allowable_Nm"]
        result["f_L"] = peak["f_L"]
        result["governing_component_peak"] = peak["name"]
    if applied_equivalent is not None:
        result["torque_applied_Nm"] = applied_equivalent
        result["p_eq_MPa"] = governing.get("p_eq_MPa")
        result["safety_S_Feq"] = torque / applied_equivalent
        result["safety_equation"] = 1
        result["utilisation_eq"] = governing.get("utilisation_eq")
    if applied_peak is not None and "torque_peak_allowable_Nm" in result:
        result["torque_peak_applied_Nm"] = applied_peak
        result["safety_S_Fmax"] = (result["torque_peak_allowable_Nm"] /
                                   applied_peak)
    return result


def method_b_fva2025(inputs):
    """FVA 600 III proposed Method-B reformulation, equation 36.

    M_t = f_Sv * (f_WS + f_S,ltr) * f_H * f_W * Re * d_w * l_tr * t_1tr
          / (2 * K_R * K_lambda * K_d * K_V)

    The limit-load criterion is the relative plastic opening volume of the SHAFT
    keyway, so Re and Rm are the shaft's and equation 33 never divides one part's
    tensile strength by another part's yield strength. f_WS takes the place of
    the shaft's tabulated f_S, and the report's corrected friction factor is
    K_R = 1 because a superposed interference fit does not raise the
    quasi-static transmissible torque.
    """
    d_w = _number(inputs.get("d_w_mm"), "d_w_mm", positive=True)
    ltr = _number(inputs.get("ltr_mm"), "ltr_mm", positive=True)
    depth_policy = resolve_bearing_depth_policy(inputs)
    t1tr = depth_policy["t1tr_mm"]
    v = _number(inputs.get("v", 0.5), "v", positive=True, allow_zero=True)
    k_lambda = _number(inputs.get("K_lambda"), "K_lambda", positive=True)
    k_r = _number(inputs.get("K_R", FVA_FRICTION_FACTOR_K_R), "K_R", positive=True)
    reversal_count = load_reversal_count(
        inputs.get("load_cycles", 10000.0), inputs.get("load_ratio_R"),
        inputs.get("N_W"))
    reversal = load_reversal_factor(reversal_count["N_W"])
    reversal["count"] = reversal_count
    distribution = load_distribution_factor(int(inputs.get("key_count", 1)),
                                            inputs.get("phi"),
                                            LOAD_TARGET_ALLOWABLE)
    f_sv = volume_support_factor(v)
    f_sltr = length_support_factor_fva(ltr, d_w)
    k_d = size_factor(d_w)
    domain = length_support_factor_domain(ltr, d_w)
    # The limit-load criterion of FVA 600 III is the plastic expansion volume of
    # the SHAFT keyway. Equation 36 therefore uses the shaft's Re, and f_WS
    # replaces the shaft's tabulated f_S. The hub keyway was deliberately not
    # measured in the project and hub cracking was out of scope, so the other
    # components are reported as not covered instead of being made governing.
    shaft = _named_component(inputs, "shaft", require_tensile=True)
    not_covered = [row["name"] for row in (inputs.get("components") or [])
                   if str((row or {}).get("name", "")).strip().lower() != "shaft"]
    f_h_source = _component_support_factors(inputs, "shaft")
    f_h = f_h_source["f_H"]
    f_ws = strength_support_factor(shaft["Rm_MPa"], shaft["Re_MPa"])
    f_sges = f_ws["f_WS"] + f_sltr["f_S_ltr"]
    numerator = (f_sv["f_Sv"] * f_sges * f_h * reversal["f_W"] *
                 shaft["Re_MPa"] * d_w * ltr * t1tr)
    denominator = 2.0 * k_r * k_lambda * k_d["K_d"] * distribution["K_V"]
    torque = numerator / denominator / 1000.0
    safety = _number(inputs.get("safety_factor", 1.2), "safety_factor", positive=True)
    factor_audit = factor_provenance_audit(inputs, factors=("K_lambda",))
    return {"method": METHOD_B_FVA, "badge": BADGE_FVA_RESEARCH,
            "source_id": SOURCE_FVA, "status": "RESEARCH_DIAGNOSTIC",
            "torque_allowable_Nm": torque, "torque_design_Nm": torque / safety,
            "safety_factor": safety, "v": v, "f_Sv": f_sv["f_Sv"],
            "f_WS": f_ws["f_WS"], "f_S_ltr": f_sltr["f_S_ltr"],
            "f_S_ges": f_sges, "f_H": f_h,
            "f_H_provenance": f_h_source["f_H_provenance"],
            "f_W": reversal["f_W"], "K_R": k_r, "K_lambda": k_lambda,
            "K_d": k_d["K_d"], "size_factor": k_d,
            "K_V": distribution["K_V"], "load_distribution": distribution,
            "load_reversal": reversal,
            "load_reversal_count": reversal_count,
            "bearing_depth_policy": depth_policy,
            "t1tr_mm": t1tr, "length_domain": domain,
            "criterion": "SHAFT_KEYWAY_RELATIVE_OPENING_VOLUME",
            "governing_component": "shaft",
            "governing_bearing_depth_mm": t1tr,
            "Re_MPa": shaft["Re_MPa"], "Rm_MPa": shaft["Rm_MPa"],
            "components_not_covered": not_covered,
            "factor_audit": factor_audit,
            "equations": [26, 29, 33, 34, 35, 36],
            "limitations": [
                "FVA 600 III research proposal; not a published DIN edition",
                "The criterion is the shaft keyway opening volume; the hub keyway was not measured and hub cracking was out of scope",
                "Hardened joints and the hardness factor f_H could not be validated by the project",
                "DIN 743 fatigue verification remains independent",
            ]}


def interpolate_method_a_torque(trials, v_crit=0.5, safety_factor=1.2):
    limit = _number(v_crit, "v_crit", positive=True)
    safety = _number(safety_factor, "safety_factor", positive=True)
    cleaned = []
    for item in trials or []:
        torque = _number(item.get("torque_Nm"), "trial torque_Nm", positive=True)
        value = _number(item.get("v"), "trial v", positive=True, allow_zero=True)
        cleaned.append({"torque_Nm": torque, "v": value})
    cleaned.sort(key=lambda item: item["torque_Nm"])
    lower = None
    upper = None
    for item in cleaned:
        if item["v"] <= limit:
            lower = item
        elif lower is not None:
            upper = item
            break
    if lower is None or upper is None:
        return {"status": "NEEDS_BRACKETING_TRIALS", "v_crit": limit,
                "trials": cleaned, "torque_allowable_Nm": None,
                "torque_design_Nm": None, "safety_factor": safety,
                "badge": BADGE_FVA_RESEARCH, "source_id": SOURCE_FVA}
    delta_v = upper["v"] - lower["v"]
    if abs(delta_v) <= 1e-15:
        raise ValueError("Method-A interpolation trials have identical v values")
    fraction = (limit - lower["v"]) / delta_v
    torque = lower["torque_Nm"] + fraction * (upper["torque_Nm"] - lower["torque_Nm"])
    return {"status": "INTERPOLATED", "v_crit": limit, "trials": cleaned,
            "bracket": [lower, upper], "torque_allowable_Nm": torque,
            "torque_design_Nm": torque / safety, "safety_factor": safety,
            "badge": BADGE_FVA_RESEARCH, "source_id": SOURCE_FVA,
            "method": METHOD_A}


def method_a_assessment(inputs):
    cycles = int(inputs.get("cycles", 0) or 0)
    checks = {
        "minimum_cycles": cycles >= int(inputs.get("minimum_cycles", 10) or 10),
        "unloaded_frame": bool(inputs.get("unloaded_frame_verified", False)),
        "source_frame_identified": bool(inputs.get("source_frame_identified", False)),
        "coverage_within_2_percent": bool(
            inputs.get("coverage_within_2_percent", False)),
        "invariants_revalidated": bool(
            inputs.get("invariants_revalidated", False)),
        "provenance_hash_verified": bool(
            inputs.get("provenance_hash_verified", False)),
        "matching_mesh": bool(inputs.get("matching_mesh_verified", False)),
        "mesh_convergence": bool(inputs.get("mesh_convergence_verified", False)),
        "equilibrium": bool(inputs.get("equilibrium_verified", False)),
        "contact": bool(inputs.get("contact_verified", False)),
        "din743_fatigue": bool(inputs.get("din743_verified", False)),
    }
    delta = inputs.get("delta_volume_mm3")
    volume = None
    if delta not in (None, ""):
        volume = relative_opening_volume(
            delta, inputs.get("ltr_mm"), inputs.get("t1tr_mm"),
            inputs.get("UPF_um"), inputs.get("v_crit", 0.5))
    # The report requires >=10 cycles and evaluation after unloading. Other
    # checks are safety/quality evidence and remain visible even when absent.
    complete_method_a = (bool(volume) and checks["minimum_cycles"] and
                         checks["unloaded_frame"] and
                         checks["source_frame_identified"] and
                         checks["coverage_within_2_percent"] and
                         checks["invariants_revalidated"] and
                         checks["provenance_hash_verified"])
    if volume is None:
        status = "EXTERNAL_RESULT_REQUIRED"
    elif complete_method_a:
        status = "ASSESSED"
    else:
        status = "INCOMPLETE_EVIDENCE"
    result = {"method": METHOD_A, "badge": BADGE_FVA_RESEARCH,
              "source_id": SOURCE_FVA, "status": status,
              "complete_method_a": complete_method_a, "cycles": cycles,
              "checks": checks, "volume": volume,
              "criterion_met": (volume["criterion_met"]
                                if complete_method_a else None),
              "equations": [16, 17, 18],
              "limitations": [
                  "The calculation engine does not solve an ODB; the connected CAE backend can create or submit a Job only when explicitly enabled, while bundled companion presets remain NOJOB"]}
    result["torque_interpolation"] = interpolate_method_a_torque(
        inputs.get("trials") or [], inputs.get("v_crit", 0.5),
        inputs.get("safety_factor", 1.2))
    return result


def evaluate(method_id, inputs):
    method = str(method_id or "").strip().upper()
    if method == METHOD_A:
        return method_a_assessment(inputs)
    if method == METHOD_B_CURRENT:
        return method_b_current(inputs)
    if method == METHOD_B_FVA:
        return method_b_fva2025(inputs)
    if method == METHOD_C:
        return method_c_preliminary(inputs)
    raise ValueError("Unknown DIN 6892 method %r" % method_id)


ANALYTICAL_METHOD_IDS = (METHOD_B_CURRENT, METHOD_B_FVA, METHOD_C)


def companion_evaluations(primary_method_id, inputs, companion_ids=None):
    """Evaluate the analytical methods alongside the selected primary method.

    Method A needs solved FE evidence while Methods B and C are closed-form, so
    an engineer normally wants all of them for the same joint.  Each companion
    is isolated: a companion that cannot be evaluated reports its own reason and
    never invalidates the primary result.
    """
    primary = str(primary_method_id or "").strip().upper()
    requested = [str(item).strip().upper()
                 for item in (companion_ids
                              if companion_ids is not None
                              else ANALYTICAL_METHOD_IDS)]
    results = {}
    issues = []
    for method in requested:
        if method == primary:
            continue
        if method not in ANALYTICAL_METHOD_IDS:
            issues.append({
                "level": "warn", "code": "din6892_companion_invalid",
                "msg": ("%r is not an analytical companion method; expected one "
                        "of %s." % (method, ", ".join(ANALYTICAL_METHOD_IDS)))})
            continue
        try:
            calculation = evaluate(method, inputs)
        except (TypeError, ValueError, KeyError) as exc:
            results[method] = {"method": method, "status": "INVALID_INPUT",
                               "reason": str(exc),
                               "torque_allowable_Nm": None,
                               "torque_design_Nm": None}
            issues.append({
                "level": "warn", "code": "din6892_companion_invalid",
                "msg": "Companion method %s could not be evaluated: %s" %
                       (method, exc)})
            continue
        results[method] = {
            "method": method, "status": calculation.get("status"),
            "badge": calculation.get("badge"),
            "source_id": calculation.get("source_id"),
            "torque_allowable_Nm": calculation.get("torque_allowable_Nm"),
            "torque_design_Nm": calculation.get("torque_design_Nm"),
            "governing_component": calculation.get("governing_component"),
            "governing_bearing_depth_mm": calculation.get(
                "governing_bearing_depth_mm"),
            "p_zul_MPa": calculation.get("p_zul_MPa"),
            "safety_S_Feq": calculation.get(
                "safety_S_Feq", calculation.get("safety_S_F")),
            "equations": calculation.get("equations"),
            "calculation": calculation,
        }
    consistency = cross_method_consistency(primary, inputs, results)
    issues.extend(consistency.get("issues") or [])
    return {"primary_method": primary, "requested": requested,
            "results": results, "consistency": consistency, "issues": issues}


def cross_method_consistency(primary_method_id, inputs, companion_results):
    """Compare the analytical methods against each other.

    Method C is a preliminary sizing method, so it must stay on the safe side of
    the more detailed Method B. If Method C allows MORE torque than Method B, a
    joint sized with Method C alone would be unsafe, and that has to be said out
    loud instead of being left for the reader to notice in a table.
    """
    primary = str(primary_method_id or "").strip().upper()
    torques = {}
    if primary in ANALYTICAL_METHOD_IDS:
        try:
            torques[primary] = evaluate(primary, inputs).get(
                "torque_allowable_Nm")
        except (TypeError, ValueError, KeyError):
            torques[primary] = None
    for method, item in (companion_results or {}).items():
        torques[method] = (item or {}).get("torque_allowable_Nm")
    issues = []
    b_current = torques.get(METHOD_B_CURRENT)
    method_c = torques.get(METHOD_C)
    b_fva = torques.get(METHOD_B_FVA)
    ratio_c_over_b = None
    if b_current and method_c:
        ratio_c_over_b = method_c / b_current
        if ratio_c_over_b > 1.0 + 1.0e-9:
            issues.append({
                "level": "warn", "code": "din6892_method_c_not_conservative",
                "msg": ("Method C allows %.1f %% MORE torque than Method B "
                        "(%.2f N m vs %.2f N m). Preliminary sizing must stay "
                        "on the safe side, so the Method-B result governs."
                        % (100.0 * (ratio_c_over_b - 1.0), method_c, b_current))})
    ratio_fva_over_b = None
    if b_current and b_fva:
        ratio_fva_over_b = b_fva / b_current
    return {"torques_Nm": torques,
            "method_c_over_method_b": ratio_c_over_b,
            "method_c_is_conservative": (
                None if ratio_c_over_b is None
                else ratio_c_over_b <= 1.0 + 1.0e-9),
            "fva_over_method_b": ratio_fva_over_b,
            "governing_analytical_torque_Nm": (
                min(value for value in (b_current, method_c) if value)
                if (b_current or method_c) else None),
            "issues": issues,
            "note": ("Method C is a preliminary constant-pressure estimate and "
                     "the FVA reformulation is a research proposal, so the "
                     "current Method B stays the reference for a DIN-conforming "
                     "torque check."),
            "source_id": SOURCE_DIN6892}


def validate_configuration(method_id, inputs):
    issues = []
    method = str(method_id or "").strip().upper()
    if method not in METHOD_IDS:
        issues.append({"level": "error", "code": "din6892_method_unknown",
                       "msg": "Unknown DIN 6892 method %r" % method_id})
        return issues
    try:
        if method == METHOD_A:
            cycles = int(inputs.get("cycles", 0) or 0)
            if cycles < 10:
                issues.append({"level": "warn", "code": "method_a_cycles_low",
                               "msg": "Method A research workflow requires at least 10 load cycles."})
            if not inputs.get("source_frame_identified", False):
                issues.append({"level": "warn", "code": "method_a_source_frame_missing",
                               "msg": "Method A requires an identified unloaded source step/frame."})
            if inputs.get("delta_volume_mm3") in (None, ""):
                issues.append({"level": "info", "code": "method_a_external_result_required",
                               "msg": "Method A requires external FE/post-processing data."})
        elif method in (METHOD_B_CURRENT, METHOD_B_FVA):
            if not inputs.get("K_lambda"):
                issues.append({"level": "error", "code": "K_lambda_required",
                               "msg": "Method B requires an explicit K_lambda factor."})
        calculation = evaluate(method, inputs)
        audit = calculation.get("factor_audit") or {}
        placeholders = audit.get("placeholder_factors") or []
        if placeholders:
            issues.append({
                "level": "warn", "code": "din6892_factor_placeholder",
                "msg": ("Licensed DIN 6892 factor(s) %s are still at the neutral "
                        "value 1.0 with USER-INPUT provenance, so %s is "
                        "provisional." % (", ".join(placeholders), method))})
        for item in calculation.get("components_skipped") or []:
            issues.append({
                "level": "warn", "code": "din6892_component_check_incomplete",
                "msg": ("Component %s was not covered by the %s bearing check: "
                        "%s" % (item.get("name"), method, item.get("reason")))})
        size = calculation.get("size_factor") or {}
        if size and not size.get("transcription_continuous", True):
            level = "warn" if size.get("plateau_applies") else "info"
            issues.append({
                "level": level, "code": "fva_size_factor_transcription_step",
                "msg": size.get("warning", "Equation 29 transcription is discontinuous.")})
        if size and not size.get("inside_data_domain", True):
            issues.append({
                "level": "warn", "code": "fva_size_factor_out_of_domain",
                "msg": ("The size factor K_d was fitted for shaft diameters of "
                        "roughly 10 to 450 mm; d_w = %.1f mm is outside that "
                        "range." % float(size.get("d_w_mm", 0.0)))})
        domain = calculation.get("length_domain") or {}
        if domain.get("exceeds_design_limit"):
            issues.append({
                "level": "warn", "code": "din6892_length_ratio_exceeded",
                "msg": ("l_tr/d_w = %.3f exceeds 1.3; beyond that the rear part "
                        "of the key transmits practically no pressure and DIN "
                        "6892 advises against longer joints."
                        % float(domain.get("ltr_over_dw", 0.0)))})
        elif domain and not domain.get("inside_fit_domain", True):
            issues.append({
                "level": "warn", "code": "din6892_length_fit_extrapolated",
                "msg": ("l_tr/d_w = %.3f is outside the 0.5 to 1.3 range the "
                        "length support factor was fitted for; the value is "
                        "extrapolated." % float(domain.get("ltr_over_dw", 0.0)))})
        for name in calculation.get("components_not_covered") or []:
            issues.append({
                "level": "info", "code": "fva_component_not_covered",
                "msg": ("The FVA reformulation is a shaft-keyway criterion, so "
                        "the %s is not covered by it and still needs the "
                        "current Method-B or Method-C check." % name)})
        issues.extend(_bearing_depth_issues(calculation))
        issues.extend(_load_reversal_issues(calculation))
        issues.extend(_k_lambda_issues(calculation))
        issues.extend(_method_c_issues(calculation))
    except (TypeError, ValueError, KeyError) as exc:
        issues.append({"level": "error", "code": "din6892_calculation_invalid",
                       "msg": str(exc)})
    return issues


def _bearing_depth_issues(calculation):
    """Report the equation-9 cross-check and any hub-depth fallback."""
    issues = []
    policy = calculation.get("bearing_depth_policy") or {}
    if policy and policy.get("geometric_available") and not policy.get("agrees"):
        equation9 = float(policy.get("t1tr_equation9_mm") or 0.0)
        geometric = float(policy.get("t1tr_geometric_mm") or 0.0)
        applied = str(policy.get("policy_applied") or DEPTH_POLICY_EQUATION_9)
        if applied == DEPTH_POLICY_EQUATION_9 and equation9 > geometric:
            issues.append({
                "level": "warn", "code": "din6892_bearing_depth_optimistic",
                "msg": ("Equation 9 gives t1tr = %.4f mm while the shaft flank "
                        "geometry gives %.4f mm, so every Method B/C torque is "
                        "about %.0f %% optimistic. Set bearing_depth_policy to "
                        "CONSERVATIVE or GEOMETRIC to check the joint against "
                        "the flank height."
                        % (equation9, geometric,
                           100.0 * (equation9 / geometric - 1.0)
                           if geometric > 0.0 else 0.0))})
        else:
            issues.append({
                "level": "info", "code": "din6892_bearing_depth_policy_applied",
                "msg": ("The effective shaft bearing depth follows policy %s: "
                        "equation 9 gives %.4f mm, the flank geometry %.4f mm, "
                        "and %.4f mm is used."
                        % (applied, equation9, geometric,
                           float(policy.get("t1tr_mm") or 0.0)))})
    depths = calculation.get("bearing_depths") or {}
    if depths and not depths.get("hub_depth_available", True):
        issues.append({
            "level": "warn", "code": "din6892_hub_bearing_depth_missing",
            "msg": ("No hub bearing depth t2tr was supplied, so the hub keyway "
                    "and the key are checked with the shaft depth t1tr. Because "
                    "DIN 6885 gives t2 < t1, that overstates the hub bearing "
                    "area and the resulting torque.")})
    return issues


def _load_reversal_issues(calculation):
    """Make the N_W derivation of equation 3 auditable."""
    count = calculation.get("load_reversal_count") or {}
    if not count or not count.get("derived"):
        return []
    source = str(count.get("source") or "")
    if source == REVERSAL_SOURCE_UNKNOWN_DIRECTION:
        return [{
            "level": "warn", "code": "din6892_load_reversal_unknown_direction",
            "msg": ("The load direction is unknown, so all %g load cycles were "
                    "counted as load direction reversals and f_W = %.3f. Supply "
                    "load_ratio_R or N_W to remove this conservative fallback."
                    % (float(count.get("load_cycles") or 0.0),
                       float(calculation.get("f_W") or 1.0)))}]
    return [{
        "level": "info", "code": "din6892_load_reversal_derived",
        "msg": ("N_W = %g load direction reversals were derived from R = %s "
                "(%s), giving f_W = %.3f. DIN 6892 equation 3 counts load "
                "DIRECTION reversals, not load cycles."
                % (float(count.get("N_W") or 0.0), count.get("load_ratio_R"),
                   source, float(calculation.get("f_W") or 1.0)))}]


def _k_lambda_issues(calculation):
    """Check that K_lambda could have been read from the licensed diagram."""
    domain = calculation.get("K_lambda_domain") or {}
    if not domain:
        return []
    issues = []
    if domain.get("error"):
        issues.append({"level": "warn", "code": "din6892_k_lambda_domain_invalid",
                       "msg": str(domain["error"])})
        return issues
    if not domain.get("K_lambda_inside_diagram", True):
        issues.append({
            "level": "warn", "code": "din6892_k_lambda_outside_diagram",
            "msg": ("K_lambda = %.3f is outside the %.1f to %.1f range of the "
                    "DIN 6892 load-distribution diagrams, so it cannot have "
                    "been read from them."
                    % (float(domain.get("K_lambda") or 0.0),
                       domain.get("K_lambda_range", [1.0, 2.0])[0],
                       domain.get("K_lambda_range", [1.0, 2.0])[1]))})
    if domain.get("Q_A_inside_diagram") is False:
        issues.append({
            "level": "warn", "code": "din6892_k_lambda_qa_outside_diagram",
            "msg": ("Q_A = d_w/D = %.3f is outside the %.1f to %.1f axis of the "
                    "K_lambda diagrams; the reading is extrapolated."
                    % (float(domain.get("Q_A_shaft_over_hub") or 0.0),
                       domain.get("Q_A_range", [0.3, 0.9])[0],
                       domain.get("Q_A_range", [0.3, 0.9])[1]))})
    if not domain.get("ltr_over_dw_inside_diagram", True):
        issues.append({
            "level": "warn", "code": "din6892_k_lambda_length_outside_diagram",
            "msg": ("l_tr/d_w = %.3f is outside the %.1f to %.1f axis of the "
                    "K_lambda diagrams; the reading is extrapolated."
                    % (float(domain.get("ltr_over_dw") or 0.0),
                       domain.get("ltr_over_dw_range", [0.5, 2.0])[0],
                       domain.get("ltr_over_dw_range", [0.5, 2.0])[1]))})
    return issues


def _method_c_issues(calculation):
    """Method C clearance and sizing diagnostics."""
    if calculation.get("method") != METHOD_C:
        return []
    issues = []
    engaged = calculation.get("engaged_height") or {}
    if engaged.get("clearance_is_negative"):
        issues.append({
            "level": "warn", "code": "din6892_method_c_clearance_negative",
            "msg": ("The top clearance g_c = t1 + t2 - h = %.3f mm is negative: "
                    "the key is taller than the two keyway depths together, so "
                    "equation 31 does not describe this joint."
                    % float(engaged.get("top_clearance_gc_mm") or 0.0))})
    sizing = calculation.get("sizing") or {}
    if sizing.get("status") == "INVALID_INPUT":
        issues.append({
            "level": "warn", "code": "din6892_method_c_sizing_invalid",
            "msg": ("The Method C length sizing could not be evaluated: %s"
                    % sizing.get("reason"))})
    elif sizing.get("exceeds_design_limit"):
        issues.append({
            "level": "warn", "code": "din6892_method_c_sizing_too_long",
            "msg": ("The required bearing length l_tr = %.1f mm gives "
                    "l_tr/d_w = %.3f > 1.3, where the rear part of the key "
                    "transmits practically no pressure. Use more keys or "
                    "another joint type instead of a longer key."
                    % (float(sizing.get("ltr_required_mm") or 0.0),
                       float(sizing.get("ltr_over_dw_required") or 0.0)))})
    return issues
