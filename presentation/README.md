# Presentation — Model Builder 4.2

Two decks, same 29 slides, same layout, built from one source.

| File | Language | Screenshots |
|---|---|---|
| `ModelBuilder_4.2_Presentation.pptx` | English | GUI captured with the interface switched to English |
| `ModelBuilder_4.2_Presentacion.pptx` | Spanish | GUI captured in Spanish, the application's default locale |

16:9 (33.87 × 19.05 cm), Arial throughout so nothing is substituted on another
machine. The Spanish deck is kept deliberately: it is the study copy for
rehearsing the talk, and both stay in step because they are generated together.

## Slide guide

| # | Slide | Content |
|---|---|---|
| 1–3 | Opening | what it is, the problem it solves, five figures of context |
| 4 | Architecture | the two Python interpreters and the shared core |
| 5 | Journey | the six tabs in the order decisions are made |
| 6–12 | Screenshots | one slide per tab plus the validation dialog |
| 13–14 | Flow | the ten-stage pipeline and the seven project folders |
| 15–16 | Model | meshed assembly and the keyway refinement band |
| 17–20 | Method | mesh policy, evidence badges, the DIN 6885 table, the four DIN 6892 methods |
| 21–24 | Results | torque comparison, the t2tr correction, the f_W correction, equation 9 |
| 25–27 | Assurance | what has been verified, the release chain, where it really stands |
| 28–29 | Close | three open decisions and one build |

## Where the content comes from

- **Screenshots (`es/screenshots/`, `en/screenshots/`)** — the real application.
  `model_builder_gui.py` runs under a virtual X server; each tab is selected in
  code and the derived panel refreshed, so every value on screen was computed by
  the packaged engine. The English set is produced by calling the same
  `_set_language()` path the language combo box uses, not by patching the
  catalogues. The validation dialog is the real Tk `messagebox`, grabbed on a
  timer.
- **Figures (`es/figures/`, `en/figures/`)** — matplotlib, importing
  `keyjoint_core` and `din6892_methods`. The torques (999.18 / 572.51 /
  2,464.87 / 795.56 N·m), t1tr and t2tr, the f_W curve of equation 3 and the
  mesh-template catalogue are read from the code at draw time, so a slide cannot
  drift from the implementation. Decimal separators follow the language.
- **Abaqus renders** — images the engine itself wrote to `preview/` and
  `_v3test/` on earlier runs. Only the margins were cropped.
- **`es/preview/`, `en/preview/`** — a raster of every slide, so the deck can be
  reviewed without PowerPoint. Produced by `tools/render_preview.py`, which
  reads the saved `.pptx` back and draws it with Liberation Sans (Arial
  metrics). It is a layout check, not an exact PowerPoint rendering.

## Rebuilding

Needs Python 3 with `python-pptx`, `matplotlib` and `Pillow`; for the
screenshots also `tkinter`, `Xvfb` and ImageMagick.

```bash
for LANG in es en; do
  MB_LANG=$LANG python3 tools/make_diagrams.py    # figures, live engine values
  MB_LANG=$LANG python3 tools/make_shots.py       # frame captures and renders
  MB_LANG=$LANG python3 tools/make_deck.py        # write the .pptx
  MB_LANG=$LANG python3 tools/render_preview.py   # raster + report text overflow
done
python3 tools/check_figures.py diagrams           # fail on clipped figures
```

Screenshots need a display:

```bash
Xvfb :99 -screen 0 1920x1200x24 &
DISPLAY=:99 MB_LOCALE=es MB_MODE=tabs   python3 tools/capture_gui.py
DISPLAY=:99 MB_LOCALE=es MB_MODE=dialog python3 tools/capture_gui.py
DISPLAY=:99 MB_LOCALE=en MB_MODE=tabs   python3 tools/capture_gui.py
DISPLAY=:99 MB_LOCALE=en MB_MODE=dialog python3 tools/capture_gui.py
```

One wording, one geometry: `L("español", "english")` picks the text and
`MB_LANG` picks the language, so a layout fix is never made twice. The paths in
the scripts point at the working directory where the deck was built; adjust them
if you move things.

Two automated checks guard the layout and both must stay clean:
`render_preview.py` reports any text taller than its box, and `check_figures.py`
fails if a figure's content runs off the bottom of its canvas. That second check
caught two figures whose last row was being cut — the `logs/` folder row and the
closing line of the pipeline slide — after the first Spanish draft had already
been reviewed.

## Cited figures and how to confirm them

| Figure | Check |
|---|---|
| 26 DIN 6885-1 rows, 34 lengths, 7 radius bands | `len(core.DIN6885)`, `DIN6885_LENGTHS`, `DIN6885_RADII` |
| 8 mesh templates | `len(core.MESH_TEMPLATES)` — the inherited documentation says six |
| 650 keys per language, 3 languages | `i18n.validate_catalogs()` |
| 14 modules, 31 build inputs | the list in `make_exe.bat` and `make_release.BUILD_INPUT_FILES` |
| 0 errors and 3 warnings by default | `core.validate(core.default_params())` |
| M_t,zul = 999.18 N·m, hub governs | locked in `model_builder_gui.run_self_test` |
| 17 of 31 manifest entries changed since the published .exe | SHA-256 of `release/ModelBuilder_4.2/BUILD_MANIFEST.json` against the current tree |
