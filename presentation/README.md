# Presentation — Model Builder 4.2

Two decks, same 39 slides, same layout, built from one source.

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
| 13 | Pipeline | the ten stages from one click to archived evidence |
| 14 | Workspace | the seven project folders and who writes each artifact |
| 15 | Presets | the fifteen starting points, and why none skips validation |
| 16 | Design space | key forms, tapered hub, diameter range, element types, compliance mode |
| 17–18 | Model | meshed assembly and the keyway refinement band |
| 19 | Mesh policy | the eight templates with their hard gates |
| 20 | Mesh selection | the per-part candidate loop and why the verdict is the worst part |
| 21 | Analysis setup | contact, drive end, held region, step, load, output |
| 22 | Traceability | the eight evidence badges |
| 23 | DIN 6885 | the table that is never interpolated |
| 24 | Audit | what `PARAM_BUILD_AUDIT` records |
| 25 | Deliverable | the ten report sections and its four output files |
| 26 | Methods | the four DIN 6892 evaluation methods |
| 27 | Results | the allowable-torque comparison |
| 28–29 | Corrections | the t2tr correction and the f_W correction |
| 30 | Open finding | the sign of equation 9 |
| 31 | Method A | the evidence chain from a solved ODB to a criterion |
| 32 | Cross-check | the optional MATLAB companion, and why it is never the authority |
| 33 | FVA catalogue | variants VB1–VB8, material models, matching mesh |
| 34 | Verification | what has been checked, and how |
| 35 | Robustness | decisions that rule out whole classes of error |
| 36 | Distribution | the six-step release chain |
| 37 | Status | verified, awaiting decision, out of scope |
| 38–39 | Close | three open decisions and one build |

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

`tools/setup_env.sh` installs what the toolchain needs (`python-pptx`,
`matplotlib`, `Pillow`, `tkinter`, `Xvfb`, ImageMagick, Liberation fonts).

```bash
sh tools/setup_env.sh
for LANG in es en; do
  MB_LANG=$LANG python3 tools/make_diagrams.py    # figures, live engine values
  MB_LANG=$LANG python3 tools/make_shots.py       # frame captures and renders
  MB_LANG=$LANG python3 tools/make_deck.py        # write the .pptx
  MB_LANG=$LANG python3 tools/render_preview.py   # raster + report text overflow
done
python3 tools/check_figures.py diagrams           # fail on clipped figures
python3 tools/check_figures.py diagrams_en
```

Screenshots need a display:

```bash
Xvfb :99 -screen 0 1920x1200x24 &
for LOC in es en; do
  DISPLAY=:99 MB_LOCALE=$LOC MB_MODE=tabs   python3 tools/capture_gui.py
  DISPLAY=:99 MB_LOCALE=$LOC MB_MODE=dialog python3 tools/capture_gui.py
done
```

One wording, one geometry: `L("español", "english")` picks the text and
`MB_LANG` picks the language, so a layout fix is never made twice. Slide numbers
are assigned by a counter, so inserting a slide never means renumbering. The
paths in the scripts point at the working directory where the deck was built;
adjust them if you move things.

Two automated checks guard the layout and both must stay clean:
`render_preview.py` reports any text taller than its box, and `check_figures.py`
fails if a figure's content runs off the bottom of its canvas. That second check
caught two figures whose last row was being cut — the `logs/` folder row and the
closing line of the pipeline slide — after the first draft had already been
reviewed.

## Cited figures and how to confirm them

| Figure | Check |
|---|---|
| 26 DIN 6885-1 rows, 34 lengths, 7 radius bands | `len(core.DIN6885)`, `DIN6885_LENGTHS`, `DIN6885_RADII` |
| 8 mesh templates, 5 recipes, 4 meshed parts | `core.MESH_TEMPLATES`, `MESH_RECIPE_CATALOG`, `MESH_PARTS` |
| 15 presets | `len(core.PRESETS)` |
| 8 FVA variants VB1–VB8 | `din6892_methods.FVA_VARIANTS` |
| MATLAB modes OFF / EXPORT / RUN, tolerances 1e-10 and 1e-9 | `fva600_matlab.MODES`, `DEFAULT_ABS_TOLERANCE`, `DEFAULT_REL_TOLERANCE` |
| CSV contract `x_mm, z_mm, opening_um`, coverage 2 %, v_crit 0.5 | `fva600_postprocess.REQUIRED_COLUMNS`, `COVERAGE_TOLERANCE`, `process_csv` |
| 650 keys per language, 3 languages | `i18n.validate_catalogs()` |
| 14 modules, 31 build inputs | the list in `make_exe.bat` and `make_release.BUILD_INPUT_FILES` |
| 0 errors and 3 warnings by default | `core.validate(core.default_params())` |
| M_t,zul = 999.18 N·m, hub governs | locked in `model_builder_gui.run_self_test` |
| 1302.05 N·m before the correction | reconstructs as 999.18 × (t1tr/t2tr) × f_W(10⁴) = 1302.0515 |
| 17 of 31 manifest entries changed since the published .exe | SHA-256 of `release/ModelBuilder_4.2/BUILD_MANIFEST.json` against the current tree |
