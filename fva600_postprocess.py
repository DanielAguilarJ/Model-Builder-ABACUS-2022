# -*- coding: utf-8 -*-
"""Safe external CSV post-processing for FVA 600 III Method A.

This Python-3-only module does not open an ODB and does not claim that Model
Builder solved a model. It consumes a rectangular grid exported from a solved
and unloaded FE frame with canonical columns::

    x_mm,z_mm,opening_um

``opening_um`` is the permanent local keyway opening in micrometres. Delta V is
integrated with the two-dimensional trapezoidal rule (cell-wise bilinear corner
average). The FVA relative volume is then computed by the shared pure core.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os

import din6892_methods as methods

REQUIRED_COLUMNS = ("x_mm", "z_mm", "opening_um")
POSTPROCESSOR_VERSION = "fva600-csv-1.0"
EVIDENCE_CONTRACT_VERSION = 2
COVERAGE_TOLERANCE = 0.02


class PostprocessError(ValueError):
    """Raised for malformed or physically unusable post-processing data."""


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value):
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _valid_sha256(value):
    text = str(value or "").lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _finite(value, label, row_number):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise PostprocessError("Row %d: %s is not numeric" % (row_number, label))
    if not math.isfinite(number):
        raise PostprocessError("Row %d: %s must be finite" % (row_number, label))
    return number


def read_opening_csv(path):
    absolute = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    if not os.path.isfile(absolute):
        raise PostprocessError("CSV does not exist: %s" % absolute)
    with open(absolute, "r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(4096)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        headers = tuple(reader.fieldnames or ())
        missing = [name for name in REQUIRED_COLUMNS if name not in headers]
        if missing:
            raise PostprocessError("CSV is missing canonical column(s): %s" %
                                   ", ".join(missing))
        rows = []
        seen = set()
        for row_number, row in enumerate(reader, 2):
            x = _finite(row.get("x_mm"), "x_mm", row_number)
            z = _finite(row.get("z_mm"), "z_mm", row_number)
            opening = _finite(row.get("opening_um"), "opening_um", row_number)
            if opening < 0.0:
                raise PostprocessError("Row %d: opening_um cannot be negative" % row_number)
            key = (x, z)
            if key in seen:
                raise PostprocessError("Duplicate grid coordinate at row %d: %r" %
                                       (row_number, key))
            seen.add(key)
            rows.append({"x_mm": x, "z_mm": z, "opening_um": opening})
    if len(rows) < 4:
        raise PostprocessError("At least four points are required")
    return absolute, headers, rows


def integrate_opening_grid(rows):
    if not rows:
        raise PostprocessError("Opening grid is empty")
    xs = sorted(set(float(item["x_mm"]) for item in rows))
    zs = sorted(set(float(item["z_mm"]) for item in rows))
    if len(xs) < 2 or len(zs) < 2:
        raise PostprocessError("Opening grid needs at least 2 x-values and 2 z-values")
    expected = len(xs) * len(zs)
    if len(rows) != expected:
        raise PostprocessError(
            "Grid is not rectangular: %d points supplied, %d required (%d x %d)" %
            (len(rows), expected, len(xs), len(zs)))
    values = {}
    for index, item in enumerate(rows, 1):
        x = float(item["x_mm"])
        z = float(item["z_mm"])
        opening = float(item["opening_um"])
        if not all(math.isfinite(value) for value in (x, z, opening)):
            raise PostprocessError("Point %d contains a non-finite value" % index)
        if opening < 0.0:
            raise PostprocessError("Point %d has negative opening" % index)
        key = (x, z)
        if key in values:
            raise PostprocessError("Duplicate grid coordinate: %r" % (key,))
        values[key] = opening / 1000.0  # micrometres -> millimetres
    missing = [(x, z) for x in xs for z in zs if (x, z) not in values]
    if missing:
        raise PostprocessError("Grid has %d missing coordinate(s); first=%r" %
                               (len(missing), missing[0]))
    delta_volume = 0.0
    cell_count = 0
    for x_index in range(len(xs) - 1):
        x0, x1 = xs[x_index], xs[x_index + 1]
        dx = x1 - x0
        if dx <= 0.0:
            raise PostprocessError("x coordinates must increase strictly")
        for z_index in range(len(zs) - 1):
            z0, z1 = zs[z_index], zs[z_index + 1]
            dz = z1 - z0
            if dz <= 0.0:
                raise PostprocessError("z coordinates must increase strictly")
            mean_opening = 0.25 * (
                values[(x0, z0)] + values[(x1, z0)] +
                values[(x0, z1)] + values[(x1, z1)])
            delta_volume += mean_opening * dx * dz
            cell_count += 1
    return {
        "delta_volume_mm3": delta_volume,
        "integration": "2D_TRAPEZOID_CELL_CORNER_AVERAGE",
        "equation": 18,
        "point_count": len(rows),
        "cell_count": cell_count,
        "x_count": len(xs),
        "z_count": len(zs),
        "x_bounds_mm": [xs[0], xs[-1]],
        "z_bounds_mm": [zs[0], zs[-1]],
        "x_span_mm": xs[-1] - xs[0],
        "z_span_mm": zs[-1] - zs[0],
        "grid_area_mm2": (xs[-1] - xs[0]) * (zs[-1] - zs[0]),
        "opening_bounds_um": [min(values.values()) * 1000.0,
                              max(values.values()) * 1000.0],
    }


def process_csv(path, ltr_mm, t1tr_mm, UPF_um, v_crit=0.5,
                unloaded_frame_verified=False, cycles=0,
                source_step="", source_frame=""):
    absolute, headers, rows = read_opening_csv(path)
    integration = integrate_opening_grid(rows)
    try:
        cycle_count = int(cycles or 0)
    except (TypeError, ValueError):
        raise PostprocessError("cycles must be an integer")
    if cycle_count < 0:
        raise PostprocessError("cycles cannot be negative")
    volume = methods.relative_opening_volume(
        integration["delta_volume_mm3"], ltr_mm, t1tr_mm, UPF_um, v_crit)
    minimum_cycles = cycle_count >= 10
    unloaded = bool(unloaded_frame_verified)
    step_name = str(source_step or "").strip()
    frame_name = str(source_frame or "").strip()
    frame_identified = bool(step_name and frame_name)
    expected_x_span = float(ltr_mm)
    expected_z_span = float(t1tr_mm)
    expected_area = expected_x_span * expected_z_span
    grid_area = integration["grid_area_mm2"]
    coverage_ratio = grid_area / expected_area if expected_area > 0.0 else None
    x_ratio = (integration["x_span_mm"] / expected_x_span
               if expected_x_span > 0.0 else None)
    z_ratio = (integration["z_span_mm"] / expected_z_span
               if expected_z_span > 0.0 else None)
    x_bounds = integration["x_bounds_mm"]
    z_bounds = integration["z_bounds_mm"]
    x_bounds_ok = (
        expected_x_span > 0.0 and
        abs(x_bounds[0]) <= COVERAGE_TOLERANCE * expected_x_span and
        abs(x_bounds[1] - expected_x_span) <=
        COVERAGE_TOLERANCE * expected_x_span)
    z_bounds_ok = (
        expected_z_span > 0.0 and
        abs(z_bounds[0]) <= COVERAGE_TOLERANCE * expected_z_span and
        abs(z_bounds[1] - expected_z_span) <=
        COVERAGE_TOLERANCE * expected_z_span)
    coverage_ok = bool(
        coverage_ratio is not None and x_ratio is not None and
        z_ratio is not None and
        abs(coverage_ratio - 1.0) <= COVERAGE_TOLERANCE and
        abs(x_ratio - 1.0) <= COVERAGE_TOLERANCE and
        abs(z_ratio - 1.0) <= COVERAGE_TOLERANCE and
        x_bounds_ok and z_bounds_ok)
    invariants = {
        "ltr_mm": float(ltr_mm),
        "t1tr_mm": float(t1tr_mm),
        "UPF_um": float(UPF_um),
    }
    invariants_hash = _sha256_json(invariants)
    evidence_complete = (
        minimum_cycles and unloaded and frame_identified and coverage_ok)
    warnings = [
        "External data: Model Builder did not create or solve the source ODB",
        "Mesh matching, convergence, equilibrium, contact and DIN 743 fatigue require independent evidence",
    ]
    if not minimum_cycles:
        warnings.append("Method A requires at least 10 load cycles")
    if not unloaded:
        warnings.append("The CSV must come from a verified unloaded frame")
    if not frame_identified:
        warnings.append("Both source_step and source_frame are required for conclusive evidence")
    if not coverage_ok:
        warnings.append(
            "CSV grid must cover x=[0,l_tr] and z=[0,t1tr] within 2 percent "
            "per axis and by area")
    return {
        "result_schema_version": 1,
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "postprocessor_version": POSTPROCESSOR_VERSION,
        "badge": methods.BADGE_FVA_RESEARCH,
        "source_id": methods.SOURCE_FVA,
        "provenance": {
            "kind": "external_csv",
            "path": absolute,
            "sha256": _sha256(absolute),
            "size_bytes": os.path.getsize(absolute),
            "headers": list(headers),
            "source_step": step_name,
            "source_frame": frame_name,
            "model_builder_did_not_solve": True,
        },
        "integration": integration,
        "invariants": invariants,
        "invariants_sha256": invariants_hash,
        "coverage": {
            "tolerance_fraction": COVERAGE_TOLERANCE,
            "expected_x_bounds_mm": [0.0, expected_x_span],
            "expected_z_bounds_mm": [0.0, expected_z_span],
            "expected_area_mm2": expected_area,
            "grid_area_mm2": grid_area,
            "x_span_over_ltr": x_ratio,
            "z_span_over_t1tr": z_ratio,
            "grid_over_expected": coverage_ratio,
            "x_bounds_within_2_percent": x_bounds_ok,
            "z_bounds_within_2_percent": z_bounds_ok,
            "within_2_percent": coverage_ok,
        },
        "volume": volume,
        "cycles": cycle_count,
        "unloaded_frame_verified": unloaded,
        "source_frame_identified": frame_identified,
        "minimum_cycles_verified": minimum_cycles,
        "method_a_evidence_complete": evidence_complete,
        "criterion_met": volume["criterion_met"] if evidence_complete else None,
        "warnings": warnings,
    }


def _validate_evidence_result(result, require_source=True):
    if not isinstance(result, dict):
        raise PostprocessError("postprocess result must be a dictionary")
    if int(result.get("result_schema_version", -1)) != 1:
        raise PostprocessError("unsupported postprocess result schema")
    if int(result.get("evidence_contract_version", -1)) != \
            EVIDENCE_CONTRACT_VERSION:
        raise PostprocessError("Method-A evidence contract version is stale")
    if (result.get("postprocessor_version") != POSTPROCESSOR_VERSION and
            not result.get("extractor_version")):
        raise PostprocessError("Method-A evidence producer is unsupported")
    integration = result.get("integration") or {}
    volume = result.get("volume") or {}
    coverage = result.get("coverage") or {}
    invariants = result.get("invariants") or {}
    required_invariants = ("ltr_mm", "t1tr_mm", "UPF_um")
    missing = [name for name in required_invariants if name not in invariants]
    if missing:
        raise PostprocessError("evidence invariants are incomplete: %s" %
                               ", ".join(missing))
    normalized_invariants = dict(
        (name, float(invariants[name])) for name in required_invariants)
    if min(normalized_invariants.values()) <= 0.0:
        raise PostprocessError("evidence invariants must be positive")
    if result.get("invariants_sha256") != _sha256_json(normalized_invariants):
        raise PostprocessError("evidence invariant hash does not match")
    inputs = volume.get("inputs") or {}
    for name in required_invariants:
        if name not in inputs:
            raise PostprocessError("volume.inputs.%s is required" % name)
        if abs(float(inputs[name]) - normalized_invariants[name]) > 1.0e-9:
            raise PostprocessError("volume input %s differs from invariant" % name)
    if "delta_volume_mm3" not in integration or "v" not in volume:
        raise PostprocessError("postprocess result is incomplete")
    if coverage.get("within_2_percent") is not True:
        raise PostprocessError(
            "opening grid coverage must pass the mandatory 2 percent gate")
    expected_complete = bool(
        result.get("minimum_cycles_verified") and
        result.get("unloaded_frame_verified") and
        result.get("source_frame_identified") and
        coverage.get("within_2_percent"))
    if bool(result.get("method_a_evidence_complete")) != expected_complete:
        raise PostprocessError("method_a_evidence_complete is inconsistent")
    provenance = result.get("provenance") or {}
    if not _valid_sha256(provenance.get("sha256")):
        raise PostprocessError("a valid provenance SHA-256 is mandatory")
    if int(provenance.get("size_bytes", -1)) < 0 or not provenance.get("path"):
        raise PostprocessError("provenance path and size are mandatory")
    verification = verify_source_provenance(result)
    if require_source and verification.get("verified") is not True:
        raise PostprocessError(
            "source provenance verification failed: %s" %
            verification.get("reason"))
    return {"integration": integration, "volume": volume,
            "coverage": coverage, "invariants": normalized_invariants,
            "provenance_verification": verification}


def attach_result_to_params(params, result):
    """Persist a validated external result inside schema-6 DIN 6892 inputs.

    This deliberately does not enable the legacy CAE backend: importing solved
    external evidence and asking Model Builder to create a model are separate
    actions with separate provenance.
    """
    if not isinstance(params, dict):
        raise PostprocessError("params must be a dictionary")
    validated = _validate_evidence_result(result, require_source=True)
    integration = validated["integration"]
    volume = validated["volume"]
    invariants = validated["invariants"]

    # Recompute the current geometry before attachment.  The persisted ltr,
    # t1tr and UPF are immutable evidence inputs, not advisory metadata.
    import keyjoint_core as core
    probe = copy.deepcopy(params)
    derived = core.derive(probe)
    expected = {
        "ltr_mm": float(derived["load_bearing_length"]),
        "t1tr_mm": float(derived["din6892"]["derived"]
                          ["effective_bearing_depth"]["t1tr_mm"]),
        "UPF_um": float((params.get("din6892", {}) or {}).get(
            "UPF_um", 0.0) or 0.0),
    }
    for name in ("ltr_mm", "t1tr_mm", "UPF_um"):
        if abs(invariants[name] - expected[name]) > 1.0e-9:
            raise PostprocessError(
                "evidence invariant %s=%.12g differs from current %.12g" %
                (name, invariants[name], expected[name]))
    persisted_result = copy.deepcopy(result)
    persisted_result["provenance_verification"] = copy.deepcopy(
        validated["provenance_verification"])
    persisted_result["attached_invariants_verified"] = {
        "verified": True, "current": expected,
        "invariants_sha256": result["invariants_sha256"]}
    payload = copy.deepcopy(params)
    din_cfg = payload.setdefault("din6892", {})
    din_cfg["enabled"] = True
    din_cfg["method"] = methods.METHOD_A
    din_cfg["v"] = float(volume["v"])
    volume_inputs = volume.get("inputs") or {}
    if volume_inputs.get("UPF_um") is not None:
        din_cfg["UPF_um"] = float(volume_inputs["UPF_um"])
    method_a = din_cfg.setdefault("method_a", {})
    method_a.update({
        "delta_volume_mm3": float(integration["delta_volume_mm3"]),
        "cycles": int(result.get("cycles", 0) or 0),
        "minimum_cycles": 10,
        "unloaded_frame_verified": bool(result.get("unloaded_frame_verified", False)),
        "source_frame_identified": bool(result.get("source_frame_identified", False)),
        "postprocess": persisted_result,
    })
    provenance = result.get("provenance") or {}
    payload["_external_evidence"] = {
        "method": methods.METHOD_A,
        "kind": ("FVA600_OPENING_VOLUME_ODB" if result.get("extractor_version")
                 else "FVA600_OPENING_VOLUME_CSV"),
        "source_path": provenance.get("path"),
        "source_size_bytes": provenance.get("size_bytes"),
        "source_sha256": provenance.get("sha256"),
        "source_hash_verified_at_attach": True,
        "invariants_sha256": result.get("invariants_sha256"),
        "coverage_within_2_percent": True,
        "model_builder_did_not_solve": True,
    }
    return payload


def write_result_json(path, result):
    """Write a postprocess result atomically as UTF-8 JSON."""
    absolute = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    parent = os.path.dirname(absolute)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    temporary = absolute + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    os.replace(temporary, absolute)
    return absolute


def read_result_json(path):
    absolute = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    with open(absolute, "r", encoding="utf-8") as stream:
        result = json.load(stream)
    _validate_evidence_result(result, require_source=False)
    return result


def verify_source_provenance(result):
    """Recheck that the external CSV still matches persisted size and SHA-256."""
    provenance = (result or {}).get("provenance") or {}
    path = provenance.get("path")
    if not path or not os.path.isfile(path):
        return {"verified": False, "reason": "SOURCE_MISSING", "path": path}
    actual_size = os.path.getsize(path)
    actual_hash = _sha256(path)
    size_matches = actual_size == int(provenance.get("size_bytes", -1))
    hash_matches = actual_hash == provenance.get("sha256")
    related = {}
    related_verified = True
    for prefix in ("odb", "setup"):
        related_path = provenance.get(prefix + "_path")
        declared_hash = provenance.get(prefix + "_sha256")
        declared_size = provenance.get(prefix + "_size_bytes")
        if related_path or declared_hash or declared_size is not None:
            exists = bool(related_path and os.path.isfile(related_path))
            related_size = os.path.getsize(related_path) if exists else None
            related_hash = _sha256(related_path) if exists else None
            item_verified = bool(
                exists and declared_size is not None and
                _valid_sha256(declared_hash) and
                related_hash == declared_hash and
                related_size == int(declared_size))
            related[prefix] = {
                "path": related_path, "exists": exists,
                "size_matches": (related_size == int(declared_size)
                                 if exists and declared_size is not None else False),
                "sha256_matches": related_hash == declared_hash,
                "actual_size_bytes": related_size,
                "actual_sha256": related_hash,
                "verified": item_verified}
            related_verified = related_verified and item_verified
    verified = size_matches and hash_matches and related_verified
    return {
        "verified": verified,
        "reason": "MATCH" if verified else "SOURCE_CHANGED",
        "path": os.path.abspath(path),
        "size_matches": size_matches,
        "sha256_matches": hash_matches,
        "actual_size_bytes": actual_size,
        "actual_sha256": actual_hash,
        "related_sources": related,
    }
