# -*- coding: utf-8 -*-
"""Connected DIN 6892 Method-A Abaqus backend for FVA 600 III.

The module is intentionally importable by Python 2.7 and Python 3.  Abaqus
imports stay inside functions so normal-Python schema/self tests can compile
and inspect it.  It reuses ``build_parametric_model`` for the reviewed
parametric solids, then applies a dedicated matching-mesh pass, constitutive
laws, finite-sliding contacts and the cyclic loading history.

A mesh is reported as MATCHED only after actual assembly-node coordinates have
been compared on every configured load-carrying interface.  Nominally equal
seed sizes are never accepted as proof by themselves.
"""
from __future__ import print_function, division

import hashlib
import json
import math
import os
import time

import din6892_methods as methods

BACKEND = methods.BACKEND_METHOD_A_CONNECTED
BACKEND_HYBRID_HEX = methods.BACKEND_METHOD_A_HYBRID_HEX
BACKENDS = (BACKEND, BACKEND_HYBRID_HEX)
SETUP_VERSIONS = {
    BACKEND: "fva600-method-a-connected-2.0",
    BACKEND_HYBRID_HEX: "fva600-method-a-hybrid-hex-2.0",
}
SETUP_VERSION = SETUP_VERSIONS[BACKEND]
ABSOLUTE_INTERFACE_EDGE_LIMIT_MM = 1.0
REQUIRED_MATCHING_INTERFACES = (
    "SHAFT_KEY_LEFT", "SHAFT_KEY_RIGHT", "HUB_KEY_LEFT",
    "HUB_KEY_RIGHT", "SHAFT_HUB")
STEP_FIT = "FVA_FIT"
STEP_FRICTION = "FVA_SERVICE_FRICTION"
STEP_CYCLES = "FVA_METHOD_A_CYCLES"
PROP_FIT = "FVA_CONTACT_FIT"
PROP_SERVICE = "FVA_CONTACT_SERVICE"
AMP_FIT_RAMP = "FVA_INTERFERENCE_RAMP"
AMP_FIT_HOLD = "FVA_INTERFERENCE_HOLD"
AMP_TORQUE = "FVA_TORQUE_CYCLES"


def _fva(params):
    return params.get("fva_600_iii", {}) or {}


def _ensure_dir(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)
    return path


def _guard_nojob(mdb, stage):
    jobs = tuple(sorted(str(name) for name in mdb.jobs.keys()))
    if jobs:
        raise RuntimeError("strict NOJOB guard failed %s; mdb.jobs=%r" %
                           (stage, jobs))


def _face_point(face):
    points = getattr(face, "pointOn", None)
    if points:
        return tuple(float(value) for value in points[0][:3])
    centroid = face.getCentroid()
    return tuple(float(value) for value in centroid[:3])


def _node_point(node):
    return tuple(float(value) for value in node.coordinates[:3])


def _select_faces(instance, predicate, label):
    selected = instance.faces[0:0]
    for face in instance.faces:
        if predicate(_face_point(face)):
            selected = selected + instance.faces[face.index:face.index + 1]
    if not len(selected):
        raise RuntimeError("No faces selected for %s" % label)
    return selected


def _replace_surface(assembly, name, faces):
    if name in assembly.surfaces:
        del assembly.surfaces[name]
    assembly.Surface(name=name, side1Faces=faces)
    return assembly.surfaces[name]


def _replace_set(assembly, name, **kwargs):
    if name in assembly.sets:
        del assembly.sets[name]
    assembly.Set(name=name, **kwargs)
    return assembly.sets[name]


def _replace_node_label_set(assembly, name, nodes):
    """Create an assembly node set from one or more instance node sequences."""
    if name in assembly.sets:
        del assembly.sets[name]
    grouped = {}
    for node in nodes:
        instance_name = str(getattr(node, "instanceName", "") or "")
        if not instance_name:
            raise RuntimeError("Opening node lacks assembly instanceName")
        grouped.setdefault(instance_name, []).append(int(node.label))
    labels = tuple((instance_name, tuple(sorted(set(grouped[instance_name]))))
                   for instance_name in sorted(grouped))
    assembly.SetFromNodeLabels(name=name, nodeLabels=labels)
    return assembly.sets[name]


def _edge_size(edge):
    try:
        return float(edge.getSize(printResults=False))
    except Exception:
        return float(edge.getSize())


def _matching_levels(d):
    radius = float(d["R"])
    shaft_half_width = float(d["x_slot"])
    hub_half_width = 0.5 * float(d["groove_w"])
    shaft_open = math.sqrt(max(0.0, radius * radius -
                               shaft_half_width * shaft_half_width))
    hub_open = math.sqrt(max(0.0, radius * radius -
                             hub_half_width * hub_half_width))
    y_min = float(d["y_min"])
    chamfer = float(d["c"])
    shaft_low = max(y_min + chamfer, float(d["yF"]) + float(d["r2"]))
    shaft_high = shaft_open
    hub_low = max(hub_open, y_min + chamfer)
    hub_high = min(y_min + float(d["h"]) - chamfer,
                   float(d["groove_roof"]) - float(d["r1"]))
    if shaft_high <= shaft_low:
        raise RuntimeError("No planar shaft/key matching height remains")
    if hub_high <= hub_low:
        raise RuntimeError("No planar hub/key matching height remains")
    return {
        "z_low": float(d["c1"]), "z_high": float(d["c2"]),
        "shaft_low": shaft_low, "shaft_high": shaft_high,
        "hub_low": hub_low, "hub_high": hub_high,
        "shaft_open": shaft_open, "hub_open": hub_open,
    }


def _face_bbox(owner, face):
    box = owner.faces[face.index:face.index + 1].getBoundingBox()
    return (tuple(float(value) for value in box["low"][:3]),
            tuple(float(value) for value in box["high"][:3]))


def _radial_face_predicate(radius, tolerance=1.0e-4):
    def _predicate(face):
        point = _face_point(face)
        return abs(math.hypot(point[0], point[1]) - radius) <= tolerance
    return _predicate


def _flank_face_predicate(half_width, tolerance=1.0e-4):
    def _predicate(face):
        return abs(abs(_face_point(face)[0]) - half_width) <= tolerance
    return _predicate


def _partition_faces_at(part, base, axis, offset, predicate,
                        tolerance=1.0e-7):
    """Partition selected boundary faces without slicing their owner cells.

    Cell-wide datum cuts polluted the cylindrical contact with unrelated keyway
    seams and made every edge constraint incompatible.  Face-only partitions
    preserve a coarse, tetra-meshable volume while exposing congruent contact
    patches for ``copyMeshPattern``.
    """
    index = base.AX[axis][1]
    selected = []
    for face in part.faces:
        low, high = _face_bbox(part, face)
        if (low[index] < float(offset) - tolerance and
                high[index] > float(offset) + tolerance and predicate(face)):
            selected.append(face)
    if not selected:
        return 0
    datum = part.datums[part.DatumPlaneByPrincipalPlane(
        principalPlane=base.AX[axis][0], offset=float(offset)).id]
    part.PartitionFaceByDatumPlane(faces=tuple(selected), datumPlane=datum)
    return len(selected)


def prepare_matching_partitions(model, d, base):
    """Create congruent surface patches for copied interface meshes.

    The shaft/hub radial contact uses the hub opening as its common boundary.
    The physical 0.01075 mm radial-face strip caused by the configured hub
    groove clearance remains geometry, but is not falsely labelled as a
    shaft/hub contact patch.  The flank hand-off is the natural hub opening;
    this avoids a 0.0034 mm overlapping shaft/hub/key sliver.
    """
    levels = _matching_levels(d)
    levels["z_mid"] = float(d["z_mid"])
    levels["flank_transition"] = float(levels["hub_low"])
    levels["common_half_width"] = 0.5 * float(d["groove_w"])
    levels["excluded_shaft_flank_height_mm"] = max(
        0.0, float(levels["shaft_high"]) -
        float(levels["flank_transition"]))

    shaft = model.parts["Shaft"]
    key = model.parts["Key"]
    hub = model.parts["Hub"]
    for part in (shaft, key, hub):
        try:
            part.deleteMesh()
        except Exception:
            pass

    radius = float(d["R"])
    radial_shaft = _radial_face_predicate(radius)
    radial_hub = _radial_face_predicate(radius)
    flank_shaft = _flank_face_predicate(float(d["x_slot"]))
    flank_hub = _flank_face_predicate(0.5 * float(d["groove_w"]))
    flank_key = _flank_face_predicate(0.5 * float(d["b"]))
    details = []

    def cut(part_name, part, axis, offset, predicate, label):
        count = _partition_faces_at(part, base, axis, offset, predicate)
        details.append({"part": part_name, "axis": axis,
                        "offset": float(offset), "faces": int(count),
                        "label": label})
        return count

    # Shaft OD and keyway flanks: c1/c2 are natural flank boundaries but not OD
    # boundaries; all calls are harmless no-ops when a boundary already exists.
    for value in (levels["z_low"], levels["z_high"]):
        cut("Shaft", shaft, "z", value, radial_shaft, "shaft_hub_axial")
        cut("Shaft", shaft, "z", value, flank_shaft, "shaft_key_axial")
    for value in (-levels["common_half_width"],
                  levels["common_half_width"]):
        cut("Shaft", shaft, "x", value,
            lambda face, pred=radial_shaft: (pred(face) and
                                             _face_point(face)[1] > 0.0),
            "hub_opening_on_shaft_od")
    for value in (levels["shaft_low"], levels["flank_transition"]):
        cut("Shaft", shaft, "y", value, flank_shaft,
            "shaft_key_height")

    # Hub occupies exactly c1..c2 after assembly translation.  Its extrusion
    # ends are the axial contact bounds; only the upper load-carrying flank
    # boundary needs an explicit surface partition.
    cut("Hub", hub, "y", levels["hub_high"], flank_hub,
        "hub_key_height")

    # Key local z becomes global y after the -90 degree assembly rotation.  The
    # Method-A geometry deliberately keeps the axial flank unsplit so one copied
    # template covers the complete c1..c2 prism.
    key_transition = levels["flank_transition"] - float(d["y_min"])
    cut("Key", key, "z", key_transition, flank_key,
        "shaft_key_to_hub_key_handoff")

    model.rootAssembly.regenerate()
    counts = {}
    for part_name in ("Shaft", "Key", "Hub"):
        counts[part_name] = sum(item["faces"] for item in details
                                if item["part"] == part_name)
    return {"counts": counts, "details": details, "levels": levels,
            "strategy": "CONGRUENT_FACE_PARTITIONS_FOR_COPIED_MESH"}


def _select_planar_faces(owner, x_value, y_low, y_high, z_low, z_high,
                         tolerance=1.0e-5):
    selected = owner.faces[0:0]
    for face in owner.faces:
        low, high = _face_bbox(owner, face)
        if (abs(low[0] - x_value) <= tolerance and
                abs(high[0] - x_value) <= tolerance and
                low[1] >= y_low - tolerance and
                high[1] <= y_high + tolerance and
                low[2] >= z_low - tolerance and
                high[2] <= z_high + tolerance):
            selected = selected + owner.faces[face.index:face.index + 1]
    return selected


def _select_radial_faces(owner, radius, z_low, z_high,
                         tolerance=1.0e-4):
    selected = owner.faces[0:0]
    for face in owner.faces:
        point = _face_point(face)
        low, high = _face_bbox(owner, face)
        if (abs(math.hypot(point[0], point[1]) - radius) <= tolerance and
                low[2] >= z_low - tolerance and
                high[2] <= z_high + tolerance):
            selected = selected + owner.faces[face.index:face.index + 1]
    return selected


def _face_signature(owner, face, kind):
    low, high = _face_bbox(owner, face)
    if kind == "PLANAR_YZ":
        values = (low[1], high[1], low[2], high[2])
    elif kind == "RADIAL_XYZ":
        values = (low[0], high[0], low[1], high[1], low[2], high[2])
    else:
        raise ValueError("Unknown face signature kind %r" % kind)
    # Abaqus/ACIS stores native geometry in single-precision-sized buckets at
    # this scale; 1e-5 mm keys identify topology, while the later node-cloud
    # check reports the actual unrounded coordinate delta.
    return tuple(round(float(value), 5) for value in values)


def _face_map(owner, faces, kind):
    result = {}
    for face in faces:
        signature = _face_signature(owner, face, kind)
        if signature in result:
            raise RuntimeError("Duplicate %s face signature %r" %
                               (kind, signature))
        result[signature] = face
    return result


def _pair_faces(source_owner, source_faces, target_owner, target_faces,
                kind, allow_target_extras=False):
    source = _face_map(source_owner, source_faces, kind)
    target = _face_map(target_owner, target_faces, kind)
    missing = sorted(set(source) - set(target))
    extras = sorted(set(target) - set(source))
    if missing or (extras and not allow_target_extras):
        raise RuntimeError("Interface face topology mismatch (%s): missing=%r "
                           "target_extras=%r" % (kind, missing, extras))
    return ([(signature, source[signature], target[signature])
             for signature in sorted(source)], extras)


def _interface_face_groups(assembly, d, levels):
    shaft = assembly.instances["SHAFT-1"]
    key = assembly.instances["KEY-1"]
    hub = assembly.instances["HUB-1"]
    z_low, z_high = levels["z_low"], levels["z_high"]
    transition = levels["flank_transition"]
    shaft_half = float(d["x_slot"])
    hub_half = 0.5 * float(d["groove_w"])
    key_half = 0.5 * float(d["b"])
    return {
        "SHAFT_KEY_LEFT": _select_planar_faces(
            shaft, -shaft_half, levels["shaft_low"], transition,
            z_low, z_high),
        "SHAFT_KEY_RIGHT": _select_planar_faces(
            shaft, shaft_half, levels["shaft_low"], transition,
            z_low, z_high),
        "KEY_SHAFT_LEFT": _select_planar_faces(
            key, -key_half, levels["shaft_low"], transition,
            z_low, z_high),
        "KEY_SHAFT_RIGHT": _select_planar_faces(
            key, key_half, levels["shaft_low"], transition,
            z_low, z_high),
        "HUB_KEY_LEFT": _select_planar_faces(
            hub, -hub_half, transition, levels["hub_high"],
            z_low, z_high),
        "HUB_KEY_RIGHT": _select_planar_faces(
            hub, hub_half, transition, levels["hub_high"],
            z_low, z_high),
        "KEY_HUB_LEFT": _select_planar_faces(
            key, -key_half, transition, levels["hub_high"],
            z_low, z_high),
        "KEY_HUB_RIGHT": _select_planar_faces(
            key, key_half, transition, levels["hub_high"],
            z_low, z_high),
        "HUB_SHAFT": _select_radial_faces(
            hub, float(d["R"]), z_low, z_high),
        "SHAFT_HUB_ALL": _select_radial_faces(
            shaft, float(d["R"]), z_low, z_high),
    }


def _seed_face_edges(owner, faces, size, AC, assembly=None):
    edge_indices = set()
    for face in faces:
        edge_indices.update(int(index) for index in face.getEdges())
    rows = {}
    for index in sorted(edge_indices):
        edge = owner.edges[index]
        length = _edge_size(edge)
        edges = owner.edges[index:index + 1]
        if assembly is None:
            owner.seedEdgeBySize(edges=edges, size=float(size),
                                 deviationFactor=0.1, constraint=AC.FINER)
        else:
            assembly.seedEdgeBySize(edges=edges, size=float(size),
                                    deviationFactor=0.1,
                                    constraint=AC.FINER)
        rows[int(index)] = {
            "length_mm": length, "requested_size_mm": float(size),
            "nominal_divisions": max(1, int(math.ceil(length / float(size))))}
    return rows


def _seed_fillet_arcs(owner, radius, number, AC, assembly=None):
    if radius <= 0.0 or number <= 0:
        return 0
    expected = math.pi * float(radius) / 2.0
    selected = []
    for edge in owner.edges:
        length = _edge_size(edge)
        if abs(length - expected) <= 0.02 * expected + 1.0e-6:
            selected.append(edge)
    if selected:
        if assembly is None:
            owner.seedEdgeByNumber(edges=tuple(selected), number=int(number),
                                   constraint=AC.FINER)
        else:
            assembly.seedEdgeByNumber(edges=tuple(selected), number=int(number),
                                      constraint=AC.FINER)
    return len(selected)


def _boundary_nodes(owner, face):
    nodes = {}
    for edge_index in face.getEdges():
        edge = owner.edges[int(edge_index)]
        for node in (edge.getNodes() or ()):
            nodes[int(node.label)] = node
    return [nodes[label] for label in sorted(nodes)]


def _three_non_collinear_nodes(nodes):
    if len(nodes) < 3:
        raise RuntimeError("Mesh-pattern source has fewer than three boundary nodes")
    first = min(nodes, key=lambda node: int(node.label))
    q0 = _node_point(first)
    second = max(nodes, key=lambda node: sum(
        (_node_point(node)[index] - q0[index]) ** 2 for index in range(3)))
    q1 = _node_point(second)
    vector1 = tuple(q1[index] - q0[index] for index in range(3))

    def area_squared(node):
        q2 = _node_point(node)
        vector2 = tuple(q2[index] - q0[index] for index in range(3))
        cross = (vector1[1] * vector2[2] - vector1[2] * vector2[1],
                 vector1[2] * vector2[0] - vector1[0] * vector2[2],
                 vector1[0] * vector2[1] - vector1[1] * vector2[0])
        return sum(value * value for value in cross)

    third = max(nodes, key=area_squared)
    if area_squared(third) <= 1.0e-20:
        raise RuntimeError("Mesh-pattern source anchors are collinear")
    return [first, second, third]


def _copy_face_pattern(assembly, source_owner, source_face, target_face,
                       sequence, target_x=None):
    anchors = _three_non_collinear_nodes(
        _boundary_nodes(source_owner, source_face))
    mapped = []
    for node in anchors:
        point = _node_point(node)
        target = point if target_x is None else (
            float(target_x), point[1], point[2])
        mapped.append((node, target))
    # Abaqus requires coordinates to correspond to ascending node labels.
    mapped.sort(key=lambda item: int(item[0].label))
    set_name = "__FVA_COPY_SOURCE_%04d" % int(sequence)
    source_set = assembly.Set(
        name=set_name,
        faces=source_owner.faces[source_face.index:source_face.index + 1])
    try:
        assembly.copyMeshPattern(
            faces=source_set, targetFace=target_face,
            nodes=tuple(item[0] for item in mapped),
            coordinates=tuple(item[1] for item in mapped))
    finally:
        if set_name in assembly.sets:
            del assembly.sets[set_name]


def _mesh_part_tet(part, bulk_size, surface_faces, surface_size,
                   tet_type, radius, arc_number, AC):
    started = time.time()
    part.deleteMesh()
    try:
        part.deleteSeeds(regions=part.edges)
    except Exception:
        pass
    part.setMeshControls(regions=part.cells, elemShape=AC.TET,
                         technique=AC.FREE)
    part.seedPart(size=float(bulk_size), deviationFactor=0.1,
                  minSizeFactor=0.1)
    edge_rows = _seed_face_edges(part, surface_faces, surface_size, AC)
    arc_edges = _seed_fillet_arcs(
        part, float(radius), int(arc_number), AC)
    part.setElementType(regions=(part.cells,), elemTypes=(tet_type,))
    part.generateMesh()
    if not len(part.nodes) or not len(part.elements):
        raise RuntimeError("Source hub tetrahedral mesh is empty")
    return {"bulk_size_mm": float(bulk_size),
            "surface_seed_mm": float(surface_size),
            "surface_edge_seeds": edge_rows,
            "fillet_arc_edges": int(arc_edges),
            "seconds": round(time.time() - started, 3)}


def _mesh_instance_tet(assembly, instance, name, bulk_size, surface_faces,
                       surface_size, tet_type, radius, arc_number, AC,
                       generate=True, topology="FREE_TET", element_types=None):
    """Prepare/fill an independent physical instance without losing copies.

    ``FREE_TET`` is the unchanged v1 route.  ``HYBRID_HEX`` is the v2 route:
    Abaqus receives free hex-dominated controls and the exact quadratic
    C3D20R/C3D15/C3D10 family before any surface pattern is copied.
    """
    started = time.time()
    topology = str(topology or "FREE_TET").upper()
    control_counts = {}
    control_errors = []
    if topology == "HYBRID_HEX":
        control_chain = (
            ("HEX_STRUCTURED", dict(
                elemShape=AC.HEX, technique=AC.STRUCTURED)),
            ("HEX_SWEEP_MEDIAL", dict(
                elemShape=AC.HEX, technique=AC.SWEEP,
                algorithm=AC.MEDIAL_AXIS)),
            ("HEX_SWEEP_ADVANCING", dict(
                elemShape=AC.HEX, technique=AC.SWEEP,
                algorithm=AC.ADVANCING_FRONT)),
            ("TET_TRANSITION", dict(
                elemShape=AC.TET, technique=AC.FREE)),
        )
        for cell in instance.cells:
            applied = None
            for label, kwargs in control_chain:
                try:
                    assembly.setMeshControls(regions=(cell,), **kwargs)
                    applied = label
                    control_counts[label] = control_counts.get(label, 0) + 1
                    break
                except Exception as exc:
                    control_errors.append({
                        "cell": int(cell.index), "control": label,
                        "error": str(exc)[:160]})
            if applied is None:
                raise RuntimeError(
                    "No hybrid mesh control could be assigned to %s cell %d" %
                    (name, int(cell.index)))
    elif topology == "FREE_TET":
        assembly.setMeshControls(regions=instance.cells, elemShape=AC.TET,
                                 technique=AC.FREE)
        control_counts["FREE_TET"] = len(instance.cells)
    else:
        raise ValueError("Unsupported Method-A physical topology %r" % topology)
    assembly.seedPartInstance(regions=(instance,), size=float(bulk_size),
                              deviationFactor=0.1, minSizeFactor=0.1)
    edge_rows = _seed_face_edges(
        instance, surface_faces, surface_size, AC, assembly=assembly)
    arc_edges = _seed_fillet_arcs(
        instance, float(radius), int(arc_number), AC, assembly=assembly)
    configured_types = tuple(element_types or (tet_type,))
    assembly.setElementType(
        regions=(instance.cells,), elemTypes=configured_types)
    if generate:
        assembly.generateMesh(regions=(instance,))
        if not len(instance.nodes) or not len(instance.elements):
            raise RuntimeError("Copied-interface mesh is empty for %s" % name)
    return {"bulk_size_mm": float(bulk_size),
            "surface_seed_mm": float(surface_size),
            "surface_edge_seeds": edge_rows,
            "fillet_arc_edges": int(arc_edges),
            "prepared_before_copy": not bool(generate),
            "topology": topology,
            "cell_controls": control_counts,
            "control_errors": control_errors,
            "configured_element_types": [str(getattr(item, "elemCode", item))
                                         for item in configured_types],
            "seconds": round(time.time() - started, 3)}


def _surface_pattern_state(faces):
    """Return a compact fingerprint plus real facet topology evidence."""
    nodes = {}
    element_faces = 0
    element_faces_available = True
    facet_node_histogram = {}
    quad_facets = 0
    tri_facets = 0
    other_facets = 0
    for face in faces:
        face_nodes = face.getNodes()
        if face_nodes is None:
            face_nodes = ()
        for node in face_nodes:
            nodes[int(node.label)] = node
        native_faces = face.getElementFaces()
        if native_faces is None:
            element_faces_available = False
        else:
            element_faces += len(native_faces)
            for native_face in native_faces:
                node_count = len(native_face.getNodes() or ())
                key = str(int(node_count))
                facet_node_histogram[key] = facet_node_histogram.get(key, 0) + 1
                if node_count in (4, 8, 9):
                    quad_facets += 1
                elif node_count in (3, 6):
                    tri_facets += 1
                else:
                    other_facets += 1
    points = [_node_point(nodes[label]) for label in sorted(nodes)]
    if points:
        low = [min(point[index] for point in points) for index in range(3)]
        high = [max(point[index] for point in points) for index in range(3)]
        coordinate_sum = [sum(point[index] for point in points)
                          for index in range(3)]
        coordinate_sum_sq = [sum(point[index] * point[index]
                                 for point in points)
                             for index in range(3)]
    else:
        low = high = coordinate_sum = coordinate_sum_sq = None
    facets_total = quad_facets + tri_facets + other_facets
    return {
        "nodes": len(points),
        "element_faces": (element_faces
                          if element_faces_available else None),
        "element_faces_available": element_faces_available,
        "facet_node_histogram": facet_node_histogram,
        "quad_facets": quad_facets,
        "tri_facets": tri_facets,
        "other_facets": other_facets,
        "structured_quadrilateral_pattern": bool(
            facets_total > 0 and quad_facets == facets_total),
        "bounds_mm": {"low": low, "high": high},
        "coordinate_sum_mm": coordinate_sum,
        "coordinate_sum_sq_mm2": coordinate_sum_sq,
    }


def _facet_corner_points(nodes):
    """Return Abaqus corner-node coordinates for tri/quad element faces."""
    points = [_node_point(node) for node in nodes]
    count = len(points)
    if count in (3, 6):
        return points[:3], "TRI"
    if count in (4, 8, 9):
        return points[:4], "QUAD"
    return points, "UNKNOWN"


def _surface_max_element_edge(faces):
    maximum = 0.0
    face_count = 0
    topology = {"TRI": 0, "QUAD": 0, "UNKNOWN": 0}
    for face in faces:
        native_faces = face.getElementFaces()
        if native_faces is None:
            raise RuntimeError(
                "Interface face %d has no native element faces; volume mesh "
                "generation did not preserve or complete its copied pattern" %
                int(face.index))
        for element_face in native_faces:
            corners, shape = _facet_corner_points(
                list(element_face.getNodes() or ()))
            topology[shape] = topology.get(shape, 0) + 1
            face_count += 1
            if shape == "TRI":
                edge_pairs = ((0, 1), (1, 2), (2, 0))
            elif shape == "QUAD":
                edge_pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
            else:
                edge_pairs = tuple((left, right)
                                   for left in range(len(corners))
                                   for right in range(left))
            for left, right in edge_pairs:
                distance = math.sqrt(sum(
                    (corners[left][index] - corners[right][index]) ** 2
                    for index in range(3)))
                maximum = max(maximum, distance)
    return maximum, face_count, topology


def _instance_metrics(assembly, instance, base, radius, mesh_info):
    analysis = assembly.verifyMeshQuality(
        criterion=__import__("abaqusConstants").ANALYSIS_CHECKS,
        regions=(instance,))
    aspect = assembly.verifyMeshQuality(
        criterion=__import__("abaqusConstants").ASPECT_RATIO,
        regions=(instance,))
    histogram = {}
    for element in instance.elements:
        code = str(element.type)
        histogram[code] = histogram.get(code, 0) + 1
    element_count = len(instance.elements)
    histogram_count = sum(int(count) for count in histogram.values())
    hex_count = sum(count for code, count in histogram.items()
                    if code.startswith("C3D8") or code.startswith("C3D20"))
    non_hex_count = max(0, element_count - hex_count)
    fillet = base.fillet_mesh_metrics(instance, float(radius), None) \
        if radius > 0.0 else {
            "radius": 0.0, "edges": 0, "min_elems": None,
            "max_elems": None, "elem_size": None,
            "second_order": False, "band_min": None,
            "band_size": None, "band_edges": 0,
            "cap_min": None, "cap_size": None, "cap_edges": 0}
    arc_count = fillet.get("min_elems")
    return {
        "nodes": len(instance.nodes), "elements": element_count,
        "types": histogram, "histogram_count": histogram_count,
        "hex_count": hex_count,
        "hex_pct": 100.0 * hex_count / max(1, element_count),
        "non_hex_count": non_hex_count,
        "non_hex_pct": 100.0 * non_hex_count / max(1, element_count),
        "failed": len(analysis["failedElements"]),
        "warnings": len(analysis["warningElements"]),
        "components": base.connected_components(instance),
        "ar_worst": aspect.get("worst"), "ar_avg": aspect.get("average"),
        "ar_bulk_worst": aspect.get("worst"),
        "ar_bulk_avg": aspect.get("average"),
        "ar_bulk_basis": "assembly_instance_global",
        "repairs": 0, "seconds": float(mesh_info.get("seconds", 0.0)),
        "fillet_detected": bool(fillet.get("edges", 0)),
        "fillet_arc_count": int(arc_count or 0),
        "fillet_band_count": 0, "fillet": fillet,
        "reproduction_ok": None}


def _generate_matching_mesh_from_physical_sources(model, params, d, base, core):
    """Construct a copied-surface tetra mesh in dependency order.

    Hub is the first source, its bore pattern is copied to the empty Shaft
    instance, and the completed Hub/Shaft flank patterns are then copied to the
    empty Key instance.  Every destination volume is generated only after all
    of its contact-face patterns exist, so Abaqus preserves those nodes exactly
    (within the geometry kernel coordinate floor).
    """
    import abaqusConstants as AC

    cfg = _fva(params).get("mesh_matching", {}) or {}
    target = float(cfg.get("target_size_mm", 0.8))
    if target <= 0.0:
        raise ValueError("mesh_matching.target_size_mm must be positive")
    surface_seed = 0.55 * target
    order = str(params.get("element_order", "quadratic")).lower()
    hex_code = str(params.get("linear_hex_code", "C3D8")).upper()
    tet_type = base._elem_types(order, hex_code)[1]
    arc_number = int(d.get("notch_arc_elems", 6) or 6)
    bulk_sizes = {
        "Hub": max(4.0 * target,
                   float((params.get("hub", {}) or {}).get("seed", target))),
        "Shaft": max(4.0 * target,
                     float((params.get("shaft", {}) or {}).get("seed", target))),
        "Key": max(3.0 * target,
                   float((params.get("key", {}) or {}).get("seed", target))),
    }
    mesh_plan = core.resolve_mesh_plan(params, d)
    assembly = model.rootAssembly
    levels = _matching_levels(d)
    levels.update((params.get("_method_a_partitioning", {}) or {}).get(
        "levels", {}))
    if "flank_transition" not in levels:
        levels["flank_transition"] = levels["hub_low"]

    # 1. Hub source part: both bore and key-flank boundaries are locally fine.
    hub_part = model.parts["Hub"]
    hub_radial_part = _select_radial_faces(
        hub_part, float(d["R"]), 0.0, float(d["L_hub"]))
    hub_left_part = _select_planar_faces(
        hub_part, -0.5 * float(d["groove_w"]),
        levels["flank_transition"], levels["hub_high"],
        0.0, float(d["L_hub"]))
    hub_right_part = _select_planar_faces(
        hub_part, 0.5 * float(d["groove_w"]),
        levels["flank_transition"], levels["hub_high"],
        0.0, float(d["L_hub"]))
    hub_source_faces = hub_radial_part + hub_left_part + hub_right_part
    if not len(hub_radial_part) or not len(hub_left_part) or not len(hub_right_part):
        raise RuntimeError("Hub source contact faces are incomplete")
    mesh_info = {}
    mesh_info["Hub"] = _mesh_part_tet(
        hub_part, bulk_sizes["Hub"], hub_source_faces, surface_seed,
        tet_type, float(d["r1"]), arc_number, AC)
    assembly.regenerate()

    # Copying between parts is unsupported; independent instances put all
    # source and destination faces in one assembly-level mesh repository.
    assembly.makeIndependent(instances=(
        assembly.instances["SHAFT-1"], assembly.instances["KEY-1"],
        assembly.instances["HUB-1"]))
    groups = _interface_face_groups(assembly, d, levels)
    shaft = assembly.instances["SHAFT-1"]
    key = assembly.instances["KEY-1"]
    hub = assembly.instances["HUB-1"]
    sequence = 0

    radial_pairs, radial_extras = _pair_faces(
        hub, groups["HUB_SHAFT"], shaft, groups["SHAFT_HUB_ALL"],
        "RADIAL_XYZ", allow_target_extras=True)
    shaft_hub_faces = shaft.faces[0:0]
    for _signature, source_face, target_face in radial_pairs:
        _copy_face_pattern(assembly, hub, source_face, target_face, sequence)
        sequence += 1
        shaft_hub_faces = (shaft_hub_faces +
                           shaft.faces[target_face.index:target_face.index + 1])

    # 2. Fill Shaft after its radial target pattern exists.  Its key flanks are
    # seeded locally because they become the source for Key in the next stage.
    shaft_flanks = groups["SHAFT_KEY_LEFT"] + groups["SHAFT_KEY_RIGHT"]
    mesh_info["Shaft"] = _mesh_instance_tet(
        assembly, shaft, "Shaft", bulk_sizes["Shaft"], shaft_flanks,
        surface_seed, tet_type, float(d["r2"]), arc_number, AC)

    # 3. Copy all four planar flank patterns to the still-empty Key instance.
    planar_defs = (
        ("SHAFT_KEY_LEFT", shaft, groups["SHAFT_KEY_LEFT"],
         groups["KEY_SHAFT_LEFT"], -0.5 * float(d["b"])),
        ("SHAFT_KEY_RIGHT", shaft, groups["SHAFT_KEY_RIGHT"],
         groups["KEY_SHAFT_RIGHT"], 0.5 * float(d["b"])),
        ("HUB_KEY_LEFT", hub, groups["HUB_KEY_LEFT"],
         groups["KEY_HUB_LEFT"], -0.5 * float(d["b"])),
        ("HUB_KEY_RIGHT", hub, groups["HUB_KEY_RIGHT"],
         groups["KEY_HUB_RIGHT"], 0.5 * float(d["b"])),
    )
    copy_counts = {"SHAFT_HUB": len(radial_pairs)}
    for interface_name, source_owner, source_faces, target_faces, target_x in planar_defs:
        pairs, extras = _pair_faces(
            source_owner, source_faces, key, target_faces, "PLANAR_YZ")
        copy_counts[interface_name] = len(pairs)
        for _signature, source_face, target_face in pairs:
            _copy_face_pattern(
                assembly, source_owner, source_face, target_face,
                sequence, target_x=target_x)
            sequence += 1

    mesh_info["Key"] = _mesh_instance_tet(
        assembly, key, "Key", bulk_sizes["Key"], key.faces[0:0],
        surface_seed, tet_type, 0.0, 0, AC)
    assembly.regenerate()

    # Re-resolve geometry handles after assembly meshing, then verify actual
    # surface element edge lengths before the node-cloud MATCHED gate.
    groups = _interface_face_groups(assembly, d, levels)
    radial_pairs, radial_extras = _pair_faces(
        hub, groups["HUB_SHAFT"], shaft, groups["SHAFT_HUB_ALL"],
        "RADIAL_XYZ", allow_target_extras=True)
    shaft_hub_faces = shaft.faces[0:0]
    for _signature, _source, target_face in radial_pairs:
        shaft_hub_faces = (shaft_hub_faces +
                           shaft.faces[target_face.index:target_face.index + 1])
    interface_faces = {
        "SHAFT_KEY_LEFT": (groups["SHAFT_KEY_LEFT"],
                           groups["KEY_SHAFT_LEFT"]),
        "SHAFT_KEY_RIGHT": (groups["SHAFT_KEY_RIGHT"],
                            groups["KEY_SHAFT_RIGHT"]),
        "HUB_KEY_LEFT": (groups["HUB_KEY_LEFT"], groups["KEY_HUB_LEFT"]),
        "HUB_KEY_RIGHT": (groups["HUB_KEY_RIGHT"], groups["KEY_HUB_RIGHT"]),
        "SHAFT_HUB": (groups["HUB_SHAFT"], shaft_hub_faces),
    }
    interface_mesh = {}
    size_tolerance = max(1.0e-5, 1.0e-3 * target)
    for interface_name, pair in interface_faces.items():
        first_max, first_facets, first_topology = _surface_max_element_edge(pair[0])
        second_max, second_facets, second_topology = _surface_max_element_edge(pair[1])
        realised = max(first_max, second_max)
        interface_mesh[interface_name] = {
            "target_max_edge_mm": target,
            "source_seed_mm": surface_seed,
            "first_max_edge_mm": first_max,
            "second_max_edge_mm": second_max,
            "realised_max_edge_mm": realised,
            "first_element_faces": first_facets,
            "second_element_faces": second_facets,
            "passed": realised <= target + size_tolerance}
        if realised > target + size_tolerance:
            raise RuntimeError(
                "Interface mesh size failed for %s: %.9g mm > %.9g mm" %
                (interface_name, realised, target))

    reports = {}
    instances = {"Shaft": shaft, "Key": key, "Hub": hub}
    radii = {"Shaft": float(d["r2"]), "Key": 0.0,
             "Hub": float(d["r1"])}
    for part_name in ("Shaft", "Key", "Hub"):
        metrics = _instance_metrics(
            assembly, instances[part_name], base, radii[part_name],
            mesh_info[part_name])
        policy = mesh_plan["parts"][part_name]
        quality = core.evaluate_mesh_quality(part_name, metrics, policy)
        reports[part_name] = {
            "types": metrics["types"], "repairs": 0,
            "notch": {"fillet_arc_edges": mesh_info[part_name].get(
                "fillet_arc_edges", 0), "band": 0,
                "method": "ISOTROPIC_FREE_TET_LOCAL_ARC_SEED"},
            "selected_recipe": {
                "recipe_id": "FVA_COPIED_INTERFACE_FREE_TET",
                "control_strategy": "FREE_TET",
                "bulk_size_mm": bulk_sizes[part_name],
                "surface_seed_mm": surface_seed,
                "target_max_interface_edge_mm": target},
            "selected_attempt_index": 0, "attempts": [],
            "metrics_scope": "ASSEMBLY_INSTANCE",
            "metrics": metrics, "quality": quality,
            "winner_reproduced": False,
            "winner_reproduction_match": None,
            "winner_signature_exact": None,
            "winner_reproduction_deltas": {},
            "winner_reproduction_error": None,
            "edge_divisions": mesh_info[part_name].get(
                "surface_edge_seeds", {}),
            "nodes": metrics["nodes"], "elements": metrics["elements"],
            "hex_pct": metrics["hex_pct"],
            "warnings": metrics["warnings"],
            "ar_bulk_worst": metrics["ar_bulk_worst"],
            "seconds": metrics["seconds"]}
        if quality.get("hard_passed") is not True:
            raise RuntimeError("Matching mesh hard quality gate failed for %s: %s" %
                               (part_name, quality.get("hard_reasons")))

    params["_mesh_plan"] = mesh_plan
    params["_mesh_report"] = reports
    params["_fva_interface_mesh"] = {
        "method": "ASSEMBLY_COPY_MESH_PATTERN_THEN_TET_FILL",
        "element_order": order, "tet_element": (
            "C3D10" if order == "quadratic" else "C3D4"),
        "target_max_edge_mm": target, "surface_seed_mm": surface_seed,
        "bulk_sizes_mm": bulk_sizes, "copy_counts": copy_counts,
        "radial_target_extra_patches": len(radial_extras),
        "interfaces": interface_mesh}
    params["_mesh_quality"] = core.aggregate_mesh_quality(
        dict((name, item["quality"]) for name, item in reports.items()),
        mesh_plan.get("fail_on_quality", True))
    return reports


def _mesh_template_part(part, contact_faces, seed, element_types, AC,
                        topology="FREE_TET"):
    """Fine auxiliary volume whose boundary supplies a copied pattern."""
    topology = str(topology or "FREE_TET").upper()
    if topology == "HYBRID_HEX":
        control_failures = []
        for cell in part.cells:
            applied = False
            for kwargs in (
                    dict(elemShape=AC.HEX, technique=AC.STRUCTURED),
                    dict(elemShape=AC.HEX, technique=AC.SWEEP,
                         algorithm=AC.MEDIAL_AXIS)):
                try:
                    part.setMeshControls(regions=(cell,), **kwargs)
                    applied = True
                    break
                except Exception as exc:
                    control_failures.append(str(exc)[:120])
            if not applied:
                raise RuntimeError(
                    "Hybrid interface template cell %d is not hex meshable: %s" %
                    (int(cell.index), control_failures[-2:]))
    else:
        part.setMeshControls(regions=part.cells, elemShape=AC.TET,
                             technique=AC.FREE)
    part.seedPart(size=float(seed), deviationFactor=0.1, minSizeFactor=0.1)
    edge_indices = set()
    for face in contact_faces:
        edge_indices.update(int(index) for index in face.getEdges())
    for index in sorted(edge_indices):
        length = _edge_size(part.edges[index])
        number = max(1, int(math.ceil(length / float(seed) - 1.0e-12)))
        part.seedEdgeByNumber(
            edges=part.edges[index:index + 1], number=number,
            constraint=AC.FIXED)
    part.setElementType(regions=(part.cells,), elemTypes=tuple(element_types))
    part.generateMesh()
    if not len(part.nodes) or not len(part.elements):
        raise RuntimeError("Auxiliary mesh template generated no elements")
    histogram = {}
    for element in part.elements:
        histogram[str(element.type)] = histogram.get(str(element.type), 0) + 1
    if topology == "HYBRID_HEX" and any(
            not (code.startswith("C3D8") or code.startswith("C3D20"))
            for code in histogram):
        raise RuntimeError("Hybrid interface template is not all-hex: %s" % histogram)
    return {"nodes": len(part.nodes), "elements": len(part.elements),
            "types": histogram, "topology": topology,
            "fixed_boundary_edges": len(edge_indices)}


def _create_planar_template(model, name, height, axial_length, thickness,
                            seed, element_types, AC, topology="FREE_TET"):
    sketch_name = "__%s_SKETCH__" % name
    sketch = model.ConstrainedSketch(
        name=sketch_name, sheetSize=4.0 * max(height, axial_length))
    sketch.rectangle(point1=(0.0, 0.0),
                     point2=(float(axial_length), float(height)))
    part = model.Part(name=name, dimensionality=AC.THREE_D,
                      type=AC.DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=float(thickness))
    del model.sketches[sketch_name]
    faces = part.faces[0:0]
    for face in part.faces:
        low, high = _face_bbox(part, face)
        if abs(low[2]) <= 1.0e-7 and abs(high[2]) <= 1.0e-7:
            faces = faces + part.faces[face.index:face.index + 1]
    if len(faces) != 1:
        raise RuntimeError("Planar template %s has %d source faces" %
                           (name, len(faces)))
    stats = _mesh_template_part(
        part, faces, seed, element_types, AC, topology=topology)
    return part, stats


def _create_radial_template(model, name, radius, axial_length, half_opening,
                            thickness, seed, element_types, base, AC,
                            topology="FREE_TET"):
    sketch_name = "__%s_SKETCH__" % name
    sketch = model.ConstrainedSketch(
        name=sketch_name, sheetSize=6.0 * (radius + thickness))
    sketch.CircleByCenterPerimeter(
        center=(0.0, 0.0), point1=(radius + thickness, 0.0))
    sketch.CircleByCenterPerimeter(
        center=(0.0, 0.0), point1=(radius, 0.0))
    part = model.Part(name=name, dimensionality=AC.THREE_D,
                      type=AC.DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=float(axial_length))
    del model.sketches[sketch_name]
    radial = _radial_face_predicate(float(radius))
    _partition_faces_at(part, base, "x", 0.0, radial)
    _partition_faces_at(part, base, "y", 0.0, radial)
    for value in (-float(half_opening), float(half_opening)):
        _partition_faces_at(
            part, base, "x", value,
            lambda face, pred=radial: pred(face) and _face_point(face)[1] > 0.0)
    all_inner = _select_radial_faces(
        part, float(radius), 0.0, float(axial_length))
    common = part.faces[0:0]
    for face in all_inner:
        point = _face_point(face)
        if point[1] > 0.0 and abs(point[0]) < float(half_opening) - 1.0e-6:
            continue
        common = common + part.faces[face.index:face.index + 1]
    if len(common) != 4:
        raise RuntimeError("Radial template expected 4 common patches, found %d" %
                           len(common))
    stats = _mesh_template_part(
        part, common, seed, element_types, AC, topology=topology)
    return part, stats


def _position_planar_template(assembly, instance_name, part, x_plane,
                              y_low, z_high, AC):
    assembly.Instance(name=instance_name, part=part, dependent=AC.ON)
    assembly.rotate(instanceList=(instance_name,),
                    axisPoint=(0.0, 0.0, 0.0),
                    axisDirection=(0.0, 1.0, 0.0), angle=90.0)
    positioned = assembly.instances[instance_name]
    regions = positioned.cells if len(positioned.cells) else positioned.faces
    box = regions.getBoundingBox()
    assembly.translate(
        instanceList=(instance_name,),
        vector=(float(x_plane) - float(box["low"][0]),
                float(y_low) - float(box["low"][1]),
                float(z_high) - float(box["high"][2])))


def _template_planar_face(instance, x_plane, y_low, y_high, z_low, z_high):
    faces = _select_planar_faces(
        instance, float(x_plane), float(y_low), float(y_high),
        float(z_low), float(z_high))
    if len(faces) != 1:
        raise RuntimeError("Expected one planar template face, found %d" %
                           len(faces))
    return faces


def _copy_planar_template(assembly, source_instance, source_faces,
                          target_instance, target_faces, target_x, sequence):
    pairs, extras = _pair_faces(
        source_instance, source_faces, target_instance, target_faces,
        "PLANAR_YZ")
    if extras or len(pairs) != 1:
        raise RuntimeError("Planar template/target topology is not one-to-one")
    _signature, source_face, target_face = pairs[0]
    _copy_face_pattern(
        assembly, source_instance, source_face, target_face,
        sequence, target_x=float(target_x))
    return sequence + 1


def _apply_hybrid_part_controls(part, AC):
    counts = {}
    errors = []
    chain = (
        ("HEX_STRUCTURED", dict(
            elemShape=AC.HEX, technique=AC.STRUCTURED)),
        ("HEX_SWEEP_MEDIAL", dict(
            elemShape=AC.HEX, technique=AC.SWEEP,
            algorithm=AC.MEDIAL_AXIS)),
        ("HEX_SWEEP_ADVANCING", dict(
            elemShape=AC.HEX, technique=AC.SWEEP,
            algorithm=AC.ADVANCING_FRONT)),
        ("TET_TRANSITION", dict(
            elemShape=AC.TET, technique=AC.FREE)),
    )
    for cell in part.cells:
        applied = None
        for label, kwargs in chain:
            try:
                part.setMeshControls(regions=(cell,), **kwargs)
                applied = label
                counts[label] = counts.get(label, 0) + 1
                break
            except Exception as exc:
                errors.append({"cell": int(cell.index), "control": label,
                               "error": str(exc)[:160]})
        if applied is None:
            raise RuntimeError(
                "No hybrid control can be assigned to %s cell %d" %
                (part.name, int(cell.index)))
    return {"cell_controls": counts, "control_errors": errors}


def _mesh_hybrid_part(part, bulk_size, element_types, radius,
                      arc_number, AC):
    started = time.time()
    part.deleteMesh()
    try:
        part.deleteSeeds(regions=part.edges)
    except Exception:
        pass
    control_info = _apply_hybrid_part_controls(part, AC)
    part.seedPart(size=float(bulk_size), deviationFactor=0.1,
                  minSizeFactor=0.1)
    arc_edges = _seed_fillet_arcs(
        part, float(radius), int(arc_number), AC)
    part.setElementType(regions=(part.cells,),
                        elemTypes=tuple(element_types))
    part.generateMesh()
    if not len(part.nodes) or not len(part.elements):
        raise RuntimeError("Hybrid volume mesh is empty for %s" % part.name)
    histogram = {}
    for element in part.elements:
        histogram[str(element.type)] = histogram.get(str(element.type), 0) + 1
    unexpected = sorted(set(histogram) - set(("C3D20R", "C3D15", "C3D10")))
    if unexpected:
        raise RuntimeError(
            "Hybrid volume %s contains unsupported element types %s" %
            (part.name, unexpected))
    if int(histogram.get("C3D20R", 0)) < 1:
        raise RuntimeError("Hybrid volume %s contains no C3D20R" % part.name)
    control_info.update({
        "bulk_size_mm": float(bulk_size),
        "fillet_arc_edges": int(arc_edges),
        "types": histogram,
        "topology": "HYBRID_HEX",
        "seconds": round(time.time() - started, 3)})
    return control_info


def generate_hybrid_native_mesh(model, params, d, base, core):
    """Mesh physical volumes natively; matching is supplied by tied skins."""
    import abaqusConstants as AC

    mesh_plan = core.resolve_mesh_plan(params, d)
    if (mesh_plan.get("template") != "FVA_METHOD_A_HYBRID" or
            mesh_plan.get("topology_requirement") != "HYBRID_HEX" or
            mesh_plan.get("element_order") != "quadratic" or
            mesh_plan.get("quadratic_hex_code") != "C3D20R"):
        raise RuntimeError("Invalid v2 hybrid mesh plan: %s" % mesh_plan)
    element_types = base._elem_types(
        "quadratic", mesh_plan["linear_hex_code"],
        quadratic_hex_code="C3D20R", allow_tet_fallback=True,
        topology_requirement="HYBRID_HEX")
    arc_number = int(d.get("notch_arc_elems", 6) or 6)
    bulk_sizes = {
        "Shaft": float(d.get("seed_shaft", 2.5)),
        "Key": float(d.get("seed_key", 0.8)),
        "Hub": float(d.get("seed_hub", 0.8)),
    }
    radii = {"Shaft": float(d["r2"]), "Key": 0.0,
             "Hub": float(d["r1"])}
    mesh_info = {}
    for name in ("Shaft", "Key", "Hub"):
        mesh_info[name] = _mesh_hybrid_part(
            model.parts[name], bulk_sizes[name], element_types,
            radii[name], arc_number if name != "Key" else 0, AC)
    assembly = model.rootAssembly
    assembly.regenerate()
    instances = {"Shaft": assembly.instances["SHAFT-1"],
                 "Key": assembly.instances["KEY-1"],
                 "Hub": assembly.instances["HUB-1"]}
    reports = {}
    for name in ("Shaft", "Key", "Hub"):
        metrics = _instance_metrics(
            assembly, instances[name], base, radii[name], mesh_info[name])
        policy = mesh_plan["parts"][name]
        quality = core.evaluate_mesh_quality(name, metrics, policy)
        reports[name] = {
            "types": metrics["types"], "repairs": 0,
            "notch": {"fillet_arc_edges": mesh_info[name].get(
                "fillet_arc_edges", 0), "band": 0,
                "method": "NATIVE_HYBRID_HEX_LOCAL_ARC_SEED"},
            "selected_recipe": {
                "recipe_id": "FVA_NATIVE_HYBRID_HEX_WITH_TIED_QUAD_SKINS",
                "control_strategy": "STRUCTURED_SWEEP_TET_TRANSITIONS",
                "bulk_size_mm": bulk_sizes[name]},
            "selected_attempt_index": 0, "attempts": [],
            "metrics_scope": "ASSEMBLY_INSTANCE_PHYSICAL_VOLUME",
            "metrics": metrics, "quality": quality,
            "cell_controls": mesh_info[name].get("cell_controls"),
            "control_errors": mesh_info[name].get("control_errors"),
            "nodes": metrics["nodes"], "elements": metrics["elements"],
            "hex_count": metrics["hex_count"],
            "non_hex_count": metrics["non_hex_count"],
            "hex_pct": metrics["hex_pct"],
            "non_hex_pct": metrics["non_hex_pct"],
            "warnings": metrics["warnings"],
            "ar_bulk_worst": metrics["ar_bulk_worst"],
            "seconds": metrics["seconds"]}
        if quality.get("hard_passed") is not True:
            raise RuntimeError(
                "Hybrid mesh hard quality gate failed for %s: %s" %
                (name, quality.get("hard_reasons")))
    profile_failures = core.validate_realized_element_profile(
        mesh_plan, reports)
    if profile_failures:
        raise RuntimeError("Hybrid realised profile failed: %s" %
                           "; ".join(profile_failures))
    params["_mesh_plan"] = mesh_plan
    params["_mesh_report"] = reports
    params["_mesh_quality"] = core.aggregate_mesh_quality(
        dict((name, item["quality"]) for name, item in reports.items()),
        mesh_plan.get("fail_on_quality", True))
    return reports


def _mesh_skin_part(part, seed, AC):
    import mesh as abaqus_mesh

    part.setMeshControls(regions=part.faces, elemShape=AC.QUAD,
                         technique=AC.STRUCTURED)
    part.seedPart(size=float(seed), deviationFactor=0.1, minSizeFactor=0.1)
    edge_rows = {}
    for edge in part.edges:
        length = _edge_size(edge)
        divisions = max(1, int(math.ceil(length / float(seed) - 1.0e-12)))
        part.seedEdgeByNumber(
            edges=part.edges[edge.index:edge.index + 1],
            number=divisions, constraint=AC.FIXED)
        edge_rows[str(int(edge.index))] = {
            "length_mm": length, "divisions": divisions,
            "nominal_edge_mm": length / float(divisions)}
    skin_type = abaqus_mesh.ElemType(
        elemCode=AC.S8R, elemLibrary=AC.STANDARD)
    part.setElementType(regions=(part.faces,), elemTypes=(skin_type,))
    part.generateMesh()
    if not len(part.nodes) or not len(part.elements):
        raise RuntimeError("Interface skin %s generated no mesh" % part.name)
    histogram = {}
    for element in part.elements:
        histogram[str(element.type)] = histogram.get(str(element.type), 0) + 1
    if sorted(histogram) != ["S8R"]:
        raise RuntimeError("Interface skin %s is not pure S8R: %s" %
                           (part.name, histogram))
    state = _surface_pattern_state(part.faces)
    maximum, facets, topology = _surface_max_element_edge(part.faces)
    if not state.get("structured_quadrilateral_pattern"):
        raise RuntimeError("Interface skin %s is not structured QUAD" % part.name)
    return {"nodes": len(part.nodes), "elements": len(part.elements),
            "types": histogram, "edge_seeds": edge_rows,
            "max_edge_mm": maximum, "facets": facets,
            "facet_topology": topology, "pattern": state}


def _create_planar_skin_part(model, name, height, axial_length, seed, AC):
    sketch_name = "__%s_SKETCH__" % name
    sketch = model.ConstrainedSketch(
        name=sketch_name, sheetSize=4.0 * max(height, axial_length))
    sketch.rectangle(point1=(0.0, 0.0),
                     point2=(float(axial_length), float(height)))
    part = model.Part(name=name, dimensionality=AC.THREE_D,
                      type=AC.DEFORMABLE_BODY)
    part.BaseShell(sketch=sketch)
    del model.sketches[sketch_name]
    return part, _mesh_skin_part(part, seed, AC)


def _create_radial_skin_part(model, name, radius, axial_length,
                             half_opening, seed, AC):
    sketch_name = "__%s_SKETCH__" % name
    sketch = model.ConstrainedSketch(
        name=sketch_name, sheetSize=6.0 * float(radius))
    opening_y = math.sqrt(max(
        0.0, float(radius) ** 2 - float(half_opening) ** 2))
    sketch.ArcByCenterEnds(
        center=(0.0, 0.0),
        point1=(float(half_opening), opening_y),
        point2=(-float(half_opening), opening_y),
        direction=AC.CLOCKWISE)
    part = model.Part(name=name, dimensionality=AC.THREE_D,
                      type=AC.DEFORMABLE_BODY)
    part.BaseShellExtrude(sketch=sketch, depth=float(axial_length))
    del model.sketches[sketch_name]
    return part, _mesh_skin_part(part, seed, AC)


def create_matching_interface_skins(model, params, d, partition_info):
    """Create paired quadratic QUAD contact skins identical by construction."""
    import abaqusConstants as AC

    target = float((_fva(params).get("mesh_matching", {}) or {}).get(
        "target_size_mm", 0.8))
    seed = 0.45 * target
    levels = partition_info["levels"]
    z_low, z_high = float(levels["z_low"]), float(levels["z_high"])
    axial_length = z_high - z_low
    radial_name = "FVA_SKIN_RADIAL"
    shaft_key_name = "FVA_SKIN_SHAFT_KEY"
    hub_key_name = "FVA_SKIN_HUB_KEY"
    for part_name in (radial_name, shaft_key_name, hub_key_name):
        if part_name in model.parts:
            del model.parts[part_name]
    radial_part, radial_stats = _create_radial_skin_part(
        model, radial_name, float(d["R"]), axial_length,
        0.5 * float(d["groove_w"]), seed, AC)
    shaft_key_part, shaft_key_stats = _create_planar_skin_part(
        model, shaft_key_name,
        float(levels["flank_transition"]) - float(levels["shaft_low"]),
        axial_length, seed, AC)
    hub_key_part, hub_key_stats = _create_planar_skin_part(
        model, hub_key_name,
        float(levels["hub_high"]) - float(levels["flank_transition"]),
        axial_length, seed, AC)
    assembly = model.rootAssembly
    instance_parts = {}

    def planar(instance_name, part, x_plane, y_low):
        _position_planar_template(
            assembly, instance_name, part, x_plane, y_low, z_high, AC)
        instance_parts[instance_name] = part.name

    planar("FVA_SKIN_SHAFT_KEY_LEFT", shaft_key_part,
           -float(d["x_slot"]), float(levels["shaft_low"]))
    planar("FVA_SKIN_KEY_SHAFT_LEFT", shaft_key_part,
           -0.5 * float(d["b"]), float(levels["shaft_low"]))
    planar("FVA_SKIN_SHAFT_KEY_RIGHT", shaft_key_part,
           float(d["x_slot"]), float(levels["shaft_low"]))
    planar("FVA_SKIN_KEY_SHAFT_RIGHT", shaft_key_part,
           0.5 * float(d["b"]), float(levels["shaft_low"]))
    planar("FVA_SKIN_HUB_KEY_LEFT", hub_key_part,
           -0.5 * float(d["groove_w"]),
           float(levels["flank_transition"]))
    planar("FVA_SKIN_KEY_HUB_LEFT", hub_key_part,
           -0.5 * float(d["b"]), float(levels["flank_transition"]))
    planar("FVA_SKIN_HUB_KEY_RIGHT", hub_key_part,
           0.5 * float(d["groove_w"]),
           float(levels["flank_transition"]))
    planar("FVA_SKIN_KEY_HUB_RIGHT", hub_key_part,
           0.5 * float(d["b"]), float(levels["flank_transition"]))
    for instance_name in ("FVA_SKIN_SHAFT_HUB", "FVA_SKIN_HUB_SHAFT"):
        assembly.Instance(name=instance_name, part=radial_part,
                          dependent=AC.ON)
        assembly.translate(instanceList=(instance_name,),
                           vector=(0.0, 0.0, z_low))
        instance_parts[instance_name] = radial_part.name
    assembly.regenerate()
    name_to_instance = {
        "SHAFT_KEY_LEFT": "FVA_SKIN_SHAFT_KEY_LEFT",
        "KEY_SHAFT_LEFT": "FVA_SKIN_KEY_SHAFT_LEFT",
        "SHAFT_KEY_RIGHT": "FVA_SKIN_SHAFT_KEY_RIGHT",
        "KEY_SHAFT_RIGHT": "FVA_SKIN_KEY_SHAFT_RIGHT",
        "HUB_KEY_LEFT": "FVA_SKIN_HUB_KEY_LEFT",
        "KEY_HUB_LEFT": "FVA_SKIN_KEY_HUB_LEFT",
        "HUB_KEY_RIGHT": "FVA_SKIN_HUB_KEY_RIGHT",
        "KEY_HUB_RIGHT": "FVA_SKIN_KEY_HUB_RIGHT",
        "SHAFT_HUB": "FVA_SKIN_SHAFT_HUB",
        "HUB_SHAFT": "FVA_SKIN_HUB_SHAFT",
    }
    faces = dict((name, assembly.instances[instance_name].faces)
                 for name, instance_name in name_to_instance.items())
    pair_defs = (
        ("SHAFT_KEY_LEFT", "SHAFT_KEY_LEFT", "KEY_SHAFT_LEFT", (1, 2)),
        ("SHAFT_KEY_RIGHT", "SHAFT_KEY_RIGHT", "KEY_SHAFT_RIGHT", (1, 2)),
        ("HUB_KEY_LEFT", "HUB_KEY_LEFT", "KEY_HUB_LEFT", (1, 2)),
        ("HUB_KEY_RIGHT", "HUB_KEY_RIGHT", "KEY_HUB_RIGHT", (1, 2)),
        ("SHAFT_HUB", "SHAFT_HUB", "HUB_SHAFT", (0, 1, 2)),
    )
    interface_audit = {}
    for interface_name, first_name, second_name, projection in pair_defs:
        first_state = _surface_pattern_state(faces[first_name])
        second_state = _surface_pattern_state(faces[second_name])
        first_max, first_facets, first_topology = \
            _surface_max_element_edge(faces[first_name])
        second_max, second_facets, second_topology = \
            _surface_max_element_edge(faces[second_name])
        comparison = _compare_clouds(
            interface_name, _surface_nodes(faces[first_name]),
            _surface_nodes(faces[second_name]), projection, 1.0e-9)
        absolute_pass = max(first_max, second_max) <= \
            ABSOLUTE_INTERFACE_EDGE_LIMIT_MM + 1.0e-12
        quad_pass = (first_state.get("structured_quadrilateral_pattern") and
                     second_state.get("structured_quadrilateral_pattern"))
        if not comparison.get("matched") or not absolute_pass or not quad_pass:
            raise RuntimeError(
                "Interface skin gate failed for %s: match=%s edge=%s quad=%s" %
                (interface_name, comparison.get("matched"), absolute_pass,
                 quad_pass))
        interface_audit[interface_name] = {
            "construction": "PAIRED_DEPENDENT_INSTANCES_OF_ONE_S8R_PART",
            "matching": comparison,
            "target_max_edge_mm": target,
            "absolute_max_edge_limit_mm": ABSOLUTE_INTERFACE_EDGE_LIMIT_MM,
            "first_max_edge_mm": first_max,
            "second_max_edge_mm": second_max,
            "realised_max_edge_mm": max(first_max, second_max),
            "first_element_faces": first_facets,
            "second_element_faces": second_facets,
            "first_facet_topology": first_topology,
            "second_facet_topology": second_topology,
            "quadrilateral_passed": quad_pass,
            "absolute_1mm_passed": absolute_pass,
            "passed": True}
    audit = {
        "method": "TIED_QUADRATIC_STRUCTURED_CONTACT_SKINS",
        "surface_element": "S8R",
        "surface_seed_mm": seed,
        "volume_element_profile": ["C3D20R", "C3D15", "C3D10"],
        "skin_elements_excluded_from_volume_histograms": True,
        "parts": {"radial": radial_stats,
                  "shaft_key": shaft_key_stats,
                  "hub_key": hub_key_stats},
        "instance_parts": instance_parts,
        "interfaces": interface_audit,
        "quadrilateral_gate": "PASS",
        "templates_removed": False,
    }
    params["_fva_interface_skins"] = audit
    params["_fva_interface_mesh"] = {
        "backend": BACKEND_HYBRID_HEX,
        "method": "NATIVE_HYBRID_VOLUMES_PLUS_TIED_S8R_CONTACT_SKINS",
        "volume_topology": "HYBRID_HEX",
        "surface_topology": "STRUCTURED_QUADRILATERAL_S8R",
        "element_order": "quadratic",
        "element_profile": ["C3D20R", "C3D15", "C3D10"],
        "target_max_edge_mm": target,
        "surface_seed_mm": seed,
        "pattern_preservation_audit": audit,
        "hard_gates": {
            "max_non_hex_pct": 50.0,
            "at_least_one_hex_per_piece": True,
            "absolute_interface_edge_limit_mm":
                ABSOLUTE_INTERFACE_EDGE_LIMIT_MM,
            "five_interfaces": list(REQUIRED_MATCHING_INTERFACES)},
        "interfaces": interface_audit}
    return {"faces": faces, "name_to_instance": name_to_instance,
            "part_names": (radial_name, shaft_key_name, hub_key_name),
            "audit": audit}


def assign_interface_skin_section(model, skin_data, material_name):
    import abaqusConstants as AC

    section_name = "FVA_INTERFACE_SKIN_SECTION"
    if section_name in model.sections:
        del model.sections[section_name]
    model.HomogeneousShellSection(
        name=section_name, material=str(material_name), thickness=1.0e-6,
        thicknessType=AC.UNIFORM, idealization=AC.NO_IDEALIZATION,
        poissonDefinition=AC.DEFAULT, thicknessModulus=None,
        temperature=AC.GRADIENT, useDensity=AC.OFF,
        integrationRule=AC.SIMPSON, numIntPts=5)
    for part_name in skin_data["part_names"]:
        part = model.parts[part_name]
        set_name = "FVA_SKIN_ALL_FACES"
        if set_name in part.sets:
            del part.sets[set_name]
        region = part.Set(name=set_name, faces=part.faces)
        part.SectionAssignment(
            region=region, sectionName=section_name,
            offset=0.0, offsetType=AC.MIDDLE_SURFACE,
            offsetField="", thicknessAssignment=AC.FROM_SECTION)
    model.rootAssembly.regenerate()
    return {"section": section_name, "material": str(material_name),
            "thickness_mm": 1.0e-6,
            "purpose": "KINEMATIC_CONTACT_SKIN_TIED_TO_PHYSICAL_VOLUME"}


def generate_matching_mesh(model, params, d, base, core):
    """Generate all five interfaces from three fine disposable templates.

    A thin annulus supplies one cylindrical pattern to both Shaft and Hub.  Two
    small rectangular blocks supply the shaft/key and hub/key flank patterns to
    both mating bodies.  Physical volumes are filled only after every copied
    boundary exists; template instances and parts are then removed.  This is
    both faster and stricter than hoping independent automatic meshes coincide.
    """
    import abaqusConstants as AC

    cfg = _fva(params).get("mesh_matching", {}) or {}
    backend_id = str(_fva(params).get("backend", BACKEND) or BACKEND)
    hybrid = backend_id == BACKEND_HYBRID_HEX
    target = float(cfg.get("target_size_mm", 0.8))
    if target <= 0.0:
        raise ValueError("mesh_matching.target_size_mm must be positive")
    if target > ABSOLUTE_INTERFACE_EDGE_LIMIT_MM + 1.0e-12:
        raise ValueError("mesh_matching.target_size_mm must be <= 1 mm")
    surface_seed = 0.45 * target
    order = str(params.get("element_order", "quadratic")).lower()
    hex_code = str(params.get("linear_hex_code", "C3D8")).upper()
    mesh_plan = core.resolve_mesh_plan(params, d)
    if hybrid:
        if (mesh_plan.get("topology_requirement") != "HYBRID_HEX" or
                mesh_plan.get("element_order") != "quadratic" or
                mesh_plan.get("quadratic_hex_code") != "C3D20R"):
            raise RuntimeError(
                "Hybrid Method-A requires FVA_METHOD_A_HYBRID, quadratic "
                "C3D20R and HYBRID_HEX")
        element_types = base._elem_types(
            order, hex_code,
            quadratic_hex_code=mesh_plan["quadratic_hex_code"],
            allow_tet_fallback=True,
            topology_requirement="HYBRID_HEX")
        tet_type = element_types[-1]
        template_element_types = (element_types[0],)
        template_topology = "HYBRID_HEX"
        physical_topology = "HYBRID_HEX"
    else:
        tet_type = base._elem_types(order, hex_code)[1]
        element_types = (tet_type,)
        template_element_types = (tet_type,)
        template_topology = "FREE_TET"
        physical_topology = "FREE_TET"
    arc_number = int(d.get("notch_arc_elems", 6) or 6)
    bulk_sizes = {
        "Hub": max(4.0 * target,
                   float((params.get("hub", {}) or {}).get("seed", target))),
        "Shaft": max(4.0 * target,
                     float((params.get("shaft", {}) or {}).get("seed", target))),
        "Key": max(3.0 * target,
                   float((params.get("key", {}) or {}).get("seed", target))),
    }
    partitioning = params.get("_method_a_partitioning", {}) or {}
    levels = dict(_matching_levels(d))
    levels.update(partitioning.get("levels", {}))
    transition = float(levels.get("flank_transition", levels["hub_low"]))
    levels["flank_transition"] = transition
    z_low, z_high = float(levels["z_low"]), float(levels["z_high"])
    axial_length = z_high - z_low
    if axial_length <= 0.0:
        raise RuntimeError("Method-A interface axial length is not positive")

    radial_name = "__FVA_MATCH_RADIAL_TEMPLATE__"
    shaft_key_name = "__FVA_MATCH_SHAFT_KEY_TEMPLATE__"
    hub_key_name = "__FVA_MATCH_HUB_KEY_TEMPLATE__"
    auxiliary_parts = (radial_name, shaft_key_name, hub_key_name)
    assembly = model.rootAssembly
    thickness = max(0.25, surface_seed)
    radial_part, radial_stats = _create_radial_template(
        model, radial_name, float(d["R"]), axial_length,
        0.5 * float(d["groove_w"]), thickness, surface_seed,
        template_element_types, base, AC, topology=template_topology)
    shaft_key_part, shaft_key_stats = _create_planar_template(
        model, shaft_key_name, transition - float(levels["shaft_low"]),
        axial_length, thickness, surface_seed, template_element_types, AC,
        topology=template_topology)
    hub_key_part, hub_key_stats = _create_planar_template(
        model, hub_key_name, float(levels["hub_high"]) - transition,
        axial_length, thickness, surface_seed, template_element_types, AC,
        topology=template_topology)

    radial_instance_name = "__FVA_MATCH_RADIAL_TEMPLATE_I__"
    shaft_key_instance_name = "__FVA_MATCH_SHAFT_KEY_TEMPLATE_I__"
    hub_key_instance_name = "__FVA_MATCH_HUB_KEY_TEMPLATE_I__"
    auxiliary_instances = (radial_instance_name, shaft_key_instance_name,
                           hub_key_instance_name)
    assembly.Instance(name=radial_instance_name, part=radial_part,
                      dependent=AC.ON)
    assembly.translate(instanceList=(radial_instance_name,),
                       vector=(0.0, 0.0, z_low))
    template_x = float(d["d_a"]) + 20.0
    _position_planar_template(
        assembly, shaft_key_instance_name, shaft_key_part, template_x,
        float(levels["shaft_low"]), z_high, AC)
    _position_planar_template(
        assembly, hub_key_instance_name, hub_key_part,
        template_x + 2.0 * thickness + 1.0,
        transition, z_high, AC)
    assembly.regenerate()

    all_instance_names = ("SHAFT-1", "KEY-1", "HUB-1") + auxiliary_instances
    assembly.makeIndependent(instances=tuple(
        assembly.instances[name] for name in all_instance_names))
    shaft = assembly.instances["SHAFT-1"]
    key = assembly.instances["KEY-1"]
    hub = assembly.instances["HUB-1"]
    radial_source_owner = assembly.instances[radial_instance_name]
    shaft_key_source_owner = assembly.instances[shaft_key_instance_name]
    hub_key_source_owner = assembly.instances[hub_key_instance_name]

    groups = _interface_face_groups(assembly, d, levels)

    # Configure every physical target before copying any native surface mesh.
    # In Abaqus 2022, setMeshControls/seedPartInstance/setElementType invoked
    # after copyMeshPattern erase the copied pattern.  Volume generation is
    # deliberately deferred until all five interface patterns are present.
    # Physical targets receive no interface-edge seeds here; their contact
    # boundaries will be imposed by copyMeshPattern below.
    mesh_info = {}
    mesh_info["Hub"] = _mesh_instance_tet(
        assembly, hub, "Hub", bulk_sizes["Hub"], hub.faces[0:0],
        surface_seed, tet_type, float(d["r1"]), arc_number, AC,
        generate=False, topology=physical_topology,
        element_types=element_types)
    mesh_info["Shaft"] = _mesh_instance_tet(
        assembly, shaft, "Shaft", bulk_sizes["Shaft"], shaft.faces[0:0],
        surface_seed, tet_type, float(d["r2"]), arc_number, AC,
        generate=False, topology=physical_topology,
        element_types=element_types)
    mesh_info["Key"] = _mesh_instance_tet(
        assembly, key, "Key", bulk_sizes["Key"], key.faces[0:0],
        surface_seed, tet_type, 0.0, 0, AC, generate=False,
        topology=physical_topology, element_types=element_types)

    radial_all = _select_radial_faces(
        radial_source_owner, float(d["R"]), z_low, z_high)
    radial_source = radial_source_owner.faces[0:0]
    half_opening = 0.5 * float(d["groove_w"])
    for face in radial_all:
        point = _face_point(face)
        if point[1] > 0.0 and abs(point[0]) < half_opening - 1.0e-6:
            continue
        radial_source = (radial_source + radial_source_owner.faces[
            face.index:face.index + 1])
    shaft_key_source = _template_planar_face(
        shaft_key_source_owner, template_x,
        levels["shaft_low"], transition, z_low, z_high)
    hub_template_x = template_x + 2.0 * thickness + 1.0
    hub_key_source = _template_planar_face(
        hub_key_source_owner, hub_template_x,
        transition, levels["hub_high"], z_low, z_high)

    pattern_audit = {
        "template_sources": {}, "immediate_targets": {},
        "filled_targets": {},
        "required_surface_topology": (
            "STRUCTURED_QUADRILATERAL" if hybrid else "LEGACY_TRIANGULAR"),
        "quadratic_note": (
            "copyMeshPattern transfers structured C3D20R quadrilateral "
            "boundary topology into the quadratic hybrid volume fill"
            if hybrid else
            "copyMeshPattern transfers the legacy free-tet boundary topology; "
            "C3D10 midside nodes are materialized by the volume fill")}
    for audit_name, audit_faces in (
            ("RADIAL_COMMON", radial_source),
            ("SHAFT_KEY", shaft_key_source),
            ("HUB_KEY", hub_key_source)):
        audit_max, audit_facets, audit_topology = _surface_max_element_edge(audit_faces)
        audit_row = _surface_pattern_state(audit_faces)
        audit_row["max_element_edge_mm"] = audit_max
        audit_row["measured_element_faces"] = audit_facets
        audit_row["measured_facet_topology"] = audit_topology
        if hybrid and not audit_row["structured_quadrilateral_pattern"]:
            raise RuntimeError(
                "Hybrid template %s is not a structured quadrilateral pattern: %s" %
                (audit_name, audit_row["facet_node_histogram"]))
        pattern_audit["template_sources"][audit_name] = audit_row

    sequence = 0
    radial_copy_counts = {}
    # Project the disposable annular pattern only onto Hub first.  Once Hub is
    # volume-meshed, that physical native face becomes the sole source for
    # Shaft.  This avoids two independent ACIS projections of the same template
    # and therefore minimizes cylindrical coordinate noise.
    hub_radial_pairs, hub_radial_extras = _pair_faces(
        radial_source_owner, radial_source, hub, groups["HUB_SHAFT"],
        "RADIAL_XYZ")
    radial_copy_counts["Hub"] = {
        "copied_patches": len(hub_radial_pairs),
        "target_extra_patches": len(hub_radial_extras),
        "source": "DISPOSABLE_RADIAL_TEMPLATE"}
    for _signature, source_face, target_face in hub_radial_pairs:
        _copy_face_pattern(
            assembly, radial_source_owner, source_face, target_face,
            sequence)
        sequence += 1
    pattern_audit["immediate_targets"]["HUB_SHAFT"] = \
        _surface_pattern_state(groups["HUB_SHAFT"])

    planar_targets = (
        ("SHAFT_KEY_LEFT", shaft_key_source_owner, shaft_key_source,
         shaft, groups["SHAFT_KEY_LEFT"], -float(d["x_slot"])),
        ("SHAFT_KEY_RIGHT", shaft_key_source_owner, shaft_key_source,
         shaft, groups["SHAFT_KEY_RIGHT"], float(d["x_slot"])),
        ("KEY_SHAFT_LEFT", shaft_key_source_owner, shaft_key_source,
         key, groups["KEY_SHAFT_LEFT"], -0.5 * float(d["b"])),
        ("KEY_SHAFT_RIGHT", shaft_key_source_owner, shaft_key_source,
         key, groups["KEY_SHAFT_RIGHT"], 0.5 * float(d["b"])),
        ("HUB_KEY_LEFT", hub_key_source_owner, hub_key_source,
         hub, groups["HUB_KEY_LEFT"], -0.5 * float(d["groove_w"])),
        ("HUB_KEY_RIGHT", hub_key_source_owner, hub_key_source,
         hub, groups["HUB_KEY_RIGHT"], 0.5 * float(d["groove_w"])),
        ("KEY_HUB_LEFT", hub_key_source_owner, hub_key_source,
         key, groups["KEY_HUB_LEFT"], -0.5 * float(d["b"])),
        ("KEY_HUB_RIGHT", hub_key_source_owner, hub_key_source,
         key, groups["KEY_HUB_RIGHT"], 0.5 * float(d["b"])),
    )
    planar_copy_counts = {}
    for (interface_name, source_owner, source_faces, target_owner,
         target_faces, target_x) in planar_targets:
        sequence = _copy_planar_template(
            assembly, source_owner, source_faces, target_owner, target_faces,
            target_x, sequence)
        planar_copy_counts[interface_name] = 1
        pattern_audit["immediate_targets"][interface_name] = \
            _surface_pattern_state(target_faces)

    # The hub groove is wider than the shaft slot.  The two resulting narrow
    # non-contact faces are bounded by natural shaft-OD edges that are not part
    # of any copied target face.  Refining only those edges after all copies is
    # safe (it does not invalidate the native patterns) and prevents one coarse
    # 3.8 mm axial segment from creating a near-degenerate clearance tetra.
    clearance_edges = []
    clearance_divisions = 0
    clearance_width = half_opening - float(d["x_slot"])
    if clearance_width > 1.0e-9:
        edge_tolerance = max(1.0e-5, 1.0e-4 * surface_seed)
        for edge in shaft.edges:
            box = shaft.edges[edge.index:edge.index + 1].getBoundingBox()
            low = tuple(float(value) for value in box["low"][:3])
            high = tuple(float(value) for value in box["high"][:3])
            if (abs(abs(0.5 * (low[0] + high[0])) -
                    float(d["x_slot"])) <= edge_tolerance and
                    abs(0.5 * (low[1] + high[1]) -
                        float(levels["shaft_open"])) <= edge_tolerance and
                    low[2] >= z_low - edge_tolerance and
                    high[2] <= z_high + edge_tolerance and
                    high[2] - low[2] > edge_tolerance):
                clearance_edges.append(edge)
        if len(clearance_edges) != 2:
            raise RuntimeError(
                "Expected two natural shaft clearance edges, found %d" %
                len(clearance_edges))
        clearance_divisions = max(
            1, int(math.ceil(axial_length / surface_seed - 1.0e-12)))
        assembly.seedEdgeByNumber(
            edges=tuple(clearance_edges), number=clearance_divisions,
            constraint=AC.FINER)
    mesh_info["Shaft"]["clearance_edge_seeds"] = {
        "edges": len(clearance_edges), "divisions": clearance_divisions,
        "clearance_width_mm": clearance_width}

    def fill_physical_volume(physical_name, physical_instance):
        fill_started = time.time()
        assembly.generateMesh(regions=(physical_instance,))
        mesh_info[physical_name]["seconds"] = round(
            float(mesh_info[physical_name].get("seconds", 0.0)) +
            time.time() - fill_started, 3)
        empty_cells = [int(cell.index) for cell in physical_instance.cells
                       if not len(cell.getElements())]
        if empty_cells:
            raise RuntimeError(
                "Copied-interface volume has unmeshed cells for %s: %s" %
                (physical_name, empty_cells))
        if not len(physical_instance.nodes) or not len(physical_instance.elements):
            raise RuntimeError("Copied-interface mesh is empty for %s" %
                               physical_name)
        allowed_codes = set(mesh_plan["element_profile"]["allowed_types"])
        realised_codes = sorted(set(
            str(element.type) for element in physical_instance.elements))
        unexpected = sorted(set(realised_codes) - allowed_codes)
        if unexpected:
            raise RuntimeError(
                "Unexpected residual element types for %s: %s; allowed=%s" %
                (physical_name, unexpected, sorted(allowed_codes)))
        if hybrid and not any(code.startswith("C3D20")
                              for code in realised_codes):
            raise RuntimeError(
                "Hybrid volume %s contains no quadratic hexahedron" %
                physical_name)
        if not hybrid:
            expected_code = "C3D10" if order == "quadratic" else "C3D4"
            if realised_codes != [expected_code]:
                raise RuntimeError(
                    "Legacy connected volume %s changed element family: %s" %
                    (physical_name, realised_codes))

    # Hub is completed first.  Its verified physical bore pattern is then
    # copied once to Shaft, avoiding independent source-to-target projections.
    fill_physical_volume("Hub", hub)
    groups = _interface_face_groups(assembly, d, levels)
    for audit_name in ("HUB_SHAFT", "HUB_KEY_LEFT", "HUB_KEY_RIGHT"):
        pattern_audit["filled_targets"][audit_name] = \
            _surface_pattern_state(groups[audit_name])
    shaft_radial_pairs, shaft_radial_extras = _pair_faces(
        hub, groups["HUB_SHAFT"], shaft, groups["SHAFT_HUB_ALL"],
        "RADIAL_XYZ", allow_target_extras=True)
    radial_copy_counts["Shaft"] = {
        "copied_patches": len(shaft_radial_pairs),
        "target_extra_patches": len(shaft_radial_extras),
        "source": "FILLED_HUB_PHYSICAL_BORE"}
    shaft_hub_pattern_faces = shaft.faces[0:0]
    for _signature, source_face, target_face in shaft_radial_pairs:
        _copy_face_pattern(
            assembly, hub, source_face, target_face, sequence)
        sequence += 1
        shaft_hub_pattern_faces = (
            shaft_hub_pattern_faces +
            shaft.faces[target_face.index:target_face.index + 1])
    pattern_audit["immediate_targets"]["SHAFT_HUB"] = \
        _surface_pattern_state(shaft_hub_pattern_faces)
    fill_physical_volume("Shaft", shaft)
    fill_physical_volume("Key", key)
    groups = _interface_face_groups(assembly, d, levels)
    pattern_audit["filled_targets"]["SHAFT_HUB"] = \
        _surface_pattern_state(shaft_hub_pattern_faces)
    for audit_name in (
            "SHAFT_KEY_LEFT", "SHAFT_KEY_RIGHT", "KEY_SHAFT_LEFT",
            "KEY_SHAFT_RIGHT", "HUB_KEY_LEFT", "HUB_KEY_RIGHT",
            "KEY_HUB_LEFT", "KEY_HUB_RIGHT"):
        pattern_audit["filled_targets"][audit_name] = \
            _surface_pattern_state(groups[audit_name])
    if hybrid:
        pattern_failures = sorted(
            name for name, state in pattern_audit["filled_targets"].items()
            if not state.get("structured_quadrilateral_pattern"))
        if pattern_failures:
            raise RuntimeError(
                "Hybrid copied interface pattern lost quadrilateral topology: %s" %
                ", ".join(pattern_failures))
        pattern_audit["quadrilateral_gate"] = "PASS"
    else:
        pattern_audit["quadrilateral_gate"] = "NOT_REQUIRED_V1"

    # Templates are construction aids only and must never reach contact, output
    # requests, a saved CAE, or a potential analysis Job.
    for instance_name in auxiliary_instances:
        if instance_name in assembly.instances:
            del assembly.instances[instance_name]
    for part_name in auxiliary_parts:
        if part_name in model.parts:
            del model.parts[part_name]
    assembly.regenerate()

    groups = _interface_face_groups(assembly, d, levels)
    radial_pairs, radial_extras = _pair_faces(
        hub, groups["HUB_SHAFT"], shaft, groups["SHAFT_HUB_ALL"],
        "RADIAL_XYZ", allow_target_extras=True)
    shaft_hub_faces = shaft.faces[0:0]
    for _signature, _source, target_face in radial_pairs:
        shaft_hub_faces = (shaft_hub_faces +
                           shaft.faces[target_face.index:target_face.index + 1])
    interface_faces = {
        "SHAFT_KEY_LEFT": (groups["SHAFT_KEY_LEFT"],
                           groups["KEY_SHAFT_LEFT"]),
        "SHAFT_KEY_RIGHT": (groups["SHAFT_KEY_RIGHT"],
                            groups["KEY_SHAFT_RIGHT"]),
        "HUB_KEY_LEFT": (groups["HUB_KEY_LEFT"], groups["KEY_HUB_LEFT"]),
        "HUB_KEY_RIGHT": (groups["HUB_KEY_RIGHT"], groups["KEY_HUB_RIGHT"]),
        "SHAFT_HUB": (groups["HUB_SHAFT"], shaft_hub_faces),
    }
    interface_mesh = {}
    failures = []
    size_tolerance = max(1.0e-5, 1.0e-3 * target)
    for interface_name in REQUIRED_MATCHING_INTERFACES:
        pair = interface_faces[interface_name]
        first_max, first_facets, first_topology = _surface_max_element_edge(pair[0])
        second_max, second_facets, second_topology = _surface_max_element_edge(pair[1])
        realised = max(first_max, second_max)
        target_passed = realised <= target + size_tolerance
        absolute_passed = realised <= ABSOLUTE_INTERFACE_EDGE_LIMIT_MM + 1.0e-12
        quadrilateral_passed = (
            not hybrid or
            (first_topology.get("QUAD", 0) > 0 and
             second_topology.get("QUAD", 0) > 0 and
             first_topology.get("TRI", 0) == 0 and
             second_topology.get("TRI", 0) == 0 and
             first_topology.get("UNKNOWN", 0) == 0 and
             second_topology.get("UNKNOWN", 0) == 0))
        passed = target_passed and absolute_passed and quadrilateral_passed
        interface_mesh[interface_name] = {
            "target_max_edge_mm": target,
            "absolute_max_edge_limit_mm": ABSOLUTE_INTERFACE_EDGE_LIMIT_MM,
            "edge_measurement": "ELEMENT_FACE_CORNER_CONNECTIVITY",
            "source_seed_mm": surface_seed,
            "first_max_edge_mm": first_max,
            "second_max_edge_mm": second_max,
            "realised_max_edge_mm": realised,
            "first_element_faces": first_facets,
            "second_element_faces": second_facets,
            "first_facet_topology": first_topology,
            "second_facet_topology": second_topology,
            "target_passed": target_passed,
            "absolute_1mm_passed": absolute_passed,
            "quadrilateral_passed": quadrilateral_passed,
            "passed": passed}
        if not passed:
            failures.append(
                "%s edge=%.9g target=%s absolute_1mm=%s quad=%s" %
                (interface_name, realised, target_passed,
                 absolute_passed, quadrilateral_passed))
    if failures:
        raise RuntimeError("Interface mesh hard gate failed: %s" %
                           "; ".join(failures))

    reports = {}
    instances = {"Shaft": shaft, "Key": key, "Hub": hub}
    radii = {"Shaft": float(d["r2"]), "Key": 0.0,
             "Hub": float(d["r1"])}
    for part_name in ("Shaft", "Key", "Hub"):
        metrics = _instance_metrics(
            assembly, instances[part_name], base, radii[part_name],
            mesh_info[part_name])
        policy = mesh_plan["parts"][part_name]
        quality = core.evaluate_mesh_quality(part_name, metrics, policy)
        reports[part_name] = {
            "types": metrics["types"], "repairs": 0,
            "notch": {"fillet_arc_edges": mesh_info[part_name].get(
                "fillet_arc_edges", 0), "band": 0,
                "method": ("HYBRID_HEX_LOCAL_ARC_SEED" if hybrid else
                           "ISOTROPIC_FREE_TET_LOCAL_ARC_SEED")},
            "selected_recipe": {
                "recipe_id": ("FVA_TEMPLATE_COPIED_INTERFACE_HYBRID_HEX"
                              if hybrid else
                              "FVA_TEMPLATE_COPIED_INTERFACE_FREE_TET"),
                "control_strategy": ("HEX_DOMINATED" if hybrid else
                                     "FREE_TET"),
                "bulk_size_mm": bulk_sizes[part_name],
                "surface_seed_mm": surface_seed,
                "target_max_interface_edge_mm": target},
            "selected_attempt_index": 0, "attempts": [],
            "metrics_scope": "ASSEMBLY_INSTANCE",
            "metrics": metrics, "quality": quality,
            "winner_reproduced": False,
            "winner_reproduction_match": None,
            "winner_signature_exact": None,
            "winner_reproduction_deltas": {},
            "winner_reproduction_error": None,
            "edge_divisions": mesh_info[part_name].get(
                "surface_edge_seeds", {}),
            "clearance_edge_seeds": mesh_info[part_name].get(
                "clearance_edge_seeds"),
            "nodes": metrics["nodes"],
            "elements": metrics["elements"],
            "hex_count": metrics["hex_count"],
            "non_hex_count": metrics["non_hex_count"],
            "non_hex_pct": metrics["non_hex_pct"],
            "hex_pct": metrics["hex_pct"],
            "warnings": metrics["warnings"],
            "ar_bulk_worst": metrics["ar_bulk_worst"],
            "seconds": metrics["seconds"]}
        if quality.get("hard_passed") is not True:
            raise RuntimeError("Matching mesh hard quality gate failed for %s: %s" %
                               (part_name, quality.get("hard_reasons")))

    template_stats = {"radial": radial_stats,
                      "shaft_key": shaft_key_stats,
                      "hub_key": hub_key_stats}
    params["_mesh_plan"] = mesh_plan
    params["_mesh_report"] = reports
    params["_fva_interface_mesh"] = {
        "backend": backend_id,
        "method": ("DISPOSABLE_STRUCTURED_QUAD_TEMPLATE_COPY_THEN_"
                   "QUADRATIC_HYBRID_HEX_FILL" if hybrid else
                   "DISPOSABLE_TEMPLATE_COPY_PATTERN_THEN_TET_FILL"),
        "volume_topology": physical_topology,
        "surface_topology": ("STRUCTURED_QUADRILATERAL" if hybrid else
                             "LEGACY_TRIANGULAR"),
        "element_order": order,
        "element_profile": mesh_plan.get("element_profile"),
        "tet_element": "C3D10" if order == "quadratic" else "C3D4",
        "hard_gates": {
            "max_non_hex_pct": 50.0 if hybrid else 100.0,
            "at_least_one_hex_per_piece": bool(hybrid),
            "absolute_interface_edge_limit_mm":
                ABSOLUTE_INTERFACE_EDGE_LIMIT_MM,
            "five_interfaces": list(REQUIRED_MATCHING_INTERFACES)},
        "target_max_edge_mm": target, "surface_seed_mm": surface_seed,
        "bulk_sizes_mm": bulk_sizes, "template_stats": template_stats,
        "pattern_preservation_audit": pattern_audit,
        "clearance_edge_seeds": mesh_info["Shaft"].get(
            "clearance_edge_seeds"),
        "radial_source_chain": ["DISPOSABLE_RADIAL_TEMPLATE",
                                "FILLED_HUB_PHYSICAL_BORE", "SHAFT"],
        "copied_pattern_operations": sequence,
        "radial_copy_counts": radial_copy_counts,
        "planar_copy_counts": planar_copy_counts,
        "radial_physical_extra_patches": len(radial_extras),
        "templates_removed": all(name not in model.parts
                                 for name in auxiliary_parts),
        "interfaces": interface_mesh}
    params["_mesh_quality"] = core.aggregate_mesh_quality(
        dict((name, item["quality"]) for name, item in reports.items()),
        mesh_plan.get("fail_on_quality", True))
    return reports


def _material_name(component, model_id):
    compact = str(model_id).replace("CHABOCHE_LEMAITRE_", "CHABOCHE_")
    return ("FVA_%s_%s" % (component.upper(), compact))[:80]


def assign_material_models(model, params, d, base):
    import abaqusConstants as AC

    cfg = _fva(params)
    intervals = int((((cfg.get("materials", {}) or {}).get("hub", {}) or {}).get(
        "intervals", 150)) or 150)
    bundle = methods.material_model_bundle(
        cfg.get("material_pair"), d["D"], cfg.get("material_models"), intervals)
    density = float(cfg.get("density_tonne_per_mm3", 7.85e-09))
    assignments = {}
    for component, part_name, section_key in (
            ("shaft", "Shaft", base.MAT_SHAFT),
            ("hub", "Hub", base.MAT_HUB),
            ("key", "Key", base.MAT_KEY)):
        item = bundle[component]
        material_name = _material_name(component, item["model"])
        if material_name in model.materials:
            del model.materials[material_name]
        description = ("FVA 600 III %s; %s; %s" %
                       (component, item["grade"], item["model"]))
        # Abaqus 2022 rejects Python-2 ``unicode`` for string-dictionary
        # fields even when every character is ASCII.  Python 3 already returns
        # ``str`` here, so encode only when the runtime value is not ``str``.
        if not isinstance(description, str):
            description = description.encode("ascii")
        material = model.Material(name=material_name,
                                  description=description)
        material.Elastic(table=((float(item["E_MPa"]),
                                 float(item.get("nu", 0.30))),))
        material.Density(table=((density,),))
        if item["model"] == methods.SHAFT_MODEL_COMBINED:
            combined = item["combined"]
            constants = [float(item["yield_MPa"])]
            for modulus, gamma in zip(combined["C_i_MPa"],
                                      combined["gamma_i"]):
                constants.extend((float(modulus), float(gamma)))
            material.Plastic(
                hardening=AC.COMBINED, dataType=AC.PARAMETERS,
                numBackstresses=len(combined["C_i_MPa"]),
                table=(tuple(constants),))
            material.plastic.CyclicHardening(
                parameters=AC.ON,
                table=((float(item["yield_MPa"]),
                        float(combined["Q_inf_MPa"]),
                        float(combined["b_iso"])),))
        elif item["model"] == methods.HUB_MODEL_UML:
            material.Plastic(hardening=AC.ISOTROPIC,
                             table=tuple(tuple(row) for row in
                                         item["plastic_table"]))
        elif item["model"] == methods.MODEL_ELASTIC_IDEAL_PLASTIC:
            yield_value = float(item["yield_MPa"])
            material.Plastic(
                hardening=AC.ISOTROPIC,
                table=((yield_value, 0.0), (yield_value, 1.0)))
        elif item["model"] != methods.MODEL_LINEAR_ELASTIC:
            raise RuntimeError("Unhandled material model %s" % item["model"])

        section_name = base.SEC[section_key]
        model.sections[section_name].setValues(material=material_name)
        assignments[component] = {
            "part": part_name, "section": section_name,
            "material": material_name, "model": item["model"],
            "grade": item["grade"]}
    return {"bundle": bundle, "assignments": assignments,
            "density_tonne_per_mm3": density}


def _surface_nodes(faces):
    nodes = {}
    for face in faces:
        for node in face.getNodes():
            nodes[int(node.label)] = node
    return [nodes[label] for label in sorted(nodes)]


def _projected(points, indices):
    return [tuple(point[index] for index in indices) for point in points]


def _compare_clouds(name, first_nodes, second_nodes, indices, tolerance):
    """One-to-one spatial cloud comparison, independent of node ordering.

    Lexicographic ``zip(sorted(A), sorted(B))`` can pair different z rows when
    nominally equal y coordinates differ by one ACIS float unit, fabricating a
    30+ mm error.  Hash buckets plus neighbouring-cell search report the true
    Chebyshev coordinate delta and still reject missing/duplicate nodes.
    """
    first = _projected([_node_point(node) for node in first_nodes], indices)
    second = _projected([_node_point(node) for node in second_nodes], indices)
    result = {"interface": name, "first_nodes": len(first),
              "second_nodes": len(second), "tolerance_mm": tolerance,
              "projection_indices": list(indices), "matched": False,
              "max_coordinate_delta_mm": None}
    if len(first) != len(second):
        result["reason"] = "NODE_COUNT_MISMATCH"
        return result
    if not first:
        result["reason"] = "EMPTY_INTERFACE"
        return result
    cell = max(float(tolerance), 1.0e-12)

    def bucket_key(point):
        return tuple(int(math.floor(value / cell)) for value in point)

    buckets = {}
    for index, point in enumerate(second):
        buckets.setdefault(bucket_key(point), []).append(index)
    used = set()
    maximum = 0.0
    offsets = [()]
    for _axis in indices:
        offsets = [prefix + (value,) for prefix in offsets
                   for value in (-1, 0, 1)]
    for point in sorted(first):
        key = bucket_key(point)
        candidates = []
        for offset in offsets:
            neighbour = tuple(key[index] + offset[index]
                              for index in range(len(key)))
            for candidate_index in buckets.get(neighbour, ()):
                if candidate_index in used:
                    continue
                other = second[candidate_index]
                delta = max(abs(point[index] - other[index])
                            for index in range(len(point)))
                if delta <= tolerance:
                    candidates.append((delta, candidate_index))
        if not candidates:
            result["reason"] = "COORDINATE_MISMATCH"
            result["matched_nodes"] = len(used)
            return result
        delta, chosen = min(candidates)
        used.add(chosen)
        maximum = max(maximum, delta)
    result["max_coordinate_delta_mm"] = maximum
    result["matched"] = len(used) == len(second)
    result["reason"] = "MATCH" if result["matched"] else "DUPLICATE_NODE_MATCH"
    result["matched_nodes"] = len(used)
    return result


def _rectangular_subgrid_keys(keys):
    """Select a maximum rectangular Cartesian product covering all bounds.

    Quadratic serendipity faces have corner and midside nodes but no face-centre
    node.  Therefore all unique coordinates do not form a product.  Complete
    row/column families recover a deterministic corner-compatible subgrid.
    """
    key_set = set(tuple(item) for item in keys)
    if not key_set:
        raise RuntimeError("Opening-grid coordinate set is empty")
    ys = sorted(set(item[0] for item in key_set))
    zs = sorted(set(item[1] for item in key_set))
    if len(ys) < 2 or len(zs) < 2:
        raise RuntimeError("Opening grid needs at least two coordinates per axis")
    candidates = []

    def add_candidate(candidate_ys, candidate_zs, strategy):
        candidate_ys = sorted(set(candidate_ys))
        candidate_zs = sorted(set(candidate_zs))
        if len(candidate_ys) < 2 or len(candidate_zs) < 2:
            return
        if (candidate_ys[0] != ys[0] or candidate_ys[-1] != ys[-1] or
                candidate_zs[0] != zs[0] or candidate_zs[-1] != zs[-1]):
            return
        product = set((y_value, z_value)
                      for y_value in candidate_ys
                      for z_value in candidate_zs)
        if product.issubset(key_set):
            candidates.append({
                "ys": candidate_ys, "zs": candidate_zs,
                "keys": sorted(product), "strategy": strategy,
                "count": len(product)})

    complete_rows = [y_value for y_value in ys
                     if all((y_value, z_value) in key_set for z_value in zs)]
    complete_columns = [z_value for z_value in zs
                        if all((y_value, z_value) in key_set for y_value in ys)]
    add_candidate(complete_rows, zs, "COMPLETE_ROWS_X_ALL_COLUMNS")
    add_candidate(ys, complete_columns, "ALL_ROWS_X_COMPLETE_COLUMNS")

    row_groups = {}
    for y_value in ys:
        signature = tuple(z_value for z_value in zs
                          if (y_value, z_value) in key_set)
        row_groups.setdefault(signature, []).append(y_value)
    for signature, group_ys in row_groups.items():
        add_candidate(group_ys, signature, "IDENTICAL_ROW_SIGNATURES")
    column_groups = {}
    for z_value in zs:
        signature = tuple(y_value for y_value in ys
                          if (y_value, z_value) in key_set)
        column_groups.setdefault(signature, []).append(z_value)
    for signature, group_zs in column_groups.items():
        add_candidate(signature, group_zs, "IDENTICAL_COLUMN_SIGNATURES")

    if not candidates:
        raise RuntimeError(
            "No Cartesian opening subgrid covers the complete coordinate bounds")
    candidates.sort(key=lambda item: (
        item["count"], min(len(item["ys"]), len(item["zs"])),
        len(item["ys"]), item["strategy"]), reverse=True)
    selected = candidates[0]
    selected["candidate_count"] = len(candidates)
    selected["source_coordinate_counts"] = {"y": len(ys), "z": len(zs)}
    return selected


def _opening_node_map(nodes, tolerance, side):
    mapping = {}
    for node in nodes:
        point = _node_point(node)
        key = (int(round(point[1] / tolerance)),
               int(round(point[2] / tolerance)))
        if key in mapping and int(mapping[key].label) != int(node.label):
            raise RuntimeError(
                "%s opening candidates have duplicate coordinate %r" %
                (side, key))
        mapping[key] = node
    if not mapping:
        raise RuntimeError("%s opening candidates are empty" % side)
    return mapping


def _sha256_json(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if not isinstance(payload, bytes):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select_opening_cartesian_subgrid(assembly, shaft, params, d, levels,
                                     candidate_nodes=None):
    """Create paired opening node sets and durable rectangular-grid evidence."""
    matching_cfg = _fva(params).get("mesh_matching", {}) or {}
    requested_tolerance = float(matching_cfg.get("tolerance_mm", 1.0e-6))
    tolerance = max(requested_tolerance, 5.0e-5)
    x_slot = float(d["x_slot"])
    y_low = float(levels["shaft_low"])
    y_high = float(levels["flank_transition"])
    z_low = float(levels["z_low"])
    z_high = float(levels["z_high"])
    band = max(tolerance * 2.0, 1.0e-5)
    if candidate_nodes is not None:
        left_candidates = tuple(candidate_nodes.get("left") or ())
        right_candidates = tuple(candidate_nodes.get("right") or ())
        candidate_source = "TIED_STRUCTURED_SHAFT_CONTACT_SKINS"
    else:
        left_candidates = shaft.nodes.getByBoundingBox(
            xMin=-x_slot - band, xMax=-x_slot + band,
            yMin=y_low - band, yMax=y_high + band,
            zMin=z_low - band, zMax=z_high + band)
        right_candidates = shaft.nodes.getByBoundingBox(
            xMin=x_slot - band, xMax=x_slot + band,
            yMin=y_low - band, yMax=y_high + band,
            zMin=z_low - band, zMax=z_high + band)
        candidate_source = "PHYSICAL_SHAFT_FLANK_NODES_V1"
    left_map = _opening_node_map(left_candidates, tolerance, "LEFT")
    right_map = _opening_node_map(right_candidates, tolerance, "RIGHT")
    common = sorted(set(left_map) & set(right_map))
    missing_left = sorted(set(right_map) - set(left_map))
    missing_right = sorted(set(left_map) - set(right_map))
    selected = _rectangular_subgrid_keys(common)
    selected_keys = selected["keys"]
    left_nodes = tuple(left_map[key] for key in selected_keys)
    right_nodes = tuple(right_map[key] for key in selected_keys)
    _replace_node_label_set(
        assembly, "FVA_SET_SHAFT_KEYWAY_LEFT", left_nodes)
    _replace_node_label_set(
        assembly, "FVA_SET_SHAFT_KEYWAY_RIGHT", right_nodes)

    y_values = []
    z_values = []
    for key in selected_keys:
        left_point = _node_point(left_map[key])
        right_point = _node_point(right_map[key])
        y_values.append(0.5 * (left_point[1] + right_point[1]))
        z_values.append(0.5 * (left_point[2] + right_point[2]))
    realised_y_low, realised_y_high = min(y_values), max(y_values)
    realised_z_low, realised_z_high = min(z_values), max(z_values)
    physical_depth_span = realised_y_high - realised_y_low
    physical_axial_span = realised_z_high - realised_z_low
    if physical_depth_span <= 0.0 or physical_axial_span <= 0.0:
        raise RuntimeError("Opening Cartesian grid has a non-positive span")
    bounds_passed = (
        abs(realised_y_low - y_low) <= tolerance and
        abs(realised_y_high - y_high) <= tolerance and
        abs(realised_z_low - z_low) <= tolerance and
        abs(realised_z_high - z_high) <= tolerance)
    if not bounds_passed:
        raise RuntimeError(
            "Opening Cartesian grid does not cover complete interface bounds")

    din_record = d.get("din6892", {}) or {}
    effective = (din_record.get("derived", {}) or {}).get(
        "effective_bearing_depth", {}) or {}
    ltr = float(d["load_bearing_length"])
    t1tr = float(effective.get("t1tr_mm", 0.0) or 0.0)
    upf = float((params.get("din6892", {}) or {}).get("UPF_um", 0.0) or 0.0)
    if min(ltr, t1tr, upf) <= 0.0:
        raise RuntimeError("Opening-grid ltr/t1tr/UPF invariants must be positive")
    axial_scale = ltr / physical_axial_span
    depth_scale = t1tr / physical_depth_span
    pairs = []
    for key in selected_keys:
        left_node = left_map[key]
        right_node = right_map[key]
        left_point = _node_point(left_node)
        right_point = _node_point(right_node)
        physical_y = 0.5 * (left_point[1] + right_point[1])
        physical_z = 0.5 * (left_point[2] + right_point[2])
        pairs.append({
            "left_label": int(left_node.label),
            "right_label": int(right_node.label),
            "physical_y_mm": physical_y,
            "physical_z_mm": physical_z,
            "x_mm": (physical_z - realised_z_low) * axial_scale,
            "z_mm": (physical_y - realised_y_low) * depth_scale})
    integration_area = ltr * t1tr
    evidence = {
        "status": "PASS",
        "candidate_source": candidate_source,
        "selection_strategy": selected["strategy"],
        "rectangular_product": True,
        "bounds_coverage": "FULL",
        "bounds_passed": bounds_passed,
        "pairing_status": "MATCHED",
        "requested_tolerance_mm": requested_tolerance,
        "effective_tolerance_mm": tolerance,
        "candidate_counts": {
            "left": len(left_map), "right": len(right_map),
            "common": len(common), "missing_left": len(missing_left),
            "missing_right": len(missing_right)},
        "selected_pair_count": len(pairs),
        "excluded_common_count": len(common) - len(pairs),
        "grid_shape": {"depth_y_count": len(selected["ys"]),
                       "axial_z_count": len(selected["zs"]),
                       "product": len(selected["ys"]) * len(selected["zs"])},
        "physical_bounds_mm": {
            "y": [realised_y_low, realised_y_high],
            "z": [realised_z_low, realised_z_high]},
        "required_physical_bounds_mm": {
            "y": [y_low, y_high], "z": [z_low, z_high]},
        "integration_bounds_mm": {"x": [0.0, ltr], "z": [0.0, t1tr]},
        "coordinate_transform": {
            "x_from_global_z": {"origin_mm": realised_z_low,
                                "scale": axial_scale},
            "z_from_global_y": {"origin_mm": realised_y_low,
                                "scale": depth_scale}},
        "coverage": {
            "expected_area_mm2": integration_area,
            "grid_area_mm2": integration_area,
            "grid_over_expected": 1.0,
            "within_2_percent": True},
        "invariants": {"ltr_mm": ltr, "t1tr_mm": t1tr, "UPF_um": upf},
        "left_labels": [item["left_label"] for item in pairs],
        "right_labels": [item["right_label"] for item in pairs],
        "pairs": pairs,
    }
    evidence["pairs_sha256"] = _sha256_json(pairs)
    evidence["invariants_sha256"] = _sha256_json(evidence["invariants"])
    return evidence


def create_interface_surfaces(model, d, partition_info, target,
                              skin_data=None):
    assembly = model.rootAssembly
    instances = {
        "shaft": assembly.instances["SHAFT-1"],
        "key": assembly.instances["KEY-1"],
        "hub": assembly.instances["HUB-1"],
    }
    levels = partition_info["levels"]
    zlo, zhi = levels["z_low"], levels["z_high"]
    tolerance = max(1.0e-5, float(target) * 0.02)
    b2 = 0.5 * float(d["b"])
    gw2 = 0.5 * float(d["groove_w"])

    def near(value, expected):
        return abs(value - expected) <= tolerance

    def in_range(value, low, high):
        return low - tolerance <= value <= high + tolerance

    groups = _interface_face_groups(assembly, d, levels)
    radial_pairs, radial_extras = _pair_faces(
        instances["hub"], groups["HUB_SHAFT"],
        instances["shaft"], groups["SHAFT_HUB_ALL"],
        "RADIAL_XYZ", allow_target_extras=True)
    shaft_hub = instances["shaft"].faces[0:0]
    for _signature, _source, target_face in radial_pairs:
        shaft_hub = (shaft_hub + instances["shaft"].faces[
            target_face.index:target_face.index + 1])

    solid_face_arrays = {
        "SHAFT_KEY_LEFT": groups["SHAFT_KEY_LEFT"],
        "SHAFT_KEY_RIGHT": groups["SHAFT_KEY_RIGHT"],
        "KEY_SHAFT_LEFT": groups["KEY_SHAFT_LEFT"],
        "KEY_SHAFT_RIGHT": groups["KEY_SHAFT_RIGHT"],
        "HUB_KEY_LEFT": groups["HUB_KEY_LEFT"],
        "HUB_KEY_RIGHT": groups["HUB_KEY_RIGHT"],
        "KEY_HUB_LEFT": groups["KEY_HUB_LEFT"],
        "KEY_HUB_RIGHT": groups["KEY_HUB_RIGHT"],
        "SHAFT_HUB": shaft_hub,
        "HUB_SHAFT": groups["HUB_SHAFT"],
    }
    face_arrays = dict(solid_face_arrays)
    if skin_data is not None:
        face_arrays.update(skin_data["faces"])

    # Non-matching closure contacts retained for physical interconnection.
    face_arrays["SHAFT_FLOOR"] = _select_faces(
        instances["shaft"],
        lambda p: near(p[1], float(d["yF"])) and abs(p[0]) <= b2 and
        in_range(p[2], zlo, zhi), "shaft keyway floor")
    face_arrays["KEY_BOTTOM"] = _select_faces(
        instances["key"],
        lambda p: near(p[1], float(d["y_min"])) and abs(p[0]) <= b2 and
        in_range(p[2], zlo, zhi), "key bottom")
    face_arrays["HUB_ROOF"] = _select_faces(
        instances["hub"],
        lambda p: near(p[1], float(d["groove_roof"])) and abs(p[0]) <= gw2 and
        in_range(p[2], zlo, zhi), "hub keyway roof")
    face_arrays["KEY_TOP"] = _select_faces(
        instances["key"],
        lambda p: p[1] >= float(d["y_min"] + d["h"] - d["c"]) - tolerance and
        abs(p[0]) <= b2 + tolerance and in_range(p[2], zlo, zhi), "key top")

    if skin_data is not None:
        for name, faces in solid_face_arrays.items():
            _replace_surface(assembly, "FVA_SOLID_SURF_" + name, faces)
    for name, faces in face_arrays.items():
        _replace_surface(assembly, "FVA_SURF_" + name, faces)
    assembly.regenerate()
    opening_nodes = None
    if skin_data is not None:
        opening_nodes = {
            "left": _surface_nodes(face_arrays["SHAFT_KEY_LEFT"]),
            "right": _surface_nodes(face_arrays["SHAFT_KEY_RIGHT"])}
    return {"instances": instances, "faces": face_arrays,
            "solid_faces": solid_face_arrays,
            "skin_data": skin_data, "opening_nodes": opening_nodes,
            "face_counts": dict((name, len(faces))
                                for name, faces in face_arrays.items())}


def verify_matching_mesh(surface_data, config):
    faces = surface_data["faces"]
    requested_tolerance = float(config.get("tolerance_mm", 1.0e-6))
    # Native cylindrical mesh patterns copied Hub -> Shaft in Abaqus 2022 are
    # re-projected onto the target ACIS face.  A 21,930-node D40 diagnostic
    # proved one-to-one correspondence with a worst Cartesian delta of
    # 3.522634506225586e-05 mm (35.2 nm), including identical node counts and
    # facet counts.  Fifty nanometres is a conservative single-precision
    # geometry-kernel floor; it is 20,000x smaller than the 1 mm mesh limit and
    # over 200x smaller than the 0.01075 mm physical clearance strip.
    kernel_floor = 5.0e-5
    tolerance = max(requested_tolerance, kernel_floor)
    pair_defs = (
        ("SHAFT_KEY_LEFT", "SHAFT_KEY_LEFT", "KEY_SHAFT_LEFT", (1, 2)),
        ("SHAFT_KEY_RIGHT", "SHAFT_KEY_RIGHT", "KEY_SHAFT_RIGHT", (1, 2)),
        ("HUB_KEY_LEFT", "HUB_KEY_LEFT", "KEY_HUB_LEFT", (1, 2)),
        ("HUB_KEY_RIGHT", "HUB_KEY_RIGHT", "KEY_HUB_RIGHT", (1, 2)),
        ("SHAFT_HUB", "SHAFT_HUB", "HUB_SHAFT", (0, 1, 2)),
    )
    details = []
    for name, first, second, projection in pair_defs:
        details.append(_compare_clouds(
            name, _surface_nodes(faces[first]), _surface_nodes(faces[second]),
            projection, tolerance))
    passed = all(item["matched"] for item in details)
    result = {"status": "MATCHED" if passed else "MISMATCH",
              "verified": passed, "interfaces": details,
              "requested_tolerance_mm": requested_tolerance,
              "effective_tolerance_mm": tolerance,
              "kernel_coordinate_floor_mm": kernel_floor,
              "tolerance_mm": tolerance,
              "method": "ACTUAL_ASSEMBLY_NODE_SPATIAL_HASH_COMPARISON",
              "construction": (
                  "PAIRED_TIED_S8R_STRUCTURED_CONTACT_SKINS"
                  if surface_data.get("skin_data") is not None else
                  "COPY_MESH_PATTERN_THEN_VOLUME_FILL"),
              "nominal_seed_alone_accepted": False}
    if not passed:
        failed = [item["interface"] + ":" + item["reason"]
                  for item in details if not item["matched"]]
        raise RuntimeError("Contact mesh matching failed: %s" % ", ".join(failed))
    return result


def _contact_property(model, name, friction, config):
    import abaqusConstants as AC

    prop = model.ContactProperty(name)
    prop.TangentialBehavior(
        formulation=AC.PENALTY, directionality=AC.ISOTROPIC,
        slipRateDependency=AC.OFF, pressureDependency=AC.OFF,
        temperatureDependency=AC.OFF, dependencies=0,
        table=((float(friction),),), shearStressLimit=None,
        maximumElasticSlip=AC.ABSOLUTE_DISTANCE,
        absoluteDistance=float(config.get("elastic_slip_mm", 0.001)),
        elasticSlipStiffness=None)
    prop.NormalBehavior(
        contactStiffness=float(config.get(
            "normal_stiffness_N_per_mm3", 1.0e7)),
        pressureOverclosure=AC.HARD, allowSeparation=AC.ON,
        constraintEnforcementMethod=AC.PENALTY)
    return prop


def _create_contact(model, assembly, name, main_name, secondary_name,
                    interference=None, direction=None):
    import abaqusConstants as AC

    kwargs = dict(
        name=name, createStepName=STEP_FIT,
        main=assembly.surfaces["FVA_SURF_" + main_name],
        secondary=assembly.surfaces["FVA_SURF_" + secondary_name],
        sliding=AC.FINITE, interactionProperty=PROP_FIT,
        adjustMethod=AC.NONE, initialClearance=AC.OMIT)
    if interference is not None and float(interference) > 0.0:
        kwargs.update(interferenceType=AC.UNIFORM,
                      overclosure=float(interference),
                      amplitude=AMP_FIT_RAMP)
        if direction is not None:
            kwargs["interferenceDirectionType"] = AC.DIRECTION_COSINE
            kwargs["direction"] = tuple(float(value) for value in direction)
    interaction = model.SurfaceToSurfaceContactStd(**kwargs)
    step_values = {"stepName": STEP_FRICTION,
                   "interactionProperty": PROP_SERVICE}
    if interference is not None and float(interference) > 0.0:
        step_values["amplitude"] = AMP_FIT_HOLD
    interaction.setValuesInStep(**step_values)
    return interaction


def _torque_amplitude(load_ratio, cycles, total_time):
    normalized = methods.normalized_amplitude(load_ratio, cycles)
    return tuple((float(time_value) * float(total_time), float(value))
                 for time_value, value in normalized["points"])


def _create_interface_skin_ties(model, assembly, surfaces):
    import abaqusConstants as AC

    if surfaces.get("skin_data") is None:
        return []
    names = (
        "SHAFT_KEY_LEFT", "SHAFT_KEY_RIGHT",
        "KEY_SHAFT_LEFT", "KEY_SHAFT_RIGHT",
        "HUB_KEY_LEFT", "HUB_KEY_RIGHT",
        "KEY_HUB_LEFT", "KEY_HUB_RIGHT",
        "SHAFT_HUB", "HUB_SHAFT")
    created = []
    for surface_name in names:
        constraint_name = "FVA_TIE_SKIN_%s" % surface_name
        if constraint_name in model.constraints:
            del model.constraints[constraint_name]
        model.Tie(
            name=constraint_name,
            main=assembly.surfaces["FVA_SOLID_SURF_" + surface_name],
            secondary=assembly.surfaces["FVA_SURF_" + surface_name],
            positionToleranceMethod=AC.COMPUTED,
            adjust=AC.OFF, tieRotations=AC.ON, thickness=AC.ON)
        created.append(constraint_name)
    return created


def configure_method_a_physics(model, params, d, surfaces):
    import abaqusConstants as AC

    cfg = _fva(params)
    contact = cfg.get("contact", {}) or {}
    steps = cfg.get("steps", {}) or {}
    cycles = int(cfg.get("cycles", 20))
    period = float(steps.get("cycle_period_s", steps.get("cycle_time_s", 2.0)))
    total_time = period * cycles
    fit_time = float(steps.get("contact_time_s", 1.0))
    fit_increment = float(steps.get("contact_increment_s", 0.05))
    friction_time = float(steps.get("friction_time_s", 1.0))

    model.StaticStep(
        name=STEP_FIT, previous="Initial", nlgeom=AC.ON,
        timePeriod=fit_time, initialInc=fit_increment, minInc=1.0e-8,
        maxInc=fit_increment, maxNumInc=max(200, int(fit_time / fit_increment) * 4),
        matrixSolver=AC.DIRECT)
    model.StaticStep(
        name=STEP_FRICTION, previous=STEP_FIT, nlgeom=AC.ON,
        timePeriod=friction_time, initialInc=min(0.05, friction_time),
        minInc=1.0e-8, maxInc=min(0.05, friction_time), maxNumInc=400,
        matrixSolver=AC.DIRECT)
    model.StaticStep(
        name=STEP_CYCLES, previous=STEP_FRICTION, nlgeom=AC.ON,
        timePeriod=total_time, initialInc=period / 20.0,
        minInc=period * 1.0e-7, maxInc=period / 10.0,
        maxNumInc=max(800, cycles * 80), matrixSolver=AC.DIRECT)

    model.TabularAmplitude(
        name=AMP_FIT_RAMP, timeSpan=AC.STEP, smooth=AC.SOLVER_DEFAULT,
        data=((0.0, 0.0), (fit_time, 1.0)))
    model.TabularAmplitude(
        name=AMP_FIT_HOLD, timeSpan=AC.STEP, smooth=AC.SOLVER_DEFAULT,
        data=((0.0, 1.0), (friction_time, 1.0)))
    torque_data = _torque_amplitude(
        (params.get("din6892", {}) or {}).get("load_ratio_R", 0.0),
        cycles, total_time)
    model.TabularAmplitude(
        name=AMP_TORQUE, timeSpan=AC.STEP, smooth=AC.SOLVER_DEFAULT,
        data=torque_data)

    _contact_property(model, PROP_FIT,
                      float(contact.get("friction_fit", 0.0001)), contact)
    _contact_property(model, PROP_SERVICE,
                      float(contact.get("friction_service", 0.2)), contact)
    assembly = model.rootAssembly
    skin_ties = _create_interface_skin_ties(
        model, assembly, surfaces)
    half = float(contact.get("interference_per_flank_mm", 0.009))
    radial_fit = (float(d["D"]) *
                  float((params.get("din6892", {}) or {}).get(
                      "xi_per_mille", 0.0)) / 2000.0)
    pairs = (
        ("FVA_CONTACT_SHAFT_KEY_LEFT", "SHAFT_KEY_LEFT", "KEY_SHAFT_LEFT",
         half, (1.0, 0.0, 0.0)),
        ("FVA_CONTACT_SHAFT_KEY_RIGHT", "SHAFT_KEY_RIGHT", "KEY_SHAFT_RIGHT",
         half, (-1.0, 0.0, 0.0)),
        ("FVA_CONTACT_HUB_KEY_LEFT", "HUB_KEY_LEFT", "KEY_HUB_LEFT", None, None),
        ("FVA_CONTACT_HUB_KEY_RIGHT", "HUB_KEY_RIGHT", "KEY_HUB_RIGHT", None, None),
        ("FVA_CONTACT_SHAFT_HUB", "HUB_SHAFT", "SHAFT_HUB",
         radial_fit if radial_fit > 0.0 else None, None),
        ("FVA_CONTACT_KEY_FLOOR", "SHAFT_FLOOR", "KEY_BOTTOM", None, None),
        ("FVA_CONTACT_KEY_TOP", "HUB_ROOF", "KEY_TOP", None, None),
    )
    for name, main_name, secondary_name, interference, direction in pairs:
        _create_contact(model, assembly, name, main_name, secondary_name,
                        interference, direction)

    tolerance = max(1.0e-4, float(d["D"]) * 1.0e-6)
    shaft = surfaces["instances"]["shaft"]
    drive_faces = shaft.faces.getByBoundingBox(zMin=-tolerance,
                                                zMax=tolerance)
    if not len(drive_faces):
        raise RuntimeError("Shaft drive face at z=0 was not found")
    _replace_surface(assembly, "FVA_SURF_SHAFT_DRIVE", drive_faces)
    rp_feature = assembly.ReferencePoint(point=(0.0, 0.0, 0.0))
    rp = assembly.referencePoints[rp_feature.id]
    rp_set = _replace_set(assembly, "FVA_SET_RP_SHAFT",
                          referencePoints=(rp,))
    model.Coupling(
        name="FVA_COUPLING_SHAFT", controlPoint=rp_set,
        surface=assembly.surfaces["FVA_SURF_SHAFT_DRIVE"],
        influenceRadius=AC.WHOLE_SURFACE, couplingType=AC.DISTRIBUTING,
        weightingMethod=AC.UNIFORM, localCsys=None,
        u1=AC.ON, u2=AC.ON, u3=AC.ON,
        ur1=AC.OFF, ur2=AC.OFF, ur3=AC.ON)

    hub = surfaces["instances"]["hub"]
    hub_outer = _select_faces(
        hub, lambda p: abs(math.hypot(p[0], p[1]) -
                          0.5 * float(d["d_a"])) <= tolerance,
        "hub outer support")
    hub_set = _replace_set(assembly, "FVA_SET_HUB_FIXED", faces=hub_outer)
    key_set = _replace_set(
        assembly, "FVA_SET_KEY_TEMPORARY",
        faces=surfaces["faces"]["KEY_TOP"])
    model.EncastreBC(name="FVA_BC_HUB_FIXED", createStepName="Initial",
                     region=hub_set)
    shaft_bc = model.DisplacementBC(
        name="FVA_BC_SHAFT_GUIDE", createStepName="Initial", region=rp_set,
        u1=0.0, u2=0.0, u3=0.0, ur1=0.0, ur2=0.0, ur3=0.0,
        amplitude=AC.UNSET, distributionType=AC.UNIFORM, fieldName="",
        localCsys=None)
    shaft_bc.setValuesInStep(stepName=STEP_CYCLES, ur3=AC.FREED)
    key_bc = model.EncastreBC(
        name="FVA_BC_KEY_TEMPORARY", createStepName="Initial", region=key_set)
    key_bc.deactivate(STEP_CYCLES)

    torque_nmm = float(cfg.get("torque_Nm", 1256.0)) * 1000.0
    model.Moment(
        name="FVA_LOAD_TORQUE", createStepName=STEP_CYCLES,
        region=rp_set, cm3=torque_nmm, amplitude=AMP_TORQUE,
        distributionType=AC.UNIFORM, field="", localCsys=None)

    prism_nodes = shaft.nodes.getByBoundingBox(
        xMin=-float(d["x_slot"]) - tolerance,
        xMax=float(d["x_slot"]) + tolerance,
        yMin=float(d["yF"]) - tolerance,
        yMax=_matching_levels(d)["shaft_high"] + tolerance,
        zMin=float(d["c1"]) - tolerance,
        zMax=float(d["c2"]) + tolerance)
    if not len(prism_nodes):
        raise RuntimeError("No shaft-keyway prism nodes were selected")
    _replace_set(assembly, "FVA_SET_SHAFT_KEYWAY_PRISM", nodes=prism_nodes)
    levels = dict(_matching_levels(d))
    levels.update((params.get("_method_a_partitioning", {}) or {}).get(
        "levels", {}))
    if str(cfg.get("backend", "")) == BACKEND_HYBRID_HEX:
        opening_grid = select_opening_cartesian_subgrid(
            assembly, shaft, params, d, levels,
            candidate_nodes=surfaces.get("opening_nodes"))
        left_nodes = assembly.sets["FVA_SET_SHAFT_KEYWAY_LEFT"].nodes
        right_nodes = assembly.sets["FVA_SET_SHAFT_KEYWAY_RIGHT"].nodes
        opening_left_count = int(opening_grid["selected_pair_count"])
        opening_right_count = int(opening_grid["selected_pair_count"])
    else:
        # Preserve the reviewed v1 selection exactly.  v1 remains a connected
        # free-tet setup; only v2 promises a persisted Cartesian subgrid.
        flank_band = max(tolerance, float((cfg.get(
            "mesh_matching", {}) or {}).get("tolerance_mm", 1.0e-6)) * 10.0)
        left_nodes = shaft.nodes.getByBoundingBox(
            xMin=-float(d["x_slot"]) - flank_band,
            xMax=-float(d["x_slot"]) + flank_band,
            yMin=levels["shaft_low"] - tolerance,
            yMax=levels["shaft_high"] + tolerance,
            zMin=float(d["c1"]) - tolerance,
            zMax=float(d["c2"]) + tolerance)
        right_nodes = shaft.nodes.getByBoundingBox(
            xMin=float(d["x_slot"]) - flank_band,
            xMax=float(d["x_slot"]) + flank_band,
            yMin=levels["shaft_low"] - tolerance,
            yMax=levels["shaft_high"] + tolerance,
            zMin=float(d["c1"]) - tolerance,
            zMax=float(d["c2"]) + tolerance)
        if not len(left_nodes) or not len(right_nodes):
            raise RuntimeError("Shaft-keyway opening node sets are empty")
        _replace_set(assembly, "FVA_SET_SHAFT_KEYWAY_LEFT", nodes=left_nodes)
        _replace_set(assembly, "FVA_SET_SHAFT_KEYWAY_RIGHT", nodes=right_nodes)
        opening_left_count = len(left_nodes)
        opening_right_count = len(right_nodes)
        opening_grid = {
            "status": "LEGACY_V1_COMPATIBILITY",
            "rectangular_product": False,
            "bounds_coverage": "NOT_GATED_IN_V1",
            "selected_pair_count": min(opening_left_count,
                                       opening_right_count)}

    for name in list(model.fieldOutputRequests.keys()):
        del model.fieldOutputRequests[name]
    model.FieldOutputRequest(
        name="FVA_FIELD_GLOBAL", createStepName=STEP_FIT,
        variables=("S", "U", "PE", "PEEQ", "RF"), numIntervals=20)
    model.FieldOutputRequest(
        name="FVA_FIELD_CONTACT", createStepName=STEP_FIT,
        variables=("CSTRESS", "CDISP"), numIntervals=20)
    model.FieldOutputRequest(
        name="FVA_FIELD_UNLOADED_KEYWAY", createStepName=STEP_CYCLES,
        variables=("U",), region=assembly.sets["FVA_SET_SHAFT_KEYWAY_PRISM"],
        numIntervals=cycles * 2)
    model.FieldOutputRequest(
        name="FVA_FIELD_OPENING_LEFT", createStepName=STEP_CYCLES,
        variables=("U",), region=assembly.sets["FVA_SET_SHAFT_KEYWAY_LEFT"],
        numIntervals=cycles * 2)
    model.FieldOutputRequest(
        name="FVA_FIELD_OPENING_RIGHT", createStepName=STEP_CYCLES,
        variables=("U",), region=assembly.sets["FVA_SET_SHAFT_KEYWAY_RIGHT"],
        numIntervals=cycles * 2)
    for name in list(model.historyOutputRequests.keys()):
        del model.historyOutputRequests[name]
    model.HistoryOutputRequest(
        name="FVA_HISTORY_RP", createStepName=STEP_CYCLES,
        variables=("UR3", "RM3"), region=rp_set, frequency=1)
    assembly.regenerate()
    return {
        "steps": [STEP_FIT, STEP_FRICTION, STEP_CYCLES],
        "cycles": cycles, "cycle_period_s": period,
        "cycle_time_s": total_time, "torque_Nmm": torque_nmm,
        "torque_amplitude_points": len(torque_data),
        "contacts": [item[0] for item in pairs],
        "interface_skin_ties": skin_ties,
        "surface_counts": surfaces["face_counts"],
        "prism_nodes": len(prism_nodes), "drive_faces": len(drive_faces),
        "opening_left_nodes": opening_left_count,
        "opening_right_nodes": opening_right_count,
        "opening_grid": opening_grid,
        "finite_sliding": True,
        "friction_fit": float(contact.get("friction_fit", 0.0001)),
        "friction_service": float(contact.get("friction_service", 0.2)),
        "elastic_slip_mm": float(contact.get("elastic_slip_mm", 0.001)),
        "normal_stiffness_N_per_mm3": float(contact.get(
            "normal_stiffness_N_per_mm3", 1.0e7)),
        "interference_per_flank_mm": half,
        "shaft_hub_radial_interference_mm": radial_fit,
    }


def _create_or_run_job(model, params):
    from abaqus import mdb
    import abaqusConstants as AC

    execution = _fva(params).get("execution", {}) or {}
    if not bool(execution.get("create_job", False)):
        return {"created": False, "submitted": False, "status": "NOJOB"}
    name = str(execution.get("job_name") or (model.name + "_METHOD_A"))
    name = name.replace(" ", "_")[:70]
    if name in mdb.jobs:
        del mdb.jobs[name]
    cpus = max(1, int(execution.get("cpus", 1)))
    precision = str(execution.get("precision", "SINGLE")).upper()
    precision_constant = AC.DOUBLE if precision == "DOUBLE" else AC.SINGLE
    kwargs = dict(
        name=name, model=model.name, type=AC.ANALYSIS,
        description="FVA 600 III DIN 6892 Method-A cyclic model",
        numCpus=cpus, memory=90, memoryUnits=AC.PERCENTAGE,
        explicitPrecision=precision_constant,
        nodalOutputPrecision=precision_constant,
        echoPrint=AC.OFF, modelPrint=AC.OFF, contactPrint=AC.OFF,
        historyPrint=AC.OFF)
    if cpus > 1:
        kwargs["numDomains"] = cpus
        kwargs["multiprocessingMode"] = AC.DEFAULT
    job = mdb.Job(**kwargs)
    result = {"created": True, "submitted": False,
              "status": str(job.status), "name": name}
    if bool(execution.get("submit_solver", False)):
        job.submit(consistencyChecking=AC.OFF)
        job.waitForCompletion()
        result["submitted"] = True
        result["status"] = str(job.status)
    return result


def _write_setup_audit(path, payload):
    parent = os.path.dirname(path)
    _ensure_dir(parent)
    temporary = path + ".tmp"
    stream = open(temporary, "w")
    try:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    finally:
        stream.close()
    if os.path.isfile(path):
        os.remove(path)
    os.rename(temporary, path)
    return path


def build(params, core=None, base_builder=None):
    """Build and audit the connected Method-A model.

    By default this function creates no Job and never submits a solver.  Those
    operations occur only when both schema validation and explicit execution
    flags allow them.
    """
    from abaqus import mdb

    if core is None:
        import keyjoint_core as core
    if base_builder is None:
        import build_parametric_model as base_builder
    cfg = _fva(params)
    backend_id = str(cfg.get("backend", ""))
    if backend_id not in BACKENDS:
        raise ValueError("Method-A backend called for %r; supported=%r" %
                         (cfg.get("backend"), BACKENDS))
    setup_version = SETUP_VERSIONS[backend_id]
    assessment = methods.assess_backend_request(cfg)
    if not assessment.get("executable"):
        raise ValueError("Blocked Method-A backend request: %s" %
                         assessment.get("issues"))
    strict_no_job = bool(cfg.get("strict_no_job", True))
    if strict_no_job:
        _guard_nojob(mdb, "before build")

    started = time.time()
    model, _initial_report = base_builder.build_all(
        params, mesh=False, derived_updates={"_method_a_matching": True})
    d = params["_derived"]
    partition_info = prepare_matching_partitions(model, d, base_builder)
    params["_method_a_partitioning"] = partition_info
    skin_data = None
    if backend_id == BACKEND_HYBRID_HEX:
        # Cell-wide axial cuts isolate the straight keyway prism from its
        # rounded ends.  This raises the physical Shaft above the hard 50%
        # hexahedron floor while v1 retains its reviewed face-only topology.
        shaft_part = model.parts["Shaft"]
        before_cells = len(shaft_part.cells)
        for z_value in (partition_info["levels"]["z_low"],
                        partition_info["levels"]["z_high"]):
            base_builder._cut(shaft_part, "z", float(z_value))
        model.rootAssembly.regenerate()
        partition_info["hybrid_axial_cell_cuts"] = {
            "offsets_mm": [partition_info["levels"]["z_low"],
                           partition_info["levels"]["z_high"]],
            "shaft_cells_before": before_cells,
            "shaft_cells_after": len(shaft_part.cells)}
        report = generate_hybrid_native_mesh(
            model, params, d, base_builder, core)
        skin_data = create_matching_interface_skins(
            model, params, d, partition_info)
    else:
        report = generate_matching_mesh(
            model, params, d, base_builder, core)

    # Mesh changes invalidate assembly mesh sets made by build_all. Recreate
    # canonical all-node/all-element sets before contacts and output requests.
    assembly = model.rootAssembly
    assembly.regenerate()
    for tag, instance_name in (("SHAFT", "SHAFT-1"),
                               ("KEY", "KEY-1"), ("HUB", "HUB-1")):
        _replace_set(assembly, "ALL_%s_NODES" % tag,
                     nodes=assembly.instances[instance_name].nodes)
        _replace_set(assembly, "ALL_%s_ELEMENTS" % tag,
                     elements=assembly.instances[instance_name].elements)

    material_info = assign_material_models(model, params, d, base_builder)
    skin_section = None
    if skin_data is not None:
        skin_section = assign_interface_skin_section(
            model, skin_data,
            material_info["assignments"]["shaft"]["material"])
    matching_cfg = cfg.get("mesh_matching", {}) or {}
    surface_data = create_interface_surfaces(
        model, d, partition_info,
        float(matching_cfg.get("target_size_mm", 0.8)),
        skin_data=skin_data)
    matching = verify_matching_mesh(surface_data, matching_cfg)
    physics = configure_method_a_physics(model, params, d, surface_data)
    job = _create_or_run_job(model, params)

    dirs = params.get("_artifact_dirs") or base_builder.resolve_artifact_dirs(params)
    generated_dir = _ensure_dir(dirs["generated"])
    model_dir = _ensure_dir(dirs["model"])
    screenshot_dir = _ensure_dir(dirs["screenshots"])
    cae_path = None
    if params.get("save_cae", True):
        cae_path = os.path.join(model_dir, str(params["model_name"]) + ".cae")
        mdb.saveAs(pathName=cae_path)

    analysis = {
        "enabled": True, "badge": methods.BADGE_FVA_RESEARCH,
        "backend": backend_id, "setup_version": setup_version,
        "workflow": "method_a_numerical", "submitted": job["submitted"],
        "job": job.get("name"), "job_status": job["status"],
        "matching": matching, "materials": material_info,
        "interface_skin_section": skin_section,
        "physics": physics, "opening_grid": physics.get("opening_grid"),
        "interface_mesh": params.get("_fva_interface_mesh"),
        "mesh_quality": params.get("_mesh_quality"),
        "partitioning": partition_info,
        "complete_method_a": False,
        "requires_solved_unloaded_frame": True,
        "din743_independent": True,
    }
    params["_fva_method_a"] = analysis
    params["_mesh_report"] = report
    try:
        audit_ok = base_builder.write_audit(
            model, report, params, generated_dir, analysis=analysis)
    except Exception as exc:
        audit_ok = None
        analysis["base_audit_error"] = str(exc)[:500]

    preview = None
    if params.get("make_preview", True):
        preview = base_builder.render_preview(
            model, screenshot_dir, str(params["model_name"]), d, params)
    payload = {
        "setup_schema_version": 2,
        "setup_version": setup_version,
        "backend": backend_id,
        "badge": methods.BADGE_FVA_RESEARCH,
        "source_id": methods.SOURCE_FVA,
        "model_name": model.name,
        "elapsed_s": round(time.time() - started, 3),
        "cae_path": cae_path,
        "preview": preview,
        "audit_ok": audit_ok,
        "job": job,
        "matching": matching,
        "interfaces": params.get("_fva_interface_mesh"),
        "mesh_quality": params.get("_mesh_quality"),
        "mesh_report": report,
        "opening_grid": physics.get("opening_grid"),
        "partitioning": partition_info,
        "materials": material_info,
        "interface_skin_section": skin_section,
        "physics": physics,
        "method_a_complete": False,
        "next_required_evidence": [
            "solve all configured load cycles",
            "identify and verify the final unloaded frame",
            "export permanent shaft-keyway opening grid",
            "integrate DeltaV and assess v <= v_crit",
            "verify mesh convergence, equilibrium, contact and DIN 743"],
    }
    payload["hard_gates"] = {
        "matching_five_interfaces": bool(
            matching.get("status") == "MATCHED" and
            len(matching.get("interfaces") or []) ==
            len(REQUIRED_MATCHING_INTERFACES)),
        "interface_edge_le_1mm": all(
            bool(item.get("absolute_1mm_passed"))
            for item in ((params.get("_fva_interface_mesh") or {}).get(
                "interfaces") or {}).values()),
        "structured_quadrilateral_patterns": bool(
            backend_id != BACKEND_HYBRID_HEX or
            ((params.get("_fva_interface_mesh") or {}).get(
                "pattern_preservation_audit") or {}).get(
                    "quadrilateral_gate") == "PASS"),
        "hybrid_mesh_per_piece": all(
            bool((item.get("quality") or {}).get("hard_passed"))
            for item in report.values()),
        "opening_grid_rectangular_full_bounds": bool(
            backend_id != BACKEND_HYBRID_HEX or
            (physics.get("opening_grid") or {}).get("status") == "PASS"),
    }
    if not all(payload["hard_gates"].values()):
        raise RuntimeError("Method-A setup hard gates failed: %s" %
                           payload["hard_gates"])

    if strict_no_job:
        _guard_nojob(mdb, "after build")
        payload["nojob_guard"] = "PASS"
    else:
        payload["nojob_guard"] = "NOT_REQUESTED"

    # Persist the setup only after the final NOJOB guard so the durable audit
    # contains the guard result rather than an earlier, incomplete payload.
    audit_path = os.path.join(generated_dir, "FVA_METHOD_A_SETUP.json")
    payload["audit_path"] = audit_path
    _write_setup_audit(audit_path, payload)
    return payload
