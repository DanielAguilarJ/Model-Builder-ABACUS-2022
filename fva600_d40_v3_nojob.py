# -*- coding: utf-8 -*-
"""FVA 600 III research pre-solve setup on the locked D40 V3 backend.

This one-cycle NOJOB workflow is a geometry/physics regression only.  It is
explicitly not complete DIN 6892/FVA Method A (the supplied report proposes at
least 10 load cycles).
This module is executed inside the Abaqus/CAE kernel by
``build_parametric_model.py``.  It deliberately contains no Job, writeInput,
submit or ODB operation.  Geometry and mesh are delegated to the reviewed
``d40_hex_conical_master_v3_refined_hex_nojob.py`` backend; only materials,
interactions, steps, boundary conditions, load, outputs and audits are added.

Units: mm, N, MPa, tonne.  Torque entered in N m is converted to N mm.
"""
from __future__ import print_function

try:
    import imp
except ImportError:  # Python 3.12+; Abaqus 2022 still uses Python 2.7.
    import importlib.util

    class _ImpCompat(object):
        @staticmethod
        def load_source(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    imp = _ImpCompat()
import json
import math
import os
import platform
import sys
import time

BACKEND = "d40_v3_refined_hex_nojob"
MODEL_NAME_DEFAULT = "D40_FVA600_RESEARCH_PRESOLVE_1LW_NOJOB"
STEP_FIT = "Kontaktfinden"
STEP_FRICTION = "Reibung_einschalten"
STEP_TORSION = "Schwellende_Torsion_1LW"
AMP_INTERFERENCE_RAMP = "Rampe_U_PF"
AMP_INTERFERENCE_HOLD = "Konstant_U_PF"
AMP_TORQUE = "Amplitude_Mt_1LW"
PROP_FIT = "FVA_Kontakt_reibungsarm"
PROP_SERVICE = "FVA_Kontakt_mu_0p2"

SOLVER_EXTENSIONS = (
    ".inp", ".odb", ".lck", ".log", ".msg", ".sta", ".dat",
    ".res", ".stt", ".sim", ".prt", ".com", ".023", ".fil",
    ".sel", ".pac", ".abq", ".ipm", ".smabulk")


def _project_root():
    """Locate either the packaged FVA backend or the original project tree."""
    here = os.path.dirname(os.path.abspath(__file__))
    packaged = os.path.join(here, "fva_backend")
    required = (
        os.path.join(packaged, "src", "d40_hex_conical_master.py"),
        os.path.join(packaged, "src", "d40_hex_conical_master_v3_refined_hex_nojob.py"),
        os.path.join(packaged, "sources", "shaft_with_keywayyt.py"),
    )
    if all(os.path.isfile(path) for path in required):
        return packaged
    return os.path.dirname(here)


def _fva(params):
    return params.get("fva_600_iii", {}) or {}


def _nested(mapping, key, default):
    value = mapping.get(key, default)
    return default if value is None else value


def _ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def _guard_jobs(mdb, stage):
    names = tuple(str(name) for name in mdb.jobs.keys())
    if names:
        raise RuntimeError(
            "STRICT NOJOB guard failed after %s; jobs=%r" % (stage, names))


def _solver_files(out_dir):
    if not os.path.isdir(out_dir):
        return ()
    forbidden = []
    for root, _directories, files in os.walk(out_dir):
        for name in files:
            if name.lower().endswith(SOLVER_EXTENSIONS):
                forbidden.append(os.path.relpath(os.path.join(root, name),
                                                 out_dir))
    return tuple(sorted(forbidden))


def _guard_solver_files(out_dir, stage):
    forbidden = _solver_files(out_dir)
    if forbidden:
        raise RuntimeError(
            "STRICT NOJOB guard failed after %s; solver files=%r" %
            (stage, forbidden))


def _guard_nojob(mdb, out_dir, stage):
    _guard_jobs(mdb, stage)
    _guard_solver_files(out_dir, stage)


def _guard_configuration(params):
    fva = _fva(params)
    if not bool(fva.get("enabled", False)):
        raise ValueError("FVA backend called while fva_600_iii.enabled is false")
    if str(fva.get("backend", "")).strip().lower() != BACKEND:
        raise ValueError("Unsupported FVA backend: %r" % fva.get("backend"))
    if str(fva.get("variant_id", "VB1")).strip().upper() != "VB1":
        raise ValueError("Locked FVA backend realizes VB1 only; no variant coercion is allowed")
    if str(fva.get("material_pair", "C45N_C45N")).strip().upper() != "C45N_C45N":
        raise ValueError("Locked FVA backend realizes C45+N only; 42CrMoS4+QT is calculation-only")
    if str(fva.get("requested_method", "A_FE_VOLUME")).strip().upper() != "A_FE_VOLUME":
        raise ValueError("Locked FVA backend is only a partial Method-A pre-solve setup")
    if str(fva.get("workflow", "")).strip().lower() != "pre_solve_regression":
        raise ValueError("FVA one-cycle backend is only a pre_solve_regression")
    if str(fva.get("method", "")).strip().lower() != "research_method_a_setup":
        raise ValueError("FVA backend must be labelled research_method_a_setup")
    if bool(fva.get("is_complete_method_a", False)):
        raise ValueError("One LW / NOJOB must never claim complete Method A")
    if int(fva.get("cycles", 0)) != 1:
        raise ValueError("FVA pre-solve regression requires exactly one load cycle")
    if not bool(fva.get("strict_no_job", False)):
        raise ValueError("strict_no_job must remain true")
    if not bool(params.get("make_preview", True)):
        raise ValueError(
            "FVA visual evidence is mandatory; make_preview must remain true")
    analysis = params.get("analysis", {}) or {}
    forbidden = [key for key in ("enabled", "create_job", "submit")
                 if bool(analysis.get(key, False))]
    if forbidden:
        raise ValueError(
            "Generic analysis/job switches are forbidden in FVA mode: %r" %
            tuple(forbidden))
    if bool((params.get("study", {}) or {}).get("enabled", False)):
        raise ValueError("Mesh studies are disabled in the locked FVA backend")
    torque = float(fva.get("torque_Nm", 0.0) or 0.0)
    if torque <= 0.0:
        raise ValueError("fva_600_iii.torque_Nm must be positive")
    contact = fva.get("contact", {}) or {}
    if abs(float(contact.get("interference_total_mm", 0.0)) - 0.018) > 1e-12:
        raise ValueError("FVA VB1 requires U_PF = 0.018 mm")
    if abs(float(contact.get("interference_per_flank_mm", 0.0)) - 0.009) > 1e-12:
        raise ValueError("FVA VB1 requires 0.009 mm per flank")


def _load_refined_backend(run_dir, model_name, model_dir=None,
                          generated_dir=None, screenshots_dir=None):
    root = _project_root()
    path = os.path.join(
        root, "src", "d40_hex_conical_master_v3_refined_hex_nojob.py")
    if not os.path.isfile(path):
        raise RuntimeError("Refined V3 backend not found: %s" % path)
    old_root = os.environ.get("D40_PROJECT_ROOT")
    old_out = os.environ.get("D40_V3_REFINED_OUTPUT_DIR")
    os.environ["D40_PROJECT_ROOT"] = root
    os.environ["D40_V3_REFINED_OUTPUT_DIR"] = run_dir
    try:
        module = imp.load_source(
            "d40_v3_fva600_refined_backend_%d" % int(time.time() * 1000),
            path)
    finally:
        if old_root is None:
            os.environ.pop("D40_PROJECT_ROOT", None)
        else:
            os.environ["D40_PROJECT_ROOT"] = old_root
        if old_out is None:
            os.environ.pop("D40_V3_REFINED_OUTPUT_DIR", None)
        else:
            os.environ["D40_V3_REFINED_OUTPUT_DIR"] = old_out
    model_dir = model_dir or run_dir
    generated_dir = generated_dir or run_dir
    screenshots_dir = screenshots_dir or os.path.join(run_dir, "figures")
    module.MODEL_NAME = model_name
    module.RUN_DIR = run_dir
    module.CAE_PATH = os.path.join(model_dir, model_name + ".cae")
    module.AUDIT_PATH = os.path.join(generated_dir, "V3_REFINED_HEX_AUDIT.txt")
    module.FIGURE_DIR = screenshots_dir
    return module


def _uml_table(re_value, rm_value, k_prime, exponent, intervals):
    """Ramberg-Osgood plastic strain table shown in report Figure 54.

    The first row anchors Abaqus plastic strain at zero.  The following row at
    the same stress and all later rows use epsilon_pl=(sigma/K')**(1/n').
    This reproduces the duplicated first stress visible in Figure 54.
    """
    rows = [(float(re_value), 0.0)]
    count = max(2, int(intervals))
    for index in range(count + 1):
        fraction = float(index) / float(count)
        stress = re_value + (rm_value - re_value) * fraction
        plastic = (stress / k_prime) ** (1.0 / exponent)
        rows.append((float(stress), float(plastic)))
    return tuple(rows)


def _assign_fva_materials(data, config):
    import abaqusConstants as AC
    import regionToolset

    model = data["model"]
    mats = config.get("materials", {}) or {}
    shaft_data = mats.get("shaft", {}) or {}
    hub_data = mats.get("hub", {}) or {}
    key_data = mats.get("key", {}) or {}
    density = float(config.get("density_tonne_per_mm3", 7.85e-09))

    shaft = model.Material(name="Welle_C45N_FVA")
    shaft.Elastic(table=((float(_nested(shaft_data, "E_MPa", 187000.0)),
                          float(_nested(shaft_data, "nu", 0.30))),))
    shaft.Density(table=((density,),))
    shaft.Plastic(
        hardening=AC.COMBINED, dataType=AC.PARAMETERS,
        numBackstresses=1,
        table=((float(_nested(shaft_data, "Re_MPa", 378.0)),
                float(_nested(shaft_data, "C1_MPa", 15260.0)),
                float(_nested(shaft_data, "gamma1", 50.8))),))
    shaft.plastic.CyclicHardening(
        parameters=AC.ON,
        table=((float(_nested(shaft_data, "Re_MPa", 378.0)),
                float(_nested(shaft_data, "Qinf_MPa", 32.74)),
                float(_nested(shaft_data, "b_iso", 249.8))),))

    hub = model.Material(name="Nabe_C45N_UML_FVA")
    hub.Elastic(table=((float(_nested(hub_data, "E_MPa", 196000.0)),
                        float(_nested(hub_data, "nu", 0.30))),))
    hub.Density(table=((density,),))
    uml = _uml_table(
        float(_nested(hub_data, "Re_MPa", 279.0743851)),
        float(_nested(hub_data, "Rm_MPa", 579.0)),
        float(_nested(hub_data, "K_prime_MPa", 955.0)),
        float(_nested(hub_data, "n_prime", 0.15)),
        int(_nested(hub_data, "intervals", 150)))
    hub.Plastic(hardening=AC.ISOTROPIC, table=uml)

    key = model.Material(name="Passfeder_C45QT_FVA")
    key.Elastic(table=((float(_nested(key_data, "E_MPa", 210000.0)),
                        float(_nested(key_data, "nu", 0.30))),))
    key.Density(table=((density,),))
    key_yield = float(_nested(key_data, "yield_MPa", 928.0))
    key.Plastic(hardening=AC.ISOTROPIC,
                table=((key_yield, 0.0), (key_yield, 1.0)))

    model.HomogeneousSolidSection(
        name="FVA_SEC_WELLE", material="Welle_C45N_FVA", thickness=None)
    model.HomogeneousSolidSection(
        name="FVA_SEC_NABE", material="Nabe_C45N_UML_FVA", thickness=None)
    model.HomogeneousSolidSection(
        name="FVA_SEC_PASSFEDER", material="Passfeder_C45QT_FVA",
        thickness=None)
    data["shaft"].SectionAssignment(
        region=regionToolset.Region(cells=data["shaft"].cells),
        sectionName="FVA_SEC_WELLE")
    for name in ("bushing", "hub"):
        data[name].SectionAssignment(
            region=regionToolset.Region(cells=data[name].cells),
            sectionName="FVA_SEC_NABE")
    data["key"].SectionAssignment(
        region=regionToolset.Region(cells=data["key"].cells),
        sectionName="FVA_SEC_PASSFEDER")
    data["uml_table"] = uml


def _face_point(face):
    points = getattr(face, "pointOn", None)
    if points:
        point = points[0]
        return tuple(float(value) for value in point[:3])
    centroid = face.getCentroid()
    return tuple(float(value) for value in centroid[:3])


def _select_faces(instance, predicate, label):
    # Abaqus 2022 requires a FaceArray for Surface(...); a Python tuple of
    # Face objects raises the non-diagnostic "Feature creation failed".
    selected = instance.faces[0:0]
    for face in instance.faces:
        point = _face_point(face)
        if predicate(point):
            selected = selected + instance.faces[face.index:face.index + 1]
    if not len(selected):
        raise RuntimeError("No faces selected for %s" % label)
    return selected


def _make_surface(assembly, name, faces):
    assembly.Surface(name=name, side1Faces=faces)
    return assembly.surfaces[name]


def _make_set(assembly, name, faces=None, nodes=None, reference_points=None):
    if faces is not None:
        assembly.Set(name=name, faces=faces)
    elif nodes is not None:
        assembly.Set(name=name, nodes=nodes)
    else:
        assembly.Set(name=name, referencePoints=reference_points)
    return assembly.sets[name]


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


def _surface_inventory(data):
    """Create named physical surfaces using the locked global coordinates."""
    assembly = data["model"].rootAssembly
    instances = data["instances"]
    shaft = instances["shaft"]
    key = instances["key"]
    bush = instances["bushing"]
    hub = instances["hub"]
    z0, z1 = 17.0, 55.0

    def near(value, target, tol):
        return abs(value - target) <= tol

    faces = {}
    faces["PF_LEFT"] = _select_faces(
        key, lambda p: near(p[0], -6.0, 0.08) and
        15.25 <= p[1] <= 22.15 and z0 - 0.1 <= p[2] <= z1 + 0.1,
        "Passfeder left flank")
    faces["PF_RIGHT"] = _select_faces(
        key, lambda p: near(p[0], 6.0, 0.08) and
        15.25 <= p[1] <= 22.15 and z0 - 0.1 <= p[2] <= z1 + 0.1,
        "Passfeder right flank")
    faces["PF_FLOOR"] = _select_faces(
        key, lambda p: near(p[1], 15.0, 0.08) and abs(p[0]) <= 5.7 and
        z0 - 0.1 <= p[2] <= z1 + 0.1, "Passfeder floor")
    faces["PF_TOP"] = _select_faces(
        key, lambda p: p[1] >= 22.0 and abs(p[0]) <= 6.05 and
        z0 - 0.1 <= p[2] <= z1 + 0.1, "Passfeder crown")

    faces["WELLE_LEFT"] = _select_faces(
        shaft, lambda p: near(p[0], -6.0, 0.12) and
        15.0 <= p[1] <= 20.1 and 10.8 <= p[2] <= 61.2,
        "Welle left keyway flank")
    faces["WELLE_RIGHT"] = _select_faces(
        shaft, lambda p: near(p[0], 6.0, 0.12) and
        15.0 <= p[1] <= 20.1 and 10.8 <= p[2] <= 61.2,
        "Welle right keyway flank")
    faces["WELLE_FLOOR"] = _select_faces(
        shaft, lambda p: near(p[1], 15.0, 0.12) and abs(p[0]) <= 6.1 and
        10.8 <= p[2] <= 61.2, "Welle keyway floor")

    faces["BUSH_LEFT"] = _select_faces(
        bush, lambda p: near(p[0], -6.01075, 0.12) and
        19.8 <= p[1] <= 23.4 and z0 - 0.1 <= p[2] <= z1 + 0.1,
        "Bushing left groove flank")
    faces["BUSH_RIGHT"] = _select_faces(
        bush, lambda p: near(p[0], 6.01075, 0.12) and
        19.8 <= p[1] <= 23.4 and z0 - 0.1 <= p[2] <= z1 + 0.1,
        "Bushing right groove flank")
    faces["BUSH_ROOF"] = _select_faces(
        bush, lambda p: p[1] >= 22.8 and abs(p[0]) <= 6.2 and
        z0 - 0.1 <= p[2] <= z1 + 0.1, "Bushing groove roof")

    faces["SHAFT_OD"] = _select_faces(
        shaft, lambda p: 19.75 <= math.hypot(p[0], p[1]) <= 20.25 and
        z0 - 0.1 <= p[2] <= z1 + 0.1 and
        not (p[1] > 14.8 and abs(p[0]) < 6.3), "Shaft outside diameter")
    faces["BUSH_ID"] = _select_faces(
        bush, lambda p: 19.75 <= math.hypot(p[0], p[1]) <= 20.25 and
        z0 - 0.1 <= p[2] <= z1 + 0.1 and
        not (p[1] > 19.7 and abs(p[0]) < 6.3), "Bushing bore")
    faces["BUSH_TAPER"] = _select_faces(
        bush, lambda p: 29.5 <= math.hypot(p[0], p[1]) <= 32.3 and
        z0 - 0.1 <= p[2] <= z1 + 0.1, "Bushing taper")
    faces["HUB_TAPER"] = _select_faces(
        hub, lambda p: 29.5 <= math.hypot(p[0], p[1]) <= 32.3 and
        z0 - 0.1 <= p[2] <= z1 + 0.1, "Hub taper")
    faces["HUB_OUTER"] = _select_faces(
        hub, lambda p: 39.7 <= math.hypot(p[0], p[1]) <= 40.3 and
        z0 - 0.1 <= p[2] <= z1 + 0.1, "Hub outer cylinder")
    faces["KEY_TOP_BC"] = faces["PF_TOP"]

    for name, selected in faces.items():
        _make_surface(assembly, "FVA_SURF_" + name, selected)
    return dict((name, len(selected)) for name, selected in faces.items())


def _create_interaction(model, assembly, name, main_name, secondary_name,
                        interference=None, direction=None):
    import abaqusConstants as AC

    kwargs = dict(
        name=name, createStepName=STEP_FIT,
        main=assembly.surfaces["FVA_SURF_" + main_name],
        secondary=assembly.surfaces["FVA_SURF_" + secondary_name],
        sliding=AC.FINITE, interactionProperty=PROP_FIT,
        adjustMethod=AC.NONE, initialClearance=AC.OMIT)
    if interference is not None:
        kwargs.update(
            interferenceType=AC.UNIFORM, overclosure=float(interference),
            amplitude=AMP_INTERFERENCE_RAMP)
        if direction is not None:
            kwargs["interferenceDirectionType"] = AC.DIRECTION_COSINE
            kwargs["direction"] = tuple(float(value) for value in direction)
    interaction = model.SurfaceToSurfaceContactStd(**kwargs)
    if interference is None:
        interaction.setValuesInStep(
            stepName=STEP_FRICTION, interactionProperty=PROP_SERVICE)
    else:
        interaction.setValuesInStep(
            stepName=STEP_FRICTION, interactionProperty=PROP_SERVICE,
            amplitude=AMP_INTERFERENCE_HOLD)
    return interaction


def _configure_fva_physics(data, config):
    import abaqusConstants as AC

    model = data["model"]
    assembly = model.rootAssembly
    contact = config.get("contact", {}) or {}
    steps = config.get("steps", {}) or {}

    model.StaticStep(
        name=STEP_FIT, previous="Initial", nlgeom=AC.ON,
        timePeriod=float(steps.get("contact_time_s", 1.0)),
        initialInc=float(steps.get("contact_increment_s", 0.05)),
        minInc=1.0e-7,
        maxInc=float(steps.get("contact_increment_s", 0.05)),
        maxNumInc=200, matrixSolver=AC.DIRECT)
    model.StaticStep(
        name=STEP_FRICTION, previous=STEP_FIT, nlgeom=AC.ON,
        timePeriod=float(steps.get("friction_time_s", 1.0)),
        initialInc=0.05, minInc=1.0e-7, maxInc=0.05,
        maxNumInc=200, matrixSolver=AC.DIRECT)
    model.StaticStep(
        name=STEP_TORSION, previous=STEP_FRICTION, nlgeom=AC.ON,
        timePeriod=float(steps.get("cycle_time_s", 2.0)),
        initialInc=0.05, minInc=1.0e-7, maxInc=0.10,
        maxNumInc=400, matrixSolver=AC.DIRECT)

    model.TabularAmplitude(
        name=AMP_INTERFERENCE_RAMP, timeSpan=AC.STEP,
        smooth=AC.SOLVER_DEFAULT, data=((0.0, 0.0), (1.0, 1.0)))
    model.TabularAmplitude(
        name=AMP_INTERFERENCE_HOLD, timeSpan=AC.STEP,
        smooth=AC.SOLVER_DEFAULT, data=((0.0, 1.0), (1.0, 1.0)))
    model.TabularAmplitude(
        name=AMP_TORQUE, timeSpan=AC.STEP, smooth=AC.SOLVER_DEFAULT,
        data=((0.0, 0.0), (1.0, 1.0), (2.0, 0.0)))

    _contact_property(
        model, PROP_FIT, float(contact.get("friction_fit", 0.0001)),
        contact)
    _contact_property(
        model, PROP_SERVICE, float(contact.get("friction_service", 0.2)),
        contact)
    surface_counts = _surface_inventory(data)
    interference = float(contact.get("interference_per_flank_mm", 0.009))
    pairs = (
        ("Kontakt_Welle_PF_Flanke_Links", "PF_LEFT", "WELLE_LEFT",
         interference, (1.0, 0.0, 0.0)),
        ("Kontakt_Welle_PF_Flanke_Rechts", "PF_RIGHT", "WELLE_RIGHT",
         interference, (-1.0, 0.0, 0.0)),
        ("Kontakt_Welle_PF_Nutgrund", "PF_FLOOR", "WELLE_FLOOR",
         None, None),
        ("Kontakt_Bushing_PF_Flanke_Links", "BUSH_LEFT", "PF_LEFT",
         None, None),
        ("Kontakt_Bushing_PF_Flanke_Rechts", "BUSH_RIGHT", "PF_RIGHT",
         None, None),
        ("Kontakt_Bushing_PF_Deckflaeche", "BUSH_ROOF", "PF_TOP",
         None, None),
        ("Kontakt_Bushing_Welle", "BUSH_ID", "SHAFT_OD", None, None),
        ("Kontakt_Hub_Bushing_Konus", "HUB_TAPER", "BUSH_TAPER",
         None, None),
    )
    for name, main_name, secondary_name, fit, direction in pairs:
        _create_interaction(
            model, assembly, name, main_name, secondary_name, fit, direction)

    # Shaft load face and distributing coupling on global Z axis.
    tol = 1.0e-3
    shaft_instance = data["instances"]["shaft"]
    drive_faces = shaft_instance.faces.getByBoundingBox(
        zMin=-tol, zMax=tol)
    if not len(drive_faces):
        raise RuntimeError("Shaft z=0 load face not found")
    _make_surface(assembly, "FVA_SURF_SHAFT_DRIVE", drive_faces)
    rp_feature = assembly.ReferencePoint(point=(0.0, 0.0, 0.0))
    rp = assembly.referencePoints[rp_feature.id]
    rp_set = _make_set(
        assembly, "FVA_SET_RP_SHAFT", reference_points=(rp,))
    model.Coupling(
        name="FVA_COUPLING_SHAFT", controlPoint=rp_set,
        surface=assembly.surfaces["FVA_SURF_SHAFT_DRIVE"],
        influenceRadius=AC.WHOLE_SURFACE, couplingType=AC.DISTRIBUTING,
        weightingMethod=AC.UNIFORM, localCsys=None,
        u1=AC.ON, u2=AC.ON, u3=AC.ON,
        ur1=AC.OFF, ur2=AC.OFF, ur3=AC.ON)

    hub_set = _make_set(
        assembly, "FVA_SET_HUB_FIXED",
        faces=assembly.surfaces["FVA_SURF_HUB_OUTER"].faces)
    key_set = _make_set(
        assembly, "FVA_SET_KEY_TOP",
        faces=assembly.surfaces["FVA_SURF_KEY_TOP_BC"].faces)
    bushing_set = assembly.sets["ALL_BUSHING_NODES"]
    shaft_bc = model.EncastreBC(
        name="FVA_BC_SHAFT_INITIAL", createStepName="Initial", region=rp_set)
    key_bc = model.EncastreBC(
        name="FVA_BC_KEY_INITIAL", createStepName="Initial", region=key_set)
    bushing_bc = model.EncastreBC(
        name="FVA_BC_BUSHING_INITIAL", createStepName="Initial",
        region=bushing_set)
    model.EncastreBC(
        name="FVA_BC_HUB_FIXED", createStepName="Initial", region=hub_set)
    for bc in (shaft_bc, key_bc, bushing_bc):
        bc.deactivate(STEP_TORSION)

    torque_nmm = float(config.get("torque_Nm", 1256.0)) * 1000.0
    model.Moment(
        name="FVA_LOAD_TORQUE_1LW", createStepName=STEP_TORSION,
        region=rp_set, cm3=torque_nmm, amplitude=AMP_TORQUE,
        distributionType=AC.UNIFORM, field="", localCsys=None)

    prism_nodes = shaft_instance.nodes.getByBoundingBox(
        xMin=-6.3, yMin=14.7, zMin=17.0 - 1.0e-4,
        xMax=6.3, yMax=20.3, zMax=55.0 + 1.0e-4)
    if not len(prism_nodes):
        raise RuntimeError("No shaft-keyway prism nodes selected")
    _make_set(assembly, "FVA_SET_WELLENNUT_PRISM", nodes=prism_nodes)

    for name in list(model.fieldOutputRequests.keys()):
        del model.fieldOutputRequests[name]
    model.FieldOutputRequest(
        name="FVA_FIELD_GLOBAL", createStepName=STEP_FIT,
        variables=("S", "U", "PE", "PEEQ", "RF"), numIntervals=20)
    model.FieldOutputRequest(
        name="FVA_FIELD_CONTACT", createStepName=STEP_FIT,
        variables=("CSTRESS", "CDISP"), numIntervals=20)
    model.FieldOutputRequest(
        name="FVA_FIELD_UNLOADED_KEYWAY", createStepName=STEP_TORSION,
        variables=("U",), region=assembly.sets["FVA_SET_WELLENNUT_PRISM"],
        numIntervals=2)
    for name in list(model.historyOutputRequests.keys()):
        del model.historyOutputRequests[name]
    model.HistoryOutputRequest(
        name="FVA_HISTORY_RP", createStepName=STEP_TORSION,
        variables=("UR3", "RM3"), region=rp_set, frequency=1)
    assembly.regenerate()
    data["fva"] = {
        "surface_counts": surface_counts,
        "pairs": tuple(row[0] for row in pairs),
        "torque_Nmm": torque_nmm,
        "prism_nodes": len(prism_nodes),
        "drive_faces": len(drive_faces),
    }
    return data


def _capture_fva_evidence(data, refined, base_images):
    """Capture reproducible FVA physics evidence without creating a job."""
    import abaqusConstants as AC
    from abaqus import session

    if len(base_images) != 12:
        raise RuntimeError(
            "Expected 12 locked geometry/mesh images; got %d" %
            len(base_images))
    model = data["model"]
    assembly = model.rootAssembly
    viewport = refined._viewport()
    if viewport is None:
        raise RuntimeError("No Abaqus viewport is available for FVA evidence")
    _ensure_dir(refined.FIGURE_DIR)
    session.printOptions.setValues(
        vpDecorations=AC.OFF, vpBackground=AC.OFF, reduceColors=False)
    session.pngOptions.setValues(imageSize=(1600, 1200))
    try:
        viewport.view.setProjection(projection=AC.PARALLEL)
    except Exception:
        pass

    images = []
    all_instances = tuple(assembly.instances.keys())

    def reset(step, visible, mapping, bcs=False, constraints=False,
              interactions=False, loads=False, show_rp=False,
              fraction=0.001, arrow_size=10):
        # The part-to-assembly flip clears stale display groups in CAE 2022.
        viewport.setValues(displayedObject=data["key"])
        viewport.setValues(displayedObject=assembly)
        viewport.assemblyDisplay.symbolOptions.setValues(
            faceSymbolDensity=1, edgeSymbolDensity=1,
            meshSymbolFraction=float(fraction),
            arrowSymbolSize=int(arrow_size),
            otherSymbolSize=int(arrow_size))
        viewport.assemblyDisplay.setValues(
            viewCut=AC.OFF, mesh=AC.OFF, renderStyle=AC.SHADED,
            visibleInstances=tuple(visible), step=step,
            bcs=AC.ON if bcs else AC.OFF,
            constraints=AC.ON if constraints else AC.OFF,
            interactions=AC.ON if interactions else AC.OFF,
            loads=AC.ON if loads else AC.OFF,
            predefinedFields=AC.OFF, connectors=AC.OFF,
            engineeringFeatures=AC.OFF)
        refined._hide_capture_datums(viewport.assemblyDisplay)
        if show_rp:
            viewport.assemblyDisplay.geometryOptions.setValues(
                referencePointLabels=AC.ON,
                referencePointSymbols=AC.ON)
        try:
            viewport.setColor(colorMapping=viewport.colorMappings[mapping])
        except Exception as exc:
            if mapping in ("Material", "Section"):
                raise RuntimeError(
                    "Required %s color mapping is unavailable: %s" %
                    (mapping, exc))
            viewport.setColor(colorMapping=viewport.colorMappings["Default"])

    def camera(view_name, target, width):
        viewport.view.setValues(session.views[view_name])
        viewport.view.fitView()
        refined._retarget_view(viewport, target, width)
        viewport.forceRefresh()

    def capture(name):
        path = refined._print_view(
            session, viewport, os.path.join(refined.FIGURE_DIR, name))
        images.append(path)
        return path

    # Surface/contact evidence at the contact-finding step.  Abaqus' native
    # Interaction color map displays the actual named regions; sparse glyphs
    # keep the very fine C3D20R model legible.
    reset(STEP_FIT, ("SHAFT-1", "KEY-1", "BUSHING-1"),
          "Interaction", interactions=True)
    camera("Front", (0.0, 20.0, 36.0), 34.0)
    capture("13_contacts_keyway_interaction_front")

    reset(STEP_FIT, ("BUSHING-1", "HUB-1"),
          "Interaction", interactions=True)
    camera("Iso", (0.0, 0.0, 36.0), 92.0)
    capture("14_contact_taper_interaction_iso")

    # Initial mounting BCs are isolated by component to avoid millions of
    # overlapping node symbols in one unreadable view.
    reset("Initial", ("KEY-1",), "Boundary condition", bcs=True,
          fraction=0.01)
    camera("Iso", (0.0, 19.0, 36.0), 48.0)
    capture("15_initial_key_top_bc_iso")

    reset("Initial", ("BUSHING-1",), "Boundary condition", bcs=True,
          fraction=0.00001)
    camera("Iso", (0.0, 0.0, 36.0), 85.0)
    capture("16_initial_bushing_bc_iso")

    reset("Initial", ("SHAFT-1",), "Constraint", bcs=True,
          constraints=True, show_rp=True, fraction=0.001)
    camera("Back", (0.0, 0.0, 0.0), 52.0)
    capture("17_initial_rp_distributing_coupling_back")

    reset(STEP_TORSION, ("HUB-1",), "Boundary condition", bcs=True,
          fraction=0.001)
    camera("Iso", (0.0, 0.0, 36.0), 100.0)
    capture("18_service_hub_fixed_iso")

    # The Moment glyph coincides with the RP in CAE 2022.  This view records
    # the real load region; the following XY plot records its exact magnitude
    # and the complete triangular load path.
    reset(STEP_TORSION, ("SHAFT-1",), "Load", loads=True,
          show_rp=True, fraction=1.0, arrow_size=28)
    camera("Iso", (0.0, 0.0, 12.0), 62.0)
    capture("19_torque_CM3_at_RP_location_iso")

    xy_name = "FVA_Mt_1LW_CM3_at_RP_%.12g_Nm" % (
        data["fva"]["torque_Nmm"] / 1000.0)
    plot_name = "FVA_Mt_1LW_PLOT"
    if xy_name in session.xyDataObjects:
        del session.xyDataObjects[xy_name]
    if plot_name in session.xyPlots:
        del session.xyPlots[plot_name]
    try:
        torque_nm = data["fva"]["torque_Nmm"] / 1000.0
        amplitude = tuple(model.amplitudes[AMP_TORQUE].data)
        torque_data = tuple((float(row[0]), float(row[1]) * torque_nm)
                            for row in amplitude)
        xy_data = session.XYData(
            name=xy_name, data=torque_data,
            sourceDescription=(
                "FVA_LOAD_TORQUE_1LW: CM3 at FVA_SET_RP_SHAFT"))
        curve = session.Curve(xyData=xy_data)
        try:
            curve.setValues(
                legendLabel="CM3 at RP | peak %.12g N m" % torque_nm)
        except Exception:
            pass
        plot = session.XYPlot(name=plot_name)
        chart = plot.charts[list(plot.charts.keys())[0]]
        chart.setValues(curvesToPlot=(curve,))
        try:
            chart.axes1[0].axisData.setValues(title="Step time [s]")
            chart.axes2[0].axisData.setValues(title="Mt [N m]")
            chart.legend.setValues(show=True)
        except Exception:
            pass
        viewport.setValues(displayedObject=plot)
        viewport.forceRefresh()
        capture("20_torque_Mt_1LW_0_peak_0_curve")
    finally:
        try:
            del session.xyPlots[plot_name]
        except Exception:
            pass
        try:
            del session.xyDataObjects[xy_name]
        except Exception:
            pass

    # Explicit visual proof of all three FVA section families.  The native
    # Section color map leaves the locked assembly geometry untouched while
    # showing shaft, key and the shared bushing/hub assignment distinctly.
    reset("Initial", all_instances, "Section")
    camera("Iso", (0.0, 0.0, 36.0), 100.0)
    materials_sections_image = capture("21_materials_sections_iso")

    # Restore a neutral assembly view and leave no temporary model/session
    # entities behind except the PNG files themselves.
    viewport.setValues(displayedObject=data["key"])
    viewport.setValues(displayedObject=assembly)
    viewport.setColor(colorMapping=viewport.colorMappings["Default"])
    viewport.assemblyDisplay.setValues(
        viewCut=AC.OFF, mesh=AC.ON, renderStyle=AC.SHADED,
        visibleInstances=all_instances, bcs=AC.OFF,
        constraints=AC.OFF, interactions=AC.OFF, loads=AC.OFF)
    refined._hide_capture_datums(viewport.assemblyDisplay)
    viewport.view.setValues(session.views["Iso"])
    viewport.view.fitView()
    viewport.forceRefresh()

    evidence = {
        "geometry_alignment": {
            "images": list(base_images[4:8]),
            "checks": ["full assembly", "axial alignment",
                       "key-bushing clearance"]},
        "mesh": {
            "images": (list(base_images[0:6]) +
                       list(base_images[8:12])),
            "checks": ["100 percent C3D20R", "critical local refinement"]},
        "materials_surfaces_contacts": {
            "images": list(images[0:2]) + [materials_sections_image],
            "checks": ["three FVA section families",
                       "keyway contact regions", "conical interface"]},
        "bc_rp_coupling": {
            "images": list(images[2:6]),
            "checks": ["initial key BC", "initial bushing BC",
                       "shaft RP coupling", "service hub support"]},
        "steps_load_amplitude": {
            "images": list(images[6:8]),
            "checks": ["CM3 region at RP", "one 0-peak-0 cycle"]},
    }
    return tuple(images), evidence


def _validate_visual_evidence(images, evidence):
    required = (
        "geometry_alignment", "mesh", "materials_surfaces_contacts",
        "bc_rp_coupling", "steps_load_amplitude")
    if tuple(sorted(evidence.keys())) != tuple(sorted(required)):
        raise RuntimeError("Incomplete visual evidence manifest: %r" %
                           (tuple(sorted(evidence.keys())),))
    known = set(images)
    if len(images) != 21:
        raise RuntimeError("Expected exactly 21 evidence images; got %d" %
                           len(images))
    for path in images:
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            raise RuntimeError("Missing or empty visual evidence: %s" % path)
    for milestone in required:
        selected = tuple(evidence[milestone].get("images", ()))
        if not selected or any(path not in known for path in selected):
            raise RuntimeError("Invalid visual milestone %s" % milestone)


def _repo_names(repository):
    return tuple(sorted(str(name) for name in repository.keys()))


def _write_audit(data, params, out_dir, cae_path, images, evidence):
    model = data["model"]
    fva = _fva(params)
    audit_txt = os.path.join(out_dir, "PARAM_BUILD_AUDIT.txt")
    audit_json = os.path.join(out_dir, "PARAM_BUILD_AUDIT.json")
    geo = data["audit"]
    records = geo["records"]
    shaft_record = records["shaft"]
    shaft_warning_rate = (
        100.0 * len(shaft_record["warnings"]) /
        float(shaft_record["elements"]))

    _validate_visual_evidence(images, evidence)
    contracts = (
        ("steps", model.steps,
         ("Initial", STEP_FIT, STEP_FRICTION, STEP_TORSION)),
        ("interactions", model.interactions,
         tuple(data["fva"]["pairs"])),
        ("contact properties", model.interactionProperties,
         (PROP_FIT, PROP_SERVICE)),
        ("boundary conditions", model.boundaryConditions,
         ("FVA_BC_BUSHING_INITIAL", "FVA_BC_HUB_FIXED",
          "FVA_BC_KEY_INITIAL", "FVA_BC_SHAFT_INITIAL")),
        ("loads", model.loads, ("FVA_LOAD_TORQUE_1LW",)),
        ("amplitudes", model.amplitudes,
         (AMP_INTERFERENCE_RAMP, AMP_INTERFERENCE_HOLD, AMP_TORQUE)),
        ("constraints", model.constraints, ("FVA_COUPLING_SHAFT",)),
        ("field output", model.fieldOutputRequests,
         ("FVA_FIELD_CONTACT", "FVA_FIELD_GLOBAL",
          "FVA_FIELD_UNLOADED_KEYWAY")),
        ("history output", model.historyOutputRequests,
         ("FVA_HISTORY_RP",)),
    )
    for label, repository, expected in contracts:
        actual = set(_repo_names(repository))
        if actual != set(expected):
            raise RuntimeError(
                "FVA %s repository mismatch: actual=%r expected=%r" %
                (label, tuple(sorted(actual)), tuple(sorted(expected))))
    amplitude_data = tuple(tuple(float(value) for value in row)
                           for row in model.amplitudes[AMP_TORQUE].data)
    if amplitude_data != ((0.0, 0.0), (1.0, 1.0), (2.0, 0.0)):
        raise RuntimeError("FVA torque amplitude changed: %r" %
                           (amplitude_data,))
    if not data.get("nojob_stages"):
        raise RuntimeError("NOJOB stage evidence was not recorded")
    lines = [
        "PARAMETRIC MODEL BUILDER - FVA 600 III RESEARCH PRE-SOLVE AUDIT",
        "VERDICT: OK",
        "EVIDENCE_BADGE: FVA-RESEARCH",
        "generated=%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "model=%s" % model.name,
        "backend=%s" % BACKEND,
        "workflow=pre_solve_regression; complete_method_A=false; cycles=1; "
        "load_path=0_to_Mt_to_0",
        "torque_Nm=%.12g; torque_Nmm=%.12g" %
        (float(fva.get("torque_Nm", 1256.0)), data["fva"]["torque_Nmm"]),
        "amplitude=%s; data=((0,0),(1,1),(2,0)); final_load=0" % AMP_TORQUE,
        "steps=%r" % (_repo_names(model.steps),),
        "interactions=%r" % (_repo_names(model.interactions),),
        "contact_properties=%r" % (_repo_names(model.interactionProperties),),
        "boundary_conditions=%r" % (_repo_names(model.boundaryConditions),),
        "loads=%r" % (_repo_names(model.loads),),
        "amplitudes=%r" % (_repo_names(model.amplitudes),),
        "constraints=%r" % (_repo_names(model.constraints),),
        "surface_counts=%r" % data["fva"]["surface_counts"],
        "wellennut_prism_nodes=%d" % data["fva"]["prism_nodes"],
        "materials=Welle_C45N_Chaboche; Nabe_Bushing_C45N_UML; "
        "Passfeder_C45QT_idealplastic",
        "poisson_ratio=0.3; status=assumption_inherited_from_D40_master_"
        "not_explicit_in_FVA_report",
        "report_geometry_lPF_mm=50; current_locked_key_length_mm=38; "
        "status=audited_user_required_difference",
        "extra_current_model_interface=Bushing_Hub_taper; "
        "status=audited_adaptation",
        "figure29_text_cycles=20; plotted_pulses_appear_21; "
        "implemented_cycles=1_by_user_requirement",
        "element_contract=100pct_C3D20R",
        "shaft_analysis_check_warnings=%d/%d; rate_percent=%.12g; "
        "failed=%d; interpretation=PASS_not_failed_elements" %
        (len(shaft_record["warnings"]), shaft_record["elements"],
         shaft_warning_rate, len(shaft_record["failures"])),
        "shaft_warning_localization=distributed_not_exclusively_keyway; "
        "no_exclusive_localization_claim",
        "jobs=0; ties=0; solver_files=0; submitted=false",
        "field_output_requests=%r" %
        (_repo_names(model.fieldOutputRequests),),
        "history_output_requests=%r" %
        (_repo_names(model.historyOutputRequests),),
        "nojob_stages=%r" % (tuple(data["nojob_stages"]),),
        "cae=%s" % cae_path,
        "visual_image_count=%d" % len(images),
        "visual_milestones=%r" % (tuple(sorted(evidence.keys())),),
        "visual_images=%r" % (tuple(images),),
    ]
    for name in ("shaft", "key", "bushing", "hub"):
        record = records[name]
        lines.append(
            "part=%s; elements=%d; nodes=%d; types=%r; components=%d; "
            "failed=%d; warnings=%d; aspect_worst=%.12g" %
            (name, record["elements"], record["nodes"],
             record["histogram"], record["components"],
             len(record["failures"]), len(record["warnings"]),
             record["aspect_worst"]))
    lines.extend((
        "CHECK geometry_dimensions=PASS",
        "CHECK mesh_quality_and_C3D20R=PASS",
        "CHECK materials_and_sections=PASS",
        "CHECK contacts_steps_BC_load_amplitude=PASS",
        "CHECK strict_nojob=PASS",
    ))
    stream = open(audit_txt + ".tmp", "w")
    try:
        stream.write("\n".join(lines) + "\n")
    finally:
        stream.close()
    if os.path.exists(audit_txt):
        os.remove(audit_txt)
    os.rename(audit_txt + ".tmp", audit_txt)

    payload = {
        "verdict": "OK",
        "evidence_badge": "FVA-RESEARCH",
        "workflow": "pre_solve_regression",
        "is_complete_method_a": False,
        "model": model.name,
        "builder_version": (params.get('_derived', {}) or {}).get(
            'builder_version', '4.2'),
        "schema_version": (params.get('_derived', {}) or {}).get(
            'schema_version', 6),
        "derived": params.get('_derived', {}),
        "traceability": (params.get('_derived', {}) or {}).get('provenance', {}),
        "build_provenance": params.get('_build_provenance', {}),
        "artifact_dirs": params.get('_artifact_dirs', {}),
        "params": dict((key, value) for key, value in params.items()
                       if not key.startswith('_')),
        "backend": BACKEND,
        "fva_600_iii": fva,
        "repositories": {
            "parts": _repo_names(model.parts),
            "materials": _repo_names(model.materials),
            "sections": _repo_names(model.sections),
            "steps": _repo_names(model.steps),
            "interactions": _repo_names(model.interactions),
            "properties": _repo_names(model.interactionProperties),
            "bcs": _repo_names(model.boundaryConditions),
            "loads": _repo_names(model.loads),
            "amplitudes": _repo_names(model.amplitudes),
            "constraints": _repo_names(model.constraints),
            "field_output_requests": _repo_names(model.fieldOutputRequests),
            "history_output_requests": _repo_names(
                model.historyOutputRequests),
        },
        "fva_setup": data["fva"],
        "mesh": dict((name, {
            "elements": records[name]["elements"],
            "nodes": records[name]["nodes"],
            "histogram": records[name]["histogram"],
            "failed": len(records[name]["failures"]),
            "warnings": len(records[name]["warnings"]),
            "aspect_worst": records[name]["aspect_worst"],
        }) for name in ("shaft", "key", "bushing", "hub")),
        "mesh_quality_interpretation": {
            "shaft_warning_kind": "Abaqus ANALYSIS_CHECKS",
            "shaft_warnings": len(shaft_record["warnings"]),
            "shaft_elements": shaft_record["elements"],
            "shaft_warning_rate_percent": shaft_warning_rate,
            "shaft_failed": len(shaft_record["failures"]),
            "verdict": "PASS",
            "localization": (
                "Distributed; not exclusively in the keyway. "
                "No exclusive-localization claim is made."),
        },
        "jobs": [],
        "solver_files": [],
        "submitted": False,
        "nojob_stages": list(data["nojob_stages"]),
        "cae": cae_path,
        "visual_image_count": len(images),
        "images": list(images),
        "visual_evidence": evidence,
        "uncertainties": [
            "Poisson ratio is not explicit in the report; 0.3 is inherited.",
            "RP distance r and exact coupling subtype are not explicit.",
            "The conical D40 model adds bushing/hub geometry absent from VB1.",
            "Report key length is 50 mm while the locked current key is 38 mm.",
            "UML table is deterministically sampled from Eq. 22/23.",
        ],
    }
    stream = open(audit_json + ".tmp", "w")
    try:
        json.dump(payload, stream, indent=2, sort_keys=True)
    finally:
        stream.close()
    if os.path.exists(audit_json):
        os.remove(audit_json)
    os.rename(audit_json + ".tmp", audit_json)
    return audit_txt, audit_json


def build(params, core=None):
    """Build, configure, audit, capture and save the strict NOJOB FVA model."""
    from abaqus import mdb

    started = time.time()
    _guard_configuration(params)
    fva = _fva(params)
    artifacts = params.get("_artifact_dirs") or params.get("artifacts", {}) or {}
    legacy = str(params.get("output_dir") or os.path.join(
        _project_root(), "artifacts", "FVA600_RESEARCH_PRESOLVE_1LW_NOJOB"))
    generated_dir = str(artifacts.get("generated") or
                        artifacts.get("generated_dir") or legacy)
    model_dir = str(artifacts.get("model") or
                    artifacts.get("model_dir") or legacy)
    jobs_dir = str(artifacts.get("jobs") or
                   artifacts.get("jobs_dir") or legacy)
    screenshots_dir = str(artifacts.get("screenshots") or
                          artifacts.get("screenshots_dir") or
                          os.path.join(legacy, "figures"))
    model_name = str(params.get("model_name") or MODEL_NAME_DEFAULT)
    if model_name == "PARAM_MODEL":
        model_name = MODEL_NAME_DEFAULT
        params["model_name"] = model_name
    for directory in (generated_dir, model_dir, jobs_dir, screenshots_dir):
        _ensure_dir(directory)
    cae_path = os.path.join(model_dir, model_name + ".cae")
    for path in (cae_path, os.path.join(generated_dir, "PARAM_BUILD_AUDIT.txt"),
                 os.path.join(generated_dir, "PARAM_BUILD_AUDIT.json")):
        if os.path.exists(path):
            raise RuntimeError("Preservation guard: output exists: %s" % path)

    nojob_stages = []

    def checked(stage):
        _guard_nojob(mdb, jobs_dir, stage)
        nojob_stages.append(stage)

    checked("entry")
    occupied = tuple(str(name) for name in mdb.models.keys()
                     if str(name) != "Model-1")
    if occupied:
        raise RuntimeError("Start from a clean MDB; models=%r" % (occupied,))

    refined = _load_refined_backend(
        generated_dir, model_name, model_dir=model_dir,
        generated_dir=generated_dir, screenshots_dir=screenshots_dir)
    refined._guard_inputs()
    master = refined._install_master()
    master.validate_parameters()
    refined._status("[FVA CHECK 1/5] Building locked D40 V3 geometry")
    data = master.build_geometry()
    checked("geometry")
    refined._status("[FVA CHECK 2/5] Generating locked C3D20R mesh")
    data = refined._build_refined_mesh(data)
    checked("mesh")

    config = fva
    master._assign_materials = lambda model_data: _assign_fva_materials(
        model_data, config)
    refined._status("[FVA CHECK 3/5] Assigning report materials and assembly")
    data = refined._assemble_without_analysis(data)
    checked("materials and assembly")
    refined._status("[FVA CHECK 4/5] Adding contacts, BCs and one load cycle")
    data = _configure_fva_physics(data, config)
    checked("FVA physics")

    refined._status("[FVA CHECK 5/5] Running strict geometry/mesh audit")
    refined._audit(data)
    checked("strict audit")
    if "Model-1" in mdb.models:
        del mdb.models["Model-1"]
    if tuple(mdb.models.keys()) != (model_name,):
        raise RuntimeError("Model isolation failed: %r" %
                           (tuple(mdb.models.keys()),))
    mdb.saveAs(pathName=cae_path)
    if not os.path.isfile(cae_path) or os.path.getsize(cae_path) <= 0:
        raise RuntimeError("CAE was not saved: %s" % cae_path)
    checked("CAE save")

    base_images = refined._capture_views(data)
    checked("geometry and mesh visual captures")
    physics_images, evidence = _capture_fva_evidence(
        data, refined, base_images)
    images = tuple(base_images) + tuple(physics_images)
    _validate_visual_evidence(images, evidence)
    checked("FVA physics visual captures")

    data["nojob_stages"] = tuple(nojob_stages)
    audit_txt, audit_json = _write_audit(
        data, params, generated_dir, cae_path, images, evidence)
    checked("final audit")
    data["nojob_stages"] = tuple(nojob_stages)
    # Re-persist after the final guard so the serialized audit contains the
    # same complete NOJOB stage list as the returned build data.
    audit_txt, audit_json = _write_audit(
        data, params, generated_dir, cae_path, images, evidence)
    _guard_nojob(mdb, jobs_dir, "persisted final audit")
    print("[FVA] FVA-RESEARCH PRE-SOLVE / STRICT NOJOB BUILD PASS")
    print("[FVA] model   : %s" % model_name)
    print("[FVA] CAE     : %s" % cae_path)
    print("[FVA] audit   : %s" % audit_txt)
    print("[FVA] JSON    : %s" % audit_json)
    print("[FVA] images  : %d across %d visual milestones" %
          (len(images), len(evidence)))
    print("[FVA] jobs    : 0")
    print("[FVA] solve   : NOT CREATED / NOT SUBMITTED")
    print("[FVA] elapsed : %.3f s" % (time.time() - started))
    return data
