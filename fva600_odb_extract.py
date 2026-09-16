# -*- coding: utf-8 -*-
"""Extract permanent keyway opening from a solved Method-A ODB.

Pure helpers are Python 2.7/3 compatible; ``odbAccess`` is imported only by the
entry function.  The exporter pairs the matching left/right shaft-keyway nodes
by their undeformed (depth, axial) coordinates and computes
``opening = U_right_x - U_left_x`` in the final unloaded frame.  It writes the
canonical ``x_mm,z_mm,opening_um`` grid consumed by ``fva600_postprocess.py``.
"""
from __future__ import print_function, division

import csv
import hashlib
import json
import math
import os
import sys

import din6892_methods as methods

EXTRACTOR_VERSION = "fva600-odb-opening-2.0"
POSTPROCESSOR_VERSION = "fva600-csv-1.0"
EVIDENCE_CONTRACT_VERSION = 2
COVERAGE_TOLERANCE = 0.02
LEFT_SET = "FVA_SET_SHAFT_KEYWAY_LEFT"
RIGHT_SET = "FVA_SET_SHAFT_KEYWAY_RIGHT"


class OdbExtractionError(ValueError):
    pass


def _finite(value, name):
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise OdbExtractionError("%s must be finite" % name)
    return number


def _sha256(path):
    digest = hashlib.sha256()
    stream = open(path, "rb")
    try:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    finally:
        stream.close()
    return digest.hexdigest()


def _sha256_json(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if not isinstance(payload, bytes):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_setup(path):
    if not path:
        return None
    absolute = os.path.abspath(path)
    if not os.path.isfile(absolute):
        raise OdbExtractionError("Method-A setup JSON does not exist: %s" % absolute)
    stream = open(absolute, "r")
    try:
        setup = json.load(stream)
    finally:
        stream.close()
    if int(setup.get("setup_schema_version", -1)) < 2:
        raise OdbExtractionError("Method-A setup schema is stale")
    grid = setup.get("opening_grid") or {}
    if (grid.get("status") != "PASS" or
            grid.get("rectangular_product") is not True or
            grid.get("bounds_passed") is not True or
            grid.get("coverage", {}).get("within_2_percent") is not True):
        raise OdbExtractionError("Method-A setup opening-grid evidence is incomplete")
    if grid.get("pairs_sha256") != _sha256_json(grid.get("pairs") or []):
        raise OdbExtractionError("Method-A setup pair hash is invalid")
    invariants = grid.get("invariants") or {}
    if grid.get("invariants_sha256") != _sha256_json(invariants):
        raise OdbExtractionError("Method-A setup invariant hash is invalid")
    setup["_absolute_path"] = absolute
    setup["_sha256"] = _sha256(absolute)
    setup["_size_bytes"] = os.path.getsize(absolute)
    return setup


def _flatten_nodes(value):
    result = []
    if value is None:
        return result
    for item in value:
        if hasattr(item, "label") and hasattr(item, "coordinates"):
            result.append(item)
        else:
            try:
                result.extend(_flatten_nodes(item))
            except TypeError:
                pass
    return result


def _coordinate_key(node, tolerance):
    coordinates = node.coordinates
    return (int(round(float(coordinates[1]) / tolerance)),
            int(round(float(coordinates[2]) / tolerance)))


def _node_map(node_set, tolerance, set_name):
    mapping = {}
    for node in _flatten_nodes(node_set.nodes):
        key = _coordinate_key(node, tolerance)
        if key in mapping:
            raise OdbExtractionError(
                "%s has duplicate depth/axial coordinate %r" % (set_name, key))
        mapping[key] = node
    if not mapping:
        raise OdbExtractionError("ODB node set %s is empty" % set_name)
    return mapping


def _displacement_map(field, node_set):
    values = field.getSubset(region=node_set).values
    result = {}
    for value in values:
        data = value.data
        result[int(value.nodeLabel)] = tuple(float(component)
                                             for component in data[:3])
    if not result:
        raise OdbExtractionError("No U values found for node set %s" %
                                 node_set.name)
    return result


def pair_opening_rows(left_set, right_set, displacement_field,
                      tolerance_mm=1.0e-6, clamp_negative=True,
                      grid_evidence=None):
    tolerance = _finite(tolerance_mm, "tolerance_mm")
    if tolerance <= 0.0:
        raise OdbExtractionError("tolerance_mm must be positive")
    left = _node_map(left_set, tolerance, left_set.name)
    right = _node_map(right_set, tolerance, right_set.name)
    if set(left) != set(right):
        missing_right = sorted(set(left) - set(right))
        missing_left = sorted(set(right) - set(left))
        raise OdbExtractionError(
            "Opening node sets do not match; missing right=%d, missing left=%d" %
            (len(missing_right), len(missing_left)))
    setup_grid_verified = False
    transform = None
    if grid_evidence is not None:
        expected_left = sorted(int(value) for value in
                               grid_evidence.get("left_labels") or [])
        expected_right = sorted(int(value) for value in
                                grid_evidence.get("right_labels") or [])
        actual_left = sorted(int(node.label) for node in left.values())
        actual_right = sorted(int(node.label) for node in right.values())
        if actual_left != expected_left or actual_right != expected_right:
            raise OdbExtractionError(
                "ODB opening sets do not match persisted setup labels")
        if int(grid_evidence.get("selected_pair_count", -1)) != len(left):
            raise OdbExtractionError(
                "ODB opening pair count differs from persisted setup")
        transform = grid_evidence.get("coordinate_transform") or {}
        if not transform.get("x_from_global_z") or not transform.get(
                "z_from_global_y"):
            raise OdbExtractionError("Setup coordinate transform is missing")
        setup_grid_verified = True
    left_u = _displacement_map(displacement_field, left_set)
    right_u = _displacement_map(displacement_field, right_set)
    y0 = min(float(node.coordinates[1]) for node in left.values())
    z0 = min(float(node.coordinates[2]) for node in left.values())
    rows = []
    negative_count = 0
    for key in sorted(left):
        left_node = left[key]
        right_node = right[key]
        if int(left_node.label) not in left_u or int(right_node.label) not in right_u:
            raise OdbExtractionError("A paired node lacks displacement output")
        opening_mm = (right_u[int(right_node.label)][0] -
                      left_u[int(left_node.label)][0])
        if opening_mm < 0.0:
            negative_count += 1
            if clamp_negative:
                opening_mm = 0.0
        if transform is None:
            x_value = float(left_node.coordinates[2]) - z0
            z_value = float(left_node.coordinates[1]) - y0
        else:
            x_rule = transform["x_from_global_z"]
            z_rule = transform["z_from_global_y"]
            x_value = ((float(left_node.coordinates[2]) -
                       float(x_rule["origin_mm"])) *
                       float(x_rule["scale"]))
            z_value = ((float(left_node.coordinates[1]) -
                       float(z_rule["origin_mm"])) *
                       float(z_rule["scale"]))
        rows.append({
            "x_mm": x_value,
            "z_mm": z_value,
            "opening_um": opening_mm * 1000.0,
            "left_label": int(left_node.label),
            "right_label": int(right_node.label),
        })
    return rows, {"paired_nodes": len(rows),
                  "setup_grid_revalidated": setup_grid_verified,
                  "negative_opening_count": negative_count,
                  "negative_policy": "CLAMP_TO_ZERO" if clamp_negative else "KEEP"}


def integrate_opening_rows(rows):
    """Integrate a rectangular nodal grid by cell-wise 2D trapezoids."""
    xs = sorted(set(float(row["x_mm"]) for row in rows))
    zs = sorted(set(float(row["z_mm"]) for row in rows))
    if len(xs) < 2 or len(zs) < 2:
        raise OdbExtractionError("Opening grid needs at least 2 x 2 coordinates")
    values = {}
    for row in rows:
        key = (float(row["x_mm"]), float(row["z_mm"]))
        if key in values:
            raise OdbExtractionError("Duplicate opening coordinate %r" % (key,))
        values[key] = float(row["opening_um"]) / 1000.0
    expected = len(xs) * len(zs)
    if len(values) != expected:
        raise OdbExtractionError(
            "Opening nodes are not a rectangular grid: %d supplied, %d required" %
            (len(values), expected))
    total = 0.0
    for ix in range(len(xs) - 1):
        x0, x1 = xs[ix], xs[ix + 1]
        for iz in range(len(zs) - 1):
            z0, z1 = zs[iz], zs[iz + 1]
            mean = 0.25 * (values[(x0, z0)] + values[(x1, z0)] +
                           values[(x0, z1)] + values[(x1, z1)])
            total += mean * (x1 - x0) * (z1 - z0)
    openings = [float(row["opening_um"]) for row in rows]
    x_span = xs[-1] - xs[0]
    z_span = zs[-1] - zs[0]
    return {"delta_volume_mm3": total,
            "integration": "2D_TRAPEZOID_CELL_CORNER_AVERAGE",
            "equation": 18,
            "point_count": len(values),
            "cell_count": (len(xs) - 1) * (len(zs) - 1),
            "x_count": len(xs), "z_count": len(zs),
            "x_bounds_mm": [xs[0], xs[-1]],
            "z_bounds_mm": [zs[0], zs[-1]],
            "x_span_mm": x_span, "z_span_mm": z_span,
            "grid_area_mm2": x_span * z_span,
            "opening_bounds_um": [min(openings), max(openings)]}


def _write_csv(path, rows):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    if sys.version_info[0] < 3:
        stream = open(path, "wb")
        kwargs = {}
    else:
        stream = open(path, "w", newline="", encoding="utf-8")
        kwargs = {}
    try:
        writer = csv.writer(stream, **kwargs)
        writer.writerow(("x_mm", "z_mm", "opening_um"))
        for row in rows:
            writer.writerow(("%.12g" % row["x_mm"],
                             "%.12g" % row["z_mm"],
                             "%.12g" % row["opening_um"]))
    finally:
        stream.close()
    return os.path.abspath(path)


def _write_json(path, payload):
    absolute = os.path.abspath(path)
    parent = os.path.dirname(absolute)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    stream = open(absolute, "w")
    try:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    finally:
        stream.close()
    return os.path.abspath(path)


def _coverage(integration, ltr_mm, t1tr_mm):
    ltr = float(ltr_mm)
    t1tr = float(t1tr_mm)
    expected_area = ltr * t1tr
    x_ratio = integration["x_span_mm"] / ltr if ltr > 0.0 else None
    z_ratio = integration["z_span_mm"] / t1tr if t1tr > 0.0 else None
    area_ratio = (integration["grid_area_mm2"] / expected_area
                  if expected_area > 0.0 else None)
    xb = integration["x_bounds_mm"]
    zb = integration["z_bounds_mm"]
    x_bounds_ok = bool(
        ltr > 0.0 and abs(xb[0]) <= COVERAGE_TOLERANCE * ltr and
        abs(xb[1] - ltr) <= COVERAGE_TOLERANCE * ltr)
    z_bounds_ok = bool(
        t1tr > 0.0 and abs(zb[0]) <= COVERAGE_TOLERANCE * t1tr and
        abs(zb[1] - t1tr) <= COVERAGE_TOLERANCE * t1tr)
    passed = bool(
        area_ratio is not None and x_ratio is not None and z_ratio is not None and
        abs(area_ratio - 1.0) <= COVERAGE_TOLERANCE and
        abs(x_ratio - 1.0) <= COVERAGE_TOLERANCE and
        abs(z_ratio - 1.0) <= COVERAGE_TOLERANCE and
        x_bounds_ok and z_bounds_ok)
    return {
        "tolerance_fraction": COVERAGE_TOLERANCE,
        "expected_x_bounds_mm": [0.0, ltr],
        "expected_z_bounds_mm": [0.0, t1tr],
        "expected_area_mm2": expected_area,
        "grid_area_mm2": integration["grid_area_mm2"],
        "x_span_over_ltr": x_ratio,
        "z_span_over_t1tr": z_ratio,
        "grid_over_expected": area_ratio,
        "x_bounds_within_2_percent": x_bounds_ok,
        "z_bounds_within_2_percent": z_bounds_ok,
        "within_2_percent": passed,
    }


def _rm3_unloaded_check(step, frame_time):
    candidates = []
    for region_name, region in step.historyRegions.items():
        for output_name, output in region.historyOutputs.items():
            if str(output_name).upper() != "RM3":
                continue
            data = [(float(item[0]), float(item[1])) for item in output.data]
            if not data:
                continue
            nearest = min(data, key=lambda item: abs(item[0] - frame_time))
            peak = max(abs(item[1]) for item in data)
            tolerance = max(1.0e-6, peak * 1.0e-4)
            candidates.append({
                "history_region": region_name,
                "output": output_name,
                "sample_time": nearest[0],
                "sample_value_Nmm": nearest[1],
                "peak_abs_Nmm": peak,
                "tolerance_Nmm": tolerance,
                "time_matches": abs(nearest[0] - frame_time) <=
                                max(1.0e-8, abs(frame_time) * 1.0e-8),
                "near_zero": abs(nearest[1]) <= tolerance})
    if not candidates:
        return {"verified": False, "reason": "RM3_HISTORY_MISSING",
                "candidates": []}
    passed = any(item["time_matches"] and item["near_zero"]
                 for item in candidates)
    return {"verified": passed,
            "reason": "RM3_NEAR_ZERO" if passed else "RM3_NOT_UNLOADED",
            "candidates": candidates}


def extract_and_assess(odb_path, out_csv, ltr_mm, t1tr_mm, UPF_um,
                       v_crit=0.5, cycles=20, step_name="FVA_METHOD_A_CYCLES",
                       frame_index=-1, tolerance_mm=1.0e-6,
                       expected_last_time=None, out_json=None,
                       unloaded_frame_confirmed=False, clamp_negative=True,
                       setup_path=None, cycle_period_s=None):
    """Open an ODB read-only and assess the final unloaded >=10-cycle frame.

    Conclusive evidence requires the persisted build setup, its rectangular
    node-grid labels/transform, the actual final frame at an integer cycle
    boundary, near-zero RM3 history, and an explicit independent confirmation.
    """
    setup = _load_setup(setup_path)
    grid_evidence = (setup or {}).get("opening_grid")
    invariants = {"ltr_mm": float(ltr_mm),
                  "t1tr_mm": float(t1tr_mm),
                  "UPF_um": float(UPF_um)}
    setup_verified = False
    physics = (setup or {}).get("physics") or {}
    if setup is not None:
        setup_invariants = grid_evidence.get("invariants") or {}
        for name, value in invariants.items():
            if name not in setup_invariants or abs(
                    float(setup_invariants[name]) - value) > 1.0e-9:
                raise OdbExtractionError(
                    "Extractor %s differs from persisted setup invariant" % name)
        configured_cycles = int(physics.get("cycles", cycles) or 0)
        if int(cycles) != configured_cycles:
            raise OdbExtractionError(
                "Extractor cycles differ from persisted setup cycles")
        if cycle_period_s is None:
            cycle_period_s = physics.get("cycle_period_s")
        if expected_last_time is None:
            expected_last_time = physics.get("cycle_time_s")
        setup_verified = True
    try:
        from odbAccess import openOdb
    except ImportError:
        raise OdbExtractionError("odbAccess is required; run inside Abaqus Python")
    absolute = os.path.abspath(odb_path)
    if not os.path.isfile(absolute):
        raise OdbExtractionError("ODB does not exist: %s" % absolute)
    odb = openOdb(path=absolute, readOnly=True)
    try:
        if step_name not in odb.steps:
            raise OdbExtractionError("ODB step %s does not exist" % step_name)
        step = odb.steps[step_name]
        if not step.frames:
            raise OdbExtractionError("ODB step %s has no frames" % step_name)
        selected_index = int(frame_index)
        if selected_index < 0:
            selected_index = len(step.frames) + selected_index
        if selected_index < 0 or selected_index >= len(step.frames):
            raise OdbExtractionError("frame_index is outside the selected step")
        frame = step.frames[selected_index]
        if "U" not in frame.fieldOutputs:
            raise OdbExtractionError("Selected frame has no U field output")
        root = odb.rootAssembly
        if LEFT_SET not in root.nodeSets or RIGHT_SET not in root.nodeSets:
            raise OdbExtractionError(
                "ODB lacks required opening sets %s/%s" % (LEFT_SET, RIGHT_SET))
        rows, pairing = pair_opening_rows(
            root.nodeSets[LEFT_SET], root.nodeSets[RIGHT_SET],
            frame.fieldOutputs["U"], tolerance_mm,
            clamp_negative=bool(clamp_negative),
            grid_evidence=grid_evidence)
        integration = integrate_opening_rows(rows)
        coverage = _coverage(integration, ltr_mm, t1tr_mm)
        volume = methods.relative_opening_volume(
            integration["delta_volume_mm3"], ltr_mm, t1tr_mm,
            UPF_um, v_crit)
        frame_time = float(frame.frameValue)
        frame_is_last = selected_index == len(step.frames) - 1
        time_verified = (
            expected_last_time is not None and
            abs(frame_time - float(expected_last_time)) <=
            max(1.0e-8, abs(float(expected_last_time)) * 1.0e-8))
        period = float(cycle_period_s or 0.0)
        cycles_completed = frame_time / period if period > 0.0 else None
        integer_cycle = (int(round(cycles_completed))
                         if cycles_completed is not None else None)
        cycle_boundary_verified = bool(
            cycles_completed is not None and
            abs(cycles_completed - integer_cycle) <= 1.0e-8)
        minimum_cycles_verified = bool(
            cycle_boundary_verified and integer_cycle >= 10 and
            integer_cycle >= int(cycles))
        rm3_check = _rm3_unloaded_check(step, frame_time)
        unloaded_verified = bool(
            unloaded_frame_confirmed and frame_is_last and time_verified and
            cycle_boundary_verified and rm3_check.get("verified"))
        csv_path = _write_csv(out_csv, rows)
        csv_hash = _sha256(csv_path)
        odb_hash = _sha256(absolute)
        evidence_complete = bool(
            setup_verified and pairing.get("setup_grid_revalidated") and
            coverage.get("within_2_percent") and
            minimum_cycles_verified and unloaded_verified)
        warnings = []
        if not setup_verified:
            warnings.append("Persisted FVA_METHOD_A_SETUP.json is required")
        if not coverage.get("within_2_percent"):
            warnings.append("Opening grid fails the mandatory 2 percent coverage gate")
        if not minimum_cycles_verified:
            warnings.append("Selected frame is not an unloaded boundary after >=10 cycles")
        if not rm3_check.get("verified"):
            warnings.append("RM3 history does not verify a near-zero unloaded frame")
        provenance = {
            "kind": "solved_odb_selected_frame",
            "path": csv_path, "sha256": csv_hash,
            "size_bytes": os.path.getsize(csv_path),
            "headers": ["x_mm", "z_mm", "opening_um"],
            "odb_path": absolute, "odb_sha256": odb_hash,
            "odb_size_bytes": os.path.getsize(absolute),
            "odb_open_mode": "READ_ONLY",
            "source_step": step_name,
            "source_frame": "index=%d,time=%.12g" %
                            (selected_index, frame_time),
            "source_frame_index": selected_index,
            "source_frame_value": frame_time,
            "opening_csv": csv_path,
            "opening_csv_sha256": csv_hash,
            "model_builder_did_not_solve": True}
        if setup is not None:
            provenance.update({
                "setup_path": setup["_absolute_path"],
                "setup_sha256": setup["_sha256"],
                "setup_size_bytes": setup["_size_bytes"]})
        result = {
            "result_schema_version": 1,
            "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
            "postprocessor_version": POSTPROCESSOR_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "badge": methods.BADGE_FVA_RESEARCH,
            "source_id": methods.SOURCE_FVA,
            "provenance": provenance,
            "invariants": invariants,
            "invariants_sha256": _sha256_json(invariants),
            "frame_selection": {
                "selected_frame_index": selected_index,
                "is_last_frame": frame_is_last,
                "expected_last_time": expected_last_time,
                "expected_time_verified": time_verified,
                "cycle_period_s": period,
                "cycles_completed": cycles_completed,
                "integer_cycle_boundary_verified": cycle_boundary_verified,
                "rm3_unloaded": rm3_check,
                "unloaded_frame_explicitly_confirmed": bool(
                    unloaded_frame_confirmed)},
            "setup_grid_verified": setup_verified,
            "pairing": pairing, "integration": integration,
            "coverage": coverage, "volume": volume,
            "cycles": int(cycles),
            "minimum_cycles_verified": minimum_cycles_verified,
            "source_frame_identified": True,
            "unloaded_frame_verified": unloaded_verified,
            "method_a_evidence_complete": evidence_complete,
            "criterion_met": (volume["criterion_met"]
                              if evidence_complete else None),
            "warnings": warnings,
        }
        if out_json:
            result["result_json"] = os.path.abspath(out_json)
            _write_json(result["result_json"], result)
        return result
    finally:
        odb.close()
