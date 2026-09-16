# Presentación — Model Builder 4.2

`ModelBuilder_4.2_Presentacion.pptx` — 29 diapositivas, 16:9 (33,87 × 19,05 cm), en español.
Tipografía Arial en todo el archivo, para que no haya sustituciones al abrirlo en otro equipo.

## Guion

| # | Diapositiva | Contenido |
|---|---|---|
| 1–3 | Apertura | qué es, qué problema resuelve, cinco cifras de contexto |
| 4 | Arquitectura | los dos intérpretes de Python y el núcleo compartido |
| 5 | Recorrido | las seis pestañas en el orden de decisión |
| 6–12 | Capturas | una diapositiva por pestaña más el diálogo de validación |
| 13–14 | Flujo | pipeline de diez etapas y las siete carpetas del proyecto |
| 15–16 | Modelo | ensamblaje mallado y la banda de refinamiento del chavetero |
| 17–20 | Método | política de malla, etiquetas de evidencia, tabla DIN 6885, cuatro métodos DIN 6892 |
| 21–24 | Resultados | comparación de pares, corrección de t2tr, corrección de f_W, la ecuación 9 |
| 25–27 | Garantías | qué se ha verificado, cadena de publicación, estado real |
| 28–29 | Cierre | tres decisiones pendientes y una compilación |

## De dónde sale cada cosa

- **Capturas (`screenshots/`)** — de la aplicación real. `model_builder_gui.py` se ejecutó bajo
  un servidor X virtual, se seleccionó cada pestaña por código y se refrescó el panel derivado,
  de modo que los valores visibles los calculó el motor empaquetado. No hay maquetas.
  El diálogo de validación es el `messagebox` real de Tk, capturado con temporizador.
- **Figuras (`figures/`)** — generadas con matplotlib importando `keyjoint_core` y
  `din6892_methods`: las cifras de los gráficos (999,18 / 572,51 / 2 464,87 / 795,56 N·m,
  t1tr, t2tr, la curva f_W, el catálogo de plantillas) se leen del código en el momento de
  dibujar, así que las diapositivas no pueden desincronizarse de la implementación.
- **Renders de Abaqus** — imágenes que el propio motor guardó en `preview/` y `_v3test/`
  durante ejecuciones anteriores. Sólo se han recortado los márgenes.
- **`preview/`** — vista previa aproximada de cada diapositiva, para revisar sin PowerPoint.
  La genera `tools/render_preview.py`, que vuelve a leer el `.pptx` y lo rasteriza con
  Liberation Sans (métricas de Arial); sirve para detectar desbordes de texto, no como
  representación exacta de PowerPoint.

## Regenerar

Requiere Python 3 con `python-pptx`, `matplotlib` y `Pillow`; para las capturas, además
`tkinter`, `Xvfb` e ImageMagick.

```bash
python3 tools/make_diagrams.py     # figuras, con valores en vivo del motor
python3 tools/make_shots.py        # encuadre de capturas y renders
python3 tools/make_deck.py         # escribe el .pptx
python3 tools/render_preview.py    # rasteriza para revisión y avisa de desbordes
```

`tools/capture_gui.py` es el que toma las capturas y necesita pantalla:

```bash
Xvfb :99 -screen 0 1920x1200x24 &
DISPLAY=:99 MB_MODE=tabs   python3 tools/capture_gui.py
DISPLAY=:99 MB_MODE=dialog python3 tools/capture_gui.py
```

Las rutas de los scripts apuntan al directorio de trabajo donde se construyó la presentación;
ajústalas si los mueves.

## Cifras citadas y su fuente

| Dato | Comprobación |
|---|---|
| 26 filas DIN 6885-1, 34 longitudes, 7 bandas de radios | `len(core.DIN6885)`, `DIN6885_LENGTHS`, `DIN6885_RADII` |
| 8 plantillas de malla | `len(core.MESH_TEMPLATES)` — la documentación heredada dice seis |
| 650 claves por idioma, 3 idiomas | `i18n.validate_catalogs()` |
| 14 módulos, 31 entradas de build | lista de `make_exe.bat` y `make_release.BUILD_INPUT_FILES` |
| 0 errores y 3 advertencias por defecto | `core.validate(core.default_params())` |
| M_t,zul = 999,18 N·m, gobierna el cubo | fijado en el autotest de `model_builder_gui.run_self_test` |
| 17 de 31 entradas cambiadas desde el .exe publicado | SHA-256 de `release/ModelBuilder_4.2/BUILD_MANIFEST.json` frente al árbol actual |
