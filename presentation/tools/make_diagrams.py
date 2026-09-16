# -*- coding: utf-8 -*-
"""Render the presentation diagrams for Model Builder 4.2.

Every number that appears in a chart is imported live from the packaged engine
(keyjoint_core / din6892_methods), so the slides cannot drift from the code.

Usage:
    python3 make_diagrams.py [name ...]     # default: all
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
OUT = "/projects/sandbox/assets/diagrams"
sys.path.insert(0, REPO)
os.makedirs(OUT, exist_ok=True)

import din6892_methods as din  # noqa: E402
import keyjoint_core as core  # noqa: E402

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
    """Format a number the Spanish way: comma decimal, thin thousands space."""
    text_value = ("%%.%df" % decimals) % value
    whole, _, frac = text_value.partition(".")
    if thousands and len(whole) > 3:
        groups = []
        while len(whole) > 3:
            groups.insert(0, whole[-3:])
            whole = whole[:-3]
        groups.insert(0, whole)
        whole = "\u2009".join(groups)
    return whole + ("," + frac if frac else "")


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
    text(ax, 0, top - 2.4, "Un solo repositorio, dos intérpretes de Python",
         size=15.5, weight="bold")
    text(ax, 0, top - 6.4,
         "El núcleo de cálculo es el único código que corre en los dos lados. "
         "Por eso no lleva f-strings ni anotaciones: tiene que compilar también "
         "en Python 2.7.", size=9.2, color=SOFT)

    band_y, band_h = 24.0, 21.5
    card(ax, 0, band_y, 46.5, band_h, fc=PANEL, r=1.8)
    chip(ax, 2.0, band_y + band_h - 3.4, "PYTHON 3  ·  ESCRITORIO", DARK)
    for i, (name, desc) in enumerate([
            ("model_builder_gui.py", "interfaz Tk, 6 pestañas, hilos"),
            ("project_workspace.py", "proyecto aislado, 7 carpetas"),
            ("abaqus_runner.py", "lanza Abaqus sin shell, log"),
            ("report_generator.py", "informe LaTeX/PDF/JSON"),
            ("fva600_postprocess.py", "integra ΔV del CSV, v_crit"),
            ("fva600_matlab.py", "contraste opcional en MATLAB")]):
        yy = band_y + band_h - 7.2 - i * 2.45
        text(ax, 2.2, yy, name, size=8.5, weight="bold")
        text(ax, 19.5, yy, desc, size=7.5, color=SOFT)

    card(ax, 53.5, band_y, 46.5, band_h, fc=PANEL, r=1.8)
    chip(ax, 55.5, band_y + band_h - 3.4, "PYTHON 2.7  ·  KERNEL DE ABAQUS 2022",
         AMBER)
    for i, (name, desc) in enumerate([
            ("build_parametric_model.py", "geometría, malla, contacto, job"),
            ("fva600_method_a_backend.py", "Método A, malla coincidente"),
            ("fva600_d40_v3_nojob.py", "regresión FVA 1 ciclo, NOJOB"),
            ("fva600_odb_extract.py", "abre el ODB, exporta apertura")]):
        yy = band_y + band_h - 7.2 - i * 2.45
        text(ax, 55.7, yy, name, size=8.5, weight="bold")
        text(ax, 77.5, yy, desc, size=7.5, color=SOFT)

    core_y, core_h = 8.0, 11.0
    card(ax, 13.0, core_y, 74.0, core_h, fc=DARK, r=1.8)
    text(ax, 50, core_y + core_h - 2.3, "NÚCLEO COMPARTIDO  ·  compatible 2.7 y 3.x",
         size=7.8, color="#8E8E96", weight="bold", ha="center")
    text(ax, 31.5, core_y + 5.3, "keyjoint_core.py", size=11.5, color=WHITE,
         weight="bold", ha="center")
    text(ax, 31.5, core_y + 2.6,
         "tabla DIN 6885 · derive() · validate()\n8 plantillas de malla",
         size=7.3, color="#8E8E96", ha="center", va="center")
    text(ax, 68.5, core_y + 5.3, "din6892_methods.py", size=11.5, color=WHITE,
         weight="bold", ha="center")
    text(ax, 68.5, core_y + 2.6,
         "métodos A / B / B-FVA / C\nfactores, políticas, catálogos",
         size=7.3, color="#8E8E96", ha="center", va="center")
    ax.add_line(Line2D([50, 50], [core_y + 1.4, core_y + 7.2], color="#3A3A42",
                       lw=1.0, zorder=6))

    arrow(ax, (23.0, band_y - 0.4), (29.0, core_y + core_h + 0.4), lw=1.4)
    arrow(ax, (77.0, band_y - 0.4), (71.0, core_y + core_h + 0.4), lw=1.4)
    arrow(ax, (46.9, band_y + band_h / 2.0), (53.1, band_y + band_h / 2.0),
          color=BLUE, lw=1.8, scale=13)
    text(ax, 50, band_y + band_h / 2.0 + 2.6, "subproceso", size=7.4,
         color=BLUE, ha="center", weight="bold")
    text(ax, 50, band_y + band_h / 2.0 - 2.8, "params.json", size=7.0,
         color=MUTED, ha="center")

    text(ax, 0, 3.0,
         "Ningún módulo de Abaqus se importa en el lado de escritorio: la "
         "interfaz arranca sin Abaqus instalado y sólo lo necesita para "
         "construir el modelo.", size=7.9, color=MUTED)
    return save(fig, "dia_arquitectura.png")


# ------------------------------------------------------------------ diagram 02
def dia_pipeline():
    fig, ax, top = canvas(12.4, 4.9)
    text(ax, 0, top - 2.3, "De un clic a la evidencia archivada",
         size=15.5, weight="bold")

    stages = [
        ("1", "Formulario", "lee las\n6 pestañas", PANEL),
        ("2", "Validación", "un error\nbloquea", "#FFF4E5"),
        ("3", "Proyecto", "7 carpetas\nproject.json", PANEL),
        ("4", "Subproceso", "abaqus cae\nnoGUI", "#E8F1FD"),
        ("5", "Geometría", "eje · chaveta\ncubo", PANEL),
        ("6", "Malla", "por pieza,\nN candidatos", PANEL),
        ("7", "Análisis", "contacto\ntorsión", "#E8F1FD"),
        ("8", "Auditoría", "AUDIT .txt\ny .json", PANEL),
        ("9", "Evidencia", "capturas\nCAE · JSON", PANEL),
        ("10", "Informe", "tex · pdf\nreport_data", "#E9F7EF"),
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
             (split + 0.6, end9, AMBER, "Python 2.7  ·  kernel de Abaqus 2022"),
             (end9 + 0.6, 100.0, GREEN, "Python 3")]
    for x0, x1, color, label in bands:
        card(ax, x0, y - 5.2, x1 - x0, 3.4, fc=color, r=1.0)
        text(ax, (x0 + x1) / 2.0, y - 3.5, label, size=7.4, color=WHITE,
             ha="center", weight="bold")

    text(ax, 0, y - 10.4, "Dos puertas duras", size=9.6, weight="bold")
    text(ax, 0, y - 14.0,
         "Ningún error de validación llega a Abaqus.  ·  Ningún proyecto se "
         "declara correcto si falta un artefacto, si el quality gate de malla "
         "no pasa o si la malla realizada no es la planificada.",
         size=8.2, color=SOFT)
    text(ax, 0, y - 18.2,
         "El solver sólo se ejecuta si el usuario lo pide (analysis.submit). "
         "Por defecto se construye, se audita y se documenta, sin resolver.",
         size=7.8, color=MUTED)
    return save(fig, "dia_pipeline.png")


# ------------------------------------------------------------------ diagram 03
def dia_workspace():
    fig, ax, top = canvas(11.6, 6.0)
    text(ax, 0, top - 2.3, "Cada ejecución vive en su propio proyecto",
         size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         "ProjectWorkspace crea <nombre>_AAAAMMDD_HHMMSS y pasa rutas absolutas "
         "al kernel. Abaqus corre con cwd = jobs/, así que ningún archivo de "
         "solver cae junto al ejecutable.", size=9.0, color=SOFT)

    rows = [
        ("input/", "params.json · technical_contract.json",
         "lo que se pidió, congelado", "#0D47A1"),
        ("generated/", "PARAM_BUILD_AUDIT.txt/.json · BUILD_RESULT.json · mesh_study.csv",
         "lo que el motor hizo de verdad", GREEN),
        ("model/", "<modelo>.cae", "la base de datos de Abaqus", "#0B5394"),
        ("jobs/", "<job>.odb · .inp · .msg · .sta",
         "todo el ruido del solver, contenido", "#4B5563"),
        ("screenshots/", "_preview.png · _preview_Front/Right · _notch_mesh.png",
         "evidencia visual reproducible", "#4A148C"),
        ("reports/", "report.tex · report.pdf · report_data.json · latex_build.log",
         "el entregable para revisión", GREEN),
        ("logs/", "abaqus.log", "comando, cwd y salida íntegra", "#4B5563"),
    ]
    y, h = top - 11.0, 5.6
    for name, files, why, color in rows:
        y -= h + 0.85
        card(ax, 0, y, 100, h, fc=PANEL, r=1.1)
        card(ax, 0, y, 0.85, h, fc=color, r=0.42)
        text(ax, 2.8, y + h * 0.64, name, size=9.8, weight="bold")
        text(ax, 2.8, y + h * 0.24, why, size=7.1, color=MUTED)
        text(ax, 27.0, y + h / 2.0, files, size=8.0, color=SOFT, family=MONO)

    text(ax, 0, 2.6,
         "project.json registra esquema, autor, idioma, estado, el comando "
         "ejecutado y cada artefacto con su tamaño y su etiqueta de evidencia.",
         size=7.9, color=MUTED)
    return save(fig, "dia_workspace.png")


# ------------------------------------------------------------------ diagram 04
def dia_badges():
    fig, ax, top = canvas(11.6, 6.4)
    text(ax, 0, top - 2.3, "Ningún número viaja sin su procedencia",
         size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         "Cada valor del informe lleva una etiqueta. Una propuesta de "
         "investigación no puede presentarse como requisito normativo vigente.",
         size=9.0, color=SOFT)

    items = [
        ("NORMATIVE", "Transcrito de la norma", "tabla DIN 6885-1:2021-11"),
        ("DIN-METHOD", "Método de la norma", "DIN 6892 Métodos B y C"),
        ("FVA-RESEARCH", "Propuesta de investigación", "FVA 600 III / informe 1686"),
        ("CORE-SCREENING", "Cribado interno", "presión uniforme, plausibilidad"),
        ("LITERATURE", "Comparación publicada", "K_ts, K_vm de literatura"),
        ("USER-INPUT", "Dato del usuario", "requiere verificación externa"),
        ("USER-OVERRIDE", "El usuario salió del sobre", "compliance_mode"),
        ("NOT-IMPLEMENTED", "Declarado no implementado", "DIN 6888, formas C–J"),
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
    text(ax, 0, top - 2.3, "Cuatro métodos, una sola jerarquía de evidencia",
         size=15.5, weight="bold")

    cols = [
        ("C_PRELIMINARY", "Dimensionado previo", "DIN-METHOD",
         ["presión admisible constante",
          "resuelve el problema inverso:\nlongitud portante necesaria"],
         es(torques["C_PRELIMINARY"]) + " N·m"),
        ("B_DIN_CURRENT", "Método B vigente", "DIN-METHOD",
         ["presión equivalente, ec. 1–12",
          "factores f_S f_H f_W K_λ K_R K_V",
          "eje, cubo y chaveta,\ncada uno en su flanco"],
         es(torques["B_DIN_CURRENT"]) + " N·m"),
        ("B_FVA_2025", "Reformulación FVA", "FVA-RESEARCH",
         ["ecuación 36 del informe 1686",
          "f_Sv, f_WS, f_S,ltr, K_d",
          "diagnóstico, nunca\ncriterio de aceptación"],
         es(torques["B_FVA_2025"]) + " N·m"),
        ("A_FE_VOLUME", "Verificación por MEF", "FVA-RESEARCH",
         ["volumen relativo de apertura",
          "exige resultado externo\nresuelto y descargado",
          "mínimo 10 ciclos de carga"],
         "requiere ODB"),
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
         "Los tres métodos analíticos se calculan siempre en paralelo y se "
         "comparan entre sí: si el Método C resultara menos conservador que el "
         "B, el modelo levanta din6892_method_c_not_conservative.",
         size=8.4, color=INK)
    text(ax, 0, y - 9.2,
         "Valores del par por defecto D40, C45+N, chaveta forma A 12 × 8 × 50, "
         "par pulsante. El resultado que gobierna es el del cubo.",
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

    labels = ["Método C\ndimensionado previo", "Método B\nvigente · por defecto",
              "Método B\npar alternante", "Método B FVA 2025\ninvestigación"]
    values = [torques["C_PRELIMINARY"], torques["B_DIN_CURRENT"], alternating,
              torques["B_FVA_2025"]]
    colors = ["#A0A0A8", BLUE, "#5AA9F0", "#C98A3C"]
    for rect, value in zip(ax.bar(labels, values, width=0.5, color=colors,
                                  zorder=3), values):
        ax.text(rect.get_x() + rect.get_width() / 2.0, value + 40, es(value),
                ha="center", va="bottom", fontsize=13, fontweight="bold",
                color=INK, family=SANS)
    ax.set_ylim(0, max(values) * 1.20)
    ax.set_ylabel("par admisible  M_t,zul   [N·m]", fontsize=9.5, color=SOFT)
    ax.set_yticks([0, 500, 1000, 1500, 2000, 2500])

    ax.axhline(1302.05, color=RED, lw=1.3, ls=(0, (5, 3)), zorder=4)
    ax.text(-0.42, 1302.05 + 45, "1 302,05  ·  antes de la corrección",
            fontsize=8.8, color=RED, ha="left", va="bottom", fontweight="bold",
            family=SANS)

    fig.text(0.062, 0.935, "La misma unión, cuatro respuestas distintas",
             fontsize=15.5, fontweight="bold", color=INK, family=SANS)
    fig.text(0.062, 0.862,
             "Valores calculados en vivo por din6892_methods para el D40 por "
             "defecto. El Método B vigente es la referencia; el resto es "
             "contraste.", fontsize=9.0, color=SOFT, family=SANS)
    fig.text(0.062, 0.035,
             "El límite lo pone el cubo, no el eje: con t2tr = 3,141 mm frente "
             "a t1tr = 5,141 mm, el flanco del cubo agota antes su capacidad.",
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
    ax.set_xlabel("N_W   ·   inversiones del sentido de carga", fontsize=9.5,
                  color=SOFT)
    ax.set_ylabel("f_W", fontsize=10.5, color=SOFT)

    ax.plot([1], [1.0], "o", ms=9, color=GREEN, zorder=6)
    ax.annotate("par pulsante  ·  R ≥ 0\nN_W = 0   f_W = 1,000\n999,18 N·m",
                xy=(1.06, 1.0), xytext=(2.3, 0.885), fontsize=9.0, color=INK,
                family=SANS, linespacing=1.6,
                arrowprops=dict(arrowstyle="-", color=GREEN, lw=1.1))
    f_alt = din.load_reversal_factor(1.0e4)["f_W"]
    ax.plot([1e4], [f_alt], "o", ms=9, color=RED, zorder=6)
    ax.annotate("par totalmente alternante\nN_W = 10 000   f_W = 0,796\n795,56 N·m",
                xy=(1.15e4, f_alt), xytext=(3.4e4, 0.86), fontsize=9.0,
                color=INK, family=SANS, linespacing=1.6,
                arrowprops=dict(arrowstyle="-", color=RED, lw=1.1))

    fig.text(0.075, 0.935, "La ecuación 3 cuenta inversiones de flanco, no ciclos",
             fontsize=15.5, fontweight="bold", color=INK, family=SANS)
    fig.text(0.075, 0.862,
             "Un par que sólo pulsa nunca cambia de flanco: no hay daño extra "
             "que penalizar. El código alimentaba 10 000 ciclos y descontaba un "
             "20 % de capacidad inexistente.", fontsize=9.0, color=SOFT,
             family=SANS)
    fig.text(0.075, 0.038,
             "N_W es ahora explícito. Si se deja vacío se deduce de la razón de "
             "carga R, y la deducción se reporta como "
             "din6892_load_reversal_derived.", fontsize=8.2, color=MUTED,
             family=SANS)
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

    # Hub body above the interface arc.
    hub_top = 7.2
    hub = [(cx + x * mm, cy + arc_y(x) * mm) for x in xs]
    hub += [(cx + half_view * mm, cy + hub_top * mm),
            (cx - half_view * mm, cy + hub_top * mm)]
    ax.add_patch(Polygon(hub, closed=True, facecolor="#DCDCE3",
                         edgecolor="#A8A8B2", lw=1.0, zorder=2))
    # Shaft body below the interface arc.
    shaft_bottom = -7.6
    shaft = [(cx + x * mm, cy + arc_y(x) * mm) for x in xs]
    shaft += [(cx + half_view * mm, cy + shaft_bottom * mm),
              (cx - half_view * mm, cy + shaft_bottom * mm)]
    ax.add_patch(Polygon(shaft, closed=True, facecolor="#C2DCF7",
                         edgecolor="#6E9CCB", lw=1.2, zorder=3))

    # Keyway pockets: shaft down to t1, hub up to t2 (both from the arc).
    ax.add_patch(Rectangle((cx - b / 2.0 * mm, cy - t1 * mm), b * mm,
                           (t1 + t2) * mm, facecolor=WHITE, edgecolor="none",
                           zorder=4))
    ax.add_patch(Rectangle((cx - b / 2.0 * mm, cy - t1 * mm), b * mm,
                           (t1 + t2) * mm, facecolor="none",
                           edgecolor="#9AA0A6", lw=0.9, zorder=6))
    # The key itself, height h, seated on the keyway floor.
    ax.add_patch(Rectangle((cx - b / 2.0 * mm, cy - t1 * mm), b * mm, h * mm,
                           facecolor=BLUE, edgecolor="#0059B3", lw=1.0,
                           zorder=5))
    text(ax, cx, cy + (-t1 + h / 2.0) * mm, "chaveta", size=label_size - 0.8,
         color=WHITE, ha="center", weight="bold", z=7)
    text(ax, cx, cy + shaft_bottom * mm * 0.86, "eje", size=label_size,
         color="#28527A", ha="center", z=7)
    text(ax, cx + 7.6 * mm, cy + hub_top * mm * 0.66, "cubo", size=label_size,
         color=SOFT, ha="center", z=7)

    # t1 on the shaft flank (right), t2 on the hub flank (left).
    xr = cx + b / 2.0 * mm + 2.9
    ax.add_line(Line2D([xr, xr], [cy - t1 * mm, cy], color=RED, lw=1.8, zorder=8))
    ax.add_line(Line2D([xr - 0.7, xr + 0.7], [cy, cy], color=RED, lw=1.2, zorder=8))
    ax.add_line(Line2D([xr - 0.7, xr + 0.7], [cy - t1 * mm, cy - t1 * mm],
                       color=RED, lw=1.2, zorder=8))
    text(ax, xr + 1.4, cy - t1 * mm / 2.0, "t1 = %s mm" % es(t1, 1), size=label_size,
         color=RED, weight="bold", z=8)

    xl = cx - b / 2.0 * mm - 2.9
    ax.add_line(Line2D([xl, xl], [cy, cy + t2 * mm], color=GREEN, lw=1.8, zorder=8))
    ax.add_line(Line2D([xl - 0.7, xl + 0.7], [cy, cy], color=GREEN, lw=1.2, zorder=8))
    ax.add_line(Line2D([xl - 0.7, xl + 0.7], [cy + t2 * mm, cy + t2 * mm],
                       color=GREEN, lw=1.2, zorder=8))
    text(ax, xl - 1.4, cy + t2 * mm / 2.0, "t2 = %s mm" % es(t2, 1),
         size=label_size, color=GREEN, weight="bold", ha="right", z=8)

    chord = None
    if show_chord:
        # The true sagitta between the arc at the centre and at (b/2 + s1).
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
    text(ax, 0, top - 2.4, "El cubo se comprobaba sobre el flanco del eje",
         size=15.5, weight="bold")
    text(ax, 0, top - 6.4,
         "DIN 6892 evalúa la presión del eje sobre l_tr · t1tr y la del cubo "
         "sobre l_tr · t2tr. Todas las piezas compartían t1tr.",
         size=9.0, color=SOFT)

    _keyway_section(ax, cx=22.0, cy=30.0, mm=1.25, show_chord=False)
    text(ax, 22.0, 14.5, "sección real a escala  ·  d1 = 40 mm, b × h = 12 × 8",
         size=7.6, color=MUTED, ha="center")
    text(ax, 22.0, 11.0, "DIN 6885-1 da t2 < t1 en las 26 filas de la tabla",
         size=7.6, color=MUTED, ha="center")

    x0, w = 47.0, 51.0
    rows = [
        ("t1tr  ·  flanco del eje", es(eff["t1tr_mm"], 3) + " mm", RED,
         "superficie convexa"),
        ("t2tr  ·  flanco del cubo", es(hub["t2tr_mm"], 3) + " mm", GREEN,
         "superficie cóncava, menos la holgura g_c"),
        ("área acreditada al cubo antes",
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
         "La chaveta recibe min(t1tr, t2tr): su flanco soporta la misma\n"
         "presión que el flanco del chavetero que lo acompaña.",
         size=8.2, color=SOFT, va="top", spacing=1.5)
    card(ax, x0, y - 16.9, w, 7.0, fc="#E9F7EF", r=1.2)
    text(ax, x0 + 2.6, y - 13.4,
         "D40 por defecto:  1 302,05  →  999,18 N·m",
         size=10.0, weight="bold", color=GREEN)
    return save(fig, "dia_t2tr.png")


# ------------------------------------------------------------------ diagram 09
def dia_eq9():
    d = core.derive(core.default_params())
    eff = d["din6892"]["derived"]["effective_bearing_depth"]

    fig, ax, top = canvas(11.8, 7.0)
    text(ax, 0, top - 2.4, "La pregunta abierta: el signo de la ecuación 9",
         size=15.5, weight="bold")
    text(ax, 0, top - 6.4,
         "Tal como está transcrita, la ecuación 9 SUMA la corrección de cuerda y "
         "devuelve t1tr = 5,141 mm: más que la propia altura del flanco, "
         "t1 = 5,0 mm.", size=9.0, color=SOFT)

    chord = _keyway_section(ax, cx=22.0, cy=32.0, mm=1.25, show_chord=True)
    text(ax, 22.0, 16.5,
         "corrección de cuerda  =  ½ (d1 − √(d1² − (b+2s1)²))  =  %s mm"
         % es(chord, 3), size=8.0, color=AMBER, ha="center", weight="bold")
    text(ax, 22.0, 12.8,
         "marcada en ámbar: la sagita real del arco a (b + 2s1)/2 = 6,8 mm",
         size=7.6, color=MUTED, ha="center")

    x0, w = 47.0, 51.0
    y = top - 11.0
    options = [
        ("EQUATION_9", es(eff["t1tr_equation9_mm"], 3) + " mm",
         "la transcripción literal  ·  valor por defecto", "#0B5394"),
        ("GEOMETRIC", es(eff["t1tr_geometric_mm"], 3) + " mm",
         "lo que exige el flanco convexo del eje", GREEN),
        ("CONSERVATIVE", es(eff["t1tr_conservative_mm"], 3) + " mm",
         "el menor de los dos, para diseño", "#4B5563"),
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
         "%s %% de diferencia en todo par de los Métodos B y C" %
         es(eff["relative_difference_percent"], 1),
         size=9.6, weight="bold", color=AMBER)
    text(ax, x0 + 2.6, y - 7.8,
         "No lo he decidido por mi cuenta. Se reportan los dos valores, la\n"
         "diferencia y una bandera; la política la elige el usuario y la\n"
         "discrepancia se avisa como din6892_bearing_depth_optimistic.",
         size=7.8, color=SOFT, va="top", spacing=1.55)
    text(ax, 0.0, 7.4,
         "La misma forma algebraica con signo positivo sí es correcta para el "
         "taladro cóncavo del cubo:\nel signo del eje parece un problema de "
         "transcripción o de datum, no de física.",
         size=7.9, color=MUTED, va="top", spacing=1.55)
    return save(fig, "dia_eq9.png")


# ------------------------------------------------------------------ diagram 10
def dia_malla():
    catalog = core.mesh_template_catalog()
    default_template = core.default_params()["mesh"]["template"]

    fig, ax, top = canvas(11.8, 7.0)
    text(ax, 0, top - 2.3, "Ocho políticas de malla, ninguna elegida a ciegas",
         size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         "AUTO compara candidatos completos por pieza y conserva el intento "
         "ganador. El score global es el peor de las piezas, nunca la media.",
         size=9.0, color=SOFT)

    headers = ["plantilla", "topología", "orden", "intentos", "score", "% hex",
               "AR máx", "presupuesto duro"]
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
            format(budgets.get("hard_elements", 0), ",d").replace(",", "\u2009"),
        ]
        for idx, (vx, value) in enumerate(zip(xs, values)):
            text(ax, vx, y + rowh / 2.0 - 0.35, value,
                 size=7.9 if idx == 0 else 7.5,
                 weight="bold" if idx == 0 else "normal",
                 color=INK if idx == 0 else SOFT)
        if is_default:
            text(ax, 21.0, y + rowh / 2.0 - 0.35, "por defecto", size=6.3,
                 color=BLUE, weight="bold")

    y -= 4.6
    text(ax, 0, y,
         "HEX_CERTIFIED exige 100 % de hexaedros, cero reparaciones y cero "
         "advertencias: si no lo consigue, el build falla en lugar de degradar "
         "a tetraedros en silencio.", size=8.4, color=INK)
    text(ax, 0, y - 4.0,
         "La documentación heredada habla de seis plantillas; desde 4.2 el "
         "código define ocho (keyjoint_core.MESH_TEMPLATES).",
         size=7.8, color=AMBER)
    return save(fig, "dia_malla.png")


# ------------------------------------------------------------------ diagram 11
def dia_release():
    fig, ax, top = canvas(11.6, 5.4)
    text(ax, 0, top - 2.3, "El ejecutable se publica, no se copia",
         size=15.5, weight="bold")
    text(ax, 0, top - 6.2,
         "make_exe.bat construye en un entorno aislado y sólo publica si la "
         "huella del código, el autotest empaquetado y la lista blanca "
         "coinciden.", size=9.0, color=SOFT)

    steps = [
        ("1", "Entorno limpio", "venv nuevo; user-site,\nPYTHONPATH y rutas\nde red anulados"),
        ("2", "Herramientas fijadas", "PyInstaller 6.22.2\nhooks 2026.7\nsólo binarios"),
        ("3", "Aislamiento", "verifica sys.path\ny versiones; compila\nlos 14 módulos"),
        ("4", "Huella previa", "SHA-256 de 31\nentradas + candado\nde la release 4.1"),
        ("5", "Empaquetado", "un .exe con motor,\ncatálogos e i18n\ndentro"),
        ("6", "Publicación", "autotest en el .exe,\nlista blanca, ZIP\ny SHA256SUMS"),
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
    text(ax, 2.2, y2 - 3.0, "El build falla si…", size=9.2, weight="bold")
    text(ax, 2.2, y2 - 6.6,
         "cambia un byte del código tras la huella  ·  el autotest del .exe no "
         "pasa  ·  la release 4.1 protegida se altera", size=7.6, color=SOFT)
    card(ax, 51.5, y2 - 9.4, 48.5, 9.2, fc=PANEL, r=1.2)
    text(ax, 53.7, y2 - 3.0, "Lo que nunca entra en el paquete", size=9.2,
         weight="bold")
    text(ax, 53.7, y2 - 6.6,
         "documentos DIN o FVA con licencia  ·  resultados .odb/.cae de un caso "
         " ·  el directorio dist histórico", size=7.6, color=SOFT)
    return save(fig, "dia_release.png")


# ------------------------------------------------------------------ diagram 12
def dia_tabs():
    fig, ax, top = canvas(11.6, 3.1)
    tabs = [
        ("1", "Proyecto", "nombre, autor, idioma\nruta de Abaqus"),
        ("2", "Geometría DIN", "d1, L/d1, ranura, radios\ny el derivado en vivo"),
        ("3", "Malla y materiales", "plantilla, orden, seeds\npreajustes C45"),
        ("4", "Análisis", "contacto, torsión\nestudio de convergencia"),
        ("5", "DIN 6892 / FVA", "método, factores, N_W\nMétodo A y MATLAB"),
        ("6", "Ejecutar y evidencias", "log en vivo, artefactos\nabrir informe"),
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
    text(ax, 0, top - 2.3, "Estado real y lo que queda por decidir",
         size=15.5, weight="bold")

    blocks = [
        ("VERIFICADO", GREEN, [
            "autotest empaquetado: 0 errores, 0 advertencias",
            "params_default.json idéntico a core.default_params()",
            "los 4 presets validan con esquema 6",
            "compatibilidad Python 2.7 auditada módulo a módulo",
            "999,18 N·m fijado en el autotest, gobierna el cubo",
        ]),
        ("PENDIENTE DE TU DECISIÓN", AMBER, [
            "signo de la ecuación 9 contra el texto DIN con licencia",
            "número de versión: 4.2 ya publicado con otra física",
            "plantilla de malla: la GUI fuerza FVA_METHOD_A_HYBRID",
            "publicar o no el cuarto preset (10 LW solve)",
        ]),
        ("FUERA DE ALCANCE HOY", "#4B5563", [
            "ninguna corrida de solver 4.2 ni especimen FVA exacto",
            "Método A sigue exigiendo un ODB externo resuelto",
            "K_λ, K_R, f_H y f_S siguen en 1,0 sin el texto con licencia",
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
         "El ejecutable publicado en release/ModelBuilder_4.2 es anterior a las "
         "dos correcciones: 17 de 31 entradas del manifiesto han cambiado desde "
         "aquel build.", size=8.4, color=INK)
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
}


def main():
    wanted = sys.argv[1:] or list(DIAGRAMS)
    print("rendering %d diagram(s)" % len(wanted))
    for name in wanted:
        if name not in DIAGRAMS:
            raise SystemExit("unknown diagram %r" % name)
        DIAGRAMS[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
