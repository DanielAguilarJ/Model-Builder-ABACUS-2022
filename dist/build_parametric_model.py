# -*- coding: utf-8 -*-
"""
================================================================================
 PARAMETRIC BUILDER v2 - Shaft / Key (Form A|B) / Hub          (NOJOB)
================================================================================
 Rebuilds the whole finite-element model from a set of parameters following the
 DIN 6885 parallel-key scheme.  Change a value (for example the shaft diameter
 D), run it, and the model is regenerated, meshed, assembled, audited and saved.

 KEY FORM SWITCH (DIN 6885)
   Form A -> rounded ends  (pill / capsule footprint, end radius b/2)
   Form B -> square ends   (rectangular footprint)

 HUB TYPE SWITCH
   cylindrical -> hub seated DIRECTLY on the shaft, bore d_i = D,
                  outer d_a = D * Q_A, own keyway of depth t2   [default]
   tapered     -> legacy variant with a tapered bushing + conical hub

 PARAMETERS (USER) vs DERIVED
   Shaft : D, dz, z0_offset, r2                 (USER)
           R = D/2, L = L_over_D * D,
           b, t1  from DIN 6885 (function of D),
           R_cap = b/2, z_0 = R_cap + z0_offset,
           z_1 = z_0 + 2*R_cap + dz,  y_F = R - t1
   Key   : l, c, chamfer angle 45 deg           (USER)
           b, h from DIN 6885,  x_w = b/2,
           y_min = R - t1,  y_max = R - t1 + h
   Hub   : L_hub, Q_A, r1                       (USER)
           d_i = D,  d_a = D * Q_A,  t2 from DIN 6885,
           groove roof = R + t2,  top clearance g_c = t1 + t2 - h

 HOW TO RUN
   abaqus cae noGUI=build_parametric_model.py -- params.json
 or from the GUI / the Abaqus plug-in.

 The model is kept NOJOB: geometry + materials + mesh + assembly + sets only.
 Abaqus kernel is Python 2.7, so this file is written for Python 2.7.
================================================================================
"""
from __future__ import print_function
import os
import sys
import json
import math

from abaqus import mdb, session
from abaqusConstants import *
import regionToolset
from mesh import ElemType

AX = {'x': (YZPLANE, 0), 'y': (XZPLANE, 1), 'z': (XYPLANE, 2)}
HEX8_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0),
              (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7))

MAT_SHAFT = 'STEEL_SHAFT'
MAT_HUB = 'STEEL_HUB'
MAT_KEY = 'STEEL_KEY'
SEC = {MAT_SHAFT: 'SEC_STEEL_SHAFT', MAT_HUB: 'SEC_STEEL_HUB',
       MAT_KEY: 'SEC_STEEL_KEY'}

# ----------------------------------------------------------------- literature
# Reference values used by the design-check block. They are published results,
# reported here for comparison only - they are NOT computed by this model.
REFS = [
    ('[1] N. L. Pedersen, "Stress concentrations in keyways and optimization of '
     'keyway design", J. Strain Analysis for Engineering Design 45(8), 593-604, 2010.'),
    ('[2] F. Kresinsky, E. Leidich, A. Hasse, "Different Failure Mechanisms in Keyed '
     'Shaft-Hub Connections under Dynamic Torque Load", ICSI 2019, TU Chemnitz.'),
    ('[3] M. Eissa, H. Fessler, "Reduction of elastic stress concentrations in '
     'end-milled keyed connections", Experimental Mechanics 23, 401-408, 1983.'),
    ('[4] DIN 6892 (parallel key strength) and DIN 743 (shaft fatigue / notch effect).'),
]
# [1], 2D pure torsion, DIN 6885 keyway with the maximum fillet of the standard
KTS_SHAFT_LIT = 2.93
# [1], hub, outer diameter three times the inner one
KTS_HUB_LIT = 3.90
# [1], full 3D model WITH CONTACT, standard DIN design: von Mises SCF, converged
KVM_3D_DIN_LIT = 22.3
# [1], optimized double-symmetric super-elliptic key (eta = 3.1), value obtained
# in the 2D contact model. [1] states this is a 67% reduction with respect to the
# DIN design evaluated in the SAME 2D model - so 5.9 must NOT be divided by the
# 3D value 22.3 above. The reductions quoted by [1] are used verbatim instead.
KVM_2D_OPT_LIT = 5.9
RED_2D_SYM_LIT = 67.0     # % reduction, double-symmetric optimum, 2D
RED_3D_UNSYM_LIT = 78.0   # % reduction, unsymmetrical optimum, verified in 3D
ETA_OPT_LIT = 3.1
# [1], degrees of freedom at which the stress was considered converged (~1% change)
DOF_CONVERGED_LIT = 4.4e6
# [2], hub wall classification: below this d/D1 the failure is in the shaft keyway
D_OVER_D1_THICK = 0.70


# ================================================================== parameters
def default_params():
    """Validated D40 design. Every value can be overridden from JSON."""
    return {
        "model_name": "PARAM_MODEL",
        "output_dir": "",
        "save_cae": True,
        "make_preview": True,
        # Fully integrated elements only (no reduced integration):
        #   linear    -> C3D8  hex + C3D4  tet
        #   quadratic -> C3D20 hex + C3D10 tet
        "element_order": "linear",        # linear | quadratic
        "linear_hex_code": "C3D8",        # C3D8 (full) | C3D8I (full + incompat.)
        # Cells owning FAILED elements are always re-meshed as tet. Cells whose
        # aspect ratio exceeds this value are too. Keep it high to favour the
        # linear HEXAHEDRAL mesh the design calls for; lower it to trade hex for
        # a better worst-case aspect ratio.
        "ar_repair_threshold": 25.0,
        # Elements forced along each quarter-circle fillet arc. Default 0 = off.
        # Turning it on DOES resolve the notch better (2 -> n elements on the
        # arc) but it raises the aspect ratio sharply, because only the
        # tangential element size shrinks. See the note in _seed_fillet_arcs.
        # Use it together with a much finer global seed, or not at all.
        "fillet_arc_elems": 0,
        "key_form": "A",                  # A = rounded ends, B = square ends
        "hub_type": "cylindrical",         # cylindrical | tapered

        "shaft": {
            "D": 40.0,                    # USER
            "L_over_D": 3.0,              # L = 3 * D
            "dz": 38.0,                   # USER, distance between arc centres
            "z0_offset": 5.0,             # z_0 = R_cap + 5
            "R_cap": 0.0,                 # USER, 0 = auto (b/2, end-mill radius)
            "r2": 0.25,                   # USER, keyway root fillet
            "seed": 1.2
        },
        "key": {
            "l": 0.0,                     # USER, 0 = auto from form
            "c": 0.8,                     # USER, 45 deg corner chamfer
            "chamfer_angle": 45.0,
            "seed": 0.6
        },
        "hub": {
            "L_hub": 38.0,                # USER
            "QA": 2.0,                    # USER, d_a = D * QA
            "r1": 0.25,                   # USER, hub keyway roof fillet
            "groove_clearance": 0.0215,   # total width clearance in the hub slot
            "seed": 1.0
        },
        # Analytical design check (no analysis is run; these are hand formulas
        # evaluated from the parameters, used to sanity-check the design and to
        # compare against published stress concentration factors).
        "design_check": {
            "enabled": True,
            "T_nom": 200.0,           # nominal torque [N m]
            "T_max": 0.0,             # peak torque [N m], 0 = same as T_nom
            "n_keys": 1,              # number of keys
            "load_distribution": 1.0, # >1 per DIN 6892 method B; 1.0 = uniform
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
        # stays linear elastic, so Re is reference information only).
        "materials": {
            MAT_SHAFT: {"grade": "C45", "E": 210000.0, "nu": 0.30, "rho": 7.85e-09, "Re": 430.0},
            MAT_HUB:   {"grade": "C45", "E": 210000.0, "nu": 0.30, "rho": 7.85e-09, "Re": 430.0},
            MAT_KEY:   {"grade": "C45", "E": 210000.0, "nu": 0.30, "rho": 7.85e-09, "Re": 430.0}
        }
    }


def deep_update(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _to_str(obj):
    """JSON gives unicode; the Abaqus 2.7 API rejects it for name arguments."""
    if isinstance(obj, dict):
        return dict((_to_str(k), _to_str(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return type(obj)(_to_str(x) for x in obj)
    try:
        uni = unicode
    except NameError:
        uni = None
    if uni is not None and isinstance(obj, uni):
        try:
            return obj.encode('ascii')
        except UnicodeEncodeError:
            return obj.encode('utf-8')
    return obj


def load_params():
    p = default_params()
    path = None
    argv = sys.argv
    if '--' in argv:
        rest = argv[argv.index('--') + 1:]
        if rest:
            path = rest[0]
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
        cand = os.path.join(here, 'params.json')
        if os.path.isfile(cand):
            path = cand
    if path and os.path.isfile(path):
        f = open(path, 'r')
        try:
            user = json.load(f)
        finally:
            f.close()
        deep_update(p, user)
        print("[params] loaded from", path)
    else:
        print("[params] no JSON found, using built-in defaults")
    return _to_str(p)


# ---------------------------------------------------------------- DIN 6885
# (D_upto, b, h, t1 shaft depth, t2 hub depth)
DIN6885 = [
    (8,   2,  2,  1.2, 1.0), (10,  3,  3,  1.8, 1.4), (12,  4,  4,  2.5, 1.8),
    (17,  5,  5,  3.0, 2.3), (22,  6,  6,  3.5, 2.8), (30,  8,  7,  4.0, 3.3),
    (38,  10, 8,  5.0, 3.3), (44,  12, 8,  5.0, 3.3), (50,  14, 9,  5.5, 3.8),
    (58,  16, 10, 6.0, 4.3), (65,  18, 11, 7.0, 4.4), (75,  20, 12, 7.5, 4.9),
    (85,  22, 14, 9.0, 5.4), (95,  25, 14, 9.0, 5.4), (110, 28, 16, 10.0, 6.4),
    (130, 32, 18, 11.0, 7.4), (150, 36, 20, 12.0, 8.4),
]


def din6885_key(D):
    """Standard parallel key (b, h, t1, t2) for shaft diameter D [mm]."""
    for d_upto, b, h, t1, t2 in DIN6885:
        if D <= d_upto:
            return {'b': float(b), 'h': float(h), 't1': float(t1), 't2': float(t2)}
    q = DIN6885[-1]
    return {'b': float(q[1]), 'h': float(q[2]), 't1': float(q[3]), 't2': float(q[4])}


def derive(params):
    """Compute every derived quantity from the USER parameters."""
    sh = params['shaft']
    ky = params['key']
    hu = params['hub']
    D = float(sh['D'])
    k = din6885_key(D)
    d = {}
    d['D'] = D
    d['R'] = D / 2.0
    d['L'] = float(sh['L_over_D']) * D
    d['b'] = k['b']
    d['h'] = k['h']
    d['t1'] = k['t1']
    d['t2'] = k['t2']
    rc_user = float(sh.get('R_cap') or 0.0)
    d['R_cap'] = rc_user if rc_user > 0 else k['b'] / 2.0
    d['R_cap_auto'] = (rc_user <= 0)
    d['z0'] = d['R_cap'] + float(sh['z0_offset'])
    d['dz'] = float(sh['dz'])
    d['z1'] = d['z0'] + 2.0 * d['R_cap'] + d['dz']
    d['c1'] = d['z0'] + d['R_cap']          # first arc centre
    d['c2'] = d['c1'] + d['dz']             # second arc centre
    d['z_mid'] = 0.5 * (d['z0'] + d['z1'])
    d['yF'] = d['R'] - d['t1']
    d['x_w'] = d['b'] / 2.0
    d['y_min'] = d['R'] - d['t1']
    d['y_max'] = d['y_min'] + d['h']
    d['form'] = str(params.get('key_form', 'A')).strip().upper()[:1] or 'A'
    l = float(ky.get('l') or 0.0)
    if l <= 0:
        # auto: Form A fills the whole capsule keyway, Form B fits the straight part
        l = (2.0 * d['R_cap'] + d['dz']) if d['form'] == 'A' else d['dz']
    d['l'] = l
    d['c'] = float(ky['c'])
    d['chamfer_angle'] = float(ky.get('chamfer_angle', 45.0))
    d['L_hub'] = float(hu['L_hub'])
    d['QA'] = float(hu['QA'])
    d['d_i'] = D
    d['d_a'] = D * d['QA']
    d['r1'] = float(hu['r1'])
    d['r2'] = float(sh['r2'])
    d['groove_w'] = d['b'] + float(hu.get('groove_clearance', 0.0))
    d['groove_roof'] = d['R'] + d['t2']
    d['g_c'] = d['t1'] + d['t2'] - d['h']

    # ---- why is c what it is?  The bottom corner chamfer of the key must clear
    # the keyway ROOT FILLET r2 in the shaft. The fillet centre sits at
    # (x_w - r2, y_F + r2); both of its tangent points give y - x = y_F - x_w + r2,
    # while the chamfer face is the line y - x = y_min - (x_w - c). With
    # y_min = y_F this reduces to the clean condition
    #        c >= r2      and      perpendicular clearance = (c - r2)/sqrt(2)
    root2 = math.sqrt(2.0)
    d['c_min_bottom'] = d['r2']
    d['clear_bottom'] = (d['c'] - d['r2']) / root2
    # Top chamfer vs the hub keyway ROOF fillet r1 (mirror of the above)
    top_limit = d['groove_w'] / 2.0 + d['groove_roof'] - d['r1']
    top_line = (d['x_w'] - d['c']) + d['y_max']
    d['clear_top'] = (top_limit - top_line) / root2
    # Straight flank left for torque transfer after chamfering both corners
    d['flank_in_shaft'] = max(0.0, (d['R'] - d['y_min']) - d['c'])
    d['flank_total'] = max(0.0, d['h'] - 2.0 * d['c'])
    # The hub keyway must not break through the hub wall
    d['hub_wall_left'] = d['d_a'] / 2.0 - d['groove_roof']

    # ---- analytical design check (see REFS) --------------------------------
    dc = params.get('design_check', {}) or {}
    d['dc_on'] = bool(dc.get('enabled', False))
    if d['dc_on']:
        T = float(dc.get('T_nom', 0.0)) * 1000.0            # N m -> N mm
        Tmax = float(dc.get('T_max', 0.0)) * 1000.0
        if Tmax <= 0:
            Tmax = T
        nk = max(1, int(dc.get('n_keys', 1)))
        phi = float(dc.get('load_distribution', 1.0)) or 1.0
        Dm = d['D']
        # nominal torsional stress of the plain shaft, tau = T / Wt, Wt = pi d^3/16
        d['Wt'] = math.pi * Dm ** 3 / 16.0
        d['T_nom'] = T
        d['T_max'] = Tmax
        d['tau_nom'] = T / d['Wt'] if d['Wt'] > 0 else 0.0
        # peak stresses ESTIMATED with published SCFs - not computed here
        d['tau_peak_lit'] = KTS_SHAFT_LIT * d['tau_nom']
        d['tau_peak_hub_lit'] = KTS_HUB_LIT * d['tau_nom']
        # DIN 6892-style surface pressure. The corner chamfer c removes bearing
        # height on both sides, exactly as the standard's h' = h - 2s does.
        d['h_bear_shaft'] = max(0.0, d['t1'] - d['c'])
        d['h_bear_hub'] = max(0.0, d['h'] - d['t1'] - d['c'])
        # load-bearing length: a Form A key only bears on its straight portion
        d['l_tr'] = max(0.0, d['l'] - d['b']) if d['form'] == 'A' else d['l']
        def _p(hb):
            den = Dm * hb * d['l_tr'] * nk
            return (2.0 * Tmax * phi / den) if den > 0 else float('inf')
        d['p_shaft'] = _p(d['h_bear_shaft'])
        d['p_hub'] = _p(d['h_bear_hub'])
        mats = params.get('materials', {})
        Re_s = float(mats.get(MAT_SHAFT, {}).get('Re', 0.0) or 0.0)
        Re_h = float(mats.get(MAT_HUB, {}).get('Re', 0.0) or 0.0)
        d['p_perm_shaft'] = float(dc.get('p_perm_shaft', 0.0) or 0.0) or Re_s
        d['p_perm_hub'] = float(dc.get('p_perm_hub', 0.0) or 0.0) or Re_h
        d['util_shaft'] = (d['p_shaft'] / d['p_perm_shaft']) if d['p_perm_shaft'] > 0 else None
        d['util_hub'] = (d['p_hub'] / d['p_perm_hub']) if d['p_perm_hub'] > 0 else None
        # torque still transmissible at the allowable pressure
        def _T(hb, pp):
            return pp * Dm * hb * d['l_tr'] * nk / (2.0 * phi) / 1000.0   # -> N m
        d['T_perm_shaft'] = _T(d['h_bear_shaft'], d['p_perm_shaft'])
        d['T_perm_hub'] = _T(d['h_bear_hub'], d['p_perm_hub'])
        d['T_perm'] = min(d['T_perm_shaft'], d['T_perm_hub'])
        # Kresinsky [2]: hub wall classification d/D1
        d['d_over_D1'] = d['d_i'] / d['d_a'] if d['d_a'] > 0 else None
        d['thick_walled'] = (d['d_over_D1'] is not None
                             and d['d_over_D1'] < D_OVER_D1_THICK)
    params['_derived'] = d
    print('[derive] D=%.1f R=%.1f L=%.1f | DIN b=%.1f h=%.1f t1=%.1f t2=%.1f' % (
        D, d['R'], d['L'], d['b'], d['h'], d['t1'], d['t2']))
    print('[derive] R_cap=%.2f z0=%.2f z1=%.2f (dz=%.1f) yF=%.2f' % (
        d['R_cap'], d['z0'], d['z1'], d['dz'], d['yF']))
    print('[derive] key Form %s l=%.2f c=%.2f | hub d_i=%.1f d_a=%.1f roof=%.2f g_c=%.3f' % (
        d['form'], d['l'], d['c'], d['d_i'], d['d_a'], d['groove_roof'], d['g_c']))
    return d


# ================================================================== geometry
def _cut(p, axis, off, tol=1e-6):
    pp, idx = AX[axis]
    dat = p.datums[p.DatumPlaneByPrincipalPlane(principalPlane=pp, offset=off).id]
    sel = []
    for c in p.cells:
        b = p.cells[c.index:c.index + 1].getBoundingBox()
        if b['low'][idx] < off - tol and b['high'][idx] > off + tol:
            sel.append(c)
    if sel:
        p.PartitionCellByDatumPlane(datumPlane=dat, cells=sel)


def _clear_instances(a):
    for i in list(a.instances.keys()):
        del a.instances[i]


def build_shaft(m, d):
    """Cylinder R, length L, capsule keyway (round ends R_cap), root fillet r2."""
    R, L = d['R'], d['L']
    b, R_cap = d['b'], d['R_cap']
    c1, c2, yF, r2 = d['c1'], d['c2'], d['yF'], d['r2']
    name = 'Shaft'

    s = m.ConstrainedSketch(name='__cyl__', sheetSize=8.0 * R)
    s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(R, 0.0))
    bl = m.Part(name='__BLANK__', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    bl.BaseSolidExtrude(sketch=s, depth=L)
    del m.sketches['__cyl__']

    # capsule cutter: footprint in (u=x, v=z), extruded through the shaft
    s2 = m.ConstrainedSketch(name='__cap__', sheetSize=8.0 * R)
    s2.Line(point1=(-b / 2.0, c1), point2=(-b / 2.0, c2))
    s2.Line(point1=(b / 2.0, c1), point2=(b / 2.0, c2))
    s2.ArcByCenterEnds(center=(0.0, c2), point1=(b / 2.0, c2),
                       point2=(-b / 2.0, c2), direction=COUNTERCLOCKWISE)
    s2.ArcByCenterEnds(center=(0.0, c1), point1=(-b / 2.0, c1),
                       point2=(b / 2.0, c1), direction=COUNTERCLOCKWISE)
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
    if r2 > 0:
        fe = [e for e in p.edges if abs(e.pointOn[0][1] - yF) < 1e-4]
        if fe:
            try:
                p.Round(radius=r2, edgeList=tuple(fe))
                print('[shaft] root fillet r2=%.3f on %d edges' % (r2, len(fe)))
            except Exception as ex:
                print('[shaft] fillet warning:', str(ex)[:90])

    # Cut at the keyway EXTREMES (z0, z1), not at the arc centres. The straight
    # wall meets the cap arc tangentially at the arc centre planes, so cutting
    # there truncates a G1 transition into a zero-angle cusp that no hex mesh
    # can fill. Measured on D40: z0/z1 -> 2 non-hex cells, c1/c2 -> 4.
    for off in (d['z0'], d['z1']):
        _cut(p, 'z', off)
    for off in (0.0, b / 2.0, -b / 2.0):
        _cut(p, 'x', off)
    _cut(p, 'y', yF)
    for off in (R * 0.45, -R * 0.45):
        _cut(p, 'x', off)
    for off in (R * 0.45, -R * 0.45):
        _cut(p, 'y', off)
    return p


def build_key(m, d):
    """Key with a chamfered cross-section and Form A (round) or B (square) ends.

    Built footprint-first: the (x, z) footprint is sketched in the part's local
    x-y plane and extruded along local z by h, then both perimeter loops get a
    45 deg chamfer of leg c.  The instance is rotated -90 deg about x in the
    assembly so the height ends up along global y.
    """
    b, h, l, c = d['b'], d['h'], d['l'], d['c']
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
    else:
        s.rectangle(point1=(-r, -l / 2.0), point2=(r, l / 2.0))
    p = m.Part(name=name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    p.BaseSolidExtrude(sketch=s, depth=h)
    del m.sketches['__key__']

    if c > 0:
        ang = float(d.get('chamfer_angle', 45.0))
        if abs(ang - 45.0) > 1e-6:
            print('[key] WARNING: chamfer_angle=%.1f deg was requested, but the '
                  'symmetric Chamfer(length=..) used here is 45 deg by '
                  'construction. Building with 45 deg (phi_c per DIN note).' % ang)
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
        # split the straight middle from the two round caps at the arc centres;
        # there the arc tangent is perpendicular to the cut, so no cusp appears
        zc = l / 2.0 - r
        for off in (zc, -zc):
            _cut(p, 'y', off)
    for off in (0.0, r - c, -(r - c)):
        _cut(p, 'x', off)
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
        raise ValueError('Hub outer diameter (%.2f) must exceed the bore (%.2f); raise QA'
                         % (d['d_a'], d['d_i']))

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
    if r1 > 0:
        ce = [e for e in p.edges
              if abs(e.pointOn[0][1] - roof) < 1e-4
              and abs(abs(e.pointOn[0][0]) - gw / 2.0) < 1e-3]
        if ce:
            try:
                p.Round(radius=r1, edgeList=tuple(ce))
                print('[hub] keyway roof fillet r1=%.3f on %d edges' % (r1, len(ce)))
            except Exception as ex:
                print('[hub] fillet warning:', str(ex)[:90])

    for off in (0.0, gw / 2.0, -gw / 2.0):
        _cut(p, 'x', off)
    _cut(p, 'y', 0.0)
    _cut(p, 'y', ri)
    return p


def build_revolved_annulus(m, name, length, r_in_small, r_in_large,
                           r_out_small, r_out_large):
    """Legacy helper (tapered variant): axis along part Y."""
    s = m.ConstrainedSketch(name='__rev__', sheetSize=20.0 * max(r_out_large, length))
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
    a.InstanceFromBooleanCut(name='__BU_CUT__', instanceToBeCut=a.instances['__BU__'],
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
def _elem_types(order, hex_code):
    """FULLY INTEGRATED elements - no reduced integration anywhere.

    linear    : C3D8  hex (full integration)          + C3D4  tet fallback
                C3D8I is also fully integrated and adds incompatible modes,
                which removes the shear locking C3D8 suffers in bending.
                C3D8R is only kept so an old input file can be reproduced.
    quadratic : C3D20 hex (full integration)          + C3D10 tet fallback
    """
    order = str(order).strip().lower()
    if order == 'quadratic':
        return (ElemType(elemCode=C3D20, elemLibrary=STANDARD),
                ElemType(elemCode=C3D10, elemLibrary=STANDARD))
    code = {'C3D8': C3D8, 'C3D8I': C3D8I, 'C3D8R': C3D8R}.get(
        str(hex_code).strip().upper(), C3D8)
    return (ElemType(elemCode=code, elemLibrary=STANDARD),
            ElemType(elemCode=C3D4, elemLibrary=STANDARD))


def _seed_fillet_arcs(p, radius, n_elems, second_order=False,
                      band_factor=20.0, grade=3.0):
    """Force n_elems elements along every quarter-circle fillet arc of radius r.

    Resolving the notch governs the accuracy of a stress concentration factor:
    reference [1] had to refine heavily before the peak stress settled. A global
    seed alone leaves only 1-2 elements on a 0.25 mm fillet, so the arcs are
    seeded explicitly here. Returns the number of edges seeded.
    """
    if radius <= 0 or n_elems <= 0:
        return 0
    target = math.pi * radius / 2.0
    sel = []
    for e in p.edges:
        try:
            L = e.getSize(printResults=False)
        except Exception:
            continue
        if abs(L - target) <= 0.02 * target + 1e-6:
            sel.append(e)
    if not sel:
        return 0
    try:
        p.seedEdgeByNumber(edges=tuple(sel), number=max(1, int(n_elems)),
                           constraint=FINER)
    except Exception as ex:
        print('   [seed] fillet arc seeding skipped:', str(ex)[:70])
        return 0

    # NOTE (measured, D40, shaft seed 2.5 mm): forcing 6 elements on the arc
    # takes the notch element size from 0.196 to 0.065 mm, but the aspect ratio
    # rises 22.5 -> 68.9, because only the TANGENTIAL size shrinks while the
    # axial and radial sizes stay at the global seed. Trying to fix that by also
    # seeding the neighbouring edges by size is worse, not better: edge seeds
    # apply to the WHOLE edge, so long edges near the notch get subdivided along
    # their entire length (measured: 0.7 to 10.3 million elements and AR up to
    # 130). Proper local refinement needs a dedicated partition around the
    # keyway root, which is not implemented. Hence this stays opt-in and the
    # audit reports the cost instead of hiding it.
    return len(sel)


def robust_mesh(p, seed, order='linear', hex_code='C3D8', ar_threshold=12.0,
                fillet_radius=0.0, fillet_arc_elems=0):
    """Mesh so that it ALWAYS produces elements: hex Structured -> hex Sweep ->
    free tet fallback, then a repair pass that re-meshes (as tet) any cell that
    still owns a failed or very distorted element."""
    p.deleteMesh()
    try:
        p.deleteSeeds(regions=p.edges)
    except Exception:
        pass
    for c in p.cells:
        done = False
        for kw in (dict(elemShape=HEX, technique=STRUCTURED),
                   dict(elemShape=HEX, technique=SWEEP, algorithm=MEDIAL_AXIS),
                   dict(elemShape=HEX, technique=SWEEP, algorithm=ADVANCING_FRONT)):
            try:
                p.setMeshControls(regions=(c,), **kw)
                done = True
                break
            except Exception:
                continue
        if not done:
            try:
                p.setMeshControls(regions=(c,), elemShape=TET, technique=FREE)
            except Exception:
                pass
    p.seedPart(size=seed, deviationFactor=0.1, minSizeFactor=0.1)
    quad = (str(order).strip().lower() == 'quadratic')
    ne = _seed_fillet_arcs(p, fillet_radius, fillet_arc_elems, quad)
    if ne:
        print('   [seed] %d fillet arc edges seeded with %d elements each'
              % (ne, int(fillet_arc_elems)))
    hexT, tetT = _elem_types(order, hex_code)
    p.setElementType(regions=(p.cells,), elemTypes=(hexT, tetT))
    p.generateMesh()

    empty = []
    for c in p.cells:
        try:
            st = p.getMeshStats(regions=(c,))
            if st.numHexElems == 0 and st.numTetElems == 0 and st.numWedgeElems == 0:
                empty.append(c)
        except Exception:
            pass
    if empty:
        p.setMeshControls(regions=tuple(empty), elemShape=TET, technique=FREE)
        p.setElementType(regions=(p.cells,), elemTypes=(hexT, tetT))
        p.generateMesh()

    thr = float(ar_threshold or 0.0)
    for _attempt in range(3):
        bad = set(e.label for e in
                  p.verifyMeshQuality(criterion=ANALYSIS_CHECKS)['failedElements'])
        if thr > 0:
            try:
                arbad = p.verifyMeshQuality(criterion=ASPECT_RATIO, threshold=thr)
                bad |= set(e.label for e in arbad.get('failedElements', []))
            except Exception:
                pass
        if not bad:
            break
        cells = []
        for c in p.cells:
            try:
                s = p.Set(name='__probe__', cells=p.cells[c.index:c.index + 1])
                labs = set(e.label for e in s.elements)
                del p.sets['__probe__']
            except Exception:
                labs = set()
                if '__probe__' in p.sets:
                    del p.sets['__probe__']
            if labs & bad:
                cells.append(c)
        if not cells:
            break
        p.setMeshControls(regions=tuple(cells), elemShape=TET, technique=FREE)
        p.setElementType(regions=(p.cells,), elemTypes=(hexT, tetT))
        p.generateMesh()

    hist = {}
    for e in p.elements:
        hist[str(e.type)] = hist.get(str(e.type), 0) + 1
    return hist


def fillet_mesh_metrics(p, radius):
    """How well is the notch actually resolved?

    Finds the quarter-circle fillet edges (arc length pi*r/2) and counts the
    mesh intervals on them. Resolving a notch is what controls the accuracy of a
    stress concentration factor, so this is reported explicitly instead of being
    assumed from the global seed. For second-order elements the mid-side nodes
    halve the node spacing, so the element count is corrected accordingly.
    """
    out = {'radius': radius, 'edges': 0, 'min_elems': None,
           'max_elems': None, 'elem_size': None, 'second_order': False}
    if radius <= 0:
        return out
    target = math.pi * radius / 2.0
    try:
        second = any(len(e.connectivity) > 8 for e in p.elements[:1])
    except Exception:
        second = False
    out['second_order'] = second
    counts = []
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
        intervals = n - 1
        nelem = intervals / 2.0 if second else intervals
        if nelem > 0:
            counts.append(nelem)
    if counts:
        out['min_elems'] = min(counts)
        out['max_elems'] = max(counts)
        out['elem_size'] = target / max(min(counts), 1e-9)
    return out


def mesh_quality(p):
    ac = p.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
    ar = p.verifyMeshQuality(criterion=ASPECT_RATIO)
    return (len(ac['failedElements']), len(ac['warningElements']),
            ar.get('worst'), ar.get('average'))


def connected_components(p):
    par = {}

    def find(x):
        r = x
        while par[r] != r:
            r = par[r]
        while par[x] != r:
            par[x], x = r, par[x]
        return r
    for e in p.elements:
        c = e.connectivity[:8]
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


def build_all(params):
    eff = _to_str(params)
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
    order = params.get('element_order', 'linear')
    hexc = params.get('linear_hex_code', 'C3D8R')
    thr = float(params.get('ar_repair_threshold', 12.0))
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

    # ---- mesh
    report = {}
    nfa = int(params.get('fillet_arc_elems', 0) or 0)
    print('[mesh] shaft ...')
    report['Shaft'] = robust_mesh(sh, params['shaft']['seed'], order, hexc, thr,
                                  d['r2'], nfa)
    print('[mesh] key ...')
    report['Key'] = robust_mesh(ky, params['key']['seed'], order, hexc, thr)
    if bu is not None:
        print('[mesh] bushing ...')
        report['Bushing'] = robust_mesh(bu, params['bushing']['seed'], order, hexc, thr,
                                        d['r1'], nfa)
    print('[mesh] hub ...')
    report['Hub'] = robust_mesh(hu, params['hub']['seed'], order, hexc, thr,
                                d['r1'], nfa)

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
                vector=(0.0, d['y_min'] - kb['low'][1], d['z_mid'] - 0.5 * (kb['low'][2] + kb['high'][2])))
    a.Instance(name='HUB-1', part=hu, dependent=ON)
    if bu is not None:
        a.Instance(name='BUSHING-1', part=bu, dependent=ON)
        for nm in ('BUSHING-1', 'HUB-1'):
            a.rotate(instanceList=(nm,), axisPoint=(0.0, 0.0, 0.0),
                     axisDirection=(1.0, 0.0, 0.0), angle=-90.0)
    for nm in (['HUB-1'] + (['BUSHING-1'] if bu is not None else [])):
        ib = a.instances[nm].cells.getBoundingBox()
        a.translate(instanceList=(nm,),
                    vector=(0.0, 0.0, d['z_mid'] - 0.5 * (ib['low'][2] + ib['high'][2])))
    a.regenerate()

    # ---- sets
    pairs = [('SHAFT', 'SHAFT-1'), ('KEY', 'KEY-1'), ('HUB', 'HUB-1')]
    if bu is not None:
        pairs.append(('BUSHING', 'BUSHING-1'))
    for tag, inst in pairs:
        for s in ('ALL_%s_NODES' % tag, 'ALL_%s_ELEMENTS' % tag):
            if s in a.sets:
                del a.sets[s]
        a.Set(name='ALL_%s_NODES' % tag, nodes=a.instances[inst].nodes)
        a.Set(name='ALL_%s_ELEMENTS' % tag, elements=a.instances[inst].elements)
    return m, report


# ================================================================== audit
def write_audit(m, report, params, out_dir):
    lines = []

    def W(s):
        lines.append(s)
        print(s)

    def _keys(obj, attr):
        try:
            return list(getattr(obj, attr).keys())
        except Exception:
            return []

    d = params.get('_derived') or derive(params)
    tapered = str(params.get('hub_type', 'cylindrical')).strip().lower() == 'tapered'
    W('PARAMETRIC BUILD AUDIT  (v2, DIN 6885)')
    W('model: %s' % m.name)
    W('key_form: %s   hub_type: %s   element_order: %s (%s)' % (
        d['form'], params.get('hub_type'), params.get('element_order'),
        params.get('linear_hex_code')))
    W('steps=%s jobs=%s constraints=%s interactions=%s' % (
        _keys(m, 'steps'), _keys(mdb, 'jobs'),
        _keys(m, 'constraints'), _keys(m, 'interactions')))
    W('')
    W('DERIVED GEOMETRY')
    W('   D=%.3f  R=%.3f  L=%.3f (=%.1f x D)' % (
        d['D'], d['R'], d['L'], params['shaft']['L_over_D']))
    W('   DIN 6885: b=%.2f  h=%.2f  t1=%.2f  t2=%.2f' % (d['b'], d['h'], d['t1'], d['t2']))
    W('   keyway: R_cap=%.2f  z0=%.2f  z1=%.2f  dz=%.2f  yF=%.3f  r2=%.3f' % (
        d['R_cap'], d['z0'], d['z1'], d['dz'], d['yF'], d['r2']))
    W('   key   : Form %s  l=%.2f  c=%.3f (phi_c=45 deg)  x_w=%.2f  y_min=%.3f  y_max=%.3f' % (
        d['form'], d['l'], d['c'], d['x_w'], d['y_min'], d['y_max']))
    W('   hub   : d_i=%.2f  d_a=%.2f (QA=%.3f)  L_hub=%.2f  roof=%.3f  r1=%.3f' % (
        d['d_i'], d['d_a'], d['QA'], d['L_hub'], d['groove_roof'], d['r1']))
    W('   top clearance g_c = t1 + t2 - h = %.3f' % d['g_c'])
    W('   R_cap = %.2f (%s)' % (d['R_cap'], 'auto b/2' if d.get('R_cap_auto') else 'user'))
    W('')
    W('WHY c = %.3f ?  (Sec 6.1)' % d['c'])
    W('   The bottom corner chamfer has to clear the keyway ROOT FILLET r2.')
    W('   Fillet tangent points give   y - x = y_F - x_w + r2 = %.3f' % (d['yF'] - d['x_w'] + d['r2']))
    W('   Chamfer face is the line     y - x = y_min - (x_w - c) = %.3f' % (d['y_min'] - (d['x_w'] - d['c'])))
    W('   => condition  c >= r2 = %.3f ;  chosen c = %.3f' % (d['c_min_bottom'], d['c']))
    W('   => perpendicular clearance (c - r2)/sqrt(2) = %.4f mm' % d['clear_bottom'])
    W('   Top chamfer clearance to the hub roof fillet r1 = %.4f mm' % d['clear_top'])
    W('   Straight flank left for torque transfer h - 2c = %.3f mm' % d['flank_total'])
    W('')
    W('MATERIALS')
    for mat in (MAT_SHAFT, MAT_HUB, MAT_KEY):
        pr = params['materials'].get(mat, {})
        W('   %-12s grade=%-5s E=%.0f MPa  nu=%.2f  rho=%.3e t/mm^3  Re(ref)=%s MPa' % (
            mat, str(pr.get('grade', 'C45')), float(pr.get('E', 0)),
            float(pr.get('nu', 0)), float(pr.get('rho', 0)), pr.get('Re', 'n/a')))
    W('')
    tot_n = tot_e = 0
    ok = True
    order_parts = ['Shaft', 'Key'] + (['Bushing'] if tapered else []) + ['Hub']
    for pn in order_parts:
        p = m.parts[pn]
        failed, warn, arw, ara = mesh_quality(p)
        nc = connected_components(p)
        bb = p.cells.getBoundingBox()
        tot_n += len(p.nodes)
        tot_e += len(p.elements)
        if failed > 0 or nc != 1:
            ok = False
        W('PART %s' % pn)
        W('   nodes=%d elements=%d types=%s' % (len(p.nodes), len(p.elements), report.get(pn)))
        W('   sections=%s' % [sa.sectionName for sa in p.sectionAssignments])
        W('   local bbox=%s' % [round(bb['high'][i] - bb['low'][i], 4) for i in range(3)])
        W('   failed=%d warnings=%d aspectRatio worst=%s avg=%s components=%d' % (
            failed, warn, arw, ara, nc))
    W('')
    W('TOTAL nodes=%d elements=%d' % (tot_n, tot_e))
    a = m.rootAssembly
    W('ASSEMBLY bounding boxes')
    for nm in sorted(a.instances.keys()):
        ib = a.instances[nm].cells.getBoundingBox()
        W('   %-10s lo=%s hi=%s' % (nm, [round(v, 3) for v in ib['low']],
                                    [round(v, 3) for v in ib['high']]))
    W('SETS: %s' % sorted(a.sets.keys()))

    W('')
    W('FIT / CLEARANCE CHECKS')
    checks = []
    if not tapered:
        checks.append(('shaft OD vs hub bore', d['d_i'] / 2.0 - d['R'], 0.0,
                       'gap>=0 (0 = line-to-line seat)'))
    checks.append(('key base vs keyway floor', d['y_min'] - d['yF'], None, 'should be ~0'))
    checks.append(('shaft keyway flank/side', (d['b'] - d['b']) / 2.0, 0.0, '>=0'))
    checks.append(('hub groove flank/side', (d['groove_w'] - d['b']) / 2.0, 0.0, '>=0'))
    checks.append(('key top vs groove roof (g_c)', d['g_c'], 0.0, 'gap>=0'))
    lmax = (2.0 * d['R_cap'] + d['dz']) if d['form'] == 'A' else d['dz']
    checks.append(('key length vs keyway (Form %s)' % d['form'], lmax - d['l'], 0.0,
                   'l <= %.2f' % lmax))
    checks.append(('hub length vs keyway span', (d['z1'] - d['z0']) - d['L_hub'], None,
                   'info only'))
    # why c is what it is:  c must clear the shaft root fillet r2
    checks.append(('chamfer c vs root fillet r2', d['c'] - d['c_min_bottom'], 0.0,
                   'need c >= r2 = %.3f' % d['c_min_bottom']))
    checks.append(('  -> bottom chamfer clearance', d['clear_bottom'], 0.0,
                   '= (c - r2)/sqrt(2)'))
    checks.append(('  -> top chamfer clearance', d['clear_top'], 0.0,
                   'vs hub roof fillet r1'))
    checks.append(('straight flank left on key', d['flank_total'], 0.0,
                   '= h - 2c, load-carrying height'))
    checks.append(('hub wall left above keyway', d['hub_wall_left'], 0.0,
                   '= d_a/2 - (R + t2); raise Q_A if <= 0'))
    all_ok = True
    for label, val, lo, note in checks:
        flag = 'ok'
        if lo is not None and val < -1e-6:
            flag = 'FAIL'
            all_ok = False
        elif lo is None and abs(val) > 1e-3:
            flag = 'info'
        W('   %-34s % .4f mm  [%s] %s' % (label, val, flag, note))
    if not all_ok:
        ok = False
    # ---- notch resolution and mesh adequacy -------------------------------
    W('')
    W('NOTCH RESOLUTION AND MESH ADEQUACY')
    fm = fillet_mesh_metrics(m.parts['Shaft'], d['r2'])
    if fm['min_elems']:
        W('   shaft root fillet r2=%.3f : arc length pi*r/2 = %.4f mm on %d edges'
          % (fm['radius'], math.pi * fm['radius'] / 2.0, fm['edges']))
        W('   elements across the fillet arc: min %.1f  max %.1f  (element size ~%.4f mm)'
          % (fm['min_elems'], fm['max_elems'], fm['elem_size']))
        if fm['min_elems'] < 4:
            W('   [WARN] fewer than 4 elements on the notch arc: a stress')
            W('          concentration factor from this mesh would be unreliable.')
            W('          Raise fillet_arc_elems, but read the trade-off below.')
        else:
            W('   [ok] at least 4 elements on the notch arc.')
        W('   measured trade-off (D40, shaft seed 2.5 mm), fillet_arc_elems =')
        W('      0 -> 2 elem on arc, size 0.196 mm, aspect ratio worst 22.5')
        W('      4 -> 4 elem,        size 0.098 mm, aspect ratio worst 33.9')
        W('      6 -> 6 elem,        size 0.065 mm, aspect ratio worst 68.9')
        W('   Only the tangential size shrinks, so the elements get slender.')
        W('   A correct fix is a dedicated partition around the keyway root')
        W('   (not implemented) or a globally finer shaft mesh.')
    else:
        W('   could not identify the fillet arc edges (r2=%.3f).' % d['r2'])
    dof = 0
    for pn in order_parts:
        dof += 3 * len(m.parts[pn].nodes)
    W('   model degrees of freedom (3 per node) = %.3e' % dof)
    W('   reference [1]: the stress was considered converged at DOF >= %.1e'
      % DOF_CONVERGED_LIT)
    W('   ratio DOF / DOF_converged[1] = %.3f' % (dof / DOF_CONVERGED_LIT))
    if dof < DOF_CONVERGED_LIT:
        W('   [NOTE] this mesh is below the refinement at which [1] reported')
        W('          convergence (their case: d=100 mm, quadratic tets, contact).')
        W('          The comparison is order-of-magnitude only, but it means a')
        W('          peak stress taken from this mesh should not yet be quoted as')
        W('          converged. Run a seed refinement study before reporting a Kt.')

    # ---- analytical design check ------------------------------------------
    if d.get('dc_on'):
        dcp = params.get('design_check', {})
        W('')
        W('DESIGN CHECK  (analytical, not from a solved analysis)')
        W('   torque: T_nom=%.1f N m   T_max=%.1f N m   keys=%d   load distribution phi=%.2f'
          % (d['T_nom'] / 1000.0, d['T_max'] / 1000.0,
             int(dcp.get('n_keys', 1)), float(dcp.get('load_distribution', 1.0))))
        W('   plain-shaft section modulus Wt = pi*D^3/16 = %.1f mm^3' % d['Wt'])
        W('   nominal torsional stress tau_nom = T/Wt = %.2f MPa' % d['tau_nom'])
        W('   -- peak stress ESTIMATES using published SCFs (reference [1]) --')
        W('      shaft: Kts=%.2f -> tau_max ~ %.2f MPa' % (KTS_SHAFT_LIT, d['tau_peak_lit']))
        W('      hub  : Kts=%.2f -> tau_max ~ %.2f MPa' % (KTS_HUB_LIT, d['tau_peak_hub_lit']))
        W('      [1] full 3D WITH CONTACT, standard DIN design: KvM = %.1f (converged).'
          % KVM_3D_DIN_LIT)
        W('      [1] super-elliptic keyway, exponent eta=%.1f: KvM = %.1f in its 2D'
          % (ETA_OPT_LIT, KVM_2D_OPT_LIT))
        W('      contact model, which [1] reports as a %.0f%% reduction versus the DIN'
          % RED_2D_SYM_LIT)
        W('      design in the SAME 2D model (do not divide 5.9 by the 3D 22.3 -')
        W('      they are different models). Its unsymmetrical optimum reached %.0f%%,'
          % RED_3D_UNSYM_LIT)
        W('      confirmed in 3D. Reshaping the keyway is therefore the single most')
        W('      effective measure available for this joint.')
        W('   -- surface pressure, DIN 6892 style [4] --')
        W('      bearing height, shaft side  h\' = t1 - c     = %.3f mm' % d['h_bear_shaft'])
        W('      bearing height, hub side    h\' = h - t1 - c = %.3f mm' % d['h_bear_hub'])
        W('      bearing length (Form %s)     l_tr           = %.3f mm' % (d['form'], d['l_tr']))
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
                W('      thick-walled hub: [2] finds the failure always in the contact')
                W('      between key and SHAFT keyway. Watch the shaft keyway flank.')
            else:
                W('      thin-walled hub: [2] reports that failure between key and HUB')
                W('      becomes possible (notably for cast iron or aluminium hubs).')
        W('      [2] also finds the governing criterion depends on shaft strength:')
        W('      low-strength steel fails by permissible pressure (plastic keyway')
        W('      deformation), higher-strength steel by a crack at the shaft with no')
        W('      prior relevant plastic deformation. Both are covered by DIN 6892')
        W('      and DIN 743 respectively.')
        W('      [3] adds: with an unchamfered key the peak shear sits at the keyway')
        W('      END; doubling hub and key length lowered peak stress by ~25%, and')
        W('      preventing contact at the keyway end lowered it by ~11%.')

    W('')
    W('VERDICT: %s' % ('OK (all parts meshed, failed=0, single component, fits ok)'
                       if ok else 'CHECK (mesh failure, disconnection or interference)'))
    W('NOTE: NOJOB model - no contact, step, load, BC or job defined. Every stress')
    W('      figure above is either a hand formula or a published reference value;')
    W('      none of them comes from a solved analysis of this model.')
    W('')
    W('REFERENCES')
    for r in REFS:
        W('   ' + r)
    txt = '\n'.join(lines) + '\n'
    if out_dir:
        try:
            f = open(os.path.join(out_dir, 'PARAM_BUILD_AUDIT.txt'), 'w')
            f.write(txt)
            f.close()
        except Exception as ex:
            print('[audit] could not write file:', str(ex)[:90])
    return ok


def resolve_out_dir(params):
    out = params.get('output_dir', '') or ''
    if not out:
        out = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    if not os.path.isdir(out):
        try:
            os.makedirs(out)
        except Exception:
            out = os.getcwd()
    return out


def render_preview(m, out_dir, name):
    try:
        vps = session.viewports
        vp = vps[vps.keys()[0]] if vps.keys() else session.Viewport(
            name='preview', origin=(0, 0), width=200, height=150)
        vp.setValues(displayedObject=m.rootAssembly)
        vp.assemblyDisplay.setValues(mesh=ON, optimizationTasks=OFF,
                                     geometricRestrictions=OFF, stopConditions=OFF)
        session.printOptions.setValues(vpDecorations=OFF, vpBackground=OFF,
                                       reduceColors=False)
        session.pngOptions.setValues(imageSize=(1600, 1200))
        vp.view.setValues(session.views['Iso'])
        vp.view.fitView()
        png = os.path.join(out_dir, name + '_preview')
        session.printToFile(fileName=png, format=PNG, canvasObjects=(vp,))
        print('[preview] wrote', png + '.png')
        return png + '.png'
    except Exception as e:
        print('[preview] skipped:', str(e))
        return None


def main():
    params = load_params()
    out_dir = str(resolve_out_dir(params))
    m, report = build_all(params)

    if params.get('save_cae', True):
        cae = str(os.path.join(out_dir, str(params['model_name']) + '.cae'))
        mdb.saveAs(pathName=cae)
        print('[save] CAE written to', cae)

    try:
        ok = write_audit(m, report, params, out_dir)
    except Exception as e:
        print('[audit] skipped due to:', str(e))
        ok = None

    if params.get('make_preview', True):
        render_preview(m, out_dir, str(params['model_name']))

    print('[done] build finished, verdict OK =', ok)


if __name__ == '__main__':
    main()
