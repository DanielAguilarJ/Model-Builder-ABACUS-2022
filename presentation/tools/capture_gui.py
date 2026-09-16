# -*- coding: utf-8 -*-
"""Capture real screenshots of the Model Builder 4.2 Tk GUI under Xvfb.

The GUI is driven programmatically: the notebook tab is selected, the derived
values panel is refreshed with the live keyjoint_core / din6892_methods result,
and the toplevel X window is grabbed with ImageMagick. Nothing is mocked; every
number visible in the screenshots comes from the packaged engine.

Usage:
    MB_MODE=tabs   python3 capture_gui.py     # one PNG per notebook tab
    MB_MODE=dialog python3 capture_gui.py     # the modal validation dialog
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

REPO = "/projects/sandbox/Model-Builder-ABACUS-2022"
OUT = "/projects/sandbox/assets/screens"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.makedirs(OUT, exist_ok=True)

import tkinter as tk  # noqa: E402

import model_builder_gui as gui  # noqa: E402

SCALE = float(os.environ.get("MB_SCALE", "1.15"))
GEOM = os.environ.get("MB_GEOM", "1500x1150+0+0")
MODE = os.environ.get("MB_MODE", "tabs")

TAB_NAMES = ["01_proyecto", "02_geometria_din", "03_malla_materiales",
             "04_analisis", "05_din6892_fva", "06_ejecutar_evidencias"]


def grab(window_id, path):
    for _attempt in range(3):
        completed = subprocess.run(
            ["import", "-window", window_id, "-quality", "100", path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if completed.returncode == 0 and os.path.isfile(path):
            return True
        time.sleep(0.5)
    sys.stderr.write("capture failed for %s\n" % path)
    return False


def settle(root, seconds=0.45):
    end = time.time() + seconds
    while time.time() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.03)


def capture_tabs(root, app, window_id):
    """Fit the window to each tab's own requested height, then grab it.

    Auto-fitting avoids a large band of empty background under the short tabs,
    while keeping the real window frame intact in every screenshot.
    """
    app.refresh_derived()
    settle(root, 0.7)
    width = int(GEOM.split("x")[0])
    written = []
    for index, tab_id in enumerate(app.notebook.tabs()):
        app.notebook.select(tab_id)
        settle(root, 0.5)
        needed = root.winfo_reqheight()
        height = max(760, min(1190, needed + 12))
        root.geometry("%dx%d+0+0" % (width, height))
        settle(root, 0.7)
        label = TAB_NAMES[index] if index < len(TAB_NAMES) else "tab_%02d" % index
        path = os.path.join(OUT, "gui_%s.png" % label)
        if grab(window_id, path):
            written.append((app.notebook.tab(tab_id, "text"), path))
    print("captured %d tab screenshots" % len(written))
    for text, path in written:
        print("  %-26s %-40s %d bytes" %
              (text.strip(), os.path.basename(path), os.path.getsize(path)))


def capture_dialog(root, app, window_id):
    """Grab the real modal validation dialog, then dismiss it."""
    path = os.path.join(OUT, "gui_07_validacion.png")

    def shoot():
        grab("root", path)
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
        try:
            for name in root.tk.call("winfo", "children", "."):
                if "message" in str(name) or "dialog" in str(name):
                    root.tk.call("destroy", name)
        except tk.TclError:
            pass

    app.notebook.select(app.notebook.tabs()[1])
    settle(root, 0.5)
    root.after(1500, shoot)
    app.validate_form()
    settle(root, 0.4)
    if os.path.isfile(path):
        print("captured validation dialog: %s (%d bytes)" %
              (os.path.basename(path), os.path.getsize(path)))
    else:
        print("validation dialog capture produced no file")


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", SCALE)
    except tk.TclError:
        pass
    app = gui.ModelBuilderApp(root)
    root.geometry(GEOM)
    settle(root, 1.3)
    window_id = hex(root.winfo_id())
    if MODE == "dialog":
        capture_dialog(root, app, window_id)
    else:
        capture_tabs(root, app, window_id)
    try:
        root.destroy()
    except tk.TclError:
        pass


if __name__ == "__main__":
    main()
