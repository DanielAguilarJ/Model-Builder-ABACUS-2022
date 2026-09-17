# -*- coding: utf-8 -*-
"""Build the Model Builder 4.2 presentation (16:9, Keynote-style).

All figures come from /projects/sandbox/assets (real screenshots, real Abaqus
renders, diagrams rendered from live engine values).

The deck exists in Spanish and English from one source: L(es, en) picks the
wording and MB_LANG picks the language, so the layout is fixed in one place.

    MB_LANG=es python3 make_deck.py
    MB_LANG=en python3 make_deck.py
"""
from __future__ import annotations

import os

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ASSETS = "/projects/sandbox/assets"
LANG = os.environ.get("MB_LANG", "es")


def L(es_text, en_text):
    """Pick the wording for the active language."""
    return en_text if LANG == "en" else es_text


DIAGRAMS = os.path.join(ASSETS, "trimmed" if LANG == "es" else "trimmed_%s" % LANG)
FRAMED = os.path.join(ASSETS, "framed" if LANG == "es" else "framed_%s" % LANG)
OUTPUT = os.path.join(
    "/projects/sandbox/Model-Builder-ABACUS-2022/presentation",
    L("ModelBuilder_4.2_Presentacion.pptx", "ModelBuilder_4.2_Presentation.pptx"))

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.85)
CONTENT_W = Inches(13.333 - 1.7)

FONT = "Arial"
INK = RGBColor(0x1D, 0x1D, 0x1F)
SOFT = RGBColor(0x6E, 0x6E, 0x73)
MUTED = RGBColor(0x86, 0x86, 0x8B)
LINE = RGBColor(0xD2, 0xD2, 0xD7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
NEAR_WHITE = RGBColor(0xF5, 0xF5, 0xF7)
BLACK = RGBColor(0x0A, 0x0A, 0x0C)
BLUE = RGBColor(0x00, 0x71, 0xE3)
BLUE_DARK = RGBColor(0x29, 0x97, 0xFF)
GREEN = RGBColor(0x1B, 0x5E, 0x20)
AMBER = RGBColor(0x8A, 0x4B, 0x08)
RED = RGBColor(0xB7, 0x1C, 0x1C)
GREY_TEXT = RGBColor(0x9E, 0x9E, 0xA7)


# ---------------------------------------------------------------- primitives
def new_deck():
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def add_slide(prs, background=WHITE):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = background
    return slide


def textbox(slide, left, top, width, height, align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    frame.paragraphs[0].alignment = align
    return box, frame


def write(frame, blocks, first_paragraph=None):
    for index, block in enumerate(blocks):
        if index == 0 and first_paragraph is not None:
            paragraph = first_paragraph
        elif index == 0:
            paragraph = frame.paragraphs[0]
        else:
            paragraph = frame.add_paragraph()
        paragraph.alignment = block.get("align", PP_ALIGN.LEFT)
        if block.get("space_before") is not None:
            paragraph.space_before = Pt(block["space_before"])
        if block.get("space_after") is not None:
            paragraph.space_after = Pt(block["space_after"])
        paragraph.line_spacing = block.get("spacing", 1.0)
        run = paragraph.add_run()
        run.text = block["text"]
        font = run.font
        font.name = block.get("font", FONT)
        font.size = Pt(block["size"])
        font.bold = block.get("bold", False)
        font.color.rgb = block.get("color", INK)
    return frame


def rule(slide, left, top, width, color=LINE, weight=1.0):
    """A hairline separator. weight is in points."""
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width,
                                   Pt(weight))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def panel(slide, left, top, width, height, color=NEAR_WHITE, radius=0.035):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top,
                                   width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    shape.adjustments[0] = radius
    return shape


def picture_fit(slide, path, box_left, box_top, box_width, box_height,
                align="center"):
    """Place an image scaled to fit the box, preserving the aspect ratio."""
    with Image.open(path) as image:
        aspect = image.size[0] / float(image.size[1])
    box_aspect = box_width / float(box_height)
    if aspect >= box_aspect:
        width = box_width
        height = Emu(int(box_width / aspect))
    else:
        height = box_height
        width = Emu(int(box_height * aspect))
    left = box_left if align == "left" else Emu(
        int(box_left + (box_width - width) / 2))
    top = Emu(int(box_top + (box_height - height) / 2))
    return slide.shapes.add_picture(path, left, top, width=width, height=height)


def slide_number(slide, index, dark=False):
    box, frame = textbox(slide, Emu(int(SLIDE_W - MARGIN - Inches(1.0))),
                         Inches(6.94), Inches(1.0), Inches(0.3),
                         align=PP_ALIGN.RIGHT)
    write(frame, [{"text": "%02d" % index, "size": 10,
                   "color": GREY_TEXT if dark else MUTED}])
    return box


def kicker(slide, text, dark=False, color=None):
    box, frame = textbox(slide, MARGIN, Inches(0.62), CONTENT_W, Inches(0.32))
    write(frame, [{"text": text.upper(), "size": 11.5, "bold": True,
                   "color": color or (BLUE_DARK if dark else BLUE)}])
    return box


def heading(slide, text, top=Inches(1.02), size=33, color=None, width=None):
    box, frame = textbox(slide, MARGIN, top, width or CONTENT_W, Inches(1.0))
    write(frame, [{"text": text, "size": size, "bold": True,
                   "color": color or INK, "spacing": 0.95}])
    return box


def subheading(slide, text, top=Inches(1.86), size=14.5, color=None,
               width=None):
    box, frame = textbox(slide, MARGIN, top, width or Inches(10.4), Inches(0.9))
    write(frame, [{"text": text, "size": size, "color": color or SOFT,
                   "spacing": 1.25}])
    return box


def caption(slide, text, top=Inches(6.62), size=11.5, color=None, width=None):
    box, frame = textbox(slide, MARGIN, top, width or Inches(11.0), Inches(0.7))
    write(frame, [{"text": text, "size": size, "color": color or MUTED,
                   "spacing": 1.25}])
    return box


# -------------------------------------------------------------- slide recipes
def slide_hero(prs):
    slide = add_slide(prs, BLACK)
    box, frame = textbox(slide, MARGIN, Inches(2.18), Inches(11.0), Inches(3.2))
    write(frame, [
        {"text": "Model Builder 4.2", "size": 62, "bold": True, "color": WHITE,
         "spacing": 0.92},
        {"text": L("Automatización trazable de uniones eje–cubo con chaveta\n"
                   "para Abaqus 2022",
                   "Traceable automation of shaft–hub key joints\n"
                   "for Abaqus 2022"),
         "size": 21, "color": GREY_TEXT, "spacing": 1.3, "space_before": 16},
    ])
    box2, frame2 = textbox(slide, MARGIN, Inches(6.28), Inches(11.5), Inches(0.8))
    write(frame2, [
        {"text": L("DIN 6885-1  ·  DIN 6892 Métodos A / B / C  ·  FVA 600 III",
                   "DIN 6885-1  ·  DIN 6892 Methods A / B / C  ·  FVA 600 III"),
         "size": 12.5, "color": RGBColor(0x7C, 0x7C, 0x86), "bold": True},
    ])
    slide_number(slide, 1, dark=True)
    return slide


def slide_problema(prs):
    slide = add_slide(prs, BLACK)
    kicker(slide, L("el problema", "the problem"), dark=True)
    box, frame = textbox(slide, MARGIN, Inches(1.55), Inches(11.4), Inches(3.4))
    write(frame, [
        {"text": L("Un modelo de chavetero bien hecho\nno es difícil: es "
                   "difícil de repetir.",
                   "A good keyway model is not the hard part.\nRepeating it "
                   "is."),
         "size": 40, "bold": True, "color": WHITE, "spacing": 1.05},
    ])
    items = [
        (L("Cada modelo se rehacía a mano", "Every model was rebuilt by hand"),
         L("la tabla DIN se consultaba en papel y se teclaba caso por caso",
           "the DIN table was read on paper and typed in case by case")),
        (L("La malla dependía del autor", "The mesh depended on its author"),
         L("sin criterio de aceptación explícito ni registro de intentos",
           "with no explicit acceptance criterion and no record of attempts")),
        (L("El resultado no se podía auditar", "The result could not be audited"),
         L("sin saber qué versión, qué norma y qué hipótesis lo produjeron",
           "with no way to know which version, standard and assumptions "
           "produced it")),
    ]
    for index, (title, body) in enumerate(items):
        left = Emu(int(MARGIN + index * Inches(3.83)))
        box, frame = textbox(slide, left, Inches(5.15), Inches(3.55), Inches(1.6))
        write(frame, [
            {"text": title, "size": 15, "bold": True, "color": WHITE,
             "spacing": 1.15},
            {"text": body, "size": 12, "color": GREY_TEXT, "spacing": 1.3,
             "space_before": 7},
        ])
        rule(slide, left, Inches(4.86), Inches(0.9), color=BLUE_DARK, weight=2.0)
    slide_number(slide, 2, dark=True)
    return slide


def slide_kpis(prs):
    slide = add_slide(prs)
    kicker(slide, L("qué es", "what it is"))
    heading(slide, L("Una sola herramienta desde la tabla de la norma\nhasta el "
                     "informe firmado",
                     "One tool, from the table in the standard\nto the signed "
                     "report"), size=31)
    kpis = [
        ("14", L("módulos de Python", "Python modules"),
         L("escritorio, kernel de Abaqus\ny núcleo compartido",
           "desktop, Abaqus kernel\nand the shared core")),
        ("26", L("filas DIN 6885-1", "DIN 6885-1 rows"),
         L("transcritas sin extrapolar,\n6 < d1 ≤ 500 mm",
           "transcribed with no extrapolation,\n6 < d1 ≤ 500 mm")),
        ("8", L("plantillas de malla", "mesh templates"),
         L("con puertas de calidad duras\ny presupuesto de elementos",
           "with hard quality gates\nand element budgets")),
        ("4", L("métodos DIN 6892", "DIN 6892 methods"),
         L("A, B, B-FVA y C, calculados\nen paralelo",
           "A, B, B-FVA and C, evaluated\nin parallel")),
        ("3", L("idiomas", "languages"),
         L("español, inglés y alemán\n650 claves con paridad",
           "Spanish, English and German\n650 keys at parity")),
    ]
    top = Inches(2.95)
    width = Inches(2.12)
    gap = Inches(0.28)
    for index, (number, label, note) in enumerate(kpis):
        left = Emu(int(MARGIN + index * (width + gap)))
        rule(slide, left, top, Inches(1.5), color=LINE)
        box, frame = textbox(slide, left, Emu(int(top + Inches(0.28))), width,
                             Inches(2.6))
        write(frame, [
            {"text": number, "size": 46, "bold": True, "color": INK,
             "spacing": 0.9},
            {"text": label, "size": 13.5, "bold": True, "color": INK,
             "spacing": 1.15, "space_before": 4},
            {"text": note, "size": 11, "color": MUTED, "spacing": 1.3,
             "space_before": 6},
        ])
    caption(slide, L("Todo lo que se ve en estas diapositivas sale de ejecutar "
                     "el código: las capturas son de la aplicación real y las "
                     "cifras las calcula el motor empaquetado.",
                     "Everything on these slides comes from running the code: "
                     "the screenshots are of the real application and the "
                     "figures are computed by the packaged engine."),
            top=Inches(6.45))
    slide_number(slide, 3)
    return slide


def slide_diagram(prs, index, image, kicker_text=None, caption_text=None,
                  background=WHITE, top=Inches(1.28), bottom=Inches(6.45)):
    slide = add_slide(prs, background)
    if kicker_text:
        kicker(slide, kicker_text)
    box_top = top if kicker_text else Inches(0.95)
    picture_fit(slide, os.path.join(DIAGRAMS, image), MARGIN, box_top,
                CONTENT_W, Emu(int(bottom - box_top)))
    if caption_text:
        caption(slide, caption_text, top=Inches(6.58))
    slide_number(slide, index)
    return slide


def slide_shot(prs, index, image, kicker_text, title, body, caption_text=None):
    slide = add_slide(prs)
    kicker(slide, kicker_text)
    text_w = Inches(4.25)
    box, frame = textbox(slide, MARGIN, Inches(1.12), text_w, Inches(4.8))
    blocks = [{"text": title, "size": 26, "bold": True, "color": INK,
               "spacing": 1.0}]
    for paragraph in body:
        blocks.append({"text": paragraph, "size": 12.5, "color": SOFT,
                       "spacing": 1.35, "space_before": 12})
    write(frame, blocks)
    picture_fit(slide, os.path.join(FRAMED, image), Inches(5.32), Inches(0.72),
                Inches(7.45), Inches(6.06))
    if caption_text:
        box2, frame2 = textbox(slide, MARGIN, Inches(6.35), text_w, Inches(0.8))
        write(frame2, [{"text": caption_text, "size": 10.5, "color": MUTED,
                        "spacing": 1.3}])
    slide_number(slide, index)
    return slide


def slide_render(prs, index, image, kicker_text, title, body, dark=True):
    slide = add_slide(prs, BLACK if dark else WHITE)
    kicker(slide, kicker_text, dark=dark)
    box, frame = textbox(slide, MARGIN, Inches(1.12), Inches(4.2), Inches(4.6))
    blocks = [{"text": title, "size": 28, "bold": True,
               "color": WHITE if dark else INK, "spacing": 1.0}]
    for paragraph in body:
        blocks.append({"text": paragraph, "size": 12.5,
                       "color": GREY_TEXT if dark else SOFT, "spacing": 1.35,
                       "space_before": 13})
    write(frame, blocks)
    picture_fit(slide, os.path.join(FRAMED, image), Inches(5.35), Inches(0.75),
                Inches(7.4), Inches(6.0))
    slide_number(slide, index, dark=dark)
    return slide


def slide_din6885(prs, index):
    slide = add_slide(prs)
    kicker(slide, L("el dato normativo", "the normative datum"))
    heading(slide, L("La tabla no se interpola: o hay fila, o hay error",
                     "The table is never interpolated: either a row or an "
                     "error"), size=31)
    subheading(slide, L("din6885_row() devuelve la fila exacta con su etiqueta "
                        "NORMATIVE. Fuera del rango de la norma lanza una "
                        "excepción, para que nadie pueda declarar conformidad "
                        "DIN con la fila más parecida.",
                        "din6885_row() returns the exact row with its "
                        "NORMATIVE badge. Outside the range of the standard it "
                        "raises, so nobody can claim DIN compliance from the "
                        "nearest row."))
    cards = [
        ("26", L("filas de sección", "cross-section rows"),
         L("b × h, t1, t2, tolerancia de t1 y el incremento d2 para cada banda "
           "de diámetro",
           "b × h, t1, t2, the t1 tolerance and the d2 increment for every "
           "diameter band")),
        ("34", L("longitudes normalizadas", "standard lengths"),
         L("de 6 a 400 mm; la chaveta se ajusta hacia abajo, nunca hacia "
           "arriba",
           "from 6 to 400 mm; the key is snapped down, never up")),
        ("7", L("bandas de radios", "radius bands"),
         L("r1 de boca y r2 de fondo por separado: no son el mismo radio",
           "mouth r1 and root r2 separately: they are not the same radius")),
        ("3", L("formas implementadas", "forms implemented"),
         L("A, B y AB. De C a J se rechazan con un mensaje propio, no en "
           "silencio",
           "A, B and AB. C through J are rejected with their own message, not "
           "silently")),
    ]
    top = Inches(3.05)
    height = Inches(1.78)
    width = Inches(2.78)
    gap = Inches(0.17)
    for index_card, (number, label, note) in enumerate(cards):
        left = Emu(int(MARGIN + index_card * (width + gap)))
        panel(slide, left, top, width, height)
        box, frame = textbox(slide, Emu(int(left + Inches(0.26))),
                             Emu(int(top + Inches(0.22))),
                             Emu(int(width - Inches(0.5))), Inches(1.42))
        write(frame, [
            {"text": number + "   " + label, "size": 14.5, "bold": True,
             "color": INK, "spacing": 1.05},
            {"text": note, "size": 10.5, "color": SOFT, "spacing": 1.3,
             "space_before": 6},
        ])
    box, frame = textbox(slide, MARGIN, Inches(5.18), CONTENT_W, Inches(1.4))
    write(frame, [
        {"text": L("D40, la fila de referencia del proyecto",
                   "D40, the project's reference row"),
         "size": 15, "bold": True, "color": INK},
        {"text": L("38 < d1 ≤ 44 mm     b × h = 12 × 8 mm     "
                   "t1 = 5,00 +0,20 mm     t2 = 3,30 mm     "
                   "d2(ref) = 48,00 mm     r1 = 0,25…0,40 mm     "
                   "r2 = 0,16…0,25 mm",
                   "38 < d1 ≤ 44 mm     b × h = 12 × 8 mm     "
                   "t1 = 5.00 +0.20 mm     t2 = 3.30 mm     "
                   "d2(ref) = 48.00 mm     r1 = 0.25…0.40 mm     "
                   "r2 = 0.16…0.25 mm"),
         "size": 13, "color": SOFT, "font": "Consolas", "space_before": 10,
         "spacing": 1.35},
    ])
    caption(slide, L("El chaflán de la chaveta no está en la tabla: es un "
                     "parámetro del usuario (c = 0,8 mm por defecto) y así se "
                     "declara en el informe.",
                     "The key chamfer is not in the table: it is a user "
                     "parameter (c = 0.8 mm by default) and the report says "
                     "so."), top=Inches(6.5))
    slide_number(slide, index)
    return slide


def slide_verificacion(prs, index):
    slide = add_slide(prs)
    kicker(slide, L("verificación", "verification"))
    heading(slide, L("Lo que se ha comprobado, y cómo",
                     "What has been checked, and how"), size=33)
    left_items = [
        (L("Autotest empaquetado", "Packaged self-test"),
         L("identidad 4.2 y esquema 6, migración 5→6, catálogos DIN y FVA, "
           "cálculos de referencia, seis plantillas de malla, informes en los "
           "tres idiomas. Termina con código 0.",
           "4.2 identity and schema 6, the 5→6 migration, DIN and FVA "
           "catalogues, golden calculations, six mesh templates, reports in "
           "all three languages. Exits with code 0.")),
        (L("Paridad de los tres catálogos", "Parity across the three catalogues"),
         L("650 claves por idioma, sin huecos; cada código de validación tiene "
           "su presentación traducida.",
           "650 keys per language with no gaps; every validation code has its "
           "translated presentation.")),
        (L("Los cuatro presets", "All four presets"),
         L("normalizan y validan con esquema 6 y cero errores, incluido el de "
           "resolución de 10 ciclos.",
           "normalize and validate under schema 6 with zero errors, including "
           "the 10-cycle solving one.")),
    ]
    right_items = [
        (L("Compatibilidad con el kernel", "Compatibility with the kernel"),
         L("los seis módulos que corren dentro de Abaqus se auditaron con AST: "
           "sin f-strings, sin anotaciones, sólo os, sys, json, math, time y "
           "hashlib. División importada del futuro.",
           "the six modules that run inside Abaqus were audited with AST: no "
           "f-strings, no annotations, only os, sys, json, math, time and "
           "hashlib. Division imported from __future__.")),
        (L("Contrato de artefactos", "Artifact contract"),
         L("el proyecto se declara correcto sólo si existen auditoría, "
           "BUILD_RESULT, CAE, capturas e informe, y si la malla realizada "
           "coincide con la planificada.",
           "a project is declared sound only if the audit, BUILD_RESULT, CAE, "
           "screenshots and report all exist, and the realised mesh matches "
           "the planned one.")),
        (L("Cifras fijadas en el test", "Figures locked in the test"),
         L("999,18 N·m gobernado por el cubo, t2tr = 3,141 mm, f_W de la "
           "ecuación 3 y el dominio de K_λ.",
           "999.18 N·m hub-governed, t2tr = 3.141 mm, f_W from equation 3 and "
           "the K_λ domain.")),
    ]
    for column, items in enumerate((left_items, right_items)):
        left = Emu(int(MARGIN + column * Inches(5.95)))
        top = Inches(2.35)
        for title, body in items:
            rule(slide, left, top, Inches(0.75), color=GREEN, weight=2.2)
            box, frame = textbox(slide, left, Emu(int(top + Inches(0.2))),
                                 Inches(5.4), Inches(1.4))
            write(frame, [
                {"text": title, "size": 15, "bold": True, "color": INK,
                 "spacing": 1.1},
                {"text": body, "size": 11.5, "color": SOFT, "spacing": 1.32,
                 "space_before": 6},
            ])
            top = Emu(int(top + Inches(1.42)))
    caption(slide, L("Lo que el autotest no hace, y así lo declara: no arranca "
                     "Abaqus, no resuelve, no compila LaTeX y no valida un "
                     "especimen FVA.",
                     "What the self-test does not do, and says so: it does not "
                     "start Abaqus, does not solve, does not compile LaTeX and "
                     "does not validate an FVA specimen."), top=Inches(6.72))
    slide_number(slide, index)
    return slide


def slide_pasos(prs, index):
    slide = add_slide(prs, BLACK)
    kicker(slide, L("próximos pasos", "next steps"), dark=True)
    heading(slide, L("Tres decisiones y una compilación",
                     "Three decisions and one build"), size=36, color=WHITE)
    steps = [
        ("01", L("Reconstruir el ejecutable", "Rebuild the executable"),
         L("make_exe.bat, sin cambios, desde el árbol completo del proyecto. "
           "El .exe publicado es anterior a las dos correcciones: 17 de 31 "
           "entradas del manifiesto han cambiado.",
           "make_exe.bat, unchanged, from the full project tree. The published "
           ".exe predates both corrections: 17 of the 31 manifest entries have "
           "changed.")),
        ("02", L("Fijar el signo de la ecuación 9",
                 "Settle the sign of equation 9"),
         L("contra el texto DIN 6892 con licencia. Si el signo negativo es el "
           "correcto, el par admisible real baja otro 46 %.",
           "against the licensed DIN 6892 text. If the minus sign is right, "
           "the real allowable torque drops another 46 %.")),
        ("03", L("Numerar la versión", "Number the version"),
         L("dos ejecutables que se identifican como 4.2 y devuelven pares "
           "distintos son una colisión de identidad. Mi recomendación es 4.3.",
           "two executables that both report 4.2 and return different torques "
           "are an identity collision. My recommendation is 4.3.")),
    ]
    top = Inches(2.7)
    for number, title, body in steps:
        box, frame = textbox(slide, MARGIN, top, Inches(1.0), Inches(0.6))
        write(frame, [{"text": number, "size": 17, "bold": True,
                       "color": BLUE_DARK}])
        box2, frame2 = textbox(slide, Inches(1.95), top, Inches(10.5), Inches(1.3))
        write(frame2, [
            {"text": title, "size": 19, "bold": True, "color": WHITE,
             "spacing": 1.05},
            {"text": body, "size": 12.5, "color": GREY_TEXT, "spacing": 1.35,
             "space_before": 7},
        ])
        rule(slide, MARGIN, Emu(int(top - Inches(0.24))), CONTENT_W,
             color=RGBColor(0x2A, 0x2A, 0x30))
        top = Emu(int(top + Inches(1.42)))
    slide_number(slide, index, dark=True)
    return slide


def slide_cierre(prs, index):
    slide = add_slide(prs, BLACK)
    box, frame = textbox(slide, MARGIN, Inches(2.5), Inches(11.0), Inches(2.6))
    write(frame, [
        {"text": L("El valor no está en el modelo.\nEstá en poder demostrar "
                   "cómo se hizo.",
                   "The value is not the model.\nIt is being able to show how "
                   "it was made."),
         "size": 36, "bold": True, "color": WHITE, "spacing": 1.1},
    ])
    box2, frame2 = textbox(slide, MARGIN, Inches(5.6), Inches(11.0), Inches(1.2))
    write(frame2, [
        {"text": L("Model Builder 4.2  ·  esquema de parámetros 6  ·  "
                   "din6892-methods-1.0  ·  auto-mesh-2.0",
                   "Model Builder 4.2  ·  parameter schema 6  ·  "
                   "din6892-methods-1.0  ·  auto-mesh-2.0"),
         "size": 12.5, "color": GREY_TEXT},
        {"text": L("Cada número de esta presentación es reproducible "
                   "ejecutando el código del repositorio.",
                   "Every number in this deck is reproducible by running the "
                   "code in the repository."),
         "size": 12.5, "color": RGBColor(0x7C, 0x7C, 0x86), "space_before": 8},
    ])
    slide_number(slide, index, dark=True)
    return slide


# ------------------------------------------------------------------ assembly
def build():
    prs = new_deck()

    slide_hero(prs)
    slide_problema(prs)
    slide_kpis(prs)

    slide_diagram(prs, 4, "dia_arquitectura.png",
                  L("arquitectura", "architecture"),
                  L("Un cambio en la tabla DIN o en un factor de DIN 6892 se "
                    "escribe una sola vez y llega a los dos intérpretes.",
                    "A change to the DIN table or to a DIN 6892 factor is "
                    "written once and reaches both interpreters."))
    slide_diagram(prs, 5, "dia_tabs.png", L("cómo se usa", "how it is used"),
                  L("Seis pestañas en el orden en que se toman las decisiones: "
                    "primero el proyecto, después la geometría normativa, y "
                    "sólo al final la ejecución.",
                    "Six tabs in the order the decisions are actually made: "
                    "the project first, then the normative geometry, and only "
                    "at the end the run."),
                  top=Inches(2.3), bottom=Inches(5.4))

    shots = [
        (6, "gui_01_proyecto.png", L("pestaña 1", "tab 1"),
         L("Proyecto", "Project"),
         [L("Nombre, autor e idioma quedan grabados en project.json: el "
            "informe se emite en el idioma del proyecto, no en el de quien lo "
            "abre.",
            "Name, author and language are recorded in project.json: the "
            "report is issued in the project's language, not in the language "
            "of whoever opens it."),
          L("La ruta de Abaqus se detecta buscando los lanzadores instalados, "
            "sin ejecutar ninguno.",
            "The Abaqus path is detected by looking for installed launchers, "
            "without executing any of them."),
          L("La carpeta raíz por defecto es Documentos/ModelBuilder Projects.",
            "The default root folder is Documents/ModelBuilder Projects.")],
         L("Captura real de la aplicación, idioma por defecto español.",
           "Real capture of the application, with the interface switched to "
           "English.")),
        (7, "gui_02_geometria_din.png", L("pestaña 2", "tab 2"),
         L("Geometría DIN", "DIN geometry"),
         [L("A la izquierda, los pocos parámetros independientes que el "
            "usuario decide. A la derecha, todo lo que la norma deriva de "
            "ellos.",
            "On the left, the few independent parameters the user decides. On "
            "the right, everything the standard derives from them."),
          L("El panel derecho se recalcula al teclear: fila DIN, longitudes, "
            "cubo, plan de malla y la lista de validación completa.",
            "The right panel recomputes as you type: DIN row, lengths, hub, "
            "mesh plan and the complete validation list."),
          L("La etiqueta NORMATIVE en verde indica que la geometría está "
            "dentro del sobre de la norma.",
            "The green NORMATIVE badge means the geometry sits inside the "
            "envelope of the standard.")],
         L("d1 = 40 mm  ·  banda 38 < d1 ≤ 44  ·  b × h = 12 × 8  ·  "
           "DIN 6885-1 Form A 12 × 8 × 50.",
           "d1 = 40 mm  ·  band 38 < d1 ≤ 44  ·  b × h = 12 × 8  ·  "
           "DIN 6885-1 Form A 12 × 8 × 50.")),
        (8, "gui_03_malla_materiales.png", L("pestaña 3", "tab 3"),
         L("Malla y materiales", "Mesh and materials"),
         [L("La plantilla se elige por nombre; el modo AUTO compara candidatos "
            "completos por pieza y conserva el ganador.",
            "The template is chosen by name; AUTO mode compares complete "
            "candidates per part and keeps the winner."),
          L("Las semillas en 0 significan automático: D/32 en el eje, b/20 en "
            "la chaveta, d_a/80 en el cubo.",
            "Seeds left at 0 mean automatic: D/32 on the shaft, b/20 on the "
            "key, d_a/80 on the hub."),
          L("El criterio rápido de presión está marcado CORE-SCREENING: es "
            "plausibilidad, no DIN 6892 Método B.",
            "The quick pressure check is badged CORE-SCREENING: it is "
            "plausibility, not DIN 6892 Method B.")],
         L("Aquí la plantilla es HEX_CERTIFIED, en modo auto y con 3 intentos.",
           "Here the template is HEX_CERTIFIED, in auto mode with 3 "
           "attempts.")),
        (9, "gui_04_analisis.png", L("pestaña 4", "tab 4"),
         L("Análisis", "Analysis"),
         [L("El análisis es opcional y está desactivado por defecto: construir "
            "y auditar no requiere resolver.",
            "The analysis is optional and off by default: building and "
            "auditing does not require solving."),
          L("Si se activa, se crea contacto general, un step estático TORSION "
            "y un momento sobre el punto de referencia del extremo motriz.",
            "When enabled it creates general contact, a static TORSION step "
            "and a moment on the reference point of the drive end."),
          L("El estudio de convergencia de malla se lanza aparte y escribe su "
            "propio CSV.",
            "The mesh convergence study runs separately and writes its own "
            "CSV.")],
         L("Crear el job y enviarlo al solver son dos casillas distintas.",
           "Creating the job and submitting it to the solver are two separate "
           "checkboxes.")),
        (10, "gui_05_din6892_fva.png", L("pestaña 5", "tab 5"),
         "DIN 6892 / FVA",
         [L("El método se elige explícitamente. Los factores licenciados que "
            "no se pueden transcribir se quedan en 1,0 y el resultado se marca "
            "PROVISIONAL_FACTORS.",
            "The method is chosen explicitly. Licensed factors that cannot be "
            "transcribed stay at 1.0 and the result is flagged "
            "PROVISIONAL_FACTORS."),
          L("N_W en blanco significa deducir de la razón de carga R; con un "
            "par pulsante da cero inversiones y f_W = 1.",
            "N_W left blank means derive it from the load ratio R; a "
            "pulsating torque gives zero reversals and f_W = 1."),
          L("El Método A no se calcula aquí: se importa un CSV de un ODB ya "
            "resuelto, con SHA-256 y cobertura verificadas.",
            "Method A is not computed here: a CSV from an already solved ODB "
            "is imported, with SHA-256 and coverage verified.")],
         L("Las normas seleccionadas se declaran una por una, incluidas las "
           "que no están implementadas.",
           "The selected standards are declared one by one, including the ones "
           "that are not implemented.")),
        (11, "gui_06_ejecutar_evidencias.png", L("pestaña 6", "tab 6"),
         L("Ejecutar y evidencias", "Run and evidence"),
         [L("El log de Abaqus se transmite en vivo a la ventana y al archivo "
            "logs/abaqus.log, con el comando y el directorio de trabajo en la "
            "cabecera.",
            "The Abaqus log is streamed live to the window and to "
            "logs/abaqus.log, with the command and the working directory in "
            "the header."),
          L("Al terminar, la lista de artefactos se rellena con tamaño y "
            "etiqueta de evidencia; los botones abren el proyecto, el informe "
            "y el modelo.",
            "When it finishes, the artifact list fills in with size and "
            "evidence badge; the buttons open the project, the report and the "
            "model."),
          L("Detener mata el árbol de procesos del solver y marca el proyecto "
            "como CANCELLED.",
            "Stop kills the solver process tree and marks the project "
            "CANCELLED.")],
         L("Ningún archivo de solver cae junto al ejecutable: el subproceso "
           "corre con cwd = jobs/.",
           "No solver file lands next to the executable: the subprocess runs "
           "with cwd = jobs/.")),
        (12, "gui_07_validacion.png",
         L("control de calidad", "quality control"),
         L("La validación habla en códigos", "Validation speaks in codes"),
         [L("Cada aviso tiene un código estable, un mensaje canónico en inglés "
            "y una presentación traducida. El código es el que se cita en el "
            "informe y en una revisión.",
            "Every issue has a stable code, a canonical English message and a "
            "translated presentation. The code is what gets cited in the "
            "report and in a review."),
          L("El diálogo informa el resultado, no lo adorna: sin errores, el "
            "recuento de advertencias y el recordatorio de que el cálculo "
            "resistente sigue etiquetado CORE-SCREENING.",
            "The dialog reports the outcome, it does not dress it up: no "
            "errors, the warning count, and the reminder that the strength "
            "calculation stays labelled CORE-SCREENING."),
          L("Un error bloquea la construcción antes de tocar Abaqus; una "
            "advertencia informa y queda registrada en la auditoría.",
            "An error blocks the build before Abaqus is touched; a warning "
            "informs and is recorded in the audit.")],
         L("Por defecto: 0 errores y 3 advertencias — un factor licenciado "
           "todavía neutro, la ecuación 9 optimista y una relación de aspecto "
           "axial alta esperada en la entalla.",
           "By default: 0 errors and 3 warnings — a licensed factor still "
           "neutral, the optimistic equation 9, and a high axial aspect ratio "
           "expected at the notch.")),
    ]
    for args in shots:
        slide_shot(prs, args[0], args[1], args[2], args[3], args[4], args[5])

    slide_diagram(prs, 13, "dia_pipeline.png",
                  L("flujo de ejecución", "execution flow"))
    slide_diagram(prs, 14, "dia_workspace.png",
                  L("lo que queda en disco", "what stays on disk"))

    slide_render(prs, 15, "model_assembly_hex.png",
                 L("el resultado", "the result"),
                 L("Sólidos, no cascarones", "Solids, not shells"),
                 [L("Eje, chaveta y cubo se construyen como volúmenes "
                    "independientes y se ensamblan con las tolerancias de la "
                    "norma.",
                    "Shaft, key and hub are built as independent solids and "
                    "assembled with the tolerances of the standard."),
                  L("La malla es hexaédrica y coincidente en las interfaces "
                    "que transmiten carga.",
                    "The mesh is hexahedral and matching on the interfaces "
                    "that carry load."),
                  L("La captura es la imagen que el propio motor guarda en "
                    "screenshots/ al terminar.",
                    "This is the image the engine itself saves to "
                    "screenshots/ when it finishes.")])
    slide_render(prs, 16, "model_notch_section.png",
                 L("el detalle que importa", "the detail that matters"),
                 L("La banda del chavetero", "The keyway band"),
                 [L("En la sección se ve la banda de elementos más finos que "
                    "rodea la ranura: no es una malla uniforme más densa, es "
                    "refinamiento donde está el gradiente.",
                    "The section shows the band of finer elements around the "
                    "keyway: not a uniformly denser mesh, but refinement where "
                    "the gradient is."),
                  L("El ancho de la banda y el número de elementos sobre el "
                    "arco del radio r2 son parámetros, y la auditoría "
                    "comprueba que se hayan cumplido.",
                    "The band width and the number of elements across the r2 "
                    "fillet arc are parameters, and the audit checks that they "
                    "were honoured."),
                  L("El conjunto de elementos NOTCH_SHAFT se construye "
                    "alrededor de las dos esquinas del chavetero para que la "
                    "consulta de concentración no se vaya a otro punto "
                    "caliente.",
                    "The NOTCH_SHAFT element set is built around both keyway "
                    "corners so the stress-concentration query cannot wander "
                    "off to an unrelated hot spot.")],
                 dark=False)

    slide_diagram(prs, 17, "dia_malla.png", L("política de malla", "mesh policy"))
    slide_diagram(prs, 18, "dia_badges.png", L("trazabilidad", "traceability"))
    slide_din6885(prs, 19)
    slide_diagram(prs, 20, "dia_metodos.png",
                  L("capacidad resistente", "load capacity"))
    slide_diagram(prs, 21, "chart_pares.png", L("resultados", "results"))
    slide_diagram(prs, 22, "dia_t2tr.png",
                  L("corrección 1 de 2", "correction 1 of 2"))
    slide_diagram(prs, 23, "chart_fw.png",
                  L("corrección 2 de 2", "correction 2 of 2"))
    slide_diagram(prs, 24, "dia_eq9.png", L("hallazgo abierto", "open finding"))
    slide_verificacion(prs, 25)
    slide_diagram(prs, 26, "dia_release.png", L("distribución", "distribution"))
    slide_diagram(prs, 27, "dia_estado.png", L("estado", "status"))
    slide_pasos(prs, 28)
    slide_cierre(prs, 29)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    prs.save(OUTPUT)
    print("saved %s" % OUTPUT)
    print("slides: %d  language: %s" % (len(prs.slides._sldIdLst), LANG))
    return OUTPUT


if __name__ == "__main__":
    build()
