# -*- coding: utf-8 -*-
"""Build the Model Builder 4.2 presentation (16:9, Keynote-style).

All figures come from /projects/sandbox/assets (real screenshots, real Abaqus
renders, diagrams rendered from live engine values). Text is Spanish.
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
DIAGRAMS = os.path.join(ASSETS, "trimmed")
FRAMED = os.path.join(ASSETS, "framed")
OUTPUT = "/projects/sandbox/Model-Builder-ABACUS-2022/presentation/ModelBuilder_4.2_Presentacion.pptx"

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
    """blocks: list of dicts with text/size/color/bold/space_before/spacing."""
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


def chip(slide, left, top, label, color, text_color=WHITE, size=10.5):
    width = Inches(0.16 * len(label) * (size / 10.5) + 0.34)
    height = Inches(0.30)
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top,
                                   width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    shape.adjustments[0] = 0.5
    frame = shape.text_frame
    frame.word_wrap = False
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = label
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = text_color
    return shape, width


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
    if align == "left":
        left = box_left
    else:
        left = Emu(int(box_left + (box_width - width) / 2))
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
    box, frame = textbox(slide, MARGIN, top, width or Inches(10.4),
                         Inches(0.9))
    write(frame, [{"text": text, "size": size, "color": color or SOFT,
                   "spacing": 1.25}])
    return box


def caption(slide, text, top=Inches(6.62), size=11.5, color=None, width=None):
    box, frame = textbox(slide, MARGIN, top, width or Inches(11.0),
                         Inches(0.7))
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
        {"text": "Automatización trazable de uniones eje–cubo con chaveta\n"
                 "para Abaqus 2022", "size": 21, "color": GREY_TEXT,
         "spacing": 1.3, "space_before": 16},
    ])
    box2, frame2 = textbox(slide, MARGIN, Inches(6.28), Inches(11.5),
                           Inches(0.8))
    write(frame2, [
        {"text": "DIN 6885-1  ·  DIN 6892 Métodos A / B / C  ·  FVA 600 III",
         "size": 12.5, "color": RGBColor(0x7C, 0x7C, 0x86), "bold": True},
    ])
    slide_number(slide, 1, dark=True)
    return slide


def slide_problema(prs):
    slide = add_slide(prs, BLACK)
    kicker(slide, "el problema", dark=True)
    box, frame = textbox(slide, MARGIN, Inches(1.55), Inches(11.4), Inches(3.4))
    write(frame, [
        {"text": "Un modelo de chavetero bien hecho\nno es difícil: es difícil "
                 "de repetir.", "size": 40, "bold": True, "color": WHITE,
         "spacing": 1.05},
    ])
    items = [
        ("Cada modelo se rehacía a mano",
         "la tabla DIN se consultaba en papel y se teclaba caso por caso"),
        ("La malla dependía del autor",
         "sin criterio de aceptación explícito ni registro de intentos"),
        ("El resultado no se podía auditar",
         "sin saber qué versión, qué norma y qué hipótesis lo produjeron"),
    ]
    left = MARGIN
    width = Inches(3.55)
    for index, (title, body) in enumerate(items):
        box, frame = textbox(slide, Emu(int(left + index * Inches(3.83))),
                             Inches(5.15), width, Inches(1.6))
        write(frame, [
            {"text": title, "size": 15, "bold": True, "color": WHITE,
             "spacing": 1.15},
            {"text": body, "size": 12, "color": GREY_TEXT, "spacing": 1.3,
             "space_before": 7},
        ])
        rule(slide, Emu(int(left + index * Inches(3.83))), Inches(4.86),
             Inches(0.9), color=BLUE_DARK, weight=2.0)
    slide_number(slide, 2, dark=True)
    return slide


def slide_kpis(prs):
    slide = add_slide(prs)
    kicker(slide, "qué es")
    heading(slide, "Una sola herramienta desde la tabla de la norma\nhasta el "
                   "informe firmado", size=31)
    kpis = [
        ("14", "módulos de Python", "escritorio, kernel de Abaqus\ny núcleo compartido"),
        ("26", "filas DIN 6885-1", "transcritas sin extrapolar,\n"
                                   "6 < d1 ≤ 500 mm"),
        ("8", "plantillas de malla", "con puertas de calidad duras\ny "
                                     "presupuesto de elementos"),
        ("4", "métodos DIN 6892", "A, B, B-FVA y C, calculados\nen paralelo"),
        ("3", "idiomas", "español, inglés y alemán\n650 claves con paridad"),
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
    caption(slide, "Todo lo que se ve en estas diapositivas sale de ejecutar "
                   "el código: las capturas son de la aplicación real y las "
                   "cifras las calcula el motor empaquetado.",
            top=Inches(6.45))
    slide_number(slide, 3)
    return slide


def slide_diagram(prs, index, image, kicker_text=None, caption_text=None,
                  background=WHITE, top=Inches(1.28), bottom=Inches(6.45)):
    slide = add_slide(prs, background)
    if kicker_text:
        kicker(slide, kicker_text)
    box_top = top if kicker_text else Inches(0.95)
    box_height = Emu(int(bottom - box_top))
    picture_fit(slide, os.path.join(DIAGRAMS, image), MARGIN, box_top,
                CONTENT_W, box_height)
    if caption_text:
        caption(slide, caption_text, top=Inches(6.58))
    slide_number(slide, index)
    return slide


def slide_shot(prs, index, image, kicker_text, title, body, caption_text=None):
    """Screenshot on the right, explanation on the left."""
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
    kicker(slide, "el dato normativo")
    heading(slide, "La tabla no se interpola: o hay fila, o hay error", size=31)
    subheading(slide, "din6885_row() devuelve la fila exacta con su etiqueta "
                      "NORMATIVE. Fuera del rango de la norma lanza una "
                      "excepción, para que nadie pueda declarar conformidad "
                      "DIN con la fila más parecida.")
    cards = [
        ("26", "filas de sección", "b × h, t1, t2, tolerancia de t1 y el "
                                   "incremento d2 para cada banda de diámetro"),
        ("34", "longitudes normalizadas", "de 6 a 400 mm; la chaveta se ajusta "
                                          "hacia abajo, nunca hacia arriba"),
        ("7", "bandas de radios", "r1 de boca y r2 de fondo por separado: no "
                                  "son el mismo radio"),
        ("3", "formas implementadas", "A, B y AB. De C a J se rechazan con un "
                                      "mensaje propio, no en silencio"),
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
        {"text": "D40, la fila de referencia del proyecto", "size": 15,
         "bold": True, "color": INK},
        {"text": "38 < d1 ≤ 44 mm     b × h = 12 × 8 mm     t1 = 5,00 +0,20 mm"
                 "     t2 = 3,30 mm     d2(ref) = 48,00 mm     "
                 "r1 = 0,25…0,40 mm     r2 = 0,16…0,25 mm",
         "size": 13, "color": SOFT, "font": "Consolas", "space_before": 10,
         "spacing": 1.35},
    ])
    caption(slide, "El chaflán de la chaveta no está en la tabla: es un "
                   "parámetro del usuario (c = 0,8 mm por defecto) y así se "
                   "declara en el informe.", top=Inches(6.5))
    slide_number(slide, index)
    return slide


def slide_verificacion(prs, index):
    slide = add_slide(prs)
    kicker(slide, "verificación")
    heading(slide, "Lo que se ha comprobado, y cómo", size=33)
    left_items = [
        ("Autotest empaquetado", "identidad 4.2 y esquema 6, migración 5→6, "
         "catálogos DIN y FVA, cálculos de referencia, seis plantillas de "
         "malla, informes en los tres idiomas. Termina con código 0."),
        ("Paridad de los tres catálogos", "650 claves por idioma, sin huecos; "
         "cada código de validación tiene su presentación traducida."),
        ("Los cuatro presets", "normalizan y validan con esquema 6 y cero "
         "errores, incluido el de resolución de 10 ciclos."),
    ]
    right_items = [
        ("Compatibilidad con el kernel", "los seis módulos que corren dentro "
         "de Abaqus se auditaron con AST: sin f-strings, sin anotaciones, sólo "
         "os, sys, json, math, time y hashlib. División importada del futuro."),
        ("Contrato de artefactos", "el proyecto se declara correcto sólo si "
         "existen auditoría, BUILD_RESULT, CAE, capturas e informe, y si la "
         "malla realizada coincide con la planificada."),
        ("Cifras fijadas en el test", "999,18 N·m gobernado por el cubo, "
         "t2tr = 3,141 mm, f_W de la ecuación 3 y el dominio de K_λ."),
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
    caption(slide, "Lo que el autotest no hace, y así lo declara: no arranca "
                   "Abaqus, no resuelve, no compila LaTeX y no valida un "
                   "especimen FVA.", top=Inches(6.72))
    slide_number(slide, index)
    return slide


def slide_pasos(prs, index):
    slide = add_slide(prs, BLACK)
    kicker(slide, "próximos pasos", dark=True)
    heading(slide, "Tres decisiones y una compilación", size=36, color=WHITE)
    steps = [
        ("01", "Reconstruir el ejecutable",
         "make_exe.bat, sin cambios, desde el árbol completo del proyecto. "
         "El .exe publicado es anterior a las dos correcciones: 17 de 31 "
         "entradas del manifiesto han cambiado."),
        ("02", "Fijar el signo de la ecuación 9",
         "contra el texto DIN 6892 con licencia. Si el signo negativo es el "
         "correcto, el par admisible real baja otro 46 %."),
        ("03", "Numerar la versión",
         "dos ejecutables que se identifican como 4.2 y devuelven pares "
         "distintos son una colisión de identidad. Mi recomendación es 4.3."),
    ]
    top = Inches(2.7)
    for number, title, body in steps:
        box, frame = textbox(slide, MARGIN, top, Inches(1.0), Inches(0.6))
        write(frame, [{"text": number, "size": 17, "bold": True,
                       "color": BLUE_DARK}])
        box2, frame2 = textbox(slide, Inches(1.95), top, Inches(10.5),
                               Inches(1.3))
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
        {"text": "El valor no está en el modelo.\nEstá en poder demostrar cómo "
                 "se hizo.", "size": 36, "bold": True, "color": WHITE,
         "spacing": 1.1},
    ])
    box2, frame2 = textbox(slide, MARGIN, Inches(5.6), Inches(11.0),
                           Inches(1.2))
    write(frame2, [
        {"text": "Model Builder 4.2  ·  esquema de parámetros 6  ·  "
                 "din6892-methods-1.0  ·  auto-mesh-2.0", "size": 12.5,
         "color": GREY_TEXT},
        {"text": "Cada número de esta presentación es reproducible ejecutando "
                 "el código del repositorio.", "size": 12.5, "color":
                 RGBColor(0x7C, 0x7C, 0x86), "space_before": 8},
    ])
    slide_number(slide, index, dark=True)
    return slide


# ------------------------------------------------------------------ assembly
def build():
    prs = new_deck()
    number = 1

    slide_hero(prs)
    number += 1
    slide_problema(prs)
    number += 1
    slide_kpis(prs)
    number += 1

    slide_diagram(prs, 4, "dia_arquitectura.png", "arquitectura",
                  "Un cambio en la tabla DIN o en un factor de DIN 6892 se "
                  "escribe una sola vez y llega a los dos intérpretes.")
    slide_diagram(prs, 5, "dia_tabs.png", "cómo se usa",
                  "Seis pestañas en el orden en que se toman las decisiones: "
                  "primero el proyecto, después la geometría normativa, y sólo "
                  "al final la ejecución.", top=Inches(2.3),
                  bottom=Inches(5.4))

    shots = [
        (6, "gui_01_proyecto.png", "pestaña 1", "Proyecto",
         ["Nombre, autor e idioma quedan grabados en project.json: el informe "
          "se emite en el idioma del proyecto, no en el de quien lo abre.",
          "La ruta de Abaqus se detecta buscando los lanzadores instalados, "
          "sin ejecutar ninguno.",
          "La carpeta raíz por defecto es Documentos/ModelBuilder Projects."],
         "Captura real de la aplicación, idioma por defecto español."),
        (7, "gui_02_geometria_din.png", "pestaña 2", "Geometría DIN",
         ["A la izquierda, los pocos parámetros independientes que el usuario "
          "decide. A la derecha, todo lo que la norma deriva de ellos.",
          "El panel derecho se recalcula al teclear: fila DIN, longitudes, "
          "cubo, plan de malla y la lista de validación completa.",
          "La etiqueta NORMATIVE en verde indica que la geometría está dentro "
          "del sobre de la norma."],
         "d1 = 40 mm  ·  banda 38 < d1 ≤ 44  ·  b × h = 12 × 8  ·  "
         "DIN 6885-1 Form A 12 × 8 × 50."),
        (8, "gui_03_malla_materiales.png", "pestaña 3", "Malla y materiales",
         ["La plantilla se elige por nombre; el modo AUTO compara candidatos "
          "completos por pieza y conserva el ganador.",
          "Las semillas en 0 significan automático: D/32 en el eje, b/20 en la "
          "chaveta, d_a/80 en el cubo.",
          "El criterio rápido de presión está marcado CORE-SCREENING: es "
          "plausibilidad, no DIN 6892 Método B."],
         "Aquí la plantilla es HEX_CERTIFIED, en modo auto y con 3 intentos."),
        (9, "gui_04_analisis.png", "pestaña 4", "Análisis",
         ["El análisis es opcional y está desactivado por defecto: construir y "
          "auditar no requiere resolver.",
          "Si se activa, se crea contacto general, un step estático TORSION y "
          "un momento sobre el punto de referencia del extremo motriz.",
          "El estudio de convergencia de malla se lanza aparte y escribe su "
          "propio CSV."],
         "Crear el job y enviarlo al solver son dos casillas distintas."),
        (10, "gui_05_din6892_fva.png", "pestaña 5", "DIN 6892 / FVA",
         ["El método se elige explícitamente. Los factores licenciados que no "
          "se pueden transcribir se quedan en 1,0 y el resultado se marca "
          "PROVISIONAL_FACTORS.",
          "N_W en blanco significa deducir de la razón de carga R; con un par "
          "pulsante da cero inversiones y f_W = 1.",
          "El Método A no se calcula aquí: se importa un CSV de un ODB ya "
          "resuelto, con SHA-256 y cobertura verificadas."],
         "Las normas seleccionadas se declaran una por una, incluidas las que "
         "no están implementadas."),
        (11, "gui_06_ejecutar_evidencias.png", "pestaña 6",
         "Ejecutar y evidencias",
         ["El log de Abaqus se transmite en vivo a la ventana y al archivo "
          "logs/abaqus.log, con el comando y el directorio de trabajo en la "
          "cabecera.",
          "Al terminar, la lista de artefactos se rellena con tamaño y "
          "etiqueta de evidencia; los botones abren el proyecto, el informe y "
          "el modelo.",
          "Detener mata el árbol de procesos del solver y marca el proyecto "
          "como CANCELLED."],
         "Ningún archivo de solver cae junto al ejecutable: el subproceso corre "
         "con cwd = jobs/."),
        (12, "gui_07_validacion.png", "control de calidad",
         "La validación habla en códigos",
         ["Cada aviso tiene un código estable, un mensaje canónico en inglés y "
          "una presentación traducida. El código es el que se cita en el "
          "informe y en una revisión.",
          "Aquí se ven los tres avisos nuevos: un factor licenciado todavía "
          "neutro, la ecuación 9 optimista y N_W deducido de R.",
          "Un error bloquea la construcción antes de tocar Abaqus; una "
          "advertencia informa y queda registrada."],
         "0 errores y 3 advertencias en la configuración por defecto."),
    ]
    for args in shots:
        slide_shot(prs, args[0], args[1], args[2], args[3], args[4], args[5])

    slide_diagram(prs, 13, "dia_pipeline.png", "flujo de ejecución")
    slide_diagram(prs, 14, "dia_workspace.png", "lo que queda en disco")

    slide_render(prs, 15, "model_assembly_hex.png", "el resultado",
                 "Sólidos, no cascarones",
                 ["Eje, chaveta y cubo se construyen como volúmenes "
                  "independientes y se ensamblan con las tolerancias de la "
                  "norma.",
                  "La malla es hexaédrica y coincidente en las interfaces que "
                  "transmiten carga.",
                  "La captura es la imagen que el propio motor guarda en "
                  "screenshots/ al terminar."])
    slide_render(prs, 16, "model_notch_section.png", "el detalle que importa",
                 "La banda del chavetero",
                 ["En la sección se ve la banda de elementos más finos que "
                  "rodea la ranura: no es una malla uniforme más densa, es "
                  "refinamiento donde está el gradiente.",
                  "El ancho de la banda y el número de elementos sobre el arco "
                  "del radio r2 son parámetros, y la auditoría comprueba que se "
                  "hayan cumplido.",
                  "El conjunto de elementos NOTCH_SHAFT se construye alrededor "
                  "de las dos esquinas del chavetero para que la consulta de "
                  "concentración no se vaya a otro punto caliente."],
                 dark=False)

    slide_diagram(prs, 17, "dia_malla.png", "política de malla")
    slide_diagram(prs, 18, "dia_badges.png", "trazabilidad")
    slide_din6885(prs, 19)
    slide_diagram(prs, 20, "dia_metodos.png", "capacidad resistente")
    slide_diagram(prs, 21, "chart_pares.png", "resultados")
    slide_diagram(prs, 22, "dia_t2tr.png", "corrección 1 de 2")
    slide_diagram(prs, 23, "chart_fw.png", "corrección 2 de 2")
    slide_diagram(prs, 24, "dia_eq9.png", "hallazgo abierto")
    slide_verificacion(prs, 25)
    slide_diagram(prs, 26, "dia_release.png", "distribución")
    slide_diagram(prs, 27, "dia_estado.png", "estado")
    slide_pasos(prs, 28)
    slide_cierre(prs, 29)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    prs.save(OUTPUT)
    print("saved %s" % OUTPUT)
    print("slides: %d" % len(prs.slides.__iter__.__self__._sldIdLst))
    return OUTPUT


if __name__ == "__main__":
    build()
