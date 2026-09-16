# -*- coding: utf-8 -*-
"""
================================================================================
 PARAMETRIC BUILDER v4.2 - Shaft / Key (Form A|B|AB) / Hub       (DIN 6885)
================================================================================
 Rebuilds the whole finite-element model from a set of parameters. Change a
 value (for example the shaft diameter D), run it, and the model is regenerated,
 meshed, assembled, audited and saved.

 V3 FOUNDATION RETAINED IN v4.2
   1. keyjoint_core.py is the SINGLE source of truth for the DIN 6885 table, the
      derived geometry, the validation rules and the design check. The GUI, this
      engine and the report generator all import it, so they can no longer drift.
   2. A validation GATE runs before anything is built: a bad parameter set is
      rejected with a plain-language reason instead of a stack trace.
   3. REAL local notch refinement. v2 could only seed the fillet arc, which
      shrank the tangential size alone and drove the aspect ratio to 68.9. v3
      PARTITIONS a band around the keyway root corner, so the notch element is
      small in BOTH in-plane directions, and grades the surrounding edges back
      to the global seed. This is the "dedicated partition around the keyway
      root" that the v2 README listed as the necessary next step.
   4. Machine-readable audit: PARAM_BUILD_AUDIT.json next to the text report.
   5. Optional ANALYSIS stage (off by default, so the model stays NOJOB): general
      contact, a torsion step driven through a kinematic coupling, the job, and
      - if it is solved - the stress concentration factor measured ON THIS MESH,
      a contact-pressure cross-check against the DIN 6892 hand formula, and a
      torque equilibrium check.
   6. Optional MESH DENSITY / QUALITY STUDY: the same geometry is re-meshed at
      several seed scales without a stress solve; invalid points remain visible.
   7. Multi-view preview including a close-up of the notch mesh.

 V4.2 INTEGRATION
   * Exact key forms A, B and AB with separate nominal, slot and bearing lengths.
   * Evidence badges prevent research, literature and screening values from being
     presented as current normative requirements.
   * Absolute artifact routes isolate CAE, jobs, captures, audits and reports in
     a timestamped project workspace created by the normal-Python GUI.

 KEY FORM SWITCH (DIN 6885)
   Form A  -> rounded ends  (pill / capsule footprint, end radius b/2)
   Form B  -> square ends   (rectangular footprint)
   Form AB -> one square and one rounded end

 HUB TYPE SWITCH
   cylindrical -> hub seated DIRECTLY on the shaft, bore d_i = D,
                  outer d_a = D * Q_A, own keyway of depth t2   [default]
   tapered     -> legacy variant with a tapered bushing + conical hub

 HOW TO RUN
   abaqus cae noGUI=build_parametric_model.py -- params_default.json
 or from the Model Builder 4.2 GUI.

 The Abaqus kernel is Python 2.7 up to and including release 2023, so this file
 is written for Python 2.7 and stays compatible with the Python 3 kernel of the
 newer releases.
================================================================================
"""
from __future__ import print_function
import os
import sys
import json
import math
import time
import hashlib

# --- the shared core must be importable even when Abaqus starts elsewhere ----
def _resolve_engine_path():
    """Return this script's real path even when Abaqus omits ``__file__``."""
    path = os.environ.get('MODEL_BUILDER_ENGINE_PATH')
    if not path:
        path = globals().get('__file__')
    if not path:
        code = getattr(_resolve_engine_path, '__code__', None)
        if code is None:
            code = getattr(_resolve_engine_path, 'func_code', None)
        path = getattr(code, 'co_filename', '') if code is not None else ''
    if not path:
        path = os.path.join(os.getcwd(), 'build_parametric_model.py')
    return os.path.abspath(path)


_ENGINE_PATH = _resolve_engine_path()
# Normalize the magic name as downstream provenance code also consumes it.
__file__ = _ENGINE_PATH
_HERE = os.environ.get('MODEL_BUILDER_RUNTIME_DIR')
if _HERE:
    _HERE = os.path.abspath(_HERE)
else:
    _HERE = os.path.dirname(_ENGINE_PATH)
if not os.path.isdir(_HERE):
    _HERE = os.path.dirname(_ENGINE_PATH)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import keyjoint_core as core
except ImportError as exc:
    core_path = os.path.join(_HERE, 'keyjoint_core.py')
    if not os.path.isfile(core_path):
        raise ImportError(
            'keyjoint_core.py was not found next to build_parametric_model.py.\n'
            'Expected: %s (engine: %s)' % (core_path, _ENGINE_PATH))
    raise ImportError(
        'keyjoint_core.py exists at %s but its import failed: %s' %
        (core_path, exc))

from abaqus import mdb, session
# Abaqus/CAE 2022 noGUI does not register every Model factory (notably
# Coupling/constraints) through ``abaqus`` alone.  The canonical CAE bootstrap
# loads interaction, constraint, step, load and output factories.
from caeModules import *
from abaqusConstants import *
import regionToolset
from mesh import ElemType

AX = {'x': (YZPLANE, 0), 'y': (XZPLANE, 1), 'z': (XYPLANE, 2)}

MAT_SHAFT = core.MAT_SHAFT
MAT_HUB = core.MAT_HUB
MAT_KEY = core.MAT_KEY
SEC = core.SEC

# literature constants are re-exported so the audit text below stays readable
REFS = core.REFS
KTS_SHAFT_LIT = core.KTS_SHAFT_LIT
KTS_HUB_LIT = core.KTS_HUB_LIT
KVM_3D_DIN_LIT = core.KVM_3D_DIN_LIT
KVM_2D_OPT_LIT = core.KVM_2D_OPT_LIT
RED_2D_SYM_LIT = core.RED_2D_SYM_LIT
RED_3D_UNSYM_LIT = core.RED_3D_UNSYM_LIT
ETA_OPT_LIT = core.ETA_OPT_LIT
DOF_CONVERGED_LIT = core.DOF_CONVERGED_LIT
D_OVER_D1_THICK = core.D_OVER_D1_THICK

# backwards-compatible aliases (the plug-in and older scripts import these)
default_params = core.default_params
deep_update = core.deep_update
_to_str = core.to_str
din6885_key = core.din6885_key
DIN6885 = core.DIN6885


def derive(params):
    """Thin wrapper so callers keep the old signature."""
    return core.derive(params, verbose=True)


# ================================================================== parameters
def load_params():
    """Read the original JSON schema first, then migrate/normalize explicitly."""
    # Abaqus/CAE 2022 may consume arguments after ``--`` before execfile() and
    # leave them out of sys.argv.  The GUI runner therefore provides the exact
    # JSON path through the environment; argv remains supported for direct use.
    path = os.environ.get('MODEL_BUILDER_PARAMS_PATH')
    if path:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise IOError(
                'MODEL_BUILDER_PARAMS_PATH does not exist: %s' % path)
    argv = sys.argv
    if path is None and '--' in argv:
        rest = argv[argv.index('--') + 1:]
        rest = [a for a in rest if not a.startswith('-')]
        if rest:
            path = rest[0]
    if path is None:
        project_root = os.environ.get('MODEL_BUILDER_PROJECT_ROOT')
        if project_root:
            cand = os.path.join(project_root, 'input', 'params.json')
            if os.path.isfile(cand):
                path = cand
    if path is None:
        cand = os.path.join(_HERE, 'params_default.json')
        if os.path.isfile(cand):
            path = cand
    if path and os.path.isfile(path):
        raw = core.read_json(path)
        p = core.normalize_params(raw)
        path = os.path.abspath(path)
        print('[params] loaded and normalized from', path)
    else:
        path = None
        p = core.normalize_params(core.default_params())
        print('[params] no JSON found, using schema-%d defaults' % core.SCHEMA_VERSION)
    p['_input_params_path'] = path
    return p


def _sha256_file(path):
    digest = hashlib.sha256()
    stream = open(path, 'rb')
    try:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    finally:
        stream.close()
    return digest.hexdigest()


def collect_build_provenance(params):
    """Fingerprint the exact engine/core/input consumed by this Abaqus run."""
    engine_path = os.path.abspath(__file__)
    if engine_path.lower().endswith(('.pyc', '.pyo')) and os.path.isfile(engine_path[:-1]):
        engine_path = engine_path[:-1]
    core_path = os.path.abspath(getattr(core, '__file__', ''))
    if core_path.lower().endswith(('.pyc', '.pyo')) and os.path.isfile(core_path[:-1]):
        core_path = core_path[:-1]
    candidates = (
        ('abaqus_engine', engine_path),
        ('shared_core', core_path),
        ('input_params', params.get('_input_params_path')),
    )
    records = []
    for role, path in candidates:
        if path and os.path.isfile(path):
            records.append({'role': role, 'path': path,
                            'size_bytes': os.path.getsize(path),
                            'sha256': _sha256_file(path)})
    declared = params.get('build_provenance', {}) or {}
    return {
        'hash_algorithm': 'sha256',
        'source_revision': os.environ.get(
            'MODEL_BUILDER_SOURCE_REVISION',
            declared.get('source_revision', 'unrecorded')),
        'runtime_inputs': records
    }


def gate(params, d):
    """Validation gate. Returns (issues, ok). Raises on a hard error."""
    issues = core.validate(params, d)
    errs = core.errors(issues)
    warns = core.warnings_(issues)
    print('[check] %d error(s), %d warning(s)' % (len(errs), len(warns)))
    for line in core.format_issues(issues):
        print(line)
    if errs:
        raise ValueError(
            'The parameter set cannot produce a valid model. First problem:\n  %s'
            % errs[0]['msg'])
    return issues


# ================================================================== geometry
def _cut(p, axis, off, tol=1e-6, only=None):
    """Partition every cell straddling a principal plane at 'off'.

    'only' is an optional predicate on the cell bounding box, used to keep the
    notch-refinement cuts LOCAL instead of slicing the whole part (that is what
    stops the cell count from exploding).
    """
    pp, idx = AX[axis]
    sel = []
    for c in p.cells:
        b = p.cells[c.index:c.index + 1].getBoundingBox()
        if b['low'][idx] < off - tol and b['high'][idx] > off + tol:
            if only is not None and not only(b):
                continue
            sel.append(c)
    if not sel:
        return 0
    dat = p.datums[p.DatumPlaneByPrincipalPlane(principalPlane=pp,
                                                offset=off).id]
    try:
        p.PartitionCellByDatumPlane(datumPlane=dat, cells=sel)
    except Exception as ex:
        print('   [cut] %s=%.4f skipped: %s' % (axis, off, str(ex)[:70]))
        return 0
    return len(sel)


def _box_overlap(lo, hi, idx):
    """Predicate factory: cell bbox must overlap [lo, hi] on axis idx."""
    def _f(b):
        return b['high'][idx] > lo - 1e-9 and b['low'][idx] < hi + 1e-9
    return _f


def _box_inside(lo, hi, idx, tol=1e-6):
    """Predicate factory: cell bbox must lie INSIDE [lo, hi] on axis idx."""
    def _f(b):
        return b['low'][idx] >= lo - tol and b['high'][idx] <= hi + tol
    return _f


def _clear_instances(a):
    for i in list(a.instances.keys()):
        del a.instances[i]


def _and(*preds):
    ps = [q for q in preds if q is not None]
    if not ps:
        return None

    def _f(b):
        for q in ps:
            if not q(b):
                return False
        return True
    return _f


def _notch_band_cuts(p, corners, band, in_axes=('x', 'y'), tol=1e-6,
                     axial='z', axial_range=None):
    """Partition a refinement band around each notch corner.

    corners : list of (u, v) corner positions in the two in-plane axes
    band    : half width of the band [mm]

    The two u planes of each corner are cut first: they are cheap because the
    keyway wall already splits the section there. The v planes are then
    restricted to the cells that lie INSIDE the u strip just created, so the
    refinement band, and the fine cells with it, stay local to the notch instead
    of slicing the whole part (which is what would make the cell count explode).
    """
    au, av = in_axes
    iu, iv = AX[au][1], AX[av][1]
    iax = AX[axial][1]
    # keep the band inside the keyway span; the plain shaft on either side must
    # stay one coarse cell, otherwise thin strips run the whole length of the
    # part and drag the refinement with them
    zpred = None
    if axial_range:
        zpred = _box_inside(min(axial_range), max(axial_range), iax, tol=1e-4)
    n = 0
    for (u, v) in corners:
        for off in (u - band, u + band):
            n += _cut(p, au, off, tol, only=zpred)
    for (u, v) in corners:
        pred = _and(_box_inside(min(u - band, u + band),
                                max(u - band, u + band), iu), zpred)
        for off in (v - band, v + band):
            n += _cut(p, av, off, tol, only=pred)
    print('   [notch] band +-%.4f mm partitioned around %d corner(s), %d cell cuts'
          % (band, len(corners), n))
    return n


def build_shaft(m, d):
    """Cylinder R, length L, capsule keyway (round ends R_cap), root fillet r2."""
    R, L = d['R'], d['L']
    slot_w, R_cap = d['slot_w'], d['R_cap']
    c1, c2, yF, r2 = d['c1'], d['c2'], d['yF'], d['r2']
    xw = d['x_slot']
    name = 'Shaft'

    s = m.ConstrainedSketch(name='__cyl__', sheetSize=8.0 * R)
    s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(R, 0.0))
    bl = m.Part(name='__BLANK__', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    bl.BaseSolidExtrude(sketch=s, depth=L)
    del m.sketches['__cyl__']

    # capsule cutter: footprint in (u=x, v=z), extruded through the shaft
    s2 = m.ConstrainedSketch(name='__cap__', sheetSize=8.0 * R)
    s2.Line(point1=(-xw, c1), point2=(-xw, c2))
    s2.Line(point1=(xw, c1), point2=(xw, c2))
    s2.ArcByCenterEnds(center=(0.0, c2), point1=(xw, c2),
                       point2=(-xw, c2), direction=COUNTERCLOCKWISE)
    s2.ArcByCenterEnds(center=(0.0, c1), point1=(-xw, c1),
                       point2=(xw, c1), direction=COUNTERCLOCKWISE)
    ct = m.Part(name='__CUTTER__', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    ct.BaseSolidExtrude(sketch=s2, depth=2.0 * R)
    del m.sketches['__cap__']

    a = m.rootAssembly
    a.DatumCsysByDefault(CARTESIAN)
    _clear_instances(a)
    a.Instance(name='__B__', part=bl, dependent=ON)
    a.Instance(name='__C__', part=ct, dependent=ON)
    a.rotate(instanceList=('__C__',), axisPoint=(0.0, 0.0, 0.0),
             axisDirection=(1.0, 0.0, 0.0), angle=90.0)
    bb = a.instances['__C__'].cells.getBoundingBox()
    a.translate(instanceList=('__C__',), vector=(0.0, yF - bb['low'][1], 0.0))
    a.InstanceFromBooleanCut(name=name, instanceToBeCut=a.instances['__B__'],
                             cuttingInstances=(a.instances['__C__'],),
                             originalInstances=DELETE)
    del m.parts['__BLANK__']
    del m.parts['__CUTTER__']
    _clear_instances(a)

    p = m.parts[name]
    d['shaft_fillet_edges'] = 0
    if r2 > 0:
        fe = [e for e in p.edges if abs(e.pointOn[0][1] - yF) < 1e-4]
        if fe:
            try:
                p.Round(radius=r2, edgeList=tuple(fe))
                d['shaft_fillet_edges'] = len(fe)
                print('[shaft] root fillet r2=%.3f on %d edges' % (r2, len(fe)))
            except Exception as ex:
                print('[shaft] fillet FAILED:', str(ex)[:90])

    # Cut at the keyway EXTREMES (z0, z1), not at the arc centres. The straight
    # wall meets the cap arc tangentially at the arc centre planes, so cutting
    # there truncates a G1 transition into a zero-angle cusp that no hex mesh
    # can fill. Measured on D40: z0/z1 -> 2 non-hex cells, c1/c2 -> 4.
    method_a_matching = bool(d.get('_method_a_matching', False))
    for off in (d['z0'], d['z1']):
        _cut(p, 'z', off)
    if method_a_matching:
        # The copied-interface backend uses free tetrahedra and needs a common
        # cylindrical quadrant topology.  Do not let keyway-only helper planes
        # split the complete outside diameter; the natural keyway faces already
        # provide those boundaries.
        _cut(p, 'x', 0.0)
        _cut(p, 'y', 0.0)
    else:
        for off in (0.0, xw, -xw):
            _cut(p, 'x', off)
        _cut(p, 'y', yF)

    # --- local notch refinement band around both keyway root corners --------
    # The copied-interface Method-A mesh uses isotropic free tetrahedra, local
    # interface edge seeds and explicit fillet-arc seeds.  The legacy hex band
    # would introduce unrelated seams into the cylindrical contact surface.
    if (not method_a_matching and d['notch_on'] and r2 > 0 and
            d['band_shaft'] > 0):
        for off in (d['c1'], d['c2']):
            _cut(p, 'z', off, only=_box_inside(-xw - d['band_shaft'],
                                               xw + d['band_shaft'], 0))
        _notch_band_cuts(p, [(xw, yF), (-xw, yF)], d['band_shaft'],
                         axial='z', axial_range=(d['c1'], d['c2']))

    if not method_a_matching:
        for off in (R * 0.45, -R * 0.45):
            _cut(p, 'x', off)
        for off in (R * 0.45, -R * 0.45):
            _cut(p, 'y', off)
    print('[shaft] %d cells after partitioning' % len(p.cells))
    return p


def build_key(m, d):
    """Key with a chamfered section and exact DIN Form A, B or AB ends.

    Form A has two rounded ends, B two straight ends, and AB one straight end
    at local -y plus one rounded end at local +y.  The AB assembly offset is
    derived separately so its straight face occupies a valid capsule slot.

    Built footprint-first: the (x, z) footprint is sketched in the part's local
    x-y plane and extruded along local z by h, then both perimeter loops get a
    45 deg chamfer.  The instance is rotated -90 deg about x in the assembly.
    """
    b, h, l, c = d['b'], d['h'], d['l'], d['c']
    method_a_matching = bool(d.get('_method_a_matching', False))
    r = b / 2.0
    name = 'Key'
    s = m.ConstrainedSketch(name='__key__', sheetSize=20.0 * max(b, l))
    if d['form'] == 'A':
        zc = l / 2.0 - r
        if zc <= 1e-9:
            raise ValueError('Form A key too short: l must exceed b (=%g)' % b)
        s.Line(point1=(-r, -zc), point2=(-r, zc))
        s.Line(point1=(r, -zc), point2=(r, zc))
        s.ArcByCenterEnds(center=(0.0, zc), point1=(r, zc),
                          point2=(-r, zc), direction=COUNTERCLOCKWISE)
        s.ArcByCenterEnds(center=(0.0, -zc), point1=(-r, -zc),
                          point2=(r, -zc), direction=COUNTERCLOCKWISE)
    elif d['form'] == 'AB':
        zc = l / 2.0 - r
        if zc <= -l / 2.0 + 1e-9:
            raise ValueError('Form AB key too short: l must exceed b/2 (=%g)'
                             % r)
        s.Line(point1=(-r, -l / 2.0), point2=(-r, zc))
        s.Line(point1=(r, zc), point2=(r, -l / 2.0))
        s.Line(point1=(r, -l / 2.0), point2=(-r, -l / 2.0))
        s.ArcByCenterEnds(center=(0.0, zc), point1=(-r, zc),
                          point2=(r, zc), direction=CLOCKWISE)
    else:
        s.rectangle(point1=(-r, -l / 2.0), point2=(r, l / 2.0))
    p = m.Part(name=name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    p.BaseSolidExtrude(sketch=s, depth=h)
    del m.sketches['__key__']

    if c > 0:
        top = [e for e in p.edges if abs(e.pointOn[0][2] - h) < 1e-6]
        bot = [e for e in p.edges if abs(e.pointOn[0][2]) < 1e-6]
        if top or bot:
            p.Chamfer(length=c, edgeList=tuple(top) + tuple(bot))
            print('[key] Form %s chamfer c=%.3f at 45 deg on %d edges'
                  % (d['form'], c, len(top) + len(bot)))

    # partitions (local frame: x = width, y = length, z = height)
    for off in (c, h - c):
        if 0 < off < h:
            _cut(p, 'z', off)
    if d['form'] == 'A':
        # split the straight middle from both round caps
        zc = l / 2.0 - r
        for off in (zc, -zc):
            _cut(p, 'y', off)
    elif d['form'] == 'AB':
        # one round cap at +y; the -y end remains straight
        _cut(p, 'y', l / 2.0 - r)
    for off in (0.0, r - c, -(r - c)):
        _cut(p, 'x', off)
    if not method_a_matching:
        _cut(p, 'y', 0.0)
    return p


def build_hub_cylindrical(m, d):
    """Hub seated directly on the shaft: bore d_i = D, outer d_a = D*QA,
    with its own keyway of depth t2 and roof fillet r1."""
    ri = d['d_i'] / 2.0
    ro = d['d_a'] / 2.0
    Lh = d['L_hub']
    gw = d['groove_w']
    roof = d['groove_roof']
    r1 = d['r1']
    name = 'Hub'
    if ro <= ri:
        raise ValueError('Hub outer diameter (%.2f) must exceed the bore (%.2f); '
                         'raise QA' % (d['d_a'], d['d_i']))

    s = m.ConstrainedSketch(name='__ann__', sheetSize=8.0 * ro)
    s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(ro, 0.0))
    s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(ri, 0.0))
    hp = m.Part(name='__HUB0__', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    hp.BaseSolidExtrude(sketch=s, depth=Lh)
    del m.sketches['__ann__']

    s2 = m.ConstrainedSketch(name='__slot__', sheetSize=8.0 * ro)
    s2.rectangle(point1=(-gw / 2.0, 0.0), point2=(gw / 2.0, roof))
    cu = m.Part(name='__SLOT__', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    cu.BaseSolidExtrude(sketch=s2, depth=Lh)
    del m.sketches['__slot__']

    a = m.rootAssembly
    _clear_instances(a)
    a.Instance(name='__H__', part=hp, dependent=ON)
    a.Instance(name='__S__', part=cu, dependent=ON)
    a.InstanceFromBooleanCut(name=name, instanceToBeCut=a.instances['__H__'],
                             cuttingInstances=(a.instances['__S__'],),
                             originalInstances=DELETE)
    del m.parts['__HUB0__']
    del m.parts['__SLOT__']
    _clear_instances(a)

    p = m.parts[name]
    d['hub_fillet_edges'] = 0
    if r1 > 0:
        ce = [e for e in p.edges
              if abs(e.pointOn[0][1] - roof) < 1e-4
              and abs(abs(e.pointOn[0][0]) - gw / 2.0) < 1e-3]
        if ce:
            try:
                p.Round(radius=r1, edgeList=tuple(ce))
                d['hub_fillet_edges'] = len(ce)
                print('[hub] keyway roof fillet r1=%.3f on %d edges'
                      % (r1, len(ce)))
            except Exception as ex:
                print('[hub] fillet FAILED:', str(ex)[:90])

    method_a_matching = bool(d.get('_method_a_matching', False))
    _cut(p, 'x', 0.0)
    _cut(p, 'y', 0.0)
    if not method_a_matching:
        for off in (gw / 2.0, -gw / 2.0):
            _cut(p, 'x', off)
        _cut(p, 'y', ri)
    if (not method_a_matching and d['notch_on'] and d['notch_hub'] and
            r1 > 0 and d['band_hub'] > 0):
        # A cut through the corner LEVEL itself is what makes the band edges
        # unambiguous. Without it the band-box boundary edges are equidistant
        # from the corner, the grading cannot pick a fine end, and the fallback
        # uniform seed puts 46 divisions on a 3 mm edge - measured on D40 as a
        # hub aspect ratio of 1077. The shaft gets the same treatment from its
        # keyway-floor cut at y = yF.
        _cut(p, 'y', roof)
        _notch_band_cuts(p, [(gw / 2.0, roof), (-gw / 2.0, roof)], d['band_hub'])
    print('[hub] %d cells after partitioning' % len(p.cells))
    return p


def build_revolved_annulus(m, name, length, r_in_small, r_in_large,
                           r_out_small, r_out_large):
    """Legacy helper (tapered variant): axis along part Y."""
    s = m.ConstrainedSketch(name='__rev__',
                            sheetSize=20.0 * max(r_out_large, length))
    cl = s.ConstructionLine(point1=(0.0, 0.0), point2=(0.0, 1.0))
    s.assignCenterline(line=cl)
    pts = [(r_in_small, 0.0), (r_out_small, 0.0),
           (r_out_large, length), (r_in_large, length)]
    for i in range(len(pts)):
        s.Line(point1=pts[i], point2=pts[(i + 1) % len(pts)])
    p = m.Part(name=name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    p.BaseSolidRevolve(sketch=s, angle=360.0, flipRevolveDirection=OFF)
    del m.sketches['__rev__']
    return p


def build_bushing_tapered(m, d, bp):
    """Legacy tapered bushing with a keyway groove (axis along part Y)."""
    L = float(bp['length'])
    ri = d['R']
    ro0 = float(bp['outer_dia_small']) / 2.0
    ro1 = float(bp['outer_dia_large']) / 2.0
    gw = d['groove_w']
    roof = d['groove_roof']
    name = 'Bushing'
    p = build_revolved_annulus(m, name, L, ri, ri, ro0, ro1)
    a = m.rootAssembly
    _clear_instances(a)
    s = m.ConstrainedSketch(name='__grv__', sheetSize=20.0 * ro1)
    s.rectangle(point1=(-gw / 2.0, 0.0), point2=(gw / 2.0, L))
    ct = m.Part(name='__GRV__', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    ct.BaseSolidExtrude(sketch=s, depth=roof)
    del m.sketches['__grv__']
    a.Instance(name='__BU__', part=p, dependent=ON)
    a.Instance(name='__GV__', part=ct, dependent=ON)
    a.InstanceFromBooleanCut(name='__BU_CUT__',
                             instanceToBeCut=a.instances['__BU__'],
                             cuttingInstances=(a.instances['__GV__'],),
                             originalInstances=DELETE)
    del m.parts['__GRV__']
    del m.parts[name]
    m.parts.changeKey(fromName='__BU_CUT__', toName=name)
    _clear_instances(a)
    p = m.parts[name]
    for off in (0.0, gw / 2.0, -gw / 2.0):
        _cut(p, 'x', off)
    _cut(p, 'z', 0.0)
    _cut(p, 'z', ri)
    return p


def build_hub_conical(m, d, bp):
    """Legacy conical hub matching the tapered bushing (axis along part Y)."""
    ro = d['d_a'] / 2.0
    ri0 = float(bp['outer_dia_small']) / 2.0
    ri1 = float(bp['outer_dia_large']) / 2.0
    p = build_revolved_annulus(m, 'Hub', d['L_hub'], ri0, ri1, ro, ro)
    _cut(p, 'x', 0.0)
    _cut(p, 'z', 0.0)
    return p


# ================================================================== meshing
def _elem_types(order, hex_code, quadratic_hex_code='C3D20R',
                allow_tet_fallback=True,
                topology_requirement='MIXED_ALLOWED'):
    """Return the exact Abaqus solid element tuple allowed by the policy."""
    order = str(order).strip().lower()
    topology = str(topology_requirement or 'MIXED_ALLOWED').strip().upper()
    if order == 'quadratic':
        qcode = str(quadratic_hex_code or 'C3D20R').strip().upper()
        qmap = {'C3D20': C3D20, 'C3D20R': C3D20R}
        if qcode not in qmap:
            raise ValueError('Quadratic hex code must be C3D20 or C3D20R.')
        types = [ElemType(elemCode=qmap[qcode], elemLibrary=STANDARD)]
        if topology == 'HYBRID_HEX':
            types.append(ElemType(elemCode=C3D15, elemLibrary=STANDARD))
        if allow_tet_fallback:
            types.append(ElemType(elemCode=C3D10, elemLibrary=STANDARD))
        return tuple(types)
    if order != 'linear':
        raise ValueError("Element order must be 'linear' or 'quadratic'.")
    lcode = str(hex_code or 'C3D8').strip().upper()
    lmap = {'C3D8': C3D8, 'C3D8I': C3D8I, 'C3D8R': C3D8R}
    if lcode not in lmap:
        raise ValueError('Linear hex code must be C3D8, C3D8I or C3D8R.')
    types = [ElemType(elemCode=lmap[lcode], elemLibrary=STANDARD)]
    if topology == 'HYBRID_HEX':
        types.append(ElemType(elemCode=C3D6, elemLibrary=STANDARD))
    if allow_tet_fallback:
        types.append(ElemType(elemCode=C3D4, elemLibrary=STANDARD))
    return tuple(types)


def _edge_ends(p, e):
    """The two end vertices of an edge, or None for a closed edge."""
    try:
        vids = e.getVertices()
    except Exception:
        return None
    if not vids or len(vids) < 2:
        return None
    try:
        return (p.vertices[vids[0]].pointOn[0], p.vertices[vids[-1]].pointOn[0])
    except Exception:
        return None


def _in_band(pt, corners, band, iu, iv, tol):
    for (cu, cv) in corners:
        if abs(pt[iu] - cu) <= band + tol and abs(pt[iv] - cv) <= band + tol:
            return True
    return False


def _seed_notch(p, nc):
    """LOCAL notch refinement seeding - the heart of the v3 improvement.

    v2 could only seed the fillet ARC, so only the TANGENTIAL element size
    shrank while the radial and axial sizes stayed at the global seed: the notch
    element went from 0.196 to 0.065 mm but the worst aspect ratio went from
    22.5 to 68.9. v3 first PARTITIONS a band around the keyway root corner
    (see _notch_band_cuts), which means the edges that run radially and
    circumferentially inside that band are SHORT. Seeding those short edges by
    size therefore refines the notch in BOTH in-plane directions at a bounded
    cost, and the elements stay compact.

    Long axial edges are deliberately left at the global seed: in torsion the
    stress varies strongly across the notch section and weakly along the
    keyway, so the elements may legitimately be elongated in that direction.
    Set notch.axial_factor > 0 to refine axially too (much more expensive).

    Edges that leave the band are seeded at grade * s_notch (a length cap keeps
    that from propagating far), which softens the jump to the global seed.
    """
    stats = {'arc': 0, 'band': 0, 'axial': 0, 'method': None,
             's_notch': 0.0, 's_band_max': 0.0, 'edges': [],
             'band_width': nc.get('band', 0.0)}
    radius = float(nc.get('radius', 0.0))
    n_arc = int(nc.get('n_arc', 0))
    band = float(nc.get('band', 0.0))
    if radius <= 0 or n_arc <= 0 or band <= 0:
        return stats
    corners = nc.get('corners') or []
    if not corners:
        return stats
    in_axes = nc.get('in_axes', ('x', 'y'))
    iu, iv = AX[in_axes[0]][1], AX[in_axes[1]][1]
    iax = AX[nc.get('axial', 'z')][1]
    s_global = float(nc.get('s_global', 0.0))
    method = str(nc.get('method', 'bias')).strip().lower()
    axial_factor = float(nc.get('axial_factor', 0.0) or 0.0)
    arc_scope = str(nc.get('arc_scope', 'all')).lower()
    zr = nc.get('axial_range')
    zlo = min(zr) - 1e-4 if zr else None
    zhi = max(zr) + 1e-4 if zr else None

    def _in_span(q):
        """The band only exists along the keyway, not over the whole part."""
        if zlo is None:
            return True
        return zlo <= q[iax] <= zhi

    arc_len = math.pi * radius / 2.0
    s_notch = arc_len / float(n_arc)
    fade_len = float(nc.get('fade_len_factor', 3.0)) * band
    # the coarse end of the graded band. Asking bias seeding to reach the global
    # seed inside a band only a few tenths of a millimetre wide is impossible, so
    # the target is capped by the band width itself; whatever is left of the jump
    # is absorbed by the free/swept mesh of the surrounding cell.
    s_band_max = max(2.0 * s_notch,
                     band / max(1.2, float(nc.get('band_max_factor', 3.0))))
    if s_global > 0:
        s_band_max = min(s_global, s_band_max)
    stats['s_notch'] = s_notch
    stats['s_band_max'] = s_band_max
    tol = max(1e-6, 1e-3 * band)
    # the fillet lives within 'radius' of the corner in v, so this catches every
    # fillet profile arc, including the ones on the keyway end caps
    v_of = sorted(set([round(cv, 9) for (cu, cv) in corners]))

    def _dist_to_corner(q):
        best = None
        for (cu, cv) in corners:
            dd = math.sqrt((q[iu] - cu) ** 2 + (q[iv] - cv) ** 2)
            if best is None or dd < best:
                best = dd
        return best if best is not None else 1e30

    # Two graded layers. 'inner' edges live entirely inside the band box and are
    # graded from s_notch at the fillet out to s_band_max at the box boundary.
    # 'outer' edges leave the box and are graded from s_band_max back to the
    # global seed, so the refinement dies out instead of leaking across the part
    # (measured: without this split 180 edges were caught and the coarse-seed
    # shaft jumped to 165 k elements).
    arc_e, size_e = [], []
    in1, in2, out1, out2, ax_e = [], [], [], [], []
    for e in p.edges:
        try:
            L = e.getSize(printResults=False)
        except Exception:
            continue
        if L <= 0:
            continue
        mid = e.pointOn[0]
        if abs(L - arc_len) <= 0.02 * arc_len + 1e-6:
            near_v = False
            for cv in v_of:
                if abs(mid[iv] - cv) <= band + tol:
                    near_v = True
                    break
            if arc_scope == 'band':
                near_v = near_v and _in_band(mid, corners, band, iu, iv, tol)
            if near_v:
                arc_e.append(e)
                continue
        ends = _edge_ends(p, e)
        if ends is None:
            continue
        q0, q1 = ends
        if not (_in_span(q0) and _in_span(q1)):
            continue
        dv = [q1[k] - q0[k] for k in range(3)]
        norm = math.sqrt(dv[0] ** 2 + dv[1] ** 2 + dv[2] ** 2) or 1.0
        i0 = _in_band(q0, corners, band, iu, iv, tol)
        i1 = _in_band(q1, corners, band, iu, iv, tol)
        if abs(dv[iax]) / norm > 0.9:            # runs along the keyway
            if axial_factor > 0 and (i0 or i1):
                ax_e.append(e)
            continue
        if not (i0 or i1):
            continue
        d0, d1 = _dist_to_corner(q0), _dist_to_corner(q1)
        graded = (method == 'bias' and abs(d0 - d1) > 0.02 * L)
        if i0 and i1:
            if graded:
                (in1 if d0 <= d1 else in2).append(e)
            elif L <= 1.2 * band:
                # equidistant from the corner (both ends the same distance away):
                # a uniform fine seed is only safe on a genuinely short edge
                size_e.append(e)
        elif (method == 'bias' and s_global > 1.5 * s_band_max
                and L <= fade_len):
            # One endpoint inside the band: fade back out to the global seed.
            # The length cap matters. Without it every radial edge of the section
            # gets a 0.5 mm seed at its inner end, and because a SWEPT hex mesh
            # carries its source face along the whole sweep, that refined section
            # is dragged down the entire plain shaft - measured on D40: 240 k
            # elements in the shaft instead of 70 k.
            (out1 if i0 else out2).append(e)

    def _try(fn, tag, edges, **kw):
        if not edges:
            return 0
        try:
            fn(edges=tuple(edges), **kw)
            return len(edges)
        except Exception as ex:
            print('   [notch] %s seeding skipped: %s' % (tag, str(ex)[:70]))
            return 0

    def _bias(tag, bucket, kwname, smin, smax, fallback):
        if not bucket:
            return 0
        try:
            p.seedEdgeByBias(biasMethod=SINGLE, minSize=smin, maxSize=smax,
                             constraint=FINER, **{kwname: tuple(bucket)})
            return len(bucket)
        except Exception as ex:
            print('   [notch] %s failed (%s), falling back to a plain size seed'
                  % (tag, str(ex)[:60]))
            return _try(p.seedEdgeBySize, tag, bucket, size=fallback,
                        deviationFactor=0.1, constraint=FINER)

    stats['arc'] = _try(p.seedEdgeByNumber, 'arc', arc_e,
                        number=max(1, n_arc), constraint=FINER)
    nband = 0
    if in1 or in2:
        stats['method'] = 'bias %.4f -> %.4f mm' % (s_notch, s_band_max)
        nband += _bias('inner end1', in1, 'end1Edges', s_notch, s_band_max, s_notch)
        nband += _bias('inner end2', in2, 'end2Edges', s_notch, s_band_max, s_notch)
    if size_e:
        if stats['method'] is None:
            stats['method'] = 'size %.4f mm' % s_notch
        nband += _try(p.seedEdgeBySize, 'band', size_e, size=s_notch,
                      deviationFactor=0.1, constraint=FINER)
    stats['band'] = nband
    nout = 0
    nout += _bias('outer end1', out1, 'end1Edges', s_band_max, s_global, s_band_max)
    nout += _bias('outer end2', out2, 'end2Edges', s_band_max, s_global, s_band_max)
    stats['fade'] = nout
    if axial_factor > 0 and ax_e:
        s_ax = axial_factor * s_notch
        if s_global > 0:
            s_ax = min(s_global, s_ax)
        stats['axial'] = _try(p.seedEdgeBySize, 'axial', ax_e, size=s_ax,
                              deviationFactor=0.1, constraint=FINER)
    touched = []
    for bucket in (arc_e, size_e, in1, in2, out1, out2, ax_e):
        for e in bucket:
            touched.append(e.index)
    stats['edges'] = touched
    print('   [notch] seeded: %d arc edges @ %d elem (%.4f mm), %d band edges '
          '(%s), %d fade-out edges (-> %.3f mm), %d axial'
          % (stats['arc'], n_arc, s_notch, stats['band'],
             stats['method'] or 'none', stats['fade'], s_global, stats['axial']))
    return stats


def _set_mesh_controls(p, strategy='HEX_STRUCTURED',
                       allow_tet_fallback=True):
    """Apply one auditable control recipe, with deterministic cell fallbacks.

    A recipe is not considered successful merely because ``setMeshControls``
    accepted it.  This function records what each cell actually received; mesh
    generation and quality checks decide whether the resulting candidate is
    admissible.
    """
    strategy = str(strategy or 'HEX_STRUCTURED').strip().upper()
    if strategy not in core.MESH_CONTROL_STRATEGIES:
        raise ValueError('Unsupported mesh control strategy %r.' % strategy)
    hex_dominated = globals().get('HEX_DOMINATED', HEX)
    recipes = {
        'HEX_STRUCTURED': (
            ('HEX_STRUCTURED', dict(elemShape=HEX, technique=STRUCTURED)),
            ('HEX_SWEEP_MEDIAL', dict(elemShape=HEX, technique=SWEEP,
                                      algorithm=MEDIAL_AXIS)),
            ('HEX_SWEEP_ADVANCING', dict(elemShape=HEX, technique=SWEEP,
                                         algorithm=ADVANCING_FRONT)),
            ('TET_FREE', dict(elemShape=TET, technique=FREE))),
        'HEX_SWEEP_MEDIAL': (
            ('HEX_SWEEP_MEDIAL', dict(elemShape=HEX, technique=SWEEP,
                                      algorithm=MEDIAL_AXIS)),
            ('HEX_SWEEP_ADVANCING', dict(elemShape=HEX, technique=SWEEP,
                                         algorithm=ADVANCING_FRONT)),
            ('TET_FREE', dict(elemShape=TET, technique=FREE))),
        'HEX_SWEEP_ADVANCING': (
            ('HEX_SWEEP_ADVANCING', dict(elemShape=HEX, technique=SWEEP,
                                         algorithm=ADVANCING_FRONT)),
            ('HEX_SWEEP_MEDIAL', dict(elemShape=HEX, technique=SWEEP,
                                      algorithm=MEDIAL_AXIS)),
            ('TET_FREE', dict(elemShape=TET, technique=FREE))),
        'HEX_DOMINATED': (
            ('HEX_DOMINATED', dict(elemShape=hex_dominated, technique=FREE)),
            ('TET_FREE', dict(elemShape=TET, technique=FREE))),
        'TET_FREE': (
            ('TET_FREE', dict(elemShape=TET, technique=FREE)),)
    }
    if not allow_tet_fallback and strategy in ('HEX_DOMINATED', 'TET_FREE'):
        raise RuntimeError('Mesh strategy %s is incompatible with HEX_ONLY; '
                           'tetrahedral fallback is disabled.' % strategy)
    control_chain = recipes[strategy]
    if not allow_tet_fallback:
        control_chain = tuple(item for item in control_chain
                              if item[0] != 'TET_FREE')
    if not control_chain:
        raise RuntimeError('No hexahedral mesh-control recipe is available for '
                           '%s while tetrahedral fallback is disabled.' % strategy)
    used = {}
    fallback_cells = 0
    failures = []
    for c in p.cells:
        applied = None
        for level, item in enumerate(control_chain):
            label, kw = item
            try:
                p.setMeshControls(regions=(c,), **kw)
                applied = label
                used[label] = used.get(label, 0) + 1
                if level > 0:
                    fallback_cells += 1
                break
            except Exception as ex:
                failures.append({'cell': c.index, 'control': label,
                                 'error': str(ex)[:120]})
        if applied is None:
            mode = ('hexahedral controls with tetrahedral fallback disabled'
                    if not allow_tet_fallback else 'configured controls')
            raise RuntimeError('No %s could be assigned to cell %d for strategy '
                               '%s; attempts=%d.' %
                               (mode, c.index, strategy, len(control_chain)))
    return {'requested': strategy, 'cell_controls': used,
            'fallback_cells': fallback_cells,
            'allow_tet_fallback': bool(allow_tet_fallback),
            'control_errors': failures}


def _cells_owning(p, hard, soft=None, exempt=None):
    """Split the cells that own bad elements into 'must repair' and 'optional'.

    hard   : element labels that FAILED the analysis checks - always repaired.
    soft   : element labels that only exceeded the aspect-ratio threshold.
    exempt : set of cell indices. A cell that is only 'soft' bad and is exempt
             is left alone.

    The notch refinement band is exempt on purpose: its elements are deliberately
    elongated ALONG the keyway, the direction with the smallest stress gradient
    in torsion. Without this exemption the repair pass re-meshes the whole band
    as free tetrahedra, which both destroys the hexahedral mesh the design calls
    for and makes the quality worse - measured on D40: 3.8 % hex, worst aspect
    ratio 60, 112 k elements in the shaft alone.
    """
    out = []
    soft = soft or set()
    if not hard and not soft:
        return out
    for c in p.cells:
        labels = set()
        try:
            if '__probe__' in p.sets:
                del p.sets['__probe__']
            s = p.Set(name='__probe__', cells=p.cells[c.index:c.index + 1])
            for e in s.elements:
                labels.add(e.label)
            del p.sets['__probe__']
        except Exception:
            if '__probe__' in p.sets:
                del p.sets['__probe__']
            continue
        if labels & hard:
            out.append(c)
            continue
        if labels & soft:
            if exempt and c.index in exempt:
                continue
            out.append(c)
    return out


def _cells_touching_edges(p, edge_indices):
    """Cell indices that own any of the given edges.

    This is how the graded notch neighbourhood is identified EXACTLY: every cell
    that carries a seed we placed on purpose. Those cells are excluded from the
    aspect-ratio repair, because their elements are deliberately elongated along
    the keyway and re-meshing them as free tetrahedra makes the mesh worse, not
    better (measured on D40: 33 % hex and worst aspect ratio 50, versus 92 % hex
    and 0 failed elements when the graded cells are left alone).
    """
    if not edge_indices:
        return set()
    want = set(edge_indices)
    out = set()
    for c in p.cells:
        try:
            if want & set(c.getEdges()):
                out.add(c.index)
        except Exception:
            continue
    return out


def robust_mesh(p, seed, order='linear', hex_code='C3D8', ar_threshold=25.0,
                notch=None, strategy='HEX_STRUCTURED', max_repairs=3,
                quadratic_hex_code='C3D20R', allow_tet_fallback=True,
                topology_requirement='MIXED_ALLOWED'):
    """Generate one complete candidate without violating its topology policy."""
    t0 = time.time()
    p.deleteMesh()
    try:
        p.deleteSeeds(regions=p.edges)
    except Exception:
        pass
    control_stats = _set_mesh_controls(
        p, strategy, allow_tet_fallback=allow_tet_fallback)
    p.seedPart(size=seed, deviationFactor=0.1, minSizeFactor=0.1)
    nstats = {}
    exempt = set()
    if notch:
        nc = dict(notch)
        nc['s_global'] = seed
        nstats = _seed_notch(p, nc)
        exempt = _cells_touching_edges(p, nstats.get('edges'))
        if exempt:
            print('   [notch] %d graded cell(s) exempt from aspect-ratio repair'
                  % len(exempt))
        nstats.pop('edges', None)
        nstats['graded_cells'] = len(exempt)
    elem_types = _elem_types(
        order, hex_code, quadratic_hex_code=quadratic_hex_code,
        allow_tet_fallback=allow_tet_fallback,
        topology_requirement=topology_requirement)
    p.setElementType(regions=(p.cells,), elemTypes=elem_types)
    p.generateMesh()

    empty = []
    empty_check_errors = []
    for c in p.cells:
        try:
            st = p.getMeshStats(regions=(c,))
            if st.numHexElems == 0 and st.numTetElems == 0 and \
                    st.numWedgeElems == 0:
                empty.append(c)
        except Exception as ex:
            empty_check_errors.append({'cell': c.index,
                                       'error': str(ex)[:120]})
    if not allow_tet_fallback and empty_check_errors:
        indices = [item['cell'] for item in empty_check_errors]
        raise RuntimeError(
            'HEX_ONLY could not verify %d cell(s) for emptiness; cell_indices=%s.' %
            (len(indices), indices[:500]))
    if empty:
        empty_indices = [c.index for c in empty]
        if not allow_tet_fallback:
            raise RuntimeError(
                'HEX_ONLY produced %d empty cell(s); cell_indices=%s. '
                'Tetrahedral degradation is disabled.' %
                (len(empty_indices), empty_indices[:500]))
        print('   [mesh] %d empty cell(s) forced to free tet' % len(empty))
        p.setMeshControls(regions=tuple(empty), elemShape=TET, technique=FREE)
        p.setElementType(regions=(p.cells,), elemTypes=elem_types)
        p.generateMesh()

    thr = float(ar_threshold or 0.0)
    repairs = 0
    repair_limit = max(0, int(max_repairs or 0))
    repaired_cells = []
    if not allow_tet_fallback:
        try:
            hard = set(e.label for e in
                       p.verifyMeshQuality(
                           criterion=ANALYSIS_CHECKS)['failedElements'])
        except Exception as ex:
            raise RuntimeError('HEX_ONLY analysis-quality verification failed: %s' %
                               str(ex)[:200])
        soft = set()
        if thr > 0:
            try:
                arbad = p.verifyMeshQuality(
                    criterion=ASPECT_RATIO, threshold=thr)
                soft = set(e.label for e in arbad.get('failedElements', []))
                soft -= hard
            except Exception as ex:
                raise RuntimeError('HEX_ONLY aspect-ratio verification failed: %s' %
                                   str(ex)[:200])
        cells = _cells_owning(p, hard, soft, exempt)
        if hard or cells:
            cell_indices = sorted(set([c.index for c in cells]))
            raise RuntimeError(
                'HEX_ONLY requires forbidden tetrahedral repair: '
                'failed_elements=%d, aspect_ratio_elements=%d, '
                'cell_count=%d, cell_indices=%s.' %
                (len(hard), len(soft), len(cell_indices), cell_indices[:500]))
        if soft:
            print('   [mesh] %d element(s) above aspect ratio %.1f are inside '
                  'the notch band and were left as hexahedra on purpose'
                  % (len(soft), thr))
    else:
        for _attempt in range(repair_limit):
            hard = set(e.label for e in
                       p.verifyMeshQuality(
                           criterion=ANALYSIS_CHECKS)['failedElements'])
            soft = set()
            if thr > 0:
                try:
                    arbad = p.verifyMeshQuality(
                        criterion=ASPECT_RATIO, threshold=thr)
                    soft = set(e.label for e in arbad.get('failedElements', []))
                    soft -= hard
                except Exception:
                    pass
            if not hard and not soft:
                break
            cells = _cells_owning(p, hard, soft, exempt)
            if not cells:
                if soft:
                    print('   [mesh] %d element(s) above aspect ratio %.1f are inside '
                          'the notch band and were left as hexahedra on purpose'
                          % (len(soft), thr))
                break
            repairs += 1
            repaired_cells.extend([c.index for c in cells])
            print('   [mesh] repair pass %d: %d cell(s) -> free tet (%d failed, '
                  '%d only slender)' %
                  (repairs, len(cells), len(hard), len(soft)))
            p.setMeshControls(
                regions=tuple(cells), elemShape=TET, technique=FREE)
            p.setElementType(regions=(p.cells,), elemTypes=elem_types)
            p.generateMesh()

    hist = {}
    for e in p.elements:
        hist[str(e.type)] = hist.get(str(e.type), 0) + 1
    if not allow_tet_fallback:
        non_hex = dict((code, count) for code, count in hist.items()
                       if not (code.startswith('C3D8') or
                               code.startswith('C3D20')))
        if non_hex:
            raise RuntimeError(
                'HEX_ONLY generated %d non-hexahedral element(s); types=%s.' %
                (sum(non_hex.values()), non_hex))
    return {'types': hist, 'notch': nstats, 'repairs': repairs,
            'seconds': round(time.time() - t0, 3), 'seed': seed,
            'strategy': str(strategy).upper(), 'controls': control_stats,
            'repaired_cells': sorted(set(repaired_cells)),
            'ar_exempt_cells': sorted(exempt),
            'element_order': str(order).lower(),
            'linear_hex_code': str(hex_code).upper(),
            'quadratic_hex_code': str(quadratic_hex_code).upper(),
            'topology_requirement': str(topology_requirement).upper(),
            'allow_tet_fallback': bool(allow_tet_fallback)}


def notch_config(d, which):
    """The notch refinement recipe for a part, or None when it is switched off."""
    if not d.get('notch_on'):
        return None
    if which == 'shaft':
        if d['r2'] <= 0 or d['band_shaft'] <= 0:
            return None
        corners = [(d['x_slot'], d['yF']), (-d['x_slot'], d['yF'])]
        radius, band = d['r2'], d['band_shaft']
    elif which == 'hub':
        if not d.get('notch_hub') or d['r1'] <= 0 or d['band_hub'] <= 0:
            return None
        gw2 = d['groove_w'] / 2.0
        corners = [(gw2, d['groove_roof']), (-gw2, d['groove_roof'])]
        radius, band = d['r1'], d['band_hub']
    else:
        return None
    return {'corners': corners, 'radius': radius, 'band': band,
            'n_arc': d['notch_arc_elems'],
            'in_axes': ('x', 'y'), 'axial': 'z',
            'axial_range': (d['c1'], d['c2']) if which == 'shaft' else None,
            'method': d.get('notch_method', 'bias'),
            'band_max_factor': d.get('notch_band_max_factor', 3.0),
            'axial_factor': d.get('notch_axial_factor', 0.0),
            'arc_scope': d.get('notch_arc_scope', 'band')}


def fillet_mesh_metrics(p, radius, nc=None):
    """How well is the notch actually resolved?

    Finds the quarter-circle fillet edges (arc length pi*r/2) and counts the
    mesh intervals on them. Resolving a notch is what controls the accuracy of a
    stress concentration factor, so this is reported explicitly instead of being
    assumed from the global seed. For second-order elements the mid-side nodes
    halve the node spacing, so the element count is corrected accordingly.

    When a notch recipe is given, the arcs are split into the ones on the
    STRAIGHT keyway runs (inside a refinement band) and the ones on the keyway
    END CAPS (no band can be built there with principal planes). Reporting a
    single minimum would otherwise hide the fact that the straight runs are well
    resolved while the caps are only at the global seed.
    """
    out = {'radius': radius, 'edges': 0, 'min_elems': None, 'max_elems': None,
           'elem_size': None, 'second_order': False,
           'band_min': None, 'band_size': None, 'band_edges': 0,
           'cap_min': None, 'cap_size': None, 'cap_edges': 0}
    if radius <= 0:
        return out
    target = math.pi * radius / 2.0
    second = False
    try:
        for e in p.elements:
            second = str(e.type) in ('C3D20', 'C3D20R', 'C3D10', 'C3D10M', 'C3D15')
            break
    except Exception:
        second = False
    out['second_order'] = second
    corners = (nc or {}).get('corners') or []
    band = float((nc or {}).get('band', 0.0) or 0.0)
    in_axes = (nc or {}).get('in_axes', ('x', 'y'))
    iu, iv = AX[in_axes[0]][1], AX[in_axes[1]][1]
    counts, bcounts, ccounts = [], [], []
    for e in p.edges:
        try:
            L = e.getSize(printResults=False)
        except Exception:
            continue
        if abs(L - target) > 0.02 * max(target, 1e-9) + 1e-6:
            continue
        out['edges'] += 1
        try:
            n = len(e.getNodes())
        except Exception:
            continue
        if n < 2:
            continue
        nelem = (n - 1) / 2.0 if second else float(n - 1)
        if nelem <= 0:
            continue
        counts.append(nelem)
        if corners and band > 0:
            if _in_band(e.pointOn[0], corners, band, iu, iv, 1e-3 * band):
                bcounts.append(nelem)
            else:
                ccounts.append(nelem)
    if counts:
        out['min_elems'] = min(counts)
        out['max_elems'] = max(counts)
        out['elem_size'] = target / max(min(counts), 1e-9)
    if bcounts:
        out['band_edges'] = len(bcounts)
        out['band_min'] = min(bcounts)
        out['band_size'] = target / max(min(bcounts), 1e-9)
    if ccounts:
        out['cap_edges'] = len(ccounts)
        out['cap_min'] = min(ccounts)
        out['cap_size'] = target / max(min(ccounts), 1e-9)
    return out


MESH_DIAGNOSTIC_LABEL_LIMIT = 500


def _bounded_quality_labels(values, limit=MESH_DIAGNOSTIC_LABEL_LIMIT):
    labels = []
    total = 0
    if values is None:
        values = []
    for element in values:
        total += 1
        if len(labels) < limit:
            labels.append(int(element.label))
    labels.sort()
    return labels, total, total > len(labels)


def mesh_quality(p, include_labels=False):
    ac = p.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
    ar = p.verifyMeshQuality(criterion=ASPECT_RATIO)
    failed_labels, failed_total, failed_truncated = _bounded_quality_labels(
        ac.get('failedElements', []))
    warning_labels, warning_total, warning_truncated = _bounded_quality_labels(
        ac.get('warningElements', []))
    if include_labels:
        return {
            'failed': failed_total,
            'warnings': warning_total,
            'failed_element_labels': failed_labels,
            'warning_element_labels': warning_labels,
            'failed_element_count': failed_total,
            'warning_element_count': warning_total,
            'failed_element_count_total': failed_total,
            'warning_element_count_total': warning_total,
            'truncated': bool(failed_truncated or warning_truncated),
            'diagnostic_label_limit': MESH_DIAGNOSTIC_LABEL_LIMIT,
            'ar_worst': ar.get('worst'),
            'ar_avg': ar.get('average')}
    return (failed_total, warning_total, ar.get('worst'), ar.get('average'))


def _bounded_mesh_diagnostics(metrics):
    """Copy metrics while enforcing the finite audit label contract."""
    out = dict(metrics or {})
    failed_total = int(out.get(
        'failed_element_count_total',
        out.get('failed_element_count', out.get('failed', 0))) or 0)
    warning_total = int(out.get(
        'warning_element_count_total',
        out.get('warning_element_count', out.get('warnings', 0))) or 0)
    failed_labels = list(out.get('failed_element_labels') or [])
    warning_labels = list(out.get('warning_element_labels') or [])
    failed_labels = failed_labels[:MESH_DIAGNOSTIC_LABEL_LIMIT]
    warning_labels = warning_labels[:MESH_DIAGNOSTIC_LABEL_LIMIT]
    out['failed_element_labels'] = failed_labels
    out['warning_element_labels'] = warning_labels
    out['failed_element_count'] = failed_total
    out['warning_element_count'] = warning_total
    out['failed_element_count_total'] = failed_total
    out['warning_element_count_total'] = warning_total
    out['truncated'] = bool(
        out.get('truncated', False) or
        failed_total > len(failed_labels) or
        warning_total > len(warning_labels))
    out['diagnostic_label_limit'] = MESH_DIAGNOSTIC_LABEL_LIMIT
    return out


def _empty_mesh_metrics(basis, seconds=0.0, topology_requirement=None,
                        quadratic_hex_code=None, reproduction_ok=None):
    return _bounded_mesh_diagnostics({
        'nodes': 0, 'elements': 0, 'types': {}, 'hex_pct': 0.0,
        'non_hex_count': 0, 'non_hex_pct': 0.0,
        'failed': 0, 'warnings': 0, 'components': 0,
        'ar_worst': 0.0, 'ar_avg': 0.0,
        'ar_bulk_worst': 0.0, 'ar_bulk_avg': 0.0,
        'ar_bulk_basis': basis, 'repairs': 0,
        'seconds': float(seconds or 0.0),
        'fillet_detected': False, 'fillet_arc_count': 0,
        'fillet_band_count': 0, 'fillet': {},
        'topology_requirement': topology_requirement,
        'quadratic_hex_code': quadratic_hex_code,
        'reproduction_ok': reproduction_ok})


def _bulk_aspect_ratio(p, excluded_cells=None):
    """Return AR outside the graded notch cells when the API supports regions."""
    all_ar = p.verifyMeshQuality(criterion=ASPECT_RATIO)
    result = {'worst': all_ar.get('worst'), 'average': all_ar.get('average'),
              'basis': 'global'}
    excluded = set(excluded_cells or [])
    if not excluded:
        return result
    bulk = tuple(c for c in p.cells if c.index not in excluded)
    if not bulk:
        return result
    try:
        ar = p.verifyMeshQuality(criterion=ASPECT_RATIO, regions=bulk)
        result = {'worst': ar.get('worst'), 'average': ar.get('average'),
                  'basis': 'bulk_excluding_%d_notch_cells' % len(excluded)}
    except Exception as ex:
        # Older Abaqus releases do not expose the regions keyword.  Falling
        # back is explicit in the audit; no optimistic value is fabricated.
        result['basis'] = 'global_fallback: %s' % str(ex)[:80]
    return result


def collect_mesh_metrics(p, rep=None, radius=0.0, notch=None):
    """Collect quality, topology and bounded diagnostic evidence."""
    rep = rep or {}
    quality_evidence = mesh_quality(p, include_labels=True)
    failed = quality_evidence['failed']
    warn = quality_evidence['warnings']
    arw = quality_evidence['ar_worst']
    ara = quality_evidence['ar_avg']
    hist = {}
    for e in p.elements:
        hist[str(e.type)] = hist.get(str(e.type), 0) + 1
    nhex = sum([v for k, v in hist.items()
                if k.startswith('C3D8') or k.startswith('C3D20')])
    elements = len(p.elements)
    nnonhex = max(0, elements - nhex)
    fm = fillet_mesh_metrics(p, float(radius or 0.0), notch) if radius else {
        'radius': 0.0, 'edges': 0, 'min_elems': None, 'max_elems': None,
        'elem_size': None, 'second_order': False, 'band_min': None,
        'band_size': None, 'band_edges': 0, 'cap_min': None,
        'cap_size': None, 'cap_edges': 0}
    bulk_ar = _bulk_aspect_ratio(p, rep.get('ar_exempt_cells'))
    arc_resolution = fm.get('band_min')
    if arc_resolution is None:
        arc_resolution = fm.get('min_elems')
    metrics = {
        'nodes': len(p.nodes), 'elements': elements, 'types': hist,
        'hex_pct': 100.0 * nhex / max(1, elements),
        'non_hex_count': nnonhex,
        'non_hex_pct': 100.0 * nnonhex / max(1, elements),
        'failed': failed, 'warnings': warn,
        'failed_element_labels': quality_evidence['failed_element_labels'],
        'warning_element_labels': quality_evidence['warning_element_labels'],
        'failed_element_count': quality_evidence['failed_element_count'],
        'warning_element_count': quality_evidence['warning_element_count'],
        'failed_element_count_total': quality_evidence['failed_element_count_total'],
        'warning_element_count_total': quality_evidence['warning_element_count_total'],
        'truncated': quality_evidence['truncated'],
        'diagnostic_label_limit': MESH_DIAGNOSTIC_LABEL_LIMIT,
        'components': connected_components(p),
        'ar_worst': arw, 'ar_avg': ara,
        'ar_bulk_worst': bulk_ar.get('worst'),
        'ar_bulk_avg': bulk_ar.get('average'),
        'ar_bulk_basis': bulk_ar.get('basis'),
        'repairs': int(rep.get('repairs', 0) or 0),
        'seconds': float(rep.get('seconds', 0.0) or 0.0),
        'fillet_detected': bool(fm.get('edges', 0)),
        'fillet_arc_count': int(arc_resolution or 0),
        'fillet_band_count': int(fm.get('band_edges', 0) or 0),
        'fillet': fm,
        'quadratic_hex_code': rep.get('quadratic_hex_code'),
        'topology_requirement': rep.get('topology_requirement'),
        'reproduction_ok': (rep.get('winner_reproduction_match')
                            if 'winner_reproduction_match' in rep else None)
    }
    return _bounded_mesh_diagnostics(metrics)


def adaptive_mesh(p, part_name, base_seed, mesh_plan, ar_threshold=25.0,
                  notch=None, fillet_radius=0.0):
    """Evaluate every configured recipe, rank it, and reproduce the winner."""
    if part_name not in mesh_plan.get('parts', {}):
        raise ValueError('No mesh policy was resolved for %s.' % part_name)
    policy = mesh_plan['parts'][part_name]
    order = mesh_plan['element_order']
    hex_code = mesh_plan['linear_hex_code']
    quadratic_hex_code = mesh_plan['quadratic_hex_code']
    topology_requirement = str(
        mesh_plan.get('topology_requirement', 'MIXED_ALLOWED')).upper()
    allow_tet_fallback = topology_requirement != 'HEX_ONLY'
    mesh_options = {
        'element_order': order,
        'linear_hex_code': hex_code,
        'quadratic_hex_code': quadratic_hex_code,
        'topology_requirement': topology_requirement,
        'allow_tet_fallback': allow_tet_fallback}
    attempts = []
    search_t0 = time.time()
    for recipe in policy.get('candidates', []):
        seed = float(base_seed) * float(recipe.get('seed_scale', 1.0))
        print('[mesh:auto] %s attempt %d %s seed=%.4f strategy=%s' % (
            part_name, int(recipe.get('attempt_index', len(attempts))) + 1,
            recipe.get('recipe_id'), seed, recipe.get('control_strategy')))
        attempt = {'recipe': json.loads(json.dumps(recipe)), 'seed': seed,
                   'options': dict(mesh_options), 'exception': None}
        try:
            rep = robust_mesh(
                p, seed, order, hex_code, ar_threshold, notch,
                strategy=recipe.get('control_strategy', 'HEX_STRUCTURED'),
                max_repairs=recipe.get('max_repairs', 3),
                quadratic_hex_code=quadratic_hex_code,
                allow_tet_fallback=allow_tet_fallback,
                topology_requirement=topology_requirement)
            metrics = collect_mesh_metrics(p, rep, fillet_radius, notch)
            quality = core.evaluate_mesh_quality(part_name, metrics, policy)
            attempt['mesh'] = rep
            attempt['metrics'] = metrics
            attempt['quality'] = quality
            print('[mesh:auto] %s %s -> %s %.1f/100, %.1f%% hex, '
                  'failed=%d components=%d' % (
                      part_name, recipe.get('recipe_id'), quality['status'],
                      quality['score'], metrics['hex_pct'], metrics['failed'],
                      metrics['components']))
        except Exception as ex:
            attempt['exception'] = str(ex)[:500]
            try:
                p.deleteMesh()
            except Exception:
                pass
            metrics = _empty_mesh_metrics(
                'candidate_exception', round(time.time() - search_t0, 3),
                topology_requirement, quadratic_hex_code)
            attempt['metrics'] = metrics
            attempt['quality'] = core.evaluate_mesh_quality(
                part_name, metrics, policy)
            attempt['quality']['hard_reasons'].append(
                'candidate exception: %s' % attempt['exception'])
            print('[mesh:auto] %s %s FAILED: %s' % (
                part_name, recipe.get('recipe_id'), attempt['exception']))
        attempts.append(attempt)
    selection = core.select_best_mesh_candidate(attempts)
    selected_index = selection['selected_index']
    selected_attempt = attempts[selected_index]
    selected_recipe = selected_attempt['recipe']
    final_rep = selected_attempt.get('mesh') or {
        'types': {}, 'notch': {}, 'repairs': 0, 'seconds': 0.0,
        'seed': selected_attempt.get('seed'),
        'strategy': selected_recipe.get('control_strategy')}
    final_metrics = selected_attempt['metrics']
    final_quality = selected_attempt['quality']
    reproduced = False
    reproduction_match = False
    reproduction_exact = False
    reproduction_deltas = {}
    reproduction_error = None

    # Always regenerate the chosen candidate.  This proves that the persisted
    # recipe, not merely whichever attempt happened to run last, owns the final
    # part mesh used by assembly, audit and the optional solver.
    if selected_attempt.get('exception') is None:
        try:
            reproduced = True
            final_rep = robust_mesh(
                p, selected_attempt['seed'], order, hex_code, ar_threshold, notch,
                strategy=selected_recipe.get('control_strategy', 'HEX_STRUCTURED'),
                max_repairs=selected_recipe.get('max_repairs', 3),
                quadratic_hex_code=quadratic_hex_code,
                allow_tet_fallback=allow_tet_fallback,
                topology_requirement=topology_requirement)
            final_metrics = collect_mesh_metrics(
                p, final_rep, fillet_radius, notch)
            old = selected_attempt['metrics']

            def _relative_delta(before, after):
                before = float(before or 0.0)
                after = float(after or 0.0)
                return abs(after - before) / max(1.0, abs(before))

            reproduction_deltas = {
                'nodes_relative': _relative_delta(old.get('nodes'),
                                                  final_metrics.get('nodes')),
                'elements_relative': _relative_delta(old.get('elements'),
                                                     final_metrics.get('elements')),
                'hex_pct_absolute': abs(float(old.get('hex_pct', 0.0) or 0.0) -
                                        float(final_metrics.get('hex_pct', 0.0) or 0.0)),
                'score_absolute': 0.0
            }
            reproduction_exact = (
                old.get('nodes') == final_metrics.get('nodes') and
                old.get('elements') == final_metrics.get('elements') and
                old.get('types') == final_metrics.get('types') and
                old.get('failed') == final_metrics.get('failed') and
                old.get('components') == final_metrics.get('components'))
            provisional_quality = core.evaluate_mesh_quality(
                part_name, final_metrics, policy)
            reproduction_deltas['score_absolute'] = abs(
                float(selected_attempt['quality'].get('score', 0.0) or 0.0) -
                float(provisional_quality.get('score', 0.0) or 0.0))
            # Advancing-front algorithms can vary a small number of elements
            # between equivalent runs.  Reproducibility therefore means the
            # same persisted recipe remains admissible and within explicit
            # 2% count / 2 percentage-point hex / 5-point score tolerances.
            reproduction_match = (
                provisional_quality.get('hard_passed') is True and
                old.get('failed') == final_metrics.get('failed') and
                old.get('components') == final_metrics.get('components') and
                set(old.get('types', {}).keys()) ==
                set(final_metrics.get('types', {}).keys()) and
                reproduction_deltas['nodes_relative'] <= 0.02 and
                reproduction_deltas['elements_relative'] <= 0.02 and
                reproduction_deltas['hex_pct_absolute'] <= 2.0 and
                reproduction_deltas['score_absolute'] <= 5.0)
            final_metrics['reproduction_ok'] = reproduction_match
            final_quality = core.evaluate_mesh_quality(
                part_name, final_metrics, policy)
        except Exception as ex:
            reproduction_error = str(ex)[:500]
            final_metrics = _empty_mesh_metrics(
                'reproduction_exception', 0.0, topology_requirement,
                quadratic_hex_code, reproduction_ok=False)
            final_quality = core.evaluate_mesh_quality(
                part_name, final_metrics, policy)
            final_quality['hard_reasons'].append(
                'winner reproduction exception: %s' % reproduction_error)

    total_seconds = round(time.time() - search_t0, 3)
    final_rep.update({
        'algorithm_version': mesh_plan['algorithm_version'],
        'template': mesh_plan['template'],
        'element_order': order,
        'linear_hex_code': hex_code,
        'quadratic_hex_code': quadratic_hex_code,
        'topology_requirement': topology_requirement,
        'allow_tet_fallback': allow_tet_fallback,
        'element_profile': mesh_plan.get('element_profile'),
        'options': dict(mesh_options),
        'selection': selection,
        'selected_recipe': selected_recipe,
        'selected_attempt_index': selected_index,
        'attempts': attempts,
        'metrics': final_metrics,
        'quality': final_quality,
        'winner_reproduced': reproduced,
        'winner_reproduction_match': reproduction_match,
        'winner_signature_exact': reproduction_exact,
        'winner_reproduction_tolerances': {
            'nodes_relative_max': 0.02, 'elements_relative_max': 0.02,
            'hex_pct_absolute_max': 2.0, 'score_absolute_max': 5.0},
        'winner_reproduction_deltas': reproduction_deltas,
        'winner_reproduction_error': reproduction_error,
        'selected_generation_seconds': final_rep.get('seconds', 0.0),
        'search_seconds': total_seconds,
        'seconds': total_seconds
    })
    # Keep top-level legacy fields synchronized with the reproduced winner.
    final_rep['types'] = final_metrics.get('types', {})
    final_rep['repairs'] = final_metrics.get('repairs', 0)
    print('[mesh:auto] %s SELECTED %s -> %s %.1f/100 '
          '(reproduced=%s, tolerance_match=%s, exact=%s, search=%.2fs)' % (
              part_name, selected_recipe.get('recipe_id'),
              final_quality.get('status'), final_quality.get('score'),
              reproduced, reproduction_match, reproduction_exact, total_seconds))
    return final_rep


_CORNERS = {'C3D8': 8, 'C3D8R': 8, 'C3D8I': 8, 'C3D20': 8, 'C3D20R': 8,
            'C3D4': 4, 'C3D10': 4, 'C3D10M': 4, 'C3D6': 6, 'C3D15': 6}


def connected_components(p):
    """Number of disconnected element clusters (1 = a single solid body)."""
    par = {}

    def find(x):
        r = x
        while par[r] != r:
            r = par[r]
        while par[x] != r:
            par[x], x = r, par[x]
        return r

    for e in p.elements:
        nc = _CORNERS.get(str(e.type), 8)
        c = e.connectivity[:nc]
        if not c:
            continue
        for n in c:
            par.setdefault(n, n)
        root = find(c[0])
        for n in c[1:]:
            b = find(n)
            if root != b:
                par[b] = root
    return len(set(find(k) for k in par))


# ================================================================== assembly
def assign_section(m, part, section_name):
    p = m.parts[part]
    p.SectionAssignment(region=regionToolset.Region(cells=p.cells),
                        sectionName=section_name, offset=0.0,
                        offsetType=MIDDLE_SURFACE, offsetField='',
                        thicknessAssignment=FROM_SECTION)


def _faces_at_radius(inst, radius, tol=1e-3, axis=2):
    """Instance faces whose pointOn lies on the cylinder r = radius."""
    out = []
    ii = [k for k in (0, 1, 2) if k != axis]
    for f in inst.faces:
        try:
            q = f.pointOn[0]
        except Exception:
            continue
        r = math.sqrt(q[ii[0]] ** 2 + q[ii[1]] ** 2)
        if abs(r - radius) <= tol * max(1.0, radius):
            out.append(f)
    return out


def _safe_set(a, name, **kw):
    if name in a.sets:
        del a.sets[name]
    return a.Set(name=name, **kw)


def _safe_surface(a, name, **kw):
    if name in a.surfaces:
        del a.surfaces[name]
    return a.Surface(name=name, **kw)


def build_all(params, mesh=True, derived_updates=None):
    """Build geometry/assembly and, by default, the legacy adaptive mesh.

    ``mesh=False`` is reserved for specialised backends that must prescribe an
    assembly-level mesh (for example the Method-A copied-interface workflow).
    Existing callers retain the exact historical behaviour because the default
    remains ``True``.  ``derived_updates`` carries internal geometry switches;
    it is deliberately not part of the persisted user schema.
    """
    eff = core.to_str(params)
    try:
        params.clear()
        params.update(eff)
    except Exception:
        params = eff
    name = str(params['model_name'])
    if name in mdb.models:
        del mdb.models[name]
    m = mdb.Model(name=name)
    d = derive(params)
    if derived_updates:
        d.update(dict(derived_updates))
        params['_derived'] = d
    issues = gate(params, d)
    mesh_plan = core.resolve_mesh_plan(params, d)
    params['_mesh_plan'] = mesh_plan
    order = mesh_plan['element_order']
    hexc = mesh_plan['linear_hex_code']
    qhexc = mesh_plan['quadratic_hex_code']
    topology_requirement = mesh_plan['topology_requirement']
    thr = float(params.get('ar_repair_threshold', 25.0))
    tapered = str(params.get('hub_type', 'cylindrical')).strip().lower() == 'tapered'

    # ---- materials & sections
    mats = params['materials']
    for mat in (MAT_SHAFT, MAT_HUB, MAT_KEY):
        prop = mats.get(mat, {"E": 210000.0, "nu": 0.30, "rho": 7.85e-09})
        ma = m.Material(name=mat, description='%s steel, linear elastic' %
                        str(prop.get('grade', 'C45')))
        ma.Elastic(table=((float(prop['E']), float(prop['nu'])),))
        ma.Density(table=((float(prop['rho']),),))
        # 'grade' and 'Re' are documentation only; the model stays elastic.
        m.HomogeneousSolidSection(name=SEC[mat], material=mat, thickness=None)

    # ---- geometry
    print('[build] shaft ...')
    sh = build_shaft(m, d)
    print('[build] key (Form %s) ...' % d['form'])
    ky = build_key(m, d)
    bu = None
    if tapered:
        print('[build] tapered bushing (legacy) ...')
        bu = build_bushing_tapered(m, d, params['bushing'])
        print('[build] conical hub (legacy) ...')
        hu = build_hub_conical(m, d, params['bushing'])
    else:
        print('[build] cylindrical hub ...')
        hu = build_hub_cylindrical(m, d)

    assign_section(m, 'Shaft', SEC[MAT_SHAFT])
    assign_section(m, 'Key', SEC[MAT_KEY])
    assign_section(m, 'Hub', SEC[MAT_HUB])
    if bu is not None:
        assign_section(m, 'Bushing', SEC[MAT_HUB])

    # ---- mesh: evaluate complete recipes independently for every piece
    report = {}
    if mesh:
        nc_shaft = None if tapered else notch_config(d, 'shaft')
        nc_hub = None if tapered else notch_config(d, 'hub')
        print('[mesh] template=%s algorithm=%s effective=%s/%s topology=%s' % (
            mesh_plan['template'], mesh_plan['algorithm_version'], order,
            qhexc if order == 'quadratic' else hexc, topology_requirement))
        print('[mesh] shaft base seed %.4f ...' % d['seed_shaft'])
        report['Shaft'] = adaptive_mesh(
            sh, 'Shaft', d['seed_shaft'], mesh_plan, thr,
            nc_shaft, d['r2'] if nc_shaft else 0.0)
        print('[mesh] key base seed %.4f ...' % d['seed_key'])
        report['Key'] = adaptive_mesh(
            ky, 'Key', d['seed_key'], mesh_plan, thr, None, 0.0)
        if bu is not None:
            print('[mesh] bushing base seed %.4f ...' % d['seed_bushing'])
            report['Bushing'] = adaptive_mesh(
                bu, 'Bushing', d['seed_bushing'], mesh_plan, thr, None, 0.0)
        print('[mesh] hub base seed %.4f ...' % d['seed_hub'])
        report['Hub'] = adaptive_mesh(
            hu, 'Hub', d['seed_hub'], mesh_plan, thr,
            nc_hub, d['r1'] if nc_hub else 0.0)
        params['_mesh_report'] = report
        params['_mesh_quality'] = core.aggregate_mesh_quality(
            dict((pn, rep.get('quality', {})) for pn, rep in report.items()),
            mesh_plan.get('fail_on_quality', True))
    else:
        print('[mesh] deferred to specialised assembly-level backend')
        params['_mesh_report'] = {}
        params['_mesh_quality'] = {
            'status': 'DEFERRED', 'hard_passed': False,
            'reason': 'specialised backend has not generated its mesh yet'}

    # ---- assembly
    a = m.rootAssembly
    _clear_instances(a)
    a.Instance(name='SHAFT-1', part=sh, dependent=ON)
    a.Instance(name='KEY-1', part=ky, dependent=ON)
    # key: local (x=b, y=l, z=h) -> rotate -90 about x gives (b, h, l)
    a.rotate(instanceList=('KEY-1',), axisPoint=(0.0, 0.0, 0.0),
             axisDirection=(1.0, 0.0, 0.0), angle=-90.0)
    kb = a.instances['KEY-1'].cells.getBoundingBox()
    a.translate(instanceList=('KEY-1',),
                vector=(0.0, d['y_min'] - kb['low'][1],
                        d['z_mid'] + d.get('key_axial_center_offset', 0.0) -
                        0.5 * (kb['low'][2] + kb['high'][2])))
    a.Instance(name='HUB-1', part=hu, dependent=ON)
    if bu is not None:
        a.Instance(name='BUSHING-1', part=bu, dependent=ON)
        for nm in ('BUSHING-1', 'HUB-1'):
            a.rotate(instanceList=(nm,), axisPoint=(0.0, 0.0, 0.0),
                     axisDirection=(1.0, 0.0, 0.0), angle=-90.0)
    for nm in (['HUB-1'] + (['BUSHING-1'] if bu is not None else [])):
        ib = a.instances[nm].cells.getBoundingBox()
        a.translate(instanceList=(nm,),
                    vector=(0.0, 0.0,
                            d['z_mid'] - 0.5 * (ib['low'][2] + ib['high'][2])))
    a.regenerate()

    # ---- sets
    pairs = [('SHAFT', 'SHAFT-1'), ('KEY', 'KEY-1'), ('HUB', 'HUB-1')]
    if bu is not None:
        pairs.append(('BUSHING', 'BUSHING-1'))
    if mesh:
        for tag, inst in pairs:
            _safe_set(a, 'ALL_%s_NODES' % tag, nodes=a.instances[inst].nodes)
            _safe_set(a, 'ALL_%s_ELEMENTS' % tag, elements=a.instances[inst].elements)

    # element set covering the shaft keyway root notch, used both to report the
    # peak stress there and to keep the SCF query away from unrelated hot spots
    d['notch_set'] = None
    if mesh and not tapered:
        w = max(d['band_shaft'], 3.0 * max(d['r2'], 1e-3))
        try:
            els = None
            for sgn in (1.0, -1.0):
                cu = sgn * d['x_slot']
                sub = a.instances['SHAFT-1'].elements.getByBoundingBox(
                    xMin=min(cu - w, cu + w), xMax=max(cu - w, cu + w),
                    yMin=d['yF'] - w, yMax=d['yF'] + w,
                    zMin=d['z0'] - w, zMax=d['z1'] + w)
                els = sub if els is None else els + sub
            if els is not None and len(els):
                _safe_set(a, 'NOTCH_SHAFT', elements=els)
                d['notch_set'] = 'NOTCH_SHAFT'
                d['notch_set_size'] = len(els)
                print('[sets] NOTCH_SHAFT: %d elements within %.3f mm of the '
                      'keyway root' % (len(els), w))
        except Exception as ex:
            print('[sets] NOTCH_SHAFT skipped:', str(ex)[:80])
    params['_issues'] = issues
    return m, report


# ================================================================== analysis
def add_analysis(m, params, d):
    """Optional stage: contact, torsion step, job. Default is OFF (NOJOB).

    Load path: the hub is held, and the torque is applied to the shaft drive end
    through a kinematic coupling to a reference point on the axis. The joint then
    has to carry the torque through the key exactly as the real one does, so the
    contact pressure can be compared against the DIN 6892 hand formula.
    """
    an = params.get('analysis', {}) or {}
    info = {'enabled': True, 'step': 'TORSION', 'job': None, 'submitted': False}
    a = m.rootAssembly
    mu = float(an.get('friction', 0.15))
    T = d['T_apply_Nmm']

    # ---- contact property + general contact -----------------------------
    prop = m.ContactProperty('CONTACT_PROP')
    if mu >= 0:
        prop.TangentialBehavior(
            formulation=PENALTY, directionality=ISOTROPIC,
            slipRateDependency=OFF, pressureDependency=OFF,
            temperatureDependency=OFF, dependencies=0, table=((mu,),),
            shearStressLimit=None, maximumElasticSlip=FRACTION,
            fraction=0.005, elasticSlipStiffness=None)
    else:
        prop.TangentialBehavior(formulation=FRICTIONLESS)
    prop.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON,
                        constraintEnforcementMethod=DEFAULT)
    m.ContactStd(name='GENERAL_CONTACT', createStepName='Initial')
    ci = m.interactions['GENERAL_CONTACT']
    ci.includedPairs.setValuesInStep(stepName='Initial', useAllstar=ON)
    ci.contactPropertyAssignments.appendInStep(
        stepName='Initial', assignments=((GLOBAL, SELF, 'CONTACT_PROP'),))
    info['friction'] = mu
    print('[analysis] general contact, friction mu=%s'
          % ('frictionless' if mu < 0 else '%.3f' % mu))

    # ---- drive end: reference point + kinematic coupling -----------------
    tol = max(1e-4, 1e-4 * d['L'])
    drive = a.instances['SHAFT-1'].faces.getByBoundingBox(
        zMin=-tol, zMax=tol)
    if not len(drive):
        raise ValueError('Could not find the shaft drive end faces at z = 0.')
    _safe_surface(a, 'SHAFT_DRIVE', side1Faces=drive)
    rp = a.ReferencePoint(point=(0.0, 0.0, 0.0))
    rpset = _safe_set(a, 'RP_DRIVE',
                      referencePoints=(a.referencePoints[rp.id],))
    m.Coupling(name='CPL_DRIVE', controlPoint=rpset,
               surface=a.surfaces['SHAFT_DRIVE'],
               influenceRadius=WHOLE_SURFACE, couplingType=KINEMATIC,
               localCsys=None, u1=ON, u2=ON, u3=ON, ur1=ON, ur2=ON, ur3=ON)
    info['drive_faces'] = len(drive)

    # ---- held region on the hub ------------------------------------------
    hold = str(an.get('hold', 'hub_outer')).strip().lower()
    hub = a.instances['HUB-1']
    if hold == 'hub_faces':
        hb = hub.cells.getBoundingBox()
        f = hub.faces.getByBoundingBox(zMin=hb['low'][2] - tol,
                                       zMax=hb['low'][2] + tol)
        f2 = hub.faces.getByBoundingBox(zMin=hb['high'][2] - tol,
                                        zMax=hb['high'][2] + tol)
        faces = f + f2
    else:
        faces = _faces_at_radius(hub, d['d_a'] / 2.0)
        faces = hub.faces[0:0] + tuple(faces) if faces else hub.faces[0:0]
    if not len(faces):
        raise ValueError('Could not find the hub faces to hold (hold=%s).' % hold)
    holdset = _safe_set(a, 'HOLD_HUB', faces=faces)
    info['hold'] = hold
    info['hold_faces'] = len(faces)

    # ---- step -------------------------------------------------------------
    nl = ON if bool(an.get('nlgeom', False)) else OFF
    st = m.StaticStep(name='TORSION', previous='Initial',
                      description='Torque %.1f N m through the keyed joint'
                                  % d['T_apply'],
                      timePeriod=1.0, nlgeom=nl,
                      maxNumInc=int(an.get('max_num_inc', 200)),
                      initialInc=float(an.get('initial_inc', 0.1)),
                      minInc=float(an.get('min_inc', 1e-08)), maxInc=1.0)
    if bool(an.get('stabilize', True)):
        try:
            st.setValues(stabilizationMethod=DISSIPATED_ENERGY_FRACTION,
                         stabilizationMagnitude=2e-4,
                         continueDampingFactors=False,
                         adaptiveDampingRatio=0.05)
            info['stabilized'] = True
        except Exception as ex:
            print('[analysis] stabilisation not applied:', str(ex)[:70])
            info['stabilized'] = False

    # ---- boundary conditions and load ------------------------------------
    m.EncastreBC(name='HOLD_HUB', createStepName='Initial', region=holdset)
    m.DisplacementBC(name='RP_GUIDE', createStepName='Initial', region=rpset,
                     u1=0.0, u2=0.0, u3=0.0, ur1=0.0, ur2=0.0, ur3=UNSET,
                     amplitude=UNSET, distributionType=UNIFORM, fieldName='',
                     localCsys=None)
    m.Moment(name='TORQUE', createStepName='TORSION', region=rpset, cm3=T,
             distributionType=UNIFORM, field='', localCsys=None)
    info['T_Nmm'] = T

    # ---- output ----------------------------------------------------------
    try:
        m.fieldOutputRequests['F-Output-1'].setValues(
            variables=('S', 'U', 'E', 'RF', 'CSTRESS', 'CDISP'), numIntervals=4)
    except Exception:
        m.FieldOutputRequest(name='F-Output-1', createStepName='TORSION',
                             variables=('S', 'U', 'E', 'RF', 'CSTRESS', 'CDISP'))
    try:
        m.HistoryOutputRequest(name='H-RP', createStepName='TORSION',
                               variables=('UR3', 'RM3'), region=rpset)
    except Exception:
        pass

    # ---- job -------------------------------------------------------------
    if bool(an.get('create_job', True)):
        jn = str(params['model_name']) + '_TORSION'
        jn = jn.replace(' ', '_')[:70]
        if jn in mdb.jobs:
            del mdb.jobs[jn]
        cpus = max(1, int(an.get('cpus', 1)))
        kw = dict(name=jn, model=m.name, type=ANALYSIS,
                  description='Torsion of the DIN 6885 keyed joint',
                  numCpus=cpus, memory=90, memoryUnits=PERCENTAGE,
                  explicitPrecision=SINGLE, nodalOutputPrecision=SINGLE,
                  echoPrint=OFF, modelPrint=OFF, contactPrint=OFF,
                  historyPrint=OFF)
        if cpus > 1:
            kw['numDomains'] = cpus
            kw['multiprocessingMode'] = DEFAULT
        mdb.Job(**kw)
        info['job'] = jn
        print('[analysis] job created:', jn)
    return info


def submit_job(job_name, out_dir):
    """Run the solver and wait. Returns (status, odb_path, seconds)."""
    t0 = time.time()
    j = mdb.jobs[job_name]
    print('[solve] submitting', job_name)
    j.submit(consistencyChecking=OFF)
    j.waitForCompletion()
    el = round(time.time() - t0, 1)
    odb = os.path.join(os.getcwd(), job_name + '.odb')
    if not os.path.isfile(odb):
        cand = os.path.join(out_dir, job_name + '.odb')
        if os.path.isfile(cand):
            odb = cand
    print('[solve] status=%s after %.1f s' % (str(j.status), el))
    return str(j.status), odb, el


def _max_of(field, comp=None, inv='mises'):
    """Max value of a field output, with the element/node label."""
    best = (None, None, None)
    for v in field.values:
        if comp is not None:
            try:
                val = v.data[comp]
            except Exception:
                continue
        else:
            val = getattr(v, inv, None)
            if val is None:
                continue
        if best[0] is None or val > best[0]:
            lab = getattr(v, 'elementLabel', None) or getattr(v, 'nodeLabel', None)
            inst = v.instance.name if getattr(v, 'instance', None) else '?'
            best = (val, lab, inst)
    return best


def post_process(odb_path, d, info):
    """Read the ODB and report what the mesh actually predicts.

    Three things are checked, because a solved model is only useful if it is
    also verified:
      * the peak von Mises at the shaft keyway root -> KvM = sigma_vM / tau_nom,
        directly comparable with the published value for the DIN design,
      * the peak contact pressure -> cross-check of the DIN 6892 hand formula,
      * the torque carried by the held hub -> equilibrium error in percent.
    """
    import visualization  # noqa: F401  (registers the ODB reader)
    from odbAccess import openOdb
    out = {'odb': odb_path}
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        stepname = info.get('step', 'TORSION')
        if stepname not in odb.steps:
            stepname = list(odb.steps.keys())[-1]
        step = odb.steps[stepname]
        fr = step.frames[-1]
        out['step'] = stepname
        out['frames'] = len(step.frames)
        out['frame_time'] = fr.frameValue

        S = fr.fieldOutputs['S']
        v, lab, inst = _max_of(S, inv='mises')
        out['mises_max_model'] = v
        out['mises_max_at'] = '%s elem %s' % (inst, lab)

        nset = d.get('notch_set')
        if nset and nset in odb.rootAssembly.elementSets:
            sub = S.getSubset(region=odb.rootAssembly.elementSets[nset])
            v2, lab2, inst2 = _max_of(sub, inv='mises')
            out['mises_notch'] = v2
            out['mises_notch_at'] = '%s elem %s' % (inst2, lab2)
            sub3 = S.getSubset(region=odb.rootAssembly.elementSets[nset])
            v3 = _max_of(sub3, inv='maxPrincipal')
            out['maxprin_notch'] = v3[0]
        tau = d.get('tau_nom_apply') or 0.0
        out['tau_nom_apply'] = tau
        if tau > 0:
            base = out.get('mises_notch') or out.get('mises_max_model')
            if base:
                out['KvM'] = base / tau
            if out.get('mises_max_model'):
                out['KvM_model'] = out['mises_max_model'] / tau

        if 'CSTRESS' in fr.fieldOutputs:
            cs = fr.fieldOutputs['CSTRESS']
            try:
                cp = cs.getScalarField(componentLabel='CPRESS')
                v4, lab4, inst4 = _max_of(cp, comp=None, inv='data')
                if v4 is None:
                    best = None
                    for val in cp.values:
                        if best is None or val.data > best:
                            best = val.data
                    v4 = best
                out['cpress_max'] = v4
            except Exception as ex:
                out['cpress_note'] = str(ex)[:80]

        # ---- torque equilibrium at the held hub surface -------------------
        if 'RF' in fr.fieldOutputs and 'HOLD_HUB' in odb.rootAssembly.nodeSets:
            rf = fr.fieldOutputs['RF'].getSubset(
                region=odb.rootAssembly.nodeSets['HOLD_HUB'])
            coords = {}
            for iname, inst_o in odb.rootAssembly.instances.items():
                cc = {}
                for n in inst_o.nodes:
                    cc[n.label] = n.coordinates
                coords[iname] = cc
            Mz = 0.0
            Fx = Fy = Fz = 0.0
            for val in rf.values:
                iname = val.instance.name if val.instance else None
                c = coords.get(iname, {}).get(val.nodeLabel)
                if c is None:
                    continue
                fx, fy, fz = val.data[0], val.data[1], val.data[2]
                Fx += fx
                Fy += fy
                Fz += fz
                Mz += c[0] * fy - c[1] * fx
            out['reaction_Mz_Nmm'] = Mz
            out['reaction_F'] = (Fx, Fy, Fz)
            T = info.get('T_Nmm') or 0.0
            if T:
                out['torque_balance_pct'] = abs(abs(Mz) - abs(T)) / abs(T) * 100.0
    finally:
        try:
            odb.close()
        except Exception:
            pass
    return out


# ================================================================== mesh study
def mesh_study(m, params, d, order, hexc, thr, selected=None):
    """Re-mesh the selected shaft recipe at several density scales.

    This remains a density/quality study unless a solver is also run; it is not
    labelled stress convergence.  The exact AUTO winner is restored afterward.
    """
    st = params.get('study', {}) or {}
    scales = [float(s) for s in (st.get('seed_scales') or [])]
    if not scales:
        return None
    selected = selected or {}
    mesh_plan = params.get('_mesh_plan') or core.resolve_mesh_plan(params, d)
    policy = mesh_plan['parts']['Shaft']
    order = mesh_plan['element_order']
    hexc = mesh_plan['linear_hex_code']
    qhexc = mesh_plan['quadratic_hex_code']
    topology_requirement = mesh_plan['topology_requirement']
    allow_tet_fallback = topology_requirement != 'HEX_ONLY'
    recipe = selected.get('selected_recipe', {}) or {}
    strategy = recipe.get('control_strategy', selected.get('strategy',
                                                           'HEX_STRUCTURED'))
    max_repairs = recipe.get('max_repairs', 3)
    p = m.parts['Shaft']
    nc = notch_config(d, 'shaft')
    base = float(selected.get('seed', d['seed_shaft']) or d['seed_shaft'])
    rows = []
    for sc in scales:
        seed = base * sc
        print('[study] selected shaft recipe %s, seed scale %.3f -> %.4f mm' % (
            recipe.get('recipe_id', strategy), sc, seed))
        rep = robust_mesh(
            p, seed, order, hexc, thr, nc, strategy=strategy,
            max_repairs=max_repairs, quadratic_hex_code=qhexc,
            allow_tet_fallback=allow_tet_fallback,
            topology_requirement=topology_requirement)
        metrics = collect_mesh_metrics(p, rep, d['r2'], nc)
        quality = core.evaluate_mesh_quality('Shaft', metrics, policy)
        fm = metrics['fillet']
        rows.append({
            'scale': sc, 'seed': seed, 'nodes': metrics['nodes'],
            'elements': metrics['elements'], 'dof': 3 * metrics['nodes'],
            'hex_pct': metrics['hex_pct'],
            'non_hex_pct': metrics['non_hex_pct'],
            'quadratic_hex_code': qhexc,
            'topology_requirement': topology_requirement,
            'arc_elems': fm.get('band_min') or fm.get('min_elems'),
            'notch_size': fm.get('band_size') or fm.get('elem_size'),
            'ar_worst': metrics['ar_worst'], 'ar_avg': metrics['ar_avg'],
            'ar_bulk_worst': metrics['ar_bulk_worst'],
            'failed': metrics['failed'], 'seconds': rep['seconds'],
            'quality_status': quality['status'],
            'quality_score': quality['score'],
            'hard_passed': quality['hard_passed'],
            'quality_reasons': quality.get('hard_reasons', []),
            'recipe_id': recipe.get('recipe_id', ''),
            'strategy': strategy})
    print('[study] restoring AUTO winner %s at seed %.4f' % (
        recipe.get('recipe_id', strategy), base))
    rep = robust_mesh(
        p, base, order, hexc, thr, nc, strategy=strategy,
        max_repairs=max_repairs, quadratic_hex_code=qhexc,
        allow_tet_fallback=allow_tet_fallback,
        topology_requirement=topology_requirement)
    restored_metrics = collect_mesh_metrics(p, rep, d['r2'], nc)
    return {'rows': rows, 'restored': rep,
            'restored_metrics': restored_metrics,
            'recipe_id': recipe.get('recipe_id', ''),
            'strategy': strategy,
            'quadratic_hex_code': qhexc,
            'topology_requirement': topology_requirement,
            'allow_tet_fallback': allow_tet_fallback,
            'admissible_scales': len([row for row in rows if row['hard_passed']]),
            'inadmissible_scales': len([row for row in rows if not row['hard_passed']]),
            'scope': 'mesh density/quality only; no stress convergence without solve'}


def write_study_csv(study, out_dir, model_name):
    if not study or not study.get('rows'):
        return None
    path = os.path.join(out_dir, '%s_mesh_study.csv' % model_name)
    cols = ['scale', 'seed', 'nodes', 'elements', 'dof', 'hex_pct',
            'arc_elems', 'notch_size', 'ar_worst', 'ar_avg',
            'ar_bulk_worst', 'failed', 'quality_status', 'quality_score',
            'hard_passed', 'recipe_id', 'strategy', 'seconds']
    try:
        f = open(path, 'w')
        try:
            f.write(','.join(cols) + '\n')
            for r in study['rows']:
                f.write(','.join(['' if r.get(c) is None else str(r.get(c))
                                  for c in cols]) + '\n')
        finally:
            f.close()
        print('[study] wrote', path)
        return path
    except Exception as ex:
        print('[study] CSV failed:', str(ex)[:80])
        return None


# ================================================================== audit
def _analysis_result_gate(params, analysis):
    """Return one explicit setup/solver gate shared by audit and build result."""
    analysis = analysis or {}
    regular = params.get('analysis', {}) or {}
    fva = params.get('fva_600_iii', {}) or {}
    fva_execution = fva.get('execution', {}) or {}
    solver_requested = bool(regular.get('submit', False) or
                            fva_execution.get('submit_solver', False))
    status = analysis.get('status')
    solver_completed = bool(
        status and str(status).strip().upper().find('COMPLET') >= 0)
    reasons = []
    if analysis.get('error'):
        reasons.append('analysis setup/processing error: %s' %
                       str(analysis.get('error'))[:500])
    if solver_requested and not solver_completed:
        reasons.append('requested solver did not complete (status=%s)' %
                       (status if status is not None else 'missing'))
    return {
        'passed': not reasons,
        'solver_requested': solver_requested,
        'solver_status': status,
        'solver_completed': solver_completed,
        'reasons': reasons}


def write_audit(m, report, params, out_dir, analysis=None, post=None,
                study=None):
    """Human report (PARAM_BUILD_AUDIT.txt) + machine report (.json)."""
    lines = []
    data = {}

    def W(s):
        lines.append(s)
        print(s)

    def _keys(obj, attr):
        try:
            return list(getattr(obj, attr).keys())
        except Exception:
            return []

    d = params.get('_derived') or core.derive(params)
    issues = params.get('_issues') or core.validate(params, d)
    tapered = str(params.get('hub_type', 'cylindrical')).strip().lower() == 'tapered'
    data['builder_version'] = core.BUILDER_VERSION
    data['schema_version'] = core.SCHEMA_VERSION
    data['evidence_badges'] = list(core.EVIDENCE_BADGES)
    data['traceability'] = core.traceability_manifest()
    data['build_provenance'] = params.get('_build_provenance', {})
    data['artifact_dirs'] = params.get('_artifact_dirs', {})
    data['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
    data['model'] = m.name
    mesh_plan = params.get('_mesh_plan') or core.resolve_mesh_plan(params, d)
    data['options'] = {'key_form': d['form'], 'hub_type': params.get('hub_type'),
                       'element_order_requested': params.get('element_order'),
                       'linear_hex_code_requested': params.get('linear_hex_code'),
                       'quadratic_hex_code_requested': params.get('quadratic_hex_code'),
                       'topology_requirement_requested':
                           (params.get('mesh', {}) or {}).get(
                               'topology_requirement', mesh_plan['topology_requirement']),
                       'element_order_effective': mesh_plan['element_order'],
                       'linear_hex_code_effective': mesh_plan['linear_hex_code'],
                       'quadratic_hex_code_effective': mesh_plan['quadratic_hex_code'],
                       'topology_requirement': mesh_plan['topology_requirement'],
                       'allow_tet_fallback': mesh_plan['allow_tet_fallback'],
                       'element_profile_effective': mesh_plan['element_profile'],
                       'ar_repair_threshold': params.get('ar_repair_threshold'),
                       'notch': params.get('notch'),
                       'mesh_template': mesh_plan['template'],
                       'mesh_algorithm_version': mesh_plan['algorithm_version']}
    data['mesh_plan'] = mesh_plan
    data['derived'] = dict((k, v) for k, v in d.items()
                           if not k.startswith('_'))
    data['issues'] = issues

    W('PARAMETRIC BUILD AUDIT  (v%s, DIN 6885)' % core.BUILDER_VERSION)
    W('model: %s      built: %s' % (m.name, data['timestamp']))
    W('key_form: %s   hub_type: %s   element_order: %s   profile: %s' % (
        d['form'], params.get('hub_type'), mesh_plan['element_order'],
        mesh_plan['element_profile']['label']))
    W('mesh: template=%s [%s] selection=%s fail_on_quality=%s topology=%s '
      'quadratic_hex=%s' % (
        mesh_plan['template'], mesh_plan['algorithm_version'],
        mesh_plan['selection'], mesh_plan['fail_on_quality'],
        mesh_plan['topology_requirement'], mesh_plan['quadratic_hex_code']))
    W('      %s' % mesh_plan.get('description', ''))
    for record in data['build_provenance'].get('runtime_inputs', []):
        W('source: %-13s sha256=%s size=%s' % (
            record.get('role', '?'), record.get('sha256', '?'),
            record.get('size_bytes', '?')))
    W('steps=%s jobs=%s constraints=%s interactions=%s' % (
        _keys(m, 'steps'), _keys(mdb, 'jobs'),
        _keys(m, 'constraints'), _keys(m, 'interactions')))
    ne = len(core.errors(issues))
    nw = len(core.warnings_(issues))
    W('parameter check: %d error(s), %d warning(s)' % (ne, nw))
    for line in core.format_issues(issues):
        W(line)
    W('')
    W('DERIVED GEOMETRY')
    W('   D=%.3f  R=%.3f  L=%.3f (=%.1f x D)' % (
        d['D'], d['R'], d['L'], d['L_over_D']))
    W('   DIN 6885-1 [%s] band %.0f..%.0f mm: b=%.2f  h=%.2f  t1=%.2f '
      '(+%.2f)  t2=%.2f  d2_ref=%.2f' % (
        core.EVIDENCE_NORMATIVE, d['din_band'][0], d['din_band'][1],
        d['b'], d['h'], d['t1'], d['t1_tol_plus'], d['t2'], d['din_d2_ref']))
    W('   keyway: R_cap=%.2f  z0=%.2f  z1=%.2f  dz=%.2f  yF=%.3f  r2=%.3f' % (
        d['R_cap'], d['z0'], d['z1'], d['dz'], d['yF'], d['r2']))
    if d['r2_din_range']:
        W('           r2 DIN range for b=%.0f is %.2f..%.2f mm -> %s' % (
            d['b'], d['r2_din_range'][0], d['r2_din_range'][1],
            'inside' if d['r2_in_din'] else 'OUTSIDE the standard'))
    W('   key   : Form %s  nominal l=%.2f [%s]  c=%.3f (phi_c=45 deg)  '
      'x_w=%.2f  y_min=%.3f  y_max=%.3f' % (
        d['form'], d['key_nominal_length'], d['key_length_badge'], d['c'],
        d['x_w'], d['y_min'], d['y_max']))
    W('           slot_total_length=%.3f  load_bearing_length=%.3f  designation=%s'
      % (d['slot_total_length'], d['load_bearing_length'], d['key_designation']))
    W('   hub   : d_i=%.2f  d_a=%.2f  hub_outer_over_shaft=%.3f  '
      'shaft_over_hub=%.3f  L_hub=%.2f  roof=%.3f  r1=%.3f' % (
        d['d_i'], d['d_a'], d['hub_outer_over_shaft'], d['shaft_over_hub'],
        d['L_hub'], d['groove_roof'], d['r1']))
    W('           r1 DIN range for b=%.0f is %.2f..%.2f mm -> %s' % (
        d['b'], d['r1_din_range'][0], d['r1_din_range'][1],
        'inside' if d.get('r1_in_din') else 'OUTSIDE the standard'))
    W('   top clearance g_c = t1 + t2 - h = %.3f' % d['g_c'])
    W('   R_cap = %.2f (%s)' % (d['R_cap'],
                                'auto b/2' if d.get('R_cap_auto') else 'user'))
    W('   mesh seeds: shaft %.4f%s  key %.4f%s  hub %.4f%s' % (
        d['seed_shaft'],
        (' (auto %s)' % d['seed_rule_shaft']) if d['seed_shaft_auto'] else '',
        d['seed_key'], ' (auto b/20)' if d['seed_key_auto'] else '',
        d['seed_hub'],
        (' (auto %s)' % d['seed_rule_hub']) if d['seed_hub_auto'] else ''))
    W('')
    W('WHY c = %.3f ?  (Sec 6.1)' % d['c'])
    W('   The bottom corner chamfer has to clear the keyway ROOT FILLET r2.')
    W('   Fillet tangent points give   y - x = y_F - x_w + r2 = %.3f'
      % (d['yF'] - d['x_w'] + d['r2']))
    W('   Chamfer face is the line     y - x = y_min - (x_w - c) = %.3f'
      % (d['y_min'] - (d['x_w'] - d['c'])))
    W('   => condition  c >= r2 = %.3f ;  chosen c = %.3f'
      % (d['c_min_bottom'], d['c']))
    W('   => perpendicular clearance (c - r2)/sqrt(2) = %.4f mm' % d['clear_bottom'])
    W('   Top chamfer clearance to the hub roof fillet r1 = %.4f mm' % d['clear_top'])
    W('   Straight flank left for torque transfer h - 2c = %.3f mm' % d['flank_total'])
    W('')
    W('MATERIALS')
    for mat in (MAT_SHAFT, MAT_HUB, MAT_KEY):
        pr = params['materials'].get(mat, {})
        W('   %-12s grade=%-5s E=%.0f MPa  nu=%.2f  rho=%.3e t/mm^3  '
          'Re(ref)=%s MPa' % (
              mat, str(pr.get('grade', 'C45')), float(pr.get('E', 0)),
              float(pr.get('nu', 0)), float(pr.get('rho', 0)), pr.get('Re', 'n/a')))
    W('')
    tot_n = tot_e = tot_hex = 0
    ok = True
    order_parts = ['Shaft', 'Key'] + (['Bushing'] if tapered else []) + ['Hub']
    data['parts'] = {}
    part_quality = {}
    audit_metrics = {}
    for pn in order_parts:
        p = m.parts[pn]
        # Work on an audit-local copy.  Specialized backends retain their
        # authoritative mesh evidence on independent assembly instances, so
        # the source report must not be mutated or remeasured on an empty Part.
        rep = dict(report.get(pn) or {})
        if pn == 'Shaft' and not tapered:
            runtime_nc, runtime_radius = notch_config(d, 'shaft'), d['r2']
        elif pn == 'Hub' and not tapered:
            runtime_nc, runtime_radius = notch_config(d, 'hub'), d['r1']
        else:
            runtime_nc, runtime_radius = None, 0.0
        metrics_scope = str(rep.get('metrics_scope', 'PART')).upper()
        if metrics_scope == 'ASSEMBLY_INSTANCE':
            metrics = dict(rep.get('metrics') or {})
            if not metrics:
                raise ValueError(
                    'ASSEMBLY_INSTANCE metrics are missing for %s.' % pn)
        else:
            metrics = collect_mesh_metrics(
                p, rep, runtime_radius, runtime_nc)
        metrics = _bounded_mesh_diagnostics(metrics)
        audit_metrics[pn] = metrics
        policy = mesh_plan['parts'][pn]
        metrics.setdefault('topology_requirement',
                           policy.get('topology_requirement'))
        metrics.setdefault('quadratic_hex_code',
                           mesh_plan.get('quadratic_hex_code'))
        metrics.setdefault('non_hex_pct',
                           max(0.0, 100.0 - float(metrics.get('hex_pct', 0.0))))
        metrics.setdefault('non_hex_count', max(
            0, int(metrics.get('elements', 0) or 0) -
            sum([v for k, v in (metrics.get('types') or {}).items()
                 if k.startswith('C3D8') or k.startswith('C3D20')])))
        quality = core.evaluate_mesh_quality(pn, metrics, policy)
        rep['metrics'] = metrics
        rep['quality'] = quality
        hist = metrics['types']
        failed = metrics['failed']
        warn = metrics['warnings']
        arw = metrics['ar_worst']
        ara = metrics['ar_avg']
        ncomp = metrics['components']
        bb = p.cells.getBoundingBox()
        nhex = sum([v for k, v in hist.items()
                   if k.startswith('C3D8') or k.startswith('C3D20')])
        tot_n += metrics['nodes']
        tot_e += metrics['elements']
        tot_hex += nhex
        if failed > 0 or ncomp != 1:
            ok = False
        pct = metrics['hex_pct']
        selected_recipe = rep.get('selected_recipe', {}) or {}
        selection = rep.get('selection', {}) or {}
        part_quality[pn] = quality
        data['parts'][pn] = {
            'metrics_scope': metrics_scope,
            'nodes': metrics['nodes'], 'elements': metrics['elements'],
            'types': hist, 'hex_pct': pct,
            'non_hex_pct': metrics.get('non_hex_pct'),
            'non_hex_count': metrics.get('non_hex_count'),
            'topology_requirement': metrics.get('topology_requirement'),
            'quadratic_hex_code': metrics.get('quadratic_hex_code'),
            'failed': failed, 'warnings': warn,
            'failed_element_labels': metrics.get('failed_element_labels', []),
            'warning_element_labels': metrics.get('warning_element_labels', []),
            'failed_element_count': metrics.get('failed_element_count', failed),
            'warning_element_count': metrics.get('warning_element_count', warn),
            'failed_element_count_total': metrics.get(
                'failed_element_count_total', failed),
            'warning_element_count_total': metrics.get(
                'warning_element_count_total', warn),
            'truncated': bool(metrics.get('truncated', False)),
            'diagnostic_label_limit': metrics.get(
                'diagnostic_label_limit', MESH_DIAGNOSTIC_LABEL_LIMIT),
            'ar_worst': arw, 'ar_avg': ara,
            'ar_bulk_worst': metrics.get('ar_bulk_worst'),
            'ar_bulk_avg': metrics.get('ar_bulk_avg'),
            'ar_bulk_basis': metrics.get('ar_bulk_basis'),
            'components': ncomp, 'cells': len(p.cells),
            'seconds': rep.get('seconds'), 'search_seconds': rep.get('search_seconds'),
            'selected_generation_seconds': rep.get('selected_generation_seconds'),
            'repairs': rep.get('repairs'), 'notch': rep.get('notch'),
            'fillet': metrics.get('fillet'),
            'bbox': [round(bb['high'][i] - bb['low'][i], 4) for i in range(3)],
            'sections': [sa.sectionName for sa in p.sectionAssignments],
            'quality': quality, 'selected_recipe': selected_recipe,
            'selected_attempt_index': rep.get('selected_attempt_index'),
            'selection': selection, 'attempts': rep.get('attempts', []),
            'winner_reproduced': rep.get('winner_reproduced'),
            'winner_reproduction_match': rep.get('winner_reproduction_match'),
            'winner_signature_exact': rep.get('winner_signature_exact'),
            'winner_reproduction_tolerances': rep.get('winner_reproduction_tolerances'),
            'winner_reproduction_deltas': rep.get('winner_reproduction_deltas'),
            'winner_reproduction_error': rep.get('winner_reproduction_error')}
        W('PART %s  QUALITY %s %.1f/100' %
          (pn, quality['status'], quality['score']))
        W('   selected recipe=%s strategy=%s attempt=%s/%d' % (
            selected_recipe.get('recipe_id', 'n/a'),
            selected_recipe.get('control_strategy', 'n/a'),
            (rep.get('selected_attempt_index', 0) + 1)
            if rep.get('selected_attempt_index') is not None else 'n/a',
            len(rep.get('attempts', []))))
        W('   winner reproduced=%s tolerance_match=%s exact_signature=%s | '
          'algorithm=%s' % (
            rep.get('winner_reproduced'), rep.get('winner_reproduction_match'),
            rep.get('winner_signature_exact'),
            rep.get('algorithm_version', mesh_plan['algorithm_version'])))
        if rep.get('winner_reproduction_deltas'):
            W('   reproduction deltas=%s tolerances=%s' % (
                rep.get('winner_reproduction_deltas'),
                rep.get('winner_reproduction_tolerances')))
        W('   nodes=%d elements=%d (%.1f%% hex, %.1f%% non-hex) types=%s'
          % (metrics['nodes'], metrics['elements'], pct,
             metrics.get('non_hex_pct', 100.0 - pct), hist))
        W('   cells=%d search=%ss selected_generation=%ss repairs=%s'
          % (len(p.cells), rep.get('search_seconds', rep.get('seconds')),
             rep.get('selected_generation_seconds'), rep.get('repairs')))
        W('   sections=%s' % data['parts'][pn]['sections'])
        W('   local bbox=%s' % data['parts'][pn]['bbox'])
        W('   failed=%d warnings=%d AR global worst=%s avg=%s components=%d'
          % (failed, warn, arw, ara, ncomp))
        W('   diagnostic labels: failed=%d warning=%d limit=%d truncated=%s' % (
            len(metrics.get('failed_element_labels', [])),
            len(metrics.get('warning_element_labels', [])),
            int(metrics.get('diagnostic_label_limit',
                            MESH_DIAGNOSTIC_LABEL_LIMIT)),
            bool(metrics.get('truncated', False))))
        W('   AR bulk worst=%s avg=%s basis=%s' % (
            metrics.get('ar_bulk_worst'), metrics.get('ar_bulk_avg'),
            metrics.get('ar_bulk_basis')))
        if quality.get('hard_reasons'):
            W('   HARD GATE FAIL: %s' % '; '.join(quality['hard_reasons']))
        for penalty in quality.get('penalties', []):
            W('   score -%.2f [%s] %s' % (
                penalty.get('points', 0.0), penalty.get('code'),
                penalty.get('detail')))
        for idx, attempt in enumerate(rep.get('attempts', [])):
            aq = attempt.get('quality', {}) or {}
            am = attempt.get('metrics', {}) or {}
            arcp = attempt.get('recipe', {}) or {}
            W('   attempt %d: %-18s %-20s %s %5.1f | elem=%d hex=%5.1f%% '
              'failed=%d comp=%d%s' % (
                  idx + 1, arcp.get('recipe_id', '?'),
                  arcp.get('control_strategy', '?'), aq.get('status', 'FAIL'),
                  float(aq.get('score', 0.0) or 0.0),
                  int(am.get('elements', 0) or 0),
                  float(am.get('hex_pct', 0.0) or 0.0),
                  int(am.get('failed', 0) or 0),
                  int(am.get('components', 0) or 0),
                  (' EXCEPTION=' + attempt.get('exception'))
                  if attempt.get('exception') else ''))
        nst = rep.get('notch') or {}
        if nst.get('arc'):
            W('   notch seeding: %d arc edge(s) @ %d elem, band %s, %d band edge(s),'
              ' %d fade-out edge(s), %d graded cell(s) exempt from AR repair'
              % (nst.get('arc', 0), d['notch_arc_elems'],
                 nst.get('method') or 'n/a', nst.get('band', 0),
                 nst.get('fade', 0), nst.get('graded_cells', 0)))
    profile_failures = core.validate_realized_element_profile(
        mesh_plan, data['parts'])
    data['element_profile_validation'] = {
        'passed': not profile_failures,
        'failures': profile_failures,
        'profile': mesh_plan.get('element_profile')}
    if profile_failures:
        ok = False
        for failure in profile_failures:
            W('ELEMENT PROFILE HARD GATE FAIL: %s' % failure)
    quality_summary = core.aggregate_mesh_quality(
        part_quality, mesh_plan.get('fail_on_quality', True))
    data['mesh_quality'] = quality_summary
    params['_mesh_quality'] = quality_summary
    if not quality_summary['passed']:
        ok = False
    W('')
    W('MESH QUALITY GATE: %s %.1f/100 hard_passed=%s passed=%s' % (
        quality_summary['status'], quality_summary['score'],
        quality_summary['hard_passed'], quality_summary['passed']))
    for reason in quality_summary.get('reasons', []):
        W('   FAIL: %s' % reason)
    W('')
    W('TOTAL nodes=%d elements=%d (%.1f%% hex)'
      % (tot_n, tot_e, 100.0 * tot_hex / max(1, tot_e)))
    data['totals'] = {'nodes': tot_n, 'elements': tot_e,
                      'hex_pct': 100.0 * tot_hex / max(1, tot_e),
                      'dof': 3 * tot_n}
    a = m.rootAssembly
    W('ASSEMBLY bounding boxes')
    data['instances'] = {}
    for nm in sorted(a.instances.keys()):
        ib = a.instances[nm].cells.getBoundingBox()
        data['instances'][nm] = {'low': [round(v, 3) for v in ib['low']],
                                 'high': [round(v, 3) for v in ib['high']]}
        W('   %-10s lo=%s hi=%s' % (nm, data['instances'][nm]['low'],
                                    data['instances'][nm]['high']))
    data['sets'] = sorted(a.sets.keys())
    data['surfaces'] = sorted(a.surfaces.keys())
    W('SETS: %s' % data['sets'])
    if data['surfaces']:
        W('SURFACES: %s' % data['surfaces'])

    W('')
    W('FIT / CLEARANCE CHECKS')
    checks = core.fit_checks(d, tapered)
    all_ok = True
    data['checks'] = []
    for label, val, lo, note in checks:
        flag = 'ok'
        if lo is not None and val < -1e-6:
            flag = 'FAIL'
            all_ok = False
        elif lo is None and abs(val) > 1e-3:
            flag = 'info'
        data['checks'].append({'label': label.strip(), 'value': val,
                               'flag': flag, 'note': note})
        W('   %-34s % .4f mm  [%s] %s' % (label, val, flag, note))
    if not all_ok:
        ok = False

    # ---- notch resolution and mesh adequacy -------------------------------
    W('')
    W('NOTCH RESOLUTION AND MESH ADEQUACY')
    nc_shaft_audit = None if tapered else notch_config(d, 'shaft')
    # Keep fillet/notch reporting on the same authoritative mesh scope used
    # for quality and totals.  Independent assembly meshes do not exist on the
    # original Part objects after makeIndependent().
    fm = dict((audit_metrics.get('Shaft') or {}).get('fillet') or {})
    hub_fm = dict((audit_metrics.get('Hub') or {}).get('fillet') or {})
    if not fm or not hub_fm:
        raise ValueError('Audited mesh metrics are missing fillet evidence.')
    data['notch_metrics'] = fm
    data['fillet_metrics'] = {'Shaft': fm, 'Hub': hub_fm}
    if fm['min_elems']:
        W('   shaft root fillet r2=%.3f : arc length pi*r/2 = %.4f mm on %d edges'
          % (fm['radius'], math.pi * fm['radius'] / 2.0, fm['edges']))
        W('   elements across the fillet arc: min %.1f  max %.1f  '
          '(element size ~%.4f mm)'
          % (fm['min_elems'], fm['max_elems'], fm['elem_size']))
        if nc_shaft_audit and d['notch_on']:
            W('   local refinement: band +-%.4f mm PARTITIONED around each keyway '
              'root' % d['band_shaft'])
            W('   corner, so the notch element is small in BOTH in-plane '
              'directions.')
            W('   In-plane target %.4f mm vs global shaft seed %.4f mm: the notch'
              % (d['s_notch_shaft'], d['seed_shaft']))
            W('   elements stay about %.0f times longer ALONG the keyway, which is'
              % d['ar_notch_expect'])
            W('   the direction of the smallest stress gradient in torsion. Set')
            W('   notch.axial_factor > 0 to refine that direction too.')
        elif tapered:
            W('   legacy tapered route: the shaft fillet geometry is measured, but')
            W('   the dedicated local notch-seeding recipe is NOT applied.')
            W('   Resolution above comes from the selected global mesh candidate;')
            W('   no local-refinement or expected axial-AR claim is made.')
        else:
            W('   local refinement is OFF (notch.enabled = false): the fillet is')
            W('   resolved by the global seed alone.')
        if fm['min_elems'] < 4:
            if tapered:
                W('   [info] fewer than 4 elements on this geometric fillet; this is')
                W('          reported as an indicator, not as a tapered-route gate.')
            else:
                W('   [WARN] fewer than 4 elements on the notch arc: a stress')
                W('          concentration factor from this mesh would be unreliable.')
        elif tapered:
            W('   [info] geometric fillet resolution only; no tapered-route notch gate.')
        else:
            W('   [ok] at least 4 elements on the notch arc.')
    else:
        W('   could not identify the shaft fillet arc edges (r2=%.3f).' % d['r2'])
    if hub_fm.get('min_elems'):
        W('   hub roof fillet r1=%.3f: %d edge(s), min %.1f element(s)/arc, '
          'band edges=%d' % (
              d['r1'], hub_fm.get('edges', 0), hub_fm['min_elems'],
              hub_fm.get('band_edges', 0)))
    elif not tapered and d.get('notch_hub'):
        W('   [WARN] could not identify the expected hub roof fillet arcs '
          '(r1=%.3f).' % d['r1'])
    dof = 3 * tot_n
    W('   model degrees of freedom (3 per node) = %.3e' % dof)
    W('   reference [1]: the stress was considered converged at DOF >= %.1e'
      % DOF_CONVERGED_LIT)
    W('   ratio DOF / DOF_converged[1] = %.3f' % (dof / DOF_CONVERGED_LIT))
    if dof < DOF_CONVERGED_LIT:
        W('   [NOTE] this mesh is below the refinement at which [1] reported')
        W('          convergence (their case: d=100 mm, quadratic tets, contact).')
        W('          The comparison is order-of-magnitude only. The optional')
        W('          density/quality study does not solve each scale; run and')
        W('          compare solved refinements before quoting a Kt.')

    # ---- mesh density / quality study (no stress solve) --------------------
    if study and study.get('rows'):
        W('')
        W('MESH DENSITY / QUALITY STUDY (selected shaft recipe; no stress solve)')
        W('   %-7s %-8s %-9s %-9s %-8s %-9s %-8s %-6s %-6s %-6s' % (
            'scale', 'seed', 'elements', 'DOF', 'arc el', 'notch mm',
            'AR bulk', 'hex %', 'failed', 'status'))
        for r in study['rows']:
            W('   %-7.3f %-8.4f %-9d %-9.2e %-8s %-9s %-8s %-6.1f %-6d %-6s' % (
                r['scale'], r['seed'], r['elements'], r['dof'],
                '%.1f' % r['arc_elems'] if r['arc_elems'] else 'n/a',
                '%.4f' % r['notch_size'] if r['notch_size'] else 'n/a',
                '%.1f' % r.get('ar_bulk_worst')
                if r.get('ar_bulk_worst') else 'n/a',
                r['hex_pct'], r.get('failed', 0),
                r.get('quality_status', 'n/a')))
            if r.get('quality_reasons'):
                W('      inadmissible: %s' % '; '.join(r['quality_reasons']))
        W('   admissible scales=%d, inadmissible scales=%d; invalid points are '
          'not convergence evidence.' % (
              study.get('admissible_scales', 0),
              study.get('inadmissible_scales', 0)))
        W('   The exact AUTO winner was restored after the study.')
        data['study'] = study['rows']

    # ---- DIN 6892 calculation engine (Methods A / B / C) -------------------
    din_record = d.get('din6892') or {}
    if din_record.get('enabled'):
        din_calc = din_record.get('calculation') or {}
        requested = din_record.get('requested', {}) or {}
        derived_din = din_record.get('derived', {}) or {}
        W('')
        W('DIN 6892 CALCULATION  engine=%s  primary method=%s [%s]'
          % (din_record.get('engine_version', 'n/a'),
             requested.get('method', 'n/a'),
             din_calc.get('badge', 'n/a')))
        W('   status: %s' % din_record.get('status', 'n/a'))
        effective = derived_din.get('effective_bearing_depth') or {}
        material = derived_din.get('material') or {}
        if effective:
            W('   effective bearing depth t1tr = %.6f mm  (equation %s, '
              'r=%.3f mm, s1=%.3f mm from %s)'
              % (float(effective.get('t1tr_mm', 0.0)),
                 effective.get('equation', 9),
                 float((effective.get('inputs') or {}).get('root_radius_mm', 0.0)),
                 float((effective.get('inputs') or {}).get('chamfer_s1_mm', 0.0)),
                 derived_din.get('chamfer_s1_source', 'n/a')))
        if material:
            W('   material source: %s [%s]'
              % (material.get('label', 'n/a'), material.get('badge', 'n/a')))
        if din_calc.get('criterion'):
            W('   limit-load criterion: %s' % din_calc['criterion'])
        if din_calc.get('variant'):
            W('   variant: %s  (%s)'
              % (din_calc['variant'], din_calc.get('variant_note', 'n/a')))
        closure = derived_din.get('friction_closure') or {}
        if closure:
            W('   friction closure (equation 12): K_Req,DIN=%.6f  applied K_R=%.6f'
              % (float(closure.get('K_Req_din', 0.0)),
                 float(closure.get('K_R', 0.0))))
        allowable = din_calc.get('torque_allowable_Nm')
        design = din_calc.get('torque_design_Nm')
        if allowable is not None:
            W('   M_t,zul    = %.2f N m   (equations %s)'
              % (float(allowable), din_calc.get('equations', 'n/a')))
            W('   M_t,design = %.2f N m   (safety factor %.3f)'
              % (float(design), float(din_calc.get('safety_factor', 1.0))))
        else:
            W('   M_t,zul    = not available for this method/state')
        if din_calc.get('governing_component'):
            W('   governing component: %s' % din_calc['governing_component'])
        for row in din_calc.get('components') or []:
            extra = ''
            if row.get('f_S') is not None:
                extra = ('  f_S=%.3f%s [%s]  f_H=%.3f'
                         % (float(row['f_S']),
                            ('' if not row.get('f_S_range')
                             else ' of %.1f..%.1f' % (float(row['f_S_range'][0]),
                                                     float(row['f_S_range'][1]))),
                            row.get('f_S_provenance', 'n/a'),
                            float(row.get('f_H', 1.0))))
            if row.get('p_zul_MPa') is not None:
                extra += '  p_zul=%.2f MPa' % float(row['p_zul_MPa'])
            W('      component %-6s Re=%.1f MPa%s  ->  M_t,zul=%.2f N m'
              % (row.get('name', '?'), float(row.get('Re_MPa', 0.0)), extra,
                 float(row.get('torque_allowable_Nm', 0.0))))
        for row in din_calc.get('components_skipped') or []:
            W('      component %-6s NOT CHECKED: %s'
              % (row.get('name', '?'), row.get('reason', 'n/a')))
        for name in din_calc.get('components_not_covered') or []:
            W('      component %-6s outside this criterion; still needs the '
              'current Method-B or Method-C pressure check' % name)
        if din_calc.get('torque_peak_allowable_Nm') is not None:
            W('   peak branch: f_L=%.3f  p_max,zul=%.2f MPa  '
              'M_t,peak=%.2f N m'
              % (float(din_calc.get('f_L', 0.0)),
                 float(din_calc.get('p_max_zul_MPa', 0.0)),
                 float(din_calc['torque_peak_allowable_Nm'])))
        if din_calc.get('safety_S_Feq') is not None:
            W('   safety (equation 1): S_Feq = M_t,zul / M_t,applied = %.4f '
              '(applied %.2f N m)'
              % (float(din_calc['safety_S_Feq']),
                 float(din_calc.get('torque_applied_Nm', 0.0))))
        audit_factors = din_calc.get('factor_audit') or {}
        if audit_factors:
            W('   licensed factors [%s]: %s'
              % (audit_factors.get('badge', core.EVIDENCE_USER_INPUT),
                 'conclusive' if audit_factors.get('conclusive')
                 else ('PROVISIONAL, still neutral 1.0: %s'
                       % ', '.join(audit_factors.get('placeholder_factors') or []))))
        companions = (din_record.get('companions') or {}).get('results') or {}
        if companions:
            W('   companion analytical methods (same joint, same inputs):')
            for name in sorted(companions):
                item = companions[name] or {}
                value = item.get('torque_allowable_Nm')
                if value is None:
                    W('      %-14s %s: %s' % (name, item.get('status', 'n/a'),
                                              item.get('reason', 'n/a')))
                else:
                    W('      %-14s M_t,zul=%9.2f N m   M_t,design=%9.2f N m   '
                      'governing=%s   [%s]'
                      % (name, float(value), float(item.get('torque_design_Nm')),
                         item.get('governing_component', 'n/a'),
                         item.get('status', 'n/a')))
        W('   NOTE: DIN 743 fatigue verification remains independent and is not '
          'performed here.')

    # ---- analytical design check ------------------------------------------
    if d.get('dc_on'):
        dcp = params.get('design_check', {})
        W('')
        W('DESIGN CHECK  [%s]  (uniform-bearing screening; NOT complete DIN 6892 Method B)'
          % core.EVIDENCE_CORE_SCREENING)
        W('   torque: T_nom=%.1f N m   T_max=%.1f N m   keys=%d   load '
          'distribution phi=%.2f'
          % (d['T_nom'] / 1000.0, d['T_max'] / 1000.0,
             int(dcp.get('n_keys', 1)), float(dcp.get('load_distribution', 1.0))))
        W('   plain-shaft section modulus Wt = pi*D^3/16 = %.1f mm^3' % d['Wt'])
        W('   nominal torsional stress tau_nom = T/Wt = %.2f MPa' % d['tau_nom'])
        W('   -- peak stress ESTIMATES using published SCFs (reference [1]) --')
        W('      shaft: Kts=%.2f -> tau_max ~ %.2f MPa'
          % (KTS_SHAFT_LIT, d['tau_peak_lit']))
        W('      hub  : Kts=%.2f -> tau_max ~ %.2f MPa'
          % (KTS_HUB_LIT, d['tau_peak_hub_lit']))
        W('      [1] full 3D WITH CONTACT, standard DIN design: KvM = %.1f '
          '(converged).' % KVM_3D_DIN_LIT)
        W('      [1] super-elliptic keyway, exponent eta=%.1f: KvM = %.1f in its 2D'
          % (ETA_OPT_LIT, KVM_2D_OPT_LIT))
        W('      contact model, which [1] reports as a %.0f%% reduction versus the '
          'DIN' % RED_2D_SYM_LIT)
        W('      design in the SAME 2D model (do not divide 5.9 by the 3D 22.3 -')
        W('      they are different models). Its unsymmetrical optimum reached '
          '%.0f%%,' % RED_3D_UNSYM_LIT)
        W('      confirmed in 3D. Reshaping the keyway is therefore the single most')
        W('      effective measure available for this joint.')
        W('   -- surface pressure screening [CORE-SCREENING] --')
        W('      bearing height, shaft side  h\' = t1 - c     = %.3f mm'
          % d['h_bear_shaft'])
        W('      bearing height, hub side    h\' = h - t1 - c = %.3f mm'
          % d['h_bear_hub'])
        W('      bearing length (Form %s)     l_tr           = %.3f mm'
          % (d['form'], d['l_tr']))
        W('      p_shaft = 2*T_max*phi/(D*h\'*l_tr*n) = %.1f MPa   (allowable %.1f)'
          % (d['p_shaft'], d['p_perm_shaft']))
        W('      p_hub                                = %.1f MPa   (allowable %.1f)'
          % (d['p_hub'], d['p_perm_hub']))
        for tag, u in (('shaft', d.get('util_shaft')), ('hub', d.get('util_hub'))):
            if u is not None:
                W('      utilisation %-5s = %.3f  [%s]'
                  % (tag, u, 'ok' if u <= 1.0 else 'OVER the allowable pressure'))
        W('      transmissible torque at the allowable pressure:')
        W('         shaft side %.1f N m | hub side %.1f N m | governing %.1f N m'
          % (d['T_perm_shaft'], d['T_perm_hub'], d['T_perm']))
        W('   -- failure mode expectation, reference [2] --')
        if d.get('d_over_D1') is not None:
            W('      d/D1 = d_i/d_a = %.3f  (threshold %.2f)'
              % (d['d_over_D1'], D_OVER_D1_THICK))
            if d['thick_walled']:
                W('      thick-walled hub: [2] finds the failure always in the '
                  'contact')
                W('      between key and SHAFT keyway. Watch the shaft keyway flank.')
            else:
                W('      thin-walled hub: [2] reports that failure between key and '
                  'HUB')
                W('      becomes possible (notably for cast iron or aluminium hubs).')
        W('      [2] also finds the governing criterion depends on shaft strength:')
        W('      low-strength steel fails by permissible pressure (plastic keyway')
        W('      deformation), higher-strength steel by a crack at the shaft with no')
        W('      prior relevant plastic deformation. Both are covered by DIN 6892')
        W('      and DIN 743 respectively.')
        W('      [3] adds: with an unchamfered key the peak shear sits at the keyway')
        W('      END; doubling hub and key length lowered peak stress by ~25%, and')
        W('      preventing contact at the keyway end lowered it by ~11%.')

    # ---- analysis stage ----------------------------------------------------
    data['analysis'] = analysis
    data['post'] = post
    analysis_gate = _analysis_result_gate(params, analysis)
    data['analysis_gate'] = analysis_gate
    if not analysis_gate['passed']:
        ok = False
        for reason in analysis_gate['reasons']:
            W('ANALYSIS HARD GATE FAIL: %s' % reason)
    if analysis:
        W('')
        W('ANALYSIS STAGE (optional, enabled)')
        W('   step %s: static, nlgeom=%s, general contact, friction %s'
          % (analysis.get('step'), params['analysis'].get('nlgeom'),
             'frictionless' if analysis.get('friction', 0) < 0
             else '%.3f' % analysis.get('friction', 0)))
        W('   torque %.1f N m applied at the shaft drive end through a KINEMATIC'
          % d['T_apply'])
        W('   coupling on %d face(s); the hub is held on %d face(s) (%s).'
          % (analysis.get('drive_faces', 0), analysis.get('hold_faces', 0),
             analysis.get('hold')))
        W('   job: %s' % analysis.get('job'))
        if analysis.get('status'):
            W('   solver status: %s (%.1f s)'
              % (analysis['status'], analysis.get('seconds', 0.0)))
    if post:
        W('')
        W('RESULTS MEASURED ON THIS MESH')
        W('   step %s, last frame time %.3f of %d frame(s)'
          % (post.get('step'), post.get('frame_time', 0.0), post.get('frames', 0)))
        tau = post.get('tau_nom_apply') or 0.0
        W('   nominal torsional stress of the plain shaft tau_nom = %.3f MPa' % tau)
        if post.get('mises_notch') is not None:
            W('   peak von Mises at the shaft keyway root = %.2f MPa  (%s)'
              % (post['mises_notch'], post.get('mises_notch_at')))
        if post.get('mises_max_model') is not None:
            W('   peak von Mises anywhere in the model  = %.2f MPa  (%s)'
              % (post['mises_max_model'], post.get('mises_max_at')))
        if post.get('KvM'):
            W('   => KvM = sigma_vM,notch / tau_nom = %.2f' % post['KvM'])
            W('      [1] reports KvM = %.1f for the standard DIN design in a '
              'converged' % KVM_3D_DIN_LIT)
            W('      3D contact model. This model gives %.0f%% of that value; if it '
              'is' % (100.0 * post['KvM'] / KVM_3D_DIN_LIT))
            W('      much lower the mesh is not yet converged at the notch - run')
            W('      and solve multiple admissible refinements before quoting it;')
            W('      the unsolved density/quality study alone is insufficient.')
        if post.get('cpress_max') is not None:
            W('   peak contact pressure CPRESS = %.1f MPa' % post['cpress_max'])
            if d.get('dc_on') and d.get('p_shaft'):
                sc = (d['p_shaft'] * d['T_apply'] / max(d['T_max'] / 1000.0, 1e-9))
                W('      uniform-bearing screening for the SAME torque gives p = %.1f '
                  'MPa' % sc)
                W('      (CORE-SCREENING assumes uniform pressure over h\'*l_tr; a')
                W('      so a higher local peak in the FE model is expected).')
        if post.get('reaction_Mz_Nmm') is not None:
            W('   torque carried by the held hub = %.1f N mm (applied %.1f N mm)'
              % (post['reaction_Mz_Nmm'], analysis.get('T_Nmm', 0.0)))
            if post.get('torque_balance_pct') is not None:
                bal = post['torque_balance_pct']
                W('   equilibrium error = %.3f %%  [%s]'
                  % (bal, 'ok' if bal < 1.0 else 'CHECK the load path'))
                if bal >= 1.0:
                    ok = False

    W('')
    verdict = ('OK (hard mesh gates, template quality policy and fits passed)'
               if ok else 'CHECK (quality gate, mesh topology or fit failed)')
    W('VERDICT: %s' % verdict)
    data['verdict'] = 'OK' if ok else 'CHECK'
    params['_audit_verdict'] = data['verdict']
    if not analysis:
        W('NOTE: NOJOB model - no contact, step, load, BC or job defined. Every '
          'stress')
        W('      figure above is either a hand formula or a published reference '
          'value;')
        W('      none of them comes from a solved analysis of this model.')
        W('      Set analysis.enabled = true to add contact, a torsion step and a '
          'job.')
    W('')
    W('REFERENCES')
    for r in REFS:
        W('   ' + r)

    txt = '\n'.join(lines) + '\n'
    au = params.get('audit', {}) or {}
    if out_dir and au.get('text', True):
        try:
            f = open(os.path.join(out_dir, 'PARAM_BUILD_AUDIT.txt'), 'w')
            f.write(txt)
            f.close()
        except Exception as ex:
            print('[audit] could not write the text file:', str(ex)[:90])
    if out_dir and au.get('json', True):
        try:
            clean = dict((k, v) for k, v in params.items()
                         if not k.startswith('_'))
            data['params'] = clean
            core.write_json(os.path.join(out_dir, 'PARAM_BUILD_AUDIT.json'), data)
            print('[audit] wrote PARAM_BUILD_AUDIT.json')
        except Exception as ex:
            print('[audit] could not write the JSON file:', str(ex)[:120])
    return ok


def resolve_artifact_dirs(params):
    """Resolve the explicit project layout and fail loudly on path errors.

    Legacy JSON without an ``artifacts`` object remains supported by mapping all
    outputs to ``output_dir``.  New GUI projects always provide absolute paths.
    There is deliberately no fallback to ``os.getcwd()``.
    """
    configured = params.get('artifacts', {}) or {}
    legacy = params.get('output_dir', '') or _HERE
    names = ('input', 'generated', 'model', 'jobs', 'screenshots',
             'reports', 'logs')
    dirs = {}
    for name in names:
        value = configured.get(name + '_dir', '') or legacy
        value = os.path.abspath(os.path.expanduser(os.path.expandvars(str(value))))
        if configured and not os.path.isabs(value):
            raise ValueError('Artifact route %s_dir must be absolute.' % name)
        if os.path.exists(value) and not os.path.isdir(value):
            raise ValueError('Artifact route is a file, not a directory: %s' % value)
        if not os.path.isdir(value):
            try:
                os.makedirs(value)
            except Exception as ex:
                raise RuntimeError('Cannot create artifact directory %s: %s'
                                   % (value, ex))
        dirs[name] = value
    params['output_dir'] = dirs['generated']
    params['_artifact_dirs'] = dirs
    return dirs


def resolve_out_dir(params):
    """Backward-compatible alias for plug-ins that expect one output folder."""
    return resolve_artifact_dirs(params)['generated']


def write_build_result(params, ok, seconds, analysis=None, preview=None):
    dirs = params.get('_artifact_dirs') or resolve_artifact_dirs(params)
    mesh_plan = params.get('_mesh_plan')
    if not mesh_plan:
        mesh_plan = core.resolve_mesh_plan(params, params.get('_derived'))
        params['_mesh_plan'] = mesh_plan
    analysis_gate = _analysis_result_gate(params, analysis)
    effective_ok = bool(ok) and bool(analysis_gate.get('passed', False))
    payload = {
        'builder_version': core.BUILDER_VERSION,
        'schema_version': core.SCHEMA_VERSION,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'model': params.get('model_name'),
        'ok': effective_ok,
        'requested_ok': bool(ok),
        'seconds': round(float(seconds), 3),
        'analysis': analysis,
        'analysis_gate': analysis_gate,
        'preview': preview,
        'mesh_quality': params.get('_mesh_quality'),
        'mesh_template': mesh_plan.get('template'),
        'mesh_algorithm_version': mesh_plan.get('algorithm_version'),
        'quadratic_hex_code': mesh_plan.get('quadratic_hex_code'),
        'topology_requirement': mesh_plan.get('topology_requirement'),
        'options': {
            'quadratic_hex_code': mesh_plan.get('quadratic_hex_code'),
            'topology_requirement': mesh_plan.get('topology_requirement'),
            'allow_tet_fallback': mesh_plan.get('allow_tet_fallback')},
        'element_profile': mesh_plan.get('element_profile'),
        'build_provenance': params.get('_build_provenance', {}),
        'audit_verdict': params.get('_audit_verdict'),
        'artifact_dirs': dirs,
        'evidence_badges': list(core.EVIDENCE_BADGES),
    }
    path = os.path.join(dirs['generated'], 'BUILD_RESULT.json')
    core.write_json(path, payload)
    print('[result] wrote', path)
    return path


# ================================================================== preview
def _viewport():
    vps = session.viewports
    names = list(vps.keys())
    if names:
        return vps[names[0]]
    return session.Viewport(name='preview', origin=(0, 0), width=200, height=150)


def render_preview(m, out_dir, name, d=None, params=None):
    """Assembly views plus, when the notch band exists, a close-up of the mesh
    there. A picture of the notch is the quickest way to see whether the local
    refinement did what the audit claims."""
    made = []
    pv = (params or {}).get('preview', {}) or {}
    views = pv.get('views') or ['Iso']
    w = int(pv.get('width', 1600))
    h = int(pv.get('height', 1200))
    try:
        vp = _viewport()
        session.printOptions.setValues(vpDecorations=OFF, vpBackground=OFF,
                                      reduceColors=False)
        session.pngOptions.setValues(imageSize=(w, h))
        vp.setValues(displayedObject=m.rootAssembly)
        try:
            vp.assemblyDisplay.setValues(mesh=ON, optimizationTasks=OFF,
                                         geometricRestrictions=OFF,
                                         stopConditions=OFF)
        except Exception:
            pass
        for vname in views:
            if vname not in session.views.keys():
                continue
            vp.view.setValues(session.views[vname])
            vp.view.fitView()
            suffix = '_preview' if vname == views[0] else '_preview_%s' % vname
            png = os.path.join(out_dir, name + suffix)
            session.printToFile(fileName=png, format=PNG, canvasObjects=(vp,))
            made.append(png + '.png')
            print('[preview] wrote', png + '.png')
    except Exception as e:
        print('[preview] assembly views skipped:', str(e)[:100])

    if d and pv.get('notch_zoom', True) and d.get('notch_on'):
        try:
            vp = _viewport()
            vp.setValues(displayedObject=m.parts['Shaft'])
            try:
                vp.partDisplay.setValues(mesh=ON)
                vp.partDisplay.geometryOptions.setValues(referenceRepresentation=OFF)
            except Exception:
                pass
            span = max(8.0 * d['band_shaft'], 2.0)
            xs, ys, zs = d['x_slot'], d['yF'], d['z_mid']
            # Look INTO the keyway from inside the slot. A straight-on view along
            # the axis is useless here: Abaqus refits the clipping planes, so the
            # nearest visible surface is the shaft end face, not the notch.
            dist = 8.0 * span
            v = (-1.0, 1.2, 1.0)
            nrm = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
            pos = (xs + dist * v[0] / nrm, ys + dist * v[1] / nrm,
                   zs + dist * v[2] / nrm)
            vp.view.setValues(session.views['Iso'])
            vp.view.fitView()
            try:
                vp.view.setProjection(projection=PARALLEL)
            except Exception:
                pass
            # NOTE: 'projection' is NOT a setValues key on View - passing it there
            # makes the whole call fail and silently leaves the fitted view.
            vp.view.setValues(cameraTarget=(xs, ys, zs), cameraPosition=pos,
                              cameraUpVector=(0.0, 1.0, 0.0))
            vp.view.setValues(width=span, height=span)
            png = os.path.join(out_dir, name + '_notch_mesh')
            session.printToFile(fileName=png, format=PNG, canvasObjects=(vp,))
            made.append(png + '.png')
            print('[preview] wrote', png + '.png')
        except Exception as e:
            print('[preview] notch close-up skipped:', str(e)[:100])
    return made[0] if made else None


# ================================================================== main
def main():
    t0 = time.time()
    params = load_params()
    params['_build_provenance'] = collect_build_provenance(params)
    dirs = resolve_artifact_dirs(params)
    generated_dir = dirs['generated']
    model_dir = dirs['model']
    jobs_dir = dirs['jobs']
    screenshots_dir = dirs['screenshots']

    # Dedicated FVA research routes. Dispatch is explicit so the immutable
    # one-cycle conical regression remains reproducible while the connected
    # Method-A backend can evolve independently.
    fva_cfg = params.get('fva_600_iii', {}) or {}
    if bool(fva_cfg.get('enabled', False)):
        d = core.derive(params, verbose=True)
        gate(params, d)
        backend_id = str(fva_cfg.get('backend', ''))
        if backend_id == 'd40_v3_refined_hex_nojob':
            try:
                import fva600_d40_v3_nojob as fva_backend
            except ImportError:
                raise ImportError(
                    'fva600_d40_v3_nojob.py must sit next to '
                    'build_parametric_model.py')
            fva_backend.build(params, core=core)
            workflow = 'pre_solve_regression'
            setup = {'backend': backend_id, 'matching': 'NOT_VERIFIED',
                     'submitted': False}
        elif backend_id in ('method_a_connected_mesh_v1',
                             'method_a_hybrid_hex_v2'):
            try:
                import fva600_method_a_backend as fva_backend
            except ImportError:
                raise ImportError(
                    'fva600_method_a_backend.py must sit next to '
                    'build_parametric_model.py')
            setup_result = fva_backend.build(
                params, core=core, base_builder=sys.modules[__name__])
            workflow = 'method_a_numerical'
            setup_audit_ok = setup_result.get('audit_ok')
            setup_error = (setup_result.get('error') or
                           (setup_result.get('job') or {}).get('error'))
            if setup_audit_ok is not True and not setup_error:
                setup_error = ('Method-A base audit did not pass '
                               '(audit_ok=%s)' % setup_audit_ok)
            setup = {
                'backend': backend_id,
                'matching': (setup_result.get('matching') or {}).get('status'),
                'submitted': bool((setup_result.get('job') or {}).get('submitted')),
                'job': (setup_result.get('job') or {}).get('name'),
                'audit_path': setup_result.get('audit_path'),
                'audit_ok': setup_audit_ok,
                'nojob_guard': setup_result.get('nojob_guard'),
                'status': (setup_result.get('job') or {}).get('status'),
                'error': setup_error,
            }
        else:
            raise ValueError('Unknown FVA backend %r' % backend_id)
        elapsed = time.time() - t0
        setup.update({'badge': core.EVIDENCE_FVA_RESEARCH,
                      'workflow': workflow})
        setup_preview = (setup_result.get('preview')
                         if backend_id in ('method_a_connected_mesh_v1',
                                           'method_a_hybrid_hex_v2')
                         else None)
        write_build_result(params, True, elapsed, analysis=setup,
                           preview=setup_preview)
        print('[done] FVA-RESEARCH %s finished in %.1f s' %
              (workflow, elapsed))
        return

    m, report = build_all(params)
    d = params['_derived']
    mesh_plan = params.get('_mesh_plan') or core.resolve_mesh_plan(params, d)
    order = mesh_plan['element_order']
    hexc = mesh_plan['linear_hex_code']
    thr = float(params.get('ar_repair_threshold', 25.0))

    study = None
    if bool((params.get('study') or {}).get('enabled', False)):
        study = mesh_study(m, params, d, order, hexc, thr,
                           report.get('Shaft'))
        write_study_csv(study, generated_dir, str(params['model_name']))

    analysis = None
    post = None
    if d.get('an_on'):
        try:
            analysis = add_analysis(m, params, d)
        except Exception as ex:
            print('[analysis] FAILED to set up:', str(ex))
            analysis = {'enabled': True, 'error': str(ex)[:200]}
    if params.get('save_cae', True):
        cae = str(os.path.join(model_dir, str(params['model_name']) + '.cae'))
        mdb.saveAs(pathName=cae)
        print('[save] CAE written to', cae)

    an = params.get('analysis', {}) or {}
    if analysis and analysis.get('job') and bool(an.get('submit', False)):
        try:
            status, odb, el = submit_job(analysis['job'], jobs_dir)
            analysis['status'] = status
            analysis['seconds'] = el
            analysis['odb'] = odb
            if bool(an.get('post_process', True)) and \
                    str(status).upper().find('COMPLET') >= 0:
                post = post_process(odb, d, analysis)
        except Exception as ex:
            print('[solve] FAILED:', str(ex))
            analysis['status'] = 'FAILED: %s' % str(ex)[:150]

    try:
        ok = write_audit(m, report, params, generated_dir,
                         analysis, post, study)
    except Exception as e:
        print('[audit] skipped due to:', str(e))
        ok = None

    preview = None
    if params.get('make_preview', True):
        preview = render_preview(m, screenshots_dir,
                                 str(params['model_name']), d, params)

    elapsed = time.time() - t0
    write_build_result(params, ok, elapsed, analysis=analysis, preview=preview)
    print('[done] build finished in %.1f s, verdict OK = %s'
          % (elapsed, ok))


if __name__ == '__main__':
    main()
