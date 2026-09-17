# -*- coding: utf-8 -*-
"""Render the presentation diagrams for Model Builder 4.2.

Every number that appears in a chart is imported live from the packaged engine
(keyjoint_core / din6892_methods), so the slides cannot drift from the code.

The deck exists in Spanish and English. Both share one layout: L(es, en) picks
the wording, MB_LANG picks the language, and the geometry stays identical so a
layout fix never has to be made twice.

Usage:
    MB_LANG=es python3 make_diagrams.py [name ...]
    MB_LANG=en python3 make_diagrams.py [name ...]
"""
from __future__ import annotations

import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import (Circle, FancyArrowPatch, FancyBboxPatch,  # noqa: E402
                                Polygon, Rectangle)
from matplotlib.lines import Line2D  # noqa: E402

REPO = "/projects/sandbox/Model-Builder-ABACUS-2022"
LANG = os.environ.get("MB_LANG", "es")
OUT = ("/projects/sandbox/assets/diagrams" if LANG == "es"
       else "/projects/sandbox/assets/diagrams_%s" % LANG)
sys.path.insert(0, REPO)
os.makedirs(OUT, exist_ok=True)

import din6892_methods as din  # noqa: E402
import keyjoint_core as core  # noqa: E402


def L(es_text, en_text):
    """Pick the wording for the active language."""
    return en_text if LANG == "en" else es_text


DPI = 220
SANS = ["Liberation Sans", "DejaVu Sans"]  # Arial metrics, matches the deck
MONO = ["Liberation Mono", "DejaVu Sans Mono"]
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = SANS
matplotlib.rcParams["axes.unicode_minus"] = False

INK = "#1D1D1F"
MUTED = "#86868B"
SOFT = "#6E6E73"
LINE = "#D2D2D7"
PANEL = "#F5F5F7"
PANEL2 = "#E6E6EB"
BLUE = "#0071E3"
DARK = "#111114"
WHITE = "#FFFFFF"
RED = "#B71C1C"
GREEN = "#1B5E20"
AMBER = "#8A4B08"

BADGE = {
    "NORMATIVE": "#1B5E20",
    "DIN-METHOD": "#0B5394",
    "FVA-RESEARCH": "#8A4B08",
    "USER-INPUT": "#7F1D1D",
    "NOT-IMPLEMENTED": "#4B5563",
    "LITERATURE": "#4A148C",
    "CORE-SCREENING": "#0D47A1",
    "USER-OVERRIDE": "#B71C1C",
}


# --------------------------------------------------------------------- helpers
def es(value, decimals=2, thousands=True):
    """Format a number for the active locale."""
    text_value = ("%%.%df" % decimals) % value
    whole, _, frac = text_value.partition(".")
    if thousands and len(whole) > 3:
        groups = []
        while len(whole) > 3:
            groups.insert(0, whole[-3:])
            whole = whole[:-3]
        groups.insert(0, whole)
        whole = "\u2009".join(groups)
    separator = "." if LANG == "en" else ","
    return whole + (separator + frac if frac else "")


def canvas(width_in, height_in, dark=False):
    fig = plt.figure(figsize=(width_in, height_in), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100.0 * height_in / width_in)
    ax.axis("off")
    if dark:
        fig.patch.set_facecolor(DARK)
    else:
        fig.patch.set_alpha(0.0)
    return fig, ax, 100.0 * height_in / width_in


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI, transparent=(fig.patch.get_alpha() == 0.0),
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  %-34s %d bytes" % (name, os.path.getsize(path)))
    return path


def card(ax, x, y, w, h, fc=PANEL, ec="none", lw=1.0, r=1.4, z=2, alpha=1.0):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=%f" % r,
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z, alpha=alpha,
        mutation_aspect=1.0))


def text(ax, x, y, s, size=11, color=INK, weight="normal", ha="left",
         va="center", z=5, spacing=1.35, family=None, rotation=0):
    return ax.text(x, y, s, fontsize=size, color=color, fontweight=weight,
                   ha=ha, va=va, zorder=z, linespacing=spacing,
                   family=family or SANS, rotation=rotation)


def arrow(ax, p0, p1, color="#C0C0C8", lw=1.5, z=4, scale=10):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="-|>", mutation_scale=scale, linewidth=lw,
        color=color, zorder=z, shrinkA=0, shrinkB=0))


def chip(ax, x, y, label, color, size=7.6, h=3.0, textcolor=WHITE):
    w = 3.0 + len(label) * size * 0.082
    card(ax, x, y - h / 2.0, w, h, fc=color, r=h / 2.0, z=6)
    text(ax, x + w / 2.0, y, label, size=size, color=textcolor,
         weight="bold", ha="center", z=7)
    return w


# ------------------------------------------------------------------ diagram 01
def dia_arquitectura():
    fig, ax, top = canvas(11.6, 6.5)
    text(ax, 0, top - 2.4,
         L("Un solo repositorio, dos intérpretes de Python",
           "One repository, two Python interpreters"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.4,
         L("El núcleo de cálculo es el único código que corre en los dos "
           "lados. Por eso no lleva f-strings ni anotaciones: tiene que "
           "compilar también en Python 2.7.",
           "The calculation core is the only code that runs on both sides. "
           "That is why it carries no f-strings and no annotations: it has to "
           "compile under Python 2.7 as well."),
         size=9.2, color=SOFT)

    band_y, band_h = 24.0, 21.5
    card(ax, 0, band_y, 46.5, band_h, fc=PANEL, r=1.8)
    chip(ax, 2.0, band_y + band_h - 3.4,
         L("PYTHON 3  ·  ESCRITORIO", "PYTHON 3  ·  DESKTOP"), DARK)
    for i, (name, desc) in enumerate([
            ("model_builder_gui.py", L("interfaz Tk, 6 pestañas, hilos",
                                       "Tk interface, 6 tabs, threads")),
            ("project_workspace.py", L("proyecto aislado, 7 carpetas",
                                       "isolated project, 7 folders")),
            ("abaqus_runner.py", L("lanza Abaqus sin shell, log",
                                   "spawns Abaqus with no shell, log")),
            ("report_generator.py", L("informe LaTeX/PDF/JSON",
                                      "LaTeX/PDF/JSON report")),
            ("fva600_postprocess.py", L("integra ΔV del CSV, v_crit",
                                        "integrates ΔV from CSV, v_crit")),
            ("fva600_matlab.py", L("contraste opcional en MATLAB",
                                   "optional MATLAB cross-check"))]):
        yy = band_y + band_h - 7.2 - i * 2.45
        text(ax, 2.2, yy, name, size=8.5, weight="bold")
        text(ax, 19.5, yy, desc, size=7.5, color=SOFT)

    card(ax, 53.5, band_y, 46.5, band_h, fc=PANEL, r=1.8)
    chip(ax, 55.5, band_y + band_h - 3.4,
         L("PYTHON 2.7  ·  KERNEL DE ABAQUS 2022",
           "PYTHON 2.7  ·  ABAQUS 2022 KERNEL"), AMBER)
    for i, (name, desc) in enumerate([
            ("build_parametric_model.py", L("geometría, malla, contacto, job",
                                            "geometry, mesh, contact, job")),
            ("fva600_method_a_backend.py", L("Método A, malla coincidente",
                                             "Method A, matching mesh")),
            ("fva600_d40_v3_nojob.py", L("regresión FVA 1 ciclo, NOJOB",
                                         "FVA 1-cycle regression, NOJOB")),
            ("fva600_odb_extract.py", L("abre el ODB, exporta apertura",
                                        "opens the ODB, exports opening"))]):
        yy = band_y + band_h - 7.2 - i * 2.45
        text(ax, 55.7, yy, name, size=8.5, weight="bold")
        text(ax, 77.5, yy, desc, size=7.5, color=SOFT)

    core_y, core_h = 8.0, 11.0
    card(ax, 13.0, core_y, 74.0, core_h, fc=DARK, r=1.8)
    text(ax, 50, core_y + core_h - 2.3,
         L("NÚCLEO COMPARTIDO  ·  compatible 2.7 y 3.x",
           "SHARED CORE  ·  2.7 and 3.x compatible"),
         size=7.8, color="#8E8E96", weight="bold", ha="center")
    text(ax, 31.5, core_y + 5.3, "keyjoint_core.py", size=11.5, color=WHITE,
         weight="bold", ha="center")
    text(ax, 31.5, core_y + 2.6,
         L("tabla DIN 6885 · derive() · validate()\n8 plantillas de malla",
           "DIN 6885 table · derive() · validate()\n8 mesh templates"),
         size=7.3, color="#8E8E96", ha="center", va="center")
    text(ax, 68.5, core_y + 5.3, "din6892_methods.py", size=11.5, color=WHITE,
         weight="bold", ha="center")
    text(ax, 68.5, core_y + 2.6,
         L("métodos A / B / B-FVA / C\nfactores, políticas, catálogos",
           "methods A / B / B-FVA / C\nfactors, policies, catalogues"),
         size=7.3, color="#8E8E96", ha="center", va="center")
    ax.add_line(Line2D([50, 50], [core_y + 1.4, core_y + 7.2], color="#3A3A42",
                       lw=1.0, zorder=6))

    arrow(ax, (23.0, band_y - 0.4), (29.0, core_y + core_h + 0.4), lw=1.4)
    arrow(ax, (77.0, band_y - 0.4), (71.0, core_y + core_h + 0.4), lw=1.4)
    arrow(ax, (46.9, band_y + band_h / 2.0), (53.1, band_y + band_h / 2.0),
          color=BLUE, lw=1.8, scale=13)
    text(ax, 50, band_y + band_h / 2.0 + 2.6, L("subproceso", "subprocess"),
         size=7.4, color=BLUE, ha="center", weight="bold")
    text(ax, 50, band_y + band_h / 2.0 - 2.8, "params.json", size=7.0,
         color=MUTED, ha="center")

    text(ax, 0, 3.0,
         L("Ningún módulo de Abaqus se importa en el lado de escritorio: la "
           "interfaz arranca sin Abaqus instalado y sólo lo necesita para "
           "construir el modelo.",
           "No Abaqus module is imported on the desktop side: the interface "
           "starts with no Abaqus installed and only needs it to build the "
           "model."),
         size=7.9, color=MUTED)
    return save(fig, "dia_arquitectura.png")


# ------------------------------------------------------------------ diagram 02
def dia_pipeline():
    fig, ax, top = canvas(12.4, 5.2)
    text(ax, 0, top - 2.3,
         L("De un clic a la evidencia archivada",
           "From one click to archived evidence"), size=15.5, weight="bold")

    stages = [
        ("1", L("Formulario", "Form"), L("lee las\n6 pestañas",
                                         "reads the\n6 tabs"), PANEL),
        ("2", L("Validación", "Validation"), L("un error\nbloquea",
                                               "one error\nblocks"), "#FFF4E5"),
        ("3", L("Proyecto", "Project"), L("7 carpetas\nproject.json",
                                          "7 folders\nproject.json"), PANEL),
        ("4", L("Subproceso", "Subprocess"), "abaqus cae\nnoGUI", "#E8F1FD"),
        ("5", L("Geometría", "Geometry"), L("eje · chaveta\ncubo",
                                            "shaft · key\nhub"), PANEL),
        ("6", L("Malla", "Mesh"), L("por pieza,\nN candidatos",
                                    "per part,\nN candidates"), PANEL),
        ("7", L("Análisis", "Analysis"), L("contacto\ntorsión",
                                           "contact\ntorsion"), "#E8F1FD"),
        ("8", L("Auditoría", "Audit"), L("AUDIT .txt\ny .json",
                                         "AUDIT .txt\nand .json"), PANEL),
        ("9", L("Evidencia", "Evidence"), L("capturas\nCAE · JSON",
                                            "screenshots\nCAE · JSON"), PANEL),
        ("10", L("Informe", "Report"), "tex · pdf\nreport_data", "#E9F7EF"),
    ]
    n, gap = len(stages), 1.1
    w = (100.0 - gap * (n - 1)) / n
    y, h = top - 21.0, 14.0
    for i, (num, title, body, fc) in enumerate(stages):
        x = i * (w + gap)
        card(ax, x, y, w, h, fc=fc, r=1.3)
        text(ax, x + 1.0, y + h - 2.4, num, size=8.2, color=BLUE, weight="bold")
        text(ax, x + 1.0, y + h - 6.0, title, size=8.8, weight="bold")
        text(ax, x + 1.0, y + 3.6, body, size=6.6, color=SOFT, va="center",
             spacing=1.5)
        if i < n - 1:
            arrow(ax, (x + w + 0.05, y + h / 2.0),
                  (x + w + gap - 0.05, y + h / 2.0), lw=1.1, scale=7)

    split = 3 * (w + gap) - gap / 2.0
    end9 = 9 * (w + gap) - gap / 2.0
    bands = [(0, split, DARK, "Python 3  ·  ModelBuilder.exe"),
             (split + 0.6, end9, AMBER,
              L("Python 2.7  ·  kernel de Abaqus 2022",
                "Python 2.7  ·  Abaqus 2022 kernel")),
             (end9 + 0.6, 100.0, GREEN, "Python 3")]
    for x0, x1, color, label in bands:
        card(ax, x0, y - 5.2, x1 - x0, 3.4, fc=color, r=1.0)
        text(ax, (x0 + x1) / 2.0, y - 3.5, label, size=7.4, color=WHITE,
             ha="center", weight="bold")

    text(ax, 0, y - 10.4, L("Dos puertas duras", "Two hard gates"), size=9.6,
         weight="bold")
    text(ax, 0, y - 14.0,
         L("Ningún error de validación llega a Abaqus.  ·  Ningún proyecto se "
           "declara correcto si falta un artefacto, si el quality gate de "
           "malla no pasa o si la malla realizada no es la planificada.",
           "No validation error ever reaches Abaqus.  ·  No project is "
           "declared sound if an artifact is missing, if the mesh quality gate "
           "fails, or if the realised mesh is not the planned one."),
         size=8.2, color=SOFT)
    text(ax, 0, y - 18.2,
         L("El solver sólo se ejecuta si el usuario lo pide "
           "(analysis.submit). Por defecto se construye, se audita y se "
           "documenta, sin resolver.",
           "The solver only runs when the user asks for it "
           "(analysis.submit). By default the model is built, audited and "
           "documented, not solved."),
         size=7.8, color=MUTED)
    return save(fig, "dia_pipeline.png")


# ------------------------------------------------------------------ diagram 03
def dia_workspace():
    fig, ax, top = canvas(11.6, 7.1)
    text(ax, 0, top - 2.3,
         L("Cada ejecución vive en su propio proyecto",
           "Every run lives in its own project"), size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         L("ProjectWorkspace crea <nombre>_AAAAMMDD_HHMMSS y pasa rutas "
           "absolutas al kernel. Abaqus corre con cwd = jobs/, así que ningún "
           "archivo de solver cae junto al ejecutable.",
           "ProjectWorkspace creates <name>_YYYYmmdd_HHMMSS and hands absolute "
           "paths to the kernel. Abaqus runs with cwd = jobs/, so no solver "
           "file ever lands next to the executable."),
         size=9.0, color=SOFT)

    rows = [
        ("input/", "params.json · technical_contract.json",
         L("lo que se pidió, congelado", "what was asked for, frozen"),
         "#0D47A1"),
        ("generated/",
         "PARAM_BUILD_AUDIT.txt/.json · BUILD_RESULT.json · mesh_study.csv",
         L("lo que el motor hizo de verdad", "what the engine actually did"),
         GREEN),
        ("model/", L("<modelo>.cae", "<model>.cae"),
         L("la base de datos de Abaqus", "the Abaqus database"), "#0B5394"),
        ("jobs/", "<job>.odb · .inp · .msg · .sta",
         L("todo el ruido del solver, contenido",
           "all the solver noise, contained"), "#4B5563"),
        ("screenshots/", "_preview.png · _preview_Front/Right · _notch_mesh.png",
         L("evidencia visual reproducible", "reproducible visual evidence"),
         "#4A148C"),
        ("reports/", "report.tex · report.pdf · report_data.json · latex_build.log",
         L("el entregable para revisión", "the deliverable for review"), GREEN),
        ("logs/", "abaqus.log",
         L("comando, cwd y salida íntegra", "command, cwd and full output"),
         "#4B5563"),
    ]
    y, h = top - 10.5, 5.6
    for name, files, why, color in rows:
        y -= h + 0.85
        card(ax, 0, y, 100, h, fc=PANEL, r=1.1)
        card(ax, 0, y, 0.85, h, fc=color, r=0.42)
        text(ax, 2.8, y + h * 0.64, name, size=9.8, weight="bold")
        text(ax, 2.8, y + h * 0.24, why, size=7.1, color=MUTED)
        text(ax, 27.0, y + h / 2.0, files, size=8.0, color=SOFT, family=MONO)

    text(ax, 0, 2.6,
         L("project.json registra esquema, autor, idioma, estado, el comando "
           "ejecutado y cada artefacto con su tamaño y su etiqueta de "
           "evidencia.",
           "project.json records the schema, author, language, status, the "
           "command that ran and every artifact with its size and evidence "
           "badge."),
         size=7.9, color=MUTED)
    return save(fig, "dia_workspace.png")


# ------------------------------------------------------------------ diagram 04
def dia_badges():
    fig, ax, top = canvas(11.6, 6.4)
    text(ax, 0, top - 2.3,
         L("Ningún número viaja sin su procedencia",
           "No number travels without its provenance"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         L("Cada valor del informe lleva una etiqueta. Una propuesta de "
           "investigación no puede presentarse como requisito normativo "
           "vigente.",
           "Every value in the report carries a badge. A research proposal can "
           "never be presented as a current normative requirement."),
         size=9.0, color=SOFT)

    items = [
        ("NORMATIVE", L("Transcrito de la norma", "Transcribed from the standard"),
         L("tabla DIN 6885-1:2021-11", "DIN 6885-1:2021-11 table")),
        ("DIN-METHOD", L("Método de la norma", "Method of the standard"),
         L("DIN 6892 Métodos B y C", "DIN 6892 Methods B and C")),
        ("FVA-RESEARCH", L("Propuesta de investigación", "Research proposal"),
         L("FVA 600 III / informe 1686", "FVA 600 III / report 1686")),
        ("CORE-SCREENING", L("Cribado interno", "Internal screening"),
         L("presión uniforme, plausibilidad", "uniform pressure, plausibility")),
        ("LITERATURE", L("Comparación publicada", "Published comparison"),
         L("K_ts, K_vm de literatura", "K_ts, K_vm from literature")),
        ("USER-INPUT", L("Dato del usuario", "User-supplied datum"),
         L("requiere verificación externa", "needs external verification")),
        ("USER-OVERRIDE", L("El usuario salió del sobre",
                            "The user left the envelope"), "compliance_mode"),
        ("NOT-IMPLEMENTED", L("Declarado no implementado",
                              "Declared not implemented"),
         L("DIN 6888, formas C–J", "DIN 6888, forms C–J")),
    ]
    colw, rowh = 48.5, 8.4
    y0 = top - 11.5
    for idx, (label, title, note) in enumerate(items):
        col, row = idx % 2, idx // 2
        x = col * (colw + 3.0)
        y = y0 - row * (rowh + 1.3) - rowh
        card(ax, x, y, colw, rowh, fc=PANEL, r=1.2)
        chip(ax, x + 1.6, y + rowh - 2.8, label, BADGE[label], size=7.2)
        text(ax, x + 1.9, y + 2.7, title, size=9.0, weight="bold")
        text(ax, x + 1.9, y + 0.8, note, size=7.1, color=MUTED)
    return save(fig, "dia_badges.png")


# ------------------------------------------------------------------ diagram 05
def dia_metodos():
    d = core.derive(core.default_params())
    torques = d["din6892"]["companions"]["consistency"]["torques_Nm"]

    fig, ax, top = canvas(11.8, 6.6)
    text(ax, 0, top - 2.3,
         L("Cuatro métodos, una sola jerarquía de evidencia",
           "Four methods, one hierarchy of evidence"), size=15.5, weight="bold")

    cols = [
        ("C_PRELIMINARY", L("Dimensionado previo", "Preliminary sizing"),
         "DIN-METHOD",
         [L("presión admisible constante", "constant allowable pressure"),
          L("resuelve el problema inverso:\nlongitud portante necesaria",
            "solves the inverse problem:\nrequired bearing length")],
         es(torques["C_PRELIMINARY"]) + " N·m"),
        ("B_DIN_CURRENT", L("Método B vigente", "Current Method B"),
         "DIN-METHOD",
         [L("presión equivalente, ec. 1–12", "equivalent pressure, eq. 1–12"),
          L("factores f_S f_H f_W K_λ K_R K_V",
            "factors f_S f_H f_W K_λ K_R K_V"),
          L("eje, cubo y chaveta,\ncada uno en su flanco",
            "shaft, hub and key,\neach on its own flank")],
         es(torques["B_DIN_CURRENT"]) + " N·m"),
        ("B_FVA_2025", L("Reformulación FVA", "FVA reformulation"),
         "FVA-RESEARCH",
         [L("ecuación 36 del informe 1686", "equation 36 of report 1686"),
          "f_Sv, f_WS, f_S,ltr, K_d",
          L("diagnóstico, nunca\ncriterio de aceptación",
            "diagnostic, never\nan acceptance criterion")],
         es(torques["B_FVA_2025"]) + " N·m"),
        ("A_FE_VOLUME", L("Verificación por MEF", "FE verification"),
         "FVA-RESEARCH",
         [L("volumen relativo de apertura", "relative opening volume"),
          L("exige resultado externo\nresuelto y descargado",
            "needs an external result,\nsolved and unloaded"),
          L("mínimo 10 ciclos de carga", "at least 10 load cycles")],
         L("requiere ODB", "needs an ODB")),
    ]
    w = 23.6
    gap = (100.0 - 4 * w) / 3.0
    y, h = top - 38.0, 30.0
    for i, (mid, title, badge, bullets, value) in enumerate(cols):
        x = i * (w + gap)
        card(ax, x, y, w, h, fc=PANEL, r=1.5)
        chip(ax, x + 1.4, y + h - 2.9, badge, BADGE[badge], size=6.9)
        text(ax, x + 1.6, y + h - 7.2, title, size=10.4, weight="bold")
        text(ax, x + 1.6, y + h - 9.8, mid, size=7.0, color=MUTED, family=MONO)
        yy = y + h - 12.6
        for bullet in bullets:
            ax.add_patch(Circle((x + 2.1, yy - 0.15), 0.26, color="#B0B0B8",
                                zorder=6))
            text(ax, x + 3.2, yy, bullet, size=7.2, color=SOFT, va="top",
                 spacing=1.5)
            yy -= 3.0 + 2.6 * bullet.count("\n")
        card(ax, x, y, w, 5.4, fc=PANEL2, r=1.5)
        text(ax, x + 1.6, y + 2.7, value, size=11.0, weight="bold",
             color=AMBER if badge == "FVA-RESEARCH" else INK)

    text(ax, 0, y - 5.0,
         L("Los tres métodos analíticos se calculan siempre en paralelo y se "
           "comparan entre sí: si el Método C resultara menos conservador que "
           "el B, el modelo levanta din6892_method_c_not_conservative.",
           "The three analytical methods are always evaluated in parallel and "
           "compared: if Method C came out less conservative than B, the model "
           "raises din6892_method_c_not_conservative."),
         size=8.4, color=INK)
    text(ax, 0, y - 9.2,
         L("Valores del par por defecto D40, C45+N, chaveta forma A 12 × 8 × "
           "50, par pulsante. El resultado que gobierna es el del cubo.",
           "Values for the bundled D40 default, C45+N, form A key 12 × 8 × 50, "
           "pulsating torque. The governing result is the hub's."),
         size=7.8, color=MUTED)
    return save(fig, "dia_metodos.png")


# -------------------------------------------------------------------- chart 06
def _method_b_inputs():
    d = core.derive(core.default_params())
    calc = d["din6892"]["calculation"]
    inputs = dict(d["din6892"]["derived"]["calculation_inputs"])
    inputs.pop("N_W", None)
    inputs.setdefault("f_S", calc["f_S"])
    inputs.setdefault("f_H", calc["f_H"])
    return inputs


def chart_pares():
    d = core.derive(core.default_params())
    torques = d["din6892"]["companions"]["consistency"]["torques_Nm"]
    alternating = din.method_b_current(
        dict(_method_b_inputs(), N_W=1.0e4))["torque_allowable_Nm"]

    fig = plt.figure(figsize=(11.6, 5.2), dpi=DPI)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0.062, 0.155, 0.905, 0.585])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.tick_params(axis="both", length=0, labelsize=9.5, colors=SOFT)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=LINE, lw=0.7, alpha=0.7)

    labels = [
        L("Método C\ndimensionado previo", "Method C\npreliminary sizing"),
        L("Método B\nvigente · por defecto", "Method B\ncurrent · default"),
        L("Método B\npar alternante", "Method B\nalternating torque"),
        L("Método B FVA 2025\ninvestigación", "Method B FVA 2025\nresearch"),
    ]
    values = [torques["C_PRELIMINARY"], torques["B_DIN_CURRENT"], alternating,
              torques["B_FVA_2025"]]
    colors = ["#A0A0A8", BLUE, "#5AA9F0", "#C98A3C"]
    for rect, value in zip(ax.bar(labels, values, width=0.5, color=colors,
                                  zorder=3), values):
        ax.text(rect.get_x() + rect.get_width() / 2.0, value + 40, es(value),
                ha="center", va="bottom", fontsize=13, fontweight="bold",
                color=INK, family=SANS)
    ax.set_ylim(0, max(values) * 1.20)
    ax.set_ylabel(L("par admisible  M_t,zul   [N·m]",
                    "allowable torque  M_t,zul   [N·m]"),
                  fontsize=9.5, color=SOFT)
    ax.set_yticks([0, 500, 1000, 1500, 2000, 2500])

    ax.axhline(1302.05, color=RED, lw=1.3, ls=(0, (5, 3)), zorder=4)
    ax.text(-0.42, 1302.05 + 45,
            L("1 302,05  ·  antes de ambas correcciones",
              "1,302.05  ·  before both corrections"),
            fontsize=8.8, color=RED, ha="left", va="bottom", fontweight="bold",
            family=SANS)

    fig.text(0.062, 0.935,
             L("La misma unión, cuatro respuestas distintas",
               "The same joint, four different answers"),
             fontsize=15.5, fontweight="bold", color=INK, family=SANS)
    fig.text(0.062, 0.862,
             L("Valores calculados en vivo por din6892_methods para el D40 por "
               "defecto. El Método B vigente es la referencia; el resto es "
               "contraste.",
               "Values computed live by din6892_methods for the bundled D40 "
               "default. Current Method B is the reference; the rest is "
               "cross-check."),
             fontsize=9.0, color=SOFT, family=SANS)
    fig.text(0.062, 0.035,
             L("El límite lo pone el cubo, no el eje: con t2tr = 3,141 mm "
               "frente a t1tr = 5,141 mm, el flanco del cubo agota antes su "
               "capacidad.",
               "The hub sets the limit, not the shaft: with t2tr = 3.141 mm "
               "against t1tr = 5.141 mm, the hub flank runs out of capacity "
               "first."),
             fontsize=8.2, color=MUTED, family=SANS)
    return save(fig, "chart_pares.png")


# -------------------------------------------------------------------- chart 07
def chart_fw():
    xs = [10.0 ** (e / 10.0) for e in range(0, 61)]
    ys = [din.load_reversal_factor(x)["f_W"] for x in xs]

    fig = plt.figure(figsize=(11.6, 5.2), dpi=DPI)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0.075, 0.17, 0.885, 0.565])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
    ax.tick_params(labelsize=9.5, colors=SOFT, length=3, color=LINE)
    ax.grid(color=LINE, lw=0.7, alpha=0.65)
    ax.set_axisbelow(True)

    ax.semilogx(xs, ys, color=BLUE, lw=2.4, zorder=4)
    ax.set_xlim(1, 1e6)
    ax.set_ylim(0.45, 1.07)
    ax.set_xlabel(L("N_W   ·   inversiones del sentido de carga",
                    "N_W   ·   load direction reversals"),
                  fontsize=9.5, color=SOFT)
    ax.set_ylabel("f_W", fontsize=10.5, color=SOFT)

    ax.plot([1], [1.0], "o", ms=9, color=GREEN, zorder=6)
    ax.annotate(L("par pulsante  ·  R ≥ 0\nN_W = 0   f_W = 1,000\n999,18 N·m",
                  "pulsating torque  ·  R ≥ 0\nN_W = 0   f_W = 1.000\n"
                  "999.18 N·m"),
                xy=(1.06, 1.0), xytext=(2.3, 0.885), fontsize=9.0, color=INK,
                family=SANS, linespacing=1.6,
                arrowprops=dict(arrowstyle="-", color=GREEN, lw=1.1))
    f_alt = din.load_reversal_factor(1.0e4)["f_W"]
    ax.plot([1e4], [f_alt], "o", ms=9, color=RED, zorder=6)
    ax.annotate(L("par totalmente alternante\nN_W = 10 000   f_W = 0,796\n"
                  "795,56 N·m",
                  "fully alternating torque\nN_W = 10,000   f_W = 0.796\n"
                  "795.56 N·m"),
                xy=(1.15e4, f_alt), xytext=(3.4e4, 0.86), fontsize=9.0,
                color=INK, family=SANS, linespacing=1.6,
                arrowprops=dict(arrowstyle="-", color=RED, lw=1.1))

    fig.text(0.075, 0.935,
             L("La ecuación 3 cuenta inversiones de flanco, no ciclos",
               "Equation 3 counts flank reversals, not cycles"),
             fontsize=15.5, fontweight="bold", color=INK, family=SANS)
    fig.text(0.075, 0.862,
             L("Un par que sólo pulsa nunca cambia de flanco: no hay daño "
               "extra que penalizar. El código alimentaba 10 000 ciclos y "
               "descontaba un 20 % de capacidad inexistente.",
               "A purely pulsating torque never changes flank: there is no "
               "extra damage to penalise. The code was feeding 10,000 cycles "
               "and discounting 20 % of capacity that cannot be lost."),
             fontsize=9.0, color=SOFT, family=SANS)
    fig.text(0.075, 0.038,
             L("N_W es ahora explícito. Si se deja vacío se deduce de la razón "
               "de carga R, y la deducción se reporta como "
               "din6892_load_reversal_derived.",
               "N_W is now explicit. Left blank, it is derived from the load "
               "ratio R and the derivation is reported as "
               "din6892_load_reversal_derived."),
             fontsize=8.2, color=MUTED, family=SANS)
    return save(fig, "chart_fw.png")


# ------------------------------------------------------- shared keyway section
def _keyway_section(ax, cx, cy, mm, d_w=40.0, b=12.0, h=8.0, t1=5.0, t2=3.3,
                    s1=0.8, show_chord=True, label_size=8.4):
    """Draw a to-scale keyway cross-section around the shaft/hub interface.

    cx, cy is the point on the interface arc at the keyway centre; mm is the
    scale factor from millimetres to diagram units. The arc really is the
    d_w circle, so the chord correction drawn here is the true sagitta.
    """
    radius = d_w / 2.0
    half_view = 11.0
    xs = [x * 0.05 for x in range(int(-half_view / 0.05), int(half_view / 0.05) + 1)]

    def arc_y(x):
        return math.sqrt(max(radius ** 2 - x ** 2, 0.0)) - radius

    hub_top = 7.2
    hub = [(cx + x * mm, cy + arc_y(x) * mm) for x in xs]
    hub += [(cx + half_view * mm, cy + hub_top * mm),
            (cx - half_view * mm, cy + hub_top * mm)]
    ax.add_patch(Polygon(hub, closed=True, facecolor="#DCDCE3",
                         edgecolor="#A8A8B2", lw=1.0, zorder=2))
    shaft_bottom = -7.6
    shaft = [(cx + x * mm, cy + arc_y(x) * mm) for x in xs]
    shaft += [(cx + half_view * mm, cy + shaft_bottom * mm),
              (cx - half_view * mm, cy + shaft_bottom * mm)]
    ax.add_patch(Polygon(shaft, closed=True, facecolor="#C2DCF7",
                         edgecolor="#6E9CCB", lw=1.2, zorder=3))

    ax.add_patch(Rectangle((cx - b / 2.0 * mm, cy - t1 * mm), b * mm,
                           (t1 + t2) * mm, facecolor=WHITE, edgecolor="none",
                           zorder=4))
    ax.add_patch(Rectangle((cx - b / 2.0 * mm, cy - t1 * mm), b * mm,
                           (t1 + t2) * mm, facecolor="none",
                           edgecolor="#9AA0A6", lw=0.9, zorder=6))
    ax.add_patch(Rectangle((cx - b / 2.0 * mm, cy - t1 * mm), b * mm, h * mm,
                           facecolor=BLUE, edgecolor="#0059B3", lw=1.0,
                           zorder=5))
    text(ax, cx, cy + (-t1 + h / 2.0) * mm, L("chaveta", "key"),
         size=label_size - 0.8, color=WHITE, ha="center", weight="bold", z=7)
    text(ax, cx, cy + shaft_bottom * mm * 0.86, L("eje", "shaft"),
         size=label_size, color="#28527A", ha="center", z=7)
    text(ax, cx + 7.6 * mm, cy + hub_top * mm * 0.66, L("cubo", "hub"),
         size=label_size, color=SOFT, ha="center", z=7)

    xr = cx + b / 2.0 * mm + 2.9
    ax.add_line(Line2D([xr, xr], [cy - t1 * mm, cy], color=RED, lw=1.8, zorder=8))
    ax.add_line(Line2D([xr - 0.7, xr + 0.7], [cy, cy], color=RED, lw=1.2, zorder=8))
    ax.add_line(Line2D([xr - 0.7, xr + 0.7], [cy - t1 * mm, cy - t1 * mm],
                       color=RED, lw=1.2, zorder=8))
    text(ax, xr + 1.4, cy - t1 * mm / 2.0, "t1 = %s mm" % es(t1, 1),
         size=label_size, color=RED, weight="bold", z=8)

    xl = cx - b / 2.0 * mm - 2.9
    ax.add_line(Line2D([xl, xl], [cy, cy + t2 * mm], color=GREEN, lw=1.8, zorder=8))
    ax.add_line(Line2D([xl - 0.7, xl + 0.7], [cy, cy], color=GREEN, lw=1.2, zorder=8))
    ax.add_line(Line2D([xl - 0.7, xl + 0.7], [cy + t2 * mm, cy + t2 * mm],
                       color=GREEN, lw=1.2, zorder=8))
    text(ax, xl - 1.4, cy + t2 * mm / 2.0, "t2 = %s mm" % es(t2, 1),
         size=label_size, color=GREEN, weight="bold", ha="right", z=8)

    chord = None
    if show_chord:
        x_edge = b / 2.0 + s1
        y_edge = arc_y(x_edge)
        chord = abs(y_edge)
        ax.add_line(Line2D([cx - x_edge * mm, cx + x_edge * mm], [cy, cy],
                           color=AMBER, lw=0.9, ls=(0, (3, 2)), zorder=8))
        for sign in (-1.0, 1.0):
            ax.add_line(Line2D([cx + sign * x_edge * mm, cx + sign * x_edge * mm],
                               [cy + y_edge * mm, cy], color=AMBER, lw=1.7,
                               zorder=8))
        ax.add_patch(Circle((cx + x_edge * mm, cy + y_edge * mm), 0.28,
                            color=AMBER, zorder=9))
        ax.add_patch(Circle((cx - x_edge * mm, cy + y_edge * mm), 0.28,
                            color=AMBER, zorder=9))
    return chord


# ------------------------------------------------------------------ diagram 08
def dia_t2tr():
    d = core.derive(core.default_params())
    eff = d["din6892"]["derived"]["effective_bearing_depth"]
    hub = d["din6892"]["derived"]["hub_effective_bearing_depth"]

    fig, ax, top = canvas(11.8, 6.6)
    text(ax, 0, top - 2.4,
         L("El cubo se comprobaba sobre el flanco del eje",
           "The hub was being checked on the shaft's flank"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.4,
         L("DIN 6892 evalúa la presión del eje sobre l_tr · t1tr y la del cubo "
           "sobre l_tr · t2tr. Todas las piezas compartían t1tr.",
           "DIN 6892 evaluates the shaft pressure over l_tr · t1tr and the hub "
           "pressure over l_tr · t2tr. Every component was sharing t1tr."),
         size=9.0, color=SOFT)

    _keyway_section(ax, cx=22.0, cy=30.0, mm=1.25, show_chord=False)
    text(ax, 22.0, 14.5,
         L("sección real a escala  ·  d1 = 40 mm, b × h = 12 × 8",
           "true cross-section, to scale  ·  d1 = 40 mm, b × h = 12 × 8"),
         size=7.6, color=MUTED, ha="center")
    text(ax, 22.0, 11.0,
         L("DIN 6885-1 da t2 < t1 en las 26 filas de la tabla",
           "DIN 6885-1 gives t2 < t1 in all 26 rows of the table"),
         size=7.6, color=MUTED, ha="center")

    x0, w = 47.0, 51.0
    rows = [
        (L("t1tr  ·  flanco del eje", "t1tr  ·  shaft flank"),
         es(eff["t1tr_mm"], 3) + " mm", RED,
         L("superficie convexa", "convex surface")),
        (L("t2tr  ·  flanco del cubo", "t2tr  ·  hub flank"),
         es(hub["t2tr_mm"], 3) + " mm", GREEN,
         L("superficie cóncava, menos la holgura g_c",
           "concave surface, less the g_c clearance")),
        (L("área acreditada al cubo antes", "area credited to the hub before"),
         "+" + es((eff["t1tr_mm"] / hub["t2tr_mm"] - 1.0) * 100.0, 1) + " %",
         AMBER, "t1tr / t2tr = " + es(eff["t1tr_mm"] / hub["t2tr_mm"], 3)),
    ]
    y = top - 11.0
    for label, value, color, note in rows:
        y -= 8.2
        card(ax, x0, y, w, 7.2, fc=PANEL, r=1.2)
        card(ax, x0, y, 0.85, 7.2, fc=color, r=0.42)
        text(ax, x0 + 2.6, y + 4.8, label, size=9.2, weight="bold")
        text(ax, x0 + 2.6, y + 1.9, note, size=7.1, color=MUTED)
        text(ax, x0 + w - 2.2, y + 3.6, value, size=11.8, weight="bold",
             color=color, ha="right")

    text(ax, x0, y - 4.2,
         L("La chaveta recibe min(t1tr, t2tr): su flanco soporta la misma\n"
           "presión que el flanco del chavetero que lo acompaña.",
           "The key gets min(t1tr, t2tr): its flank carries the same\n"
           "pressure as the mating keyway flank."),
         size=8.2, color=SOFT, va="top", spacing=1.5)
    card(ax, x0, y - 16.9, w, 7.0, fc="#E9F7EF", r=1.2)
    text(ax, x0 + 2.6, y - 13.4,
         L("Efecto neto de ambas correcciones:  1 302,05  →  999,18 N·m",
           "net effect of both corrections:  1,302.05  →  999.18 N·m"),
         size=10.0, weight="bold", color=GREEN)
    return save(fig, "dia_t2tr.png")


# ------------------------------------------------------------------ diagram 09
def dia_eq9():
    d = core.derive(core.default_params())
    eff = d["din6892"]["derived"]["effective_bearing_depth"]

    fig, ax, top = canvas(11.8, 7.0)
    text(ax, 0, top - 2.4,
         L("La pregunta abierta: el signo de la ecuación 9",
           "The open question: the sign of equation 9"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.4,
         L("Tal como está transcrita, la ecuación 9 SUMA la corrección de "
           "cuerda y devuelve t1tr = 5,141 mm: más que la propia altura del "
           "flanco, t1 = 5,0 mm.",
           "As transcribed, equation 9 ADDS the chord correction and returns "
           "t1tr = 5.141 mm: more than the flank height itself, t1 = 5.0 mm."),
         size=9.0, color=SOFT)

    chord = _keyway_section(ax, cx=22.0, cy=32.0, mm=1.25, show_chord=True)
    text(ax, 22.0, 16.5,
         L("corrección de cuerda  =  ½ (d1 − √(d1² − (b+2s1)²))  =  %s mm",
           "chord correction  =  ½ (d1 − √(d1² − (b+2s1)²))  =  %s mm")
         % es(chord, 3), size=8.0, color=AMBER, ha="center", weight="bold")
    text(ax, 22.0, 12.8,
         L("marcada en ámbar: la sagita real del arco a (b + 2s1)/2 = 6,8 mm",
           "marked in amber: the true sagitta of the arc at "
           "(b + 2s1)/2 = 6.8 mm"),
         size=7.6, color=MUTED, ha="center")

    x0, w = 47.0, 51.0
    y = top - 11.0
    options = [
        ("EQUATION_9", es(eff["t1tr_equation9_mm"], 3) + " mm",
         L("la transcripción literal  ·  valor por defecto",
           "the literal transcription  ·  default"), "#0B5394"),
        ("GEOMETRIC", es(eff["t1tr_geometric_mm"], 3) + " mm",
         L("lo que exige el flanco convexo del eje",
           "what the convex shaft flank requires"), GREEN),
        ("CONSERVATIVE", es(eff["t1tr_conservative_mm"], 3) + " mm",
         L("el menor de los dos, para diseño",
           "the smaller of the two, for design"), "#4B5563"),
    ]
    for name, value, note, color in options:
        y -= 8.2
        card(ax, x0, y, w, 7.2, fc=PANEL, r=1.2)
        card(ax, x0, y, 0.85, 7.2, fc=color, r=0.42)
        text(ax, x0 + 2.6, y + 4.8, name, size=9.0, weight="bold", family=MONO)
        text(ax, x0 + 2.6, y + 1.9, note, size=7.1, color=MUTED)
        text(ax, x0 + w - 2.2, y + 3.6, value, size=11.8, weight="bold",
             color=color, ha="right")

    card(ax, x0, y - 12.4, w, 10.8, fc="#FDF3E7", r=1.2)
    text(ax, x0 + 2.6, y - 4.6,
         L("%s %% de diferencia en todo par de los Métodos B y C",
           "%s %% spread on every Method B and C torque")
         % es(eff["relative_difference_percent"], 1),
         size=9.6, weight="bold", color=AMBER)
    text(ax, x0 + 2.6, y - 7.8,
         L("No lo he decidido por mi cuenta. Se reportan los dos valores, la\n"
           "diferencia y una bandera; la política la elige el usuario y la\n"
           "discrepancia se avisa como din6892_bearing_depth_optimistic.",
           "I did not overrule it. Both values, the difference and a flag are\n"
           "reported; the policy is the user's choice and the disagreement is\n"
           "raised as din6892_bearing_depth_optimistic."),
         size=7.8, color=SOFT, va="top", spacing=1.55)
    text(ax, 0.0, 7.4,
         L("La misma forma algebraica con signo positivo sí es correcta para "
           "el taladro cóncavo del cubo:\nel signo del eje parece un problema "
           "de transcripción o de datum, no de física.",
           "The same algebraic form with a plus sign is geometrically correct "
           "for the concave hub bore:\nthe shaft sign looks like a "
           "transcription or datum issue, not physics."),
         size=7.9, color=MUTED, va="top", spacing=1.55)
    return save(fig, "dia_eq9.png")


# ------------------------------------------------------------------ diagram 10
def dia_malla():
    catalog = core.mesh_template_catalog()
    default_template = core.default_params()["mesh"]["template"]

    fig, ax, top = canvas(11.8, 7.0)
    text(ax, 0, top - 2.3,
         L("Ocho políticas de malla, ninguna elegida a ciegas",
           "Eight mesh policies, none chosen blindly"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         L("AUTO compara candidatos completos por pieza y conserva el intento "
           "ganador. El score global es el peor de las piezas, nunca la media.",
           "AUTO compares complete candidates per part and keeps the winning "
           "attempt. The global score is the worst part, never the average."),
         size=9.0, color=SOFT)

    headers = [L("plantilla", "template"), L("topología", "topology"),
               L("orden", "order"), L("intentos", "attempts"),
               L("score", "score"), L("% hex", "% hex"),
               L("AR máx", "max AR"), L("presupuesto duro", "hard budget")]
    xs = [1.2, 27.5, 43.5, 55.0, 64.5, 72.5, 81.0, 89.0]
    y = top - 11.6
    for hx, htext in zip(xs, headers):
        text(ax, hx, y, htext.upper(), size=6.6, color=MUTED, weight="bold")
    y -= 1.5
    ax.add_line(Line2D([0, 100], [y, y], color=LINE, lw=0.9))

    rowh = 4.05
    for name in core.mesh_template_names():
        tpl = catalog[name]
        targets, budgets = tpl.get("targets", {}), tpl.get("budgets", {})
        y -= rowh
        is_default = name == default_template
        if is_default:
            card(ax, 0, y - 0.35, 100, rowh, fc="#E8F1FD", r=0.9, z=1)
        values = [
            name,
            tpl.get("topology_requirement", "-").replace("_", " ").lower(),
            tpl.get("element_order", "inherit"),
            str(tpl.get("max_attempts", "-")),
            "%g" % targets.get("pass_score", 0),
            "%g %%" % targets.get("min_hex_pct", 0),
            es(targets.get("max_bulk_ar", 0), 0),
            format(budgets.get("hard_elements", 0), ",d").replace(
                ",", "\u2009" if LANG != "en" else ","),
        ]
        for idx, (vx, value) in enumerate(zip(xs, values)):
            text(ax, vx, y + rowh / 2.0 - 0.35, value,
                 size=7.9 if idx == 0 else 7.5,
                 weight="bold" if idx == 0 else "normal",
                 color=INK if idx == 0 else SOFT)
        if is_default:
            text(ax, 21.0, y + rowh / 2.0 - 0.35, L("por defecto", "default"),
                 size=6.3, color=BLUE, weight="bold")

    y -= 4.6
    text(ax, 0, y,
         L("HEX_CERTIFIED exige 100 % de hexaedros, cero reparaciones y cero "
           "advertencias: si no lo consigue, el build falla en lugar de "
           "degradar a tetraedros en silencio.",
           "HEX_CERTIFIED demands 100 % hexahedra, zero repairs and zero "
           "warnings: if it cannot get there the build fails instead of "
           "quietly degrading to tetrahedra."),
         size=8.4, color=INK)
    text(ax, 0, y - 4.0,
         L("La documentación heredada habla de seis plantillas; desde 4.2 el "
           "código define ocho (keyjoint_core.MESH_TEMPLATES).",
           "The inherited documentation says six templates; since 4.2 the code "
           "defines eight (keyjoint_core.MESH_TEMPLATES)."),
         size=7.8, color=AMBER)
    return save(fig, "dia_malla.png")


# ------------------------------------------------------------------ diagram 11
def dia_release():
    fig, ax, top = canvas(11.6, 5.4)
    text(ax, 0, top - 2.3,
         L("El ejecutable se publica, no se copia",
           "The executable is published, not copied"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         L("make_exe.bat construye en un entorno aislado y sólo publica si la "
           "huella del código, el autotest empaquetado y la lista blanca "
           "coinciden.",
           "make_exe.bat builds in an isolated environment and only publishes "
           "if the source fingerprint, the packaged self-test and the "
           "whitelist all agree."),
         size=9.0, color=SOFT)

    steps = [
        ("1", L("Entorno limpio", "Clean environment"),
         L("venv nuevo; user-site,\nPYTHONPATH y rutas\nde red anulados",
           "fresh venv; user-site,\nPYTHONPATH and network\npaths disabled")),
        ("2", L("Herramientas fijadas", "Pinned tools"),
         L("PyInstaller 6.22.2\nhooks 2026.7\nsólo binarios",
           "PyInstaller 6.22.2\nhooks 2026.7\nbinary wheels only")),
        ("3", L("Aislamiento", "Isolation"),
         L("verifica sys.path\ny versiones; compila\nlos 14 módulos",
           "checks sys.path and\nversions; compiles\nall 14 modules")),
        ("4", L("Huella previa", "Pre-build fingerprint"),
         L("SHA-256 de 31\nentradas + candado\nde la release 4.1",
           "SHA-256 of 31 inputs\n+ lock on the\nprotected 4.1 release")),
        ("5", L("Empaquetado", "Packaging"),
         L("un .exe con motor,\ncatálogos e i18n\ndentro",
           "one .exe with engine,\ncatalogues and i18n\ninside")),
        ("6", L("Publicación", "Publication"),
         L("autotest en el .exe,\nlista blanca, ZIP\ny SHA256SUMS",
           "self-test on the .exe,\nwhitelist, ZIP\nand SHA256SUMS")),
    ]
    n, gap = len(steps), 1.6
    w = (100.0 - gap * (n - 1)) / n
    y, h = top - 26.0, 16.5
    for i, (num, title, body) in enumerate(steps):
        x = i * (w + gap)
        card(ax, x, y, w, h, fc="#E9F7EF" if i == n - 1 else PANEL, r=1.4)
        card(ax, x + 1.3, y + h - 4.9, 3.5, 3.5, fc=DARK, r=1.75)
        text(ax, x + 3.05, y + h - 3.15, num, size=7.8, color=WHITE,
             weight="bold", ha="center")
        text(ax, x + 1.3, y + h - 7.6, title, size=8.8, weight="bold")
        text(ax, x + 1.3, y + 4.0, body, size=6.9, color=SOFT, va="center",
             spacing=1.55)
        if i < n - 1:
            arrow(ax, (x + w + 0.1, y + h / 2.0),
                  (x + w + gap - 0.1, y + h / 2.0), lw=1.2, scale=8)

    y2 = y - 3.2
    card(ax, 0, y2 - 9.4, 48.5, 9.2, fc="#FDF3E7", r=1.2)
    text(ax, 2.2, y2 - 3.0, L("El build falla si…", "The build fails if…"),
         size=9.2, weight="bold")
    text(ax, 2.2, y2 - 6.6,
         L("cambia un byte del código tras la huella  ·  el autotest del .exe "
           "no pasa  ·  la release 4.1 protegida se altera",
           "one byte of source changes after the fingerprint  ·  the .exe "
           "self-test fails  ·  the protected 4.1 release is altered"),
         size=7.6, color=SOFT)
    card(ax, 51.5, y2 - 9.4, 48.5, 9.2, fc=PANEL, r=1.2)
    text(ax, 53.7, y2 - 3.0,
         L("Lo que nunca entra en el paquete",
           "What never enters the package"), size=9.2, weight="bold")
    text(ax, 53.7, y2 - 6.6,
         L("documentos DIN o FVA con licencia  ·  resultados .odb/.cae de un "
           "caso  ·  el directorio dist histórico",
           "licensed DIN or FVA documents  ·  run-specific .odb/.cae results  "
           "·  the historical dist directory"),
         size=7.6, color=SOFT)
    return save(fig, "dia_release.png")


# ------------------------------------------------------------------ diagram 12
def dia_tabs():
    fig, ax, top = canvas(11.6, 3.1)
    tabs = [
        ("1", L("Proyecto", "Project"),
         L("nombre, autor, idioma\nruta de Abaqus",
           "name, author, language\nAbaqus path")),
        ("2", L("Geometría DIN", "DIN geometry"),
         L("d1, L/d1, ranura, radios\ny el derivado en vivo",
           "d1, L/d1, keyway, radii\nand the live derivation")),
        ("3", L("Malla y materiales", "Mesh and materials"),
         L("plantilla, orden, seeds\npreajustes C45",
           "template, order, seeds\nC45 presets")),
        ("4", L("Análisis", "Analysis"),
         L("contacto, torsión\nestudio de convergencia",
           "contact, torsion\nconvergence study")),
        ("5", "DIN 6892 / FVA",
         L("método, factores, N_W\nMétodo A y MATLAB",
           "method, factors, N_W\nMethod A and MATLAB")),
        ("6", L("Ejecutar y evidencias", "Run and evidence"),
         L("log en vivo, artefactos\nabrir informe",
           "live log, artifacts\nopen the report")),
    ]
    n, gap = len(tabs), 1.4
    w = (100.0 - gap * (n - 1)) / n
    y, h = 1.6, top - 3.2
    for i, (num, title, body) in enumerate(tabs):
        x = i * (w + gap)
        card(ax, x, y, w, h, fc=PANEL, r=1.3)
        text(ax, x + 1.4, y + h - 3.2, num, size=8.8, color=BLUE, weight="bold")
        text(ax, x + 1.4, y + h - 7.0, title, size=9.2, weight="bold")
        text(ax, x + 1.4, y + 4.4, body, size=7.1, color=SOFT, va="center",
             spacing=1.5)
    return save(fig, "dia_tabs.png")


# ------------------------------------------------------------------ diagram 13
def dia_estado():
    fig, ax, top = canvas(11.6, 6.9)
    text(ax, 0, top - 2.3,
         L("Estado real y lo que queda por decidir",
           "Where it really stands, and what is still open"),
         size=15.5, weight="bold")

    blocks = [
        (L("VERIFICADO", "VERIFIED"), GREEN, [
            L("autotest empaquetado: 0 errores, 0 advertencias",
              "packaged self-test: 0 errors, 0 warnings"),
            L("params_default.json idéntico a core.default_params()",
              "params_default.json identical to core.default_params()"),
            L("los 4 presets validan con esquema 6",
              "all 4 presets validate under schema 6"),
            L("compatibilidad Python 2.7 auditada módulo a módulo",
              "Python 2.7 compatibility audited module by module"),
            L("999,18 N·m fijado en el autotest, gobierna el cubo",
              "999.18 N·m locked in the self-test, hub governs"),
        ]),
        (L("PENDIENTE DE TU DECISIÓN", "AWAITING YOUR DECISION"), AMBER, [
            L("signo de la ecuación 9 contra el texto DIN con licencia",
              "sign of equation 9 against the licensed DIN text"),
            L("número de versión: 4.2 ya publicado con otra física",
              "version number: 4.2 already shipped with different physics"),
            L("plantilla de malla: la GUI fuerza FVA_METHOD_A_HYBRID",
              "mesh template: the GUI forces FVA_METHOD_A_HYBRID"),
            L("publicar o no el cuarto preset (10 LW solve)",
              "whether to ship the fourth preset (10 LW solve)"),
        ]),
        (L("FUERA DE ALCANCE HOY", "OUT OF SCOPE TODAY"), "#4B5563", [
            L("ninguna corrida de solver 4.2 ni especimen FVA exacto",
              "no 4.2 solver run and no exact FVA specimen"),
            L("Método A sigue exigiendo un ODB externo resuelto",
              "Method A still needs an externally solved ODB"),
            L("K_λ sigue como placeholder neutro; los factores externos "
              "específicos del caso requieren revisión del texto con licencia",
              "K_λ remains a neutral placeholder; case-specific external "
              "factors require review against the licensed text"),
        ]),
    ]
    x, w = 0.0, 32.0
    gap = (100.0 - 3 * w) / 2.0
    y, h = top - 46.0, 34.0
    for idx, (title, color, items) in enumerate(blocks):
        x = idx * (w + gap)
        card(ax, x, y, w, h, fc=PANEL, r=1.5)
        chip(ax, x + 1.5, y + h - 2.9, title, color, size=7.0)
        yy = y + h - 7.4
        for item in items:
            ax.add_patch(Circle((x + 2.2, yy - 0.15), 0.26, color=color,
                                zorder=6))
            wrapped = _wrap(item, 36)
            text(ax, x + 3.4, yy, wrapped, size=7.5, color=SOFT, va="top",
                 spacing=1.5)
            yy -= 3.1 + 2.7 * wrapped.count("\n")
    text(ax, 0, y - 5.0,
         L("El ejecutable publicado en release/ModelBuilder_4.2 es anterior a "
           "las dos correcciones: 17 de 31 entradas del manifiesto han "
           "cambiado desde aquel build.",
           "The executable published in release/ModelBuilder_4.2 predates both "
           "corrections: 17 of the 31 manifest entries have changed since that "
           "build."),
         size=8.4, color=INK)
    return save(fig, "dia_estado.png")


def _wrap(value, width):
    words, lines, current = value.split(), [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)



# ------------------------------------------------------------------ diagram 14
def dia_method_a():
    """The Method A evidence chain: solved ODB to a criterion."""
    fig, ax, top = canvas(12.2, 5.9)
    text(ax, 0, top - 2.3,
         L("Método A: la cadena de evidencia",
           "Method A: the evidence chain"), size=15.5, weight="bold")
    text(ax, 0, top - 6.3,
         L("Model Builder no resuelve el Método A: consume el resultado de un "
           "ODB ya resuelto y descargado, y comprueba que sea el que dice ser.",
           "Model Builder does not solve Method A: it consumes the result of an "
           "already solved and unloaded ODB, and checks that it is what it "
           "claims to be."), size=9.0, color=SOFT)

    stages = [
        ("1", L("ODB resuelto", "Solved ODB"),
         L("externo, >= 10 ciclos\nconjuntos LEFT y RIGHT\ndel chavetero",
           "external, >= 10 cycles\nLEFT and RIGHT keyway\nnode sets"), "#E8F1FD"),
        ("2", L("Emparejado", "Node pairing"),
         L("por coordenadas SIN\ndeformar; apertura =\nU_right,x - U_left,x",
           "by UNDEFORMED\ncoordinates; opening =\nU_right,x - U_left,x"), PANEL),
        ("3", L("CSV canónico", "Canonical CSV"),
         L("x_mm, z_mm, opening_um\n+ JSON con SHA-256\ndel origen",
           "x_mm, z_mm, opening_um\n+ JSON sidecar with\nsource SHA-256"), PANEL),
        ("4", L("Integración", "Integration"),
         L("trapecio 2-D sobre la\nrejilla; cobertura\ncomprobada al 2 %",
           "2-D trapezoidal rule\nover the grid; coverage\nchecked to 2 %"), PANEL),
        ("5", L("Criterio", "Criterion"),
         L("volumen relativo de\napertura frente a\nv_crit = 0,5",
           "relative opening\nvolume against\nv_crit = 0.5"), "#E9F7EF"),
    ]
    n, gap = len(stages), 1.4
    w = (100.0 - gap * (n - 1)) / n
    y, h = top - 24.0, 16.0
    for i, (num, title, body, fc) in enumerate(stages):
        x = i * (w + gap)
        card(ax, x, y, w, h, fc=fc, r=1.4)
        text(ax, x + 1.4, y + h - 2.6, num, size=8.4, color=BLUE, weight="bold")
        text(ax, x + 1.4, y + h - 6.4, title, size=9.6, weight="bold")
        text(ax, x + 1.4, y + 4.4, body, size=6.9, color=SOFT, va="center",
             spacing=1.55)
        if i < n - 1:
            arrow(ax, (x + w + 0.1, y + h / 2.0),
                  (x + w + gap - 0.1, y + h / 2.0), lw=1.3, scale=9)

    y2 = y - 4.0
    card(ax, 0, y2 - 12.2, 48.0, 11.8, fc=PANEL, r=1.3)
    text(ax, 2.2, y2 - 3.0,
         L("Once comprobaciones, seis con poder de veto",
           "Eleven checks, six with veto power"), size=9.4, weight="bold")
    text(ax, 2.2, y2 - 8.4,
         _wrap(L("Sólo si pasan ciclos mínimos, fotograma descargado, origen "
                 "identificado, cobertura al 2 %, invariantes revalidados y "
                 "hash de procedencia, el resultado se declara "
                 "complete_method_a. Las otras cinco quedan visibles como "
                 "evidencia de calidad.",
                 "Only if minimum cycles, unloaded frame, identified source "
                 "frame, 2 % coverage, revalidated invariants and provenance "
                 "hash all pass is the result declared complete_method_a. The "
                 "other five stay visible as quality evidence."), 64),
         size=7.5, color=SOFT, va="center", spacing=1.6)
    card(ax, 52.0, y2 - 12.2, 48.0, 11.8, fc="#FDF3E7", r=1.3)
    text(ax, 54.2, y2 - 3.0,
         L("Contrato de evidencia versión 2", "Evidence contract version 2"),
         size=9.4, weight="bold")
    text(ax, 54.2, y2 - 8.4,
         _wrap(L("El extractor (fva600-odb-opening-2.0) y el post-proceso "
                 "(fva600-csv-1.0) comparten versión de contrato, tolerancia "
                 "de cobertura y procedencia SHA-256: un CSV editado a mano "
                 "no pasa.",
                 "The extractor (fva600-odb-opening-2.0) and the "
                 "post-processor (fva600-csv-1.0) share the contract version, "
                 "coverage tolerance and SHA-256 provenance: a hand-edited "
                 "CSV does not pass."), 64),
         size=7.5, color=SOFT, va="center", spacing=1.6)
    return save(fig, "dia_method_a.png")


# ------------------------------------------------------------------ diagram 15
def dia_matlab():
    """The optional MATLAB cross-check, and why it is never the authority."""
    fig, ax, top = canvas(11.8, 6.3)
    text(ax, 0, top - 2.3,
         L("MATLAB como contraste, nunca como autoridad",
           "MATLAB as a cross-check, never as the authority"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.3,
         L("El valor que Model Builder usa siempre es el de Python. MATLAB "
           "sirve para demostrar que otro motor numérico llega al mismo "
           "número.",
           "The value Model Builder uses is always the Python one. MATLAB is "
           "there to show that a second numerical engine reaches the same "
           "number."), size=9.0, color=SOFT)

    modes = [
        ("OFF", L("No se exporta nada", "Nothing is exported"),
         L("el flujo no cambia", "the workflow is unchanged"), "#4B5563"),
        ("EXPORT", L("Paquete determinista", "Deterministic bundle"),
         L("mismo contenido, mismos hashes,\nsin ejecutar MATLAB",
           "same content, same hashes,\nwithout running MATLAB"), "#0B5394"),
        ("RUN", L("Exporta y ejecuta", "Export and execute"),
         L("lista de argumentos, shell=False\ny timeout finito",
           "argument list, shell=False\nand a finite timeout"), GREEN),
    ]
    y, h = top - 21.0, 12.4
    w = 31.4
    gap = (100.0 - 3 * w) / 2.0
    for i, (name, title, note, color) in enumerate(modes):
        x = i * (w + gap)
        card(ax, x, y, w, h, fc=PANEL, r=1.4)
        chip(ax, x + 1.5, y + h - 2.9, name, color, size=7.4)
        text(ax, x + 1.7, y + h - 7.0, title, size=9.8, weight="bold")
        text(ax, x + 1.7, y + 2.9, note, size=7.4, color=SOFT, va="center",
             spacing=1.55)

    y2 = y - 3.6
    card(ax, 0, y2 - 16.8, 48.0, 16.4, fc=PANEL, r=1.3)
    text(ax, 2.2, y2 - 2.8, L("Qué contiene el paquete",
                              "What the bundle contains"),
         size=9.4, weight="bold")
    files = [
        ("opening.csv", L("el CSV canonicalizado", "the canonicalised CSV")),
        ("method_a_input.json", L("las entradas del cálculo",
                                  "the calculation inputs")),
        ("python_result.json", L("el resultado autoritativo",
                                 "the authoritative result")),
        ("<entry>.m", L("el código MATLAB generado",
                        "the generated MATLAB source")),
        ("manifest.json", L("SHA-256 de cada archivo",
                            "SHA-256 of every file")),
    ]
    yy = y2 - 6.4
    for name, note in files:
        text(ax, 2.6, yy, name, size=7.6, weight="bold", family=MONO)
        text(ax, 22.0, yy, note, size=7.4, color=SOFT)
        yy -= 2.45
    card(ax, 52.0, y2 - 16.8, 48.0, 16.4, fc="#E9F7EF", r=1.3)
    text(ax, 54.2, y2 - 2.8, L("Cómo se compara", "How it is compared"),
         size=9.4, weight="bold")
    text(ax, 54.2, y2 - 6.4,
         L("Tolerancia absoluta 1e-10 y relativa 1e-9.\nSi MATLAB discrepa, se "
           "reporta la discrepancia;\nel número de Python no se toca.",
           "Absolute tolerance 1e-10, relative 1e-9.\nIf MATLAB disagrees the "
           "discrepancy is reported;\nthe Python number is not touched."),
         size=7.6, color=SOFT, va="top", spacing=1.6)
    text(ax, 54.2, y2 - 13.0,
         L("El nombre de la función de entrada se valida con\nexpresión "
           "regular, y verify_bundle vuelve a\ncomprobar los hashes.",
           "The entry function name is validated by a regular\nexpression, and "
           "verify_bundle re-checks the\nhashes."),
         size=7.6, color=MUTED, va="top", spacing=1.6)
    return save(fig, "dia_matlab.png")


# ------------------------------------------------------------------ diagram 16
def dia_mesh_loop():
    """How a mesh is actually chosen, per part."""
    fig, ax, top = canvas(11.8, 6.1)
    text(ax, 0, top - 2.3,
         L("Cómo se elige la malla, pieza por pieza",
           "How the mesh is actually chosen, part by part"),
         size=15.5, weight="bold")
    text(ax, 0, top - 6.3,
         L("El orden de candidatos no es el mismo para todas las piezas: el "
           "eje y la chaveta empiezan por hexaedro estructurado, el cubo y el "
           "casquillo por barrido medial.",
           "The candidate order is not the same for every part: shaft and key "
           "start with structured hex, hub and bushing with medial sweep."),
         size=9.0, color=SOFT)

    order = [
        ("Shaft", "STRUCTURED_HEX"), ("Key", "STRUCTURED_HEX"),
        ("Bushing", "SWEEP_MEDIAL"), ("Hub", "SWEEP_MEDIAL"),
    ]
    y, h = top - 17.0, 8.6
    w = 23.2
    gap = (100.0 - 4 * w) / 3.0
    for i, (part, first) in enumerate(order):
        x = i * (w + gap)
        card(ax, x, y, w, h, fc=PANEL, r=1.3)
        text(ax, x + 1.6, y + h - 3.0, part, size=9.8, weight="bold")
        text(ax, x + 1.6, y + 2.6,
             L("primer candidato\n", "first candidate\n") + first,
             size=7.2, color=SOFT, va="center", spacing=1.5)
        if i < 3:
            arrow(ax, (x + w + 0.15, y + h / 2.0),
                  (x + w + gap - 0.15, y + h / 2.0), lw=1.2, scale=8)

    y2 = y - 3.4
    steps = [
        L("particiona la banda de la entalla",
          "partition the notch band"),
        L("siembra los arcos del radio", "seed the fillet arcs"),
        L("aplica la estrategia de control", "apply the control strategy"),
        L("malla con reparación de AR", "mesh with AR repair"),
        L("mide y puntúa el candidato", "measure and score the candidate"),
    ]
    card(ax, 0, y2 - 9.0, 100, 8.6, fc="#E8F1FD", r=1.3)
    text(ax, 2.2, y2 - 2.6,
         L("Cada candidato recorre el mismo ciclo",
           "Every candidate runs the same loop"), size=9.4, weight="bold")
    sx = 2.2
    for i, step in enumerate(steps):
        text(ax, sx, y2 - 6.4, "%d  %s" % (i + 1, step), size=7.4, color=SOFT)
        sx += 19.6

    y3 = y2 - 12.4
    card(ax, 0, y3 - 9.4, 48.0, 9.0, fc=PANEL, r=1.3)
    text(ax, 2.2, y3 - 2.8, L("Se acepta sólo si pasa todo",
                              "Accepted only if everything passes"),
         size=9.4, weight="bold")
    text(ax, 2.2, y3 - 6.6,
         L("score, % de hexaedros, relación de aspecto, advertencias, "
           "reparaciones y presupuesto de elementos.",
           "score, hex percentage, aspect ratio, warnings, repairs and the "
           "element budget."), size=7.6, color=SOFT, va="top", spacing=1.6)
    card(ax, 52.0, y3 - 9.4, 48.0, 9.0, fc="#FDF3E7", r=1.3)
    text(ax, 54.2, y3 - 2.8, L("El veredicto global es el peor",
                               "The global verdict is the worst part"),
         size=9.4, weight="bold")
    text(ax, 54.2, y3 - 6.6,
         L("Nunca la media. Y con fail_on_quality, el build falla en lugar de "
           "entregar una malla que no cumple.",
           "Never the average. And with fail_on_quality the build fails "
           "instead of delivering a mesh that does not comply."),
         size=7.6, color=SOFT, va="top", spacing=1.6)
    return save(fig, "dia_mesh_loop.png")


DIAGRAMS = {
    "arquitectura": dia_arquitectura,
    "pipeline": dia_pipeline,
    "workspace": dia_workspace,
    "badges": dia_badges,
    "metodos": dia_metodos,
    "pares": chart_pares,
    "fw": chart_fw,
    "t2tr": dia_t2tr,
    "eq9": dia_eq9,
    "malla": dia_malla,
    "release": dia_release,
    "tabs": dia_tabs,
    "estado": dia_estado,
    "method_a": dia_method_a,
    "matlab": dia_matlab,
    "mesh_loop": dia_mesh_loop,
}


def main():
    wanted = sys.argv[1:] or list(DIAGRAMS)
    print("rendering %d diagram(s) in %s" % (len(wanted), LANG))
    for name in wanted:
        if name not in DIAGRAMS:
            raise SystemExit("unknown diagram %r" % name)
        DIAGRAMS[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
