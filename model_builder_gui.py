# -*- coding: utf-8 -*-
"""Model Builder 4.2 — professional project-oriented GUI.

Normal Python 3 application.  Abaqus itself is launched through
``SubprocessRunner`` with the project's ``jobs`` directory as cwd.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import keyjoint_core as core
import din6892_methods as din6892
import fva600_postprocess as fva_postprocess
import fva600_matlab as fva_matlab
import model_builder_i18n as i18n
from abaqus_runner import SubprocessRunner, detect_abaqus
from project_workspace import ProjectWorkspace, default_projects_root, sanitize_name
from report_generator import generate_report

APP_TITLE = "Model Builder 4.2"
ENGINE_NAME = "build_parametric_model.py"
CORE_NAME = "keyjoint_core.py"
DEFAULTS_NAME = "params_default.json"
CONTRACT_NAME = "technical_contract.json"
I18N_DIRNAME = "i18n"
REPORT_MARKER_NAME = "report_template.tex"

COLORS = {
    "navy": "#0f172a",
    "navy2": "#172554",
    "blue": "#2563eb",
    "blue2": "#1d4ed8",
    "cyan": "#0891b2",
    "bg": "#f1f5f9",
    "card": "#ffffff",
    "text": "#0f172a",
    "muted": "#64748b",
    "line": "#cbd5e1",
    "good": "#15803d",
    "warn": "#b45309",
    "bad": "#b91c1c",
    "log": "#08111f",
    "logfg": "#d1fae5",
}


def executable_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    roots = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        roots.append(bundle)
    roots.extend((executable_dir(), os.path.dirname(os.path.abspath(__file__))))
    for root in roots:
        candidate = os.path.join(root, name)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(roots[0], name)


class InputValueError(ValueError):
    """Typed form error whose presentation is localized by the GUI."""

    def __init__(self, kind, label, value=None, minimum=None):
        ValueError.__init__(self, kind)
        self.kind = kind
        self.label = label
        self.value = value
        self.minimum = minimum


def _float(text, label):
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        raise InputValueError("number", label, value=repr(text))


def _int(text, label, minimum=1):
    value = int(_float(text, label))
    if value < minimum:
        raise InputValueError("minimum", label, value=value, minimum=minimum)
    return value


def _blank_if_none(value):
    """Round trip of an optional field: None becomes an empty entry."""
    return "" if value in (None, "") else value


def _opt_float(text, label):
    """A blank optional field means "not supplied", not zero and not 1.0.

    DIN 6892 fields such as f_S, f_H, N_W or K_A have a meaningful "resolve it
    from the standard / from the load ratio" state.  Writing a neutral number
    instead of None silently defeats the DIN 6892 Table 2 lookup and the N_W
    derivation, so an empty entry has to travel as None.
    """
    raw = str(text or "").strip()
    if not raw or raw.lower() in ("auto", "none", "null", "-"):
        return None
    return _float(raw, label)


class ModelBuilderApp(object):
    def __init__(self, root):
        self.root = root
        self.translator = i18n.Translator(
            i18n.DEFAULT_LOCALE, directory=resource_path("i18n"))
        self.locale = self.translator.locale
        self.root.title(self.tr("gui.window_title"))
        self.root.configure(bg=COLORS["bg"])
        self.root.minsize(1120, 740)
        self.root.geometry("1320x860")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.vars = {}
        self.current_workspace = None
        self.runner = None
        self.worker = None
        self._matlab_worker = None
        self._refresh_after = None
        self._loaded_params = core.default_params()
        self._selected_preset_id = "D40 - validated default"
        self._status_state = ("gui.static.ready", {})
        self._run_title_state = ("gui.static.no_run", {})
        self._run_path_state = ("gui.static.project_here", {})
        self._log_records = []
        self._configure_style()
        self._create_variables()
        self._build_shell()
        self._translate_static_widgets()
        self.apply_params(core.default_params())
        self._append_user_log("gui.log.ready", version=core.BUILDER_VERSION)

    def tr(self, key, default=None, **values):
        return self.translator.t(key, default=default, **values)

    # ------------------------------------------------------------------ style
    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure("Card.TLabelframe", background=COLORS["card"],
                        bordercolor=COLORS["line"], relief="solid")
        style.configure("Card.TLabelframe.Label", background=COLORS["card"],
                        foreground=COLORS["text"], font=("Segoe UI Semibold", 10))
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"],
                        font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=COLORS["card"],
                        foreground=COLORS["text"])
        style.configure("Muted.Card.TLabel", background=COLORS["card"],
                        foreground=COLORS["muted"], font=("Segoe UI", 8))
        style.configure("Hero.TLabel", background=COLORS["navy"], foreground="white",
                        font=("Segoe UI Semibold", 18))
        style.configure("HeroSub.TLabel", background=COLORS["navy"],
                        foreground="#bfdbfe", font=("Segoe UI", 9))
        style.configure("Accent.TButton", background=COLORS["blue"],
                        foreground="white", borderwidth=0,
                        font=("Segoe UI Semibold", 10), padding=(18, 10))
        style.map("Accent.TButton", background=[("active", COLORS["blue2"]),
                                                 ("disabled", "#94a3b8")])
        style.configure("Secondary.TButton", padding=(12, 8),
                        font=("Segoe UI Semibold", 9))
        style.configure("Danger.TButton", foreground=COLORS["bad"], padding=(12, 8))
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), font=("Segoe UI Semibold", 9))
        style.map("TNotebook.Tab", background=[("selected", COLORS["card"])],
                  foreground=[("selected", COLORS["blue2"])])
        style.configure("Horizontal.TProgressbar", troughcolor="#dbeafe",
                        background=COLORS["blue"], bordercolor="#dbeafe")

    # --------------------------------------------------------------- i18n/state
    def _translate_static_widgets(self):
        """Translate existing widget captions without recreating form variables."""
        self.root.title(self.tr("gui.window_title"))

        def visit(widget):
            try:
                current = widget.cget("text")
                translated = self.translator.translate_text(current)
                if translated != current:
                    widget.configure(text=translated)
            except (tk.TclError, TypeError):
                pass
            for child in widget.winfo_children():
                visit(child)

        visit(self.root)
        if hasattr(self, "notebook"):
            for tab_id in self.notebook.tabs():
                current = self.notebook.tab(tab_id, "text")
                self.notebook.tab(
                    tab_id, text=self.translator.translate_text(current))
        self._render_state_variables()

    def _render_state_variables(self):
        if hasattr(self, "status_var"):
            key, values = self._status_state
            self.status_var.set(self.tr(key, **values) if key else values.get("text", ""))
        if hasattr(self, "run_title"):
            key, values = self._run_title_state
            self.run_title.set(self.tr(key, **values) if key else values.get("text", ""))
        if hasattr(self, "run_path"):
            key, values = self._run_path_state
            self.run_path.set(self.tr(key, **values) if key else values.get("text", ""))

    def _set_status(self, key, **values):
        self._status_state = (key, values)
        if hasattr(self, "status_var"):
            self.status_var.set(self.tr(key, **values))

    def _set_run_title(self, key, **values):
        self._run_title_state = (key, values)
        if hasattr(self, "run_title"):
            self.run_title.set(self.tr(key, **values))

    def _set_run_path(self, text):
        self._run_path_state = (None, {"text": str(text)})
        if hasattr(self, "run_path"):
            self.run_path.set(str(text))

    def _preset_id_from_display(self, display):
        for preset_id in core.PRESETS:
            if i18n.preset_label(preset_id, self.translator) == display:
                return preset_id
        return display if display in core.PRESETS else self._selected_preset_id

    def _preset_selected(self, _event=None):
        self._selected_preset_id = self._preset_id_from_display(
            self.preset.get())

    def _refresh_preset_labels(self):
        if not hasattr(self, "preset_combo"):
            return
        labels = tuple(i18n.preset_label(item, self.translator)
                       for item in core.PRESETS)
        self.preset_combo.configure(values=labels)
        self.preset.set(i18n.preset_label(
            self._selected_preset_id, self.translator))

    def _set_language(self, locale, refresh=True):
        self.locale = self.translator.set_locale(locale)
        if hasattr(self, "language_var"):
            self.language_var.set(i18n.LANGUAGE_LABELS[self.locale])
        if isinstance(self._loaded_params, dict):
            i18n.set_param_language(self._loaded_params, self.locale)
        self._translate_static_widgets()
        self._refresh_preset_labels()
        self._render_log_records()
        if hasattr(self, "mesh_template_info"):
            self._mesh_template_changed(apply_defaults=False)
        elif refresh and hasattr(self, "derived_text"):
            self.refresh_derived()

    def _language_changed(self, _event=None):
        display = self.language_var.get()
        locale = next((code for code, label in i18n.LANGUAGE_LABELS.items()
                       if label == display), i18n.DEFAULT_LOCALE)
        self._set_language(locale)

    def _error_text(self, exc):
        if isinstance(exc, InputValueError):
            label = self.translator.translate_text(exc.label)
            if exc.kind == "number":
                return self.tr("gui.input.number", label=label, value=exc.value)
            if exc.kind == "minimum":
                return self.tr("gui.input.minimum", label=label,
                               minimum=exc.minimum)
            if exc.kind == "slot_too_short":
                return self.tr("gui.input.slot_too_short",
                               minimum=exc.minimum)
        return self.tr("gui.input.invalid_detail", detail=str(exc))

    def _append_user_log(self, key, **values):
        self._log_records.append(("i18n", key, dict(values)))
        if hasattr(self, "log"):
            self.log.insert("end", self.tr(key, **values))
            self.log.see("end")

    def _render_log_records(self):
        if not hasattr(self, "log"):
            return
        self.log.delete("1.0", "end")
        for record in self._log_records:
            if record[0] == "i18n":
                text = self.tr(record[1], **record[2])
            else:
                text = record[1]
            self.log.insert("end", text)
        self.log.see("end")

    def _create_variables(self):
        defaults = {
            "project_name": "KeyJoint Study",
            "model_name": "PARAM_MODEL",
            "author": os.environ.get("USERNAME", ""),
            "base_dir": default_projects_root(),
            "abaqus_cmd": detect_abaqus(),
            "form": "A",
            "groove_form": "N1",
            "D": "40.0",
            "L_over_D": "3.0",
            "slot_total_length": "50.0",
            "z0_offset": "5.0",
            "R_cap": "0.0",
            "r2": "0.25",
            "slot_clearance": "0.0",
            "key_length": "0.0",
            "key_chamfer": "0.8",
            "key_snap": True,
            "hub_length": "38.0",
            "hub_ratio": "2.0",
            "hub_r1": "0.25",
            "hub_clearance": "0.0215",
            "hub_type": "cylindrical",
            "mesh_template": "HEX_CERTIFIED",
            "mesh_selection": "auto",
            "mesh_max_attempts": "3",
            "mesh_fixed_recipe": "",
            "mesh_fail_quality": True,
            "element_order": "quadratic",
            "hex_code": "C3D8",
            "shaft_seed": "0.0",
            "key_seed": "0.0",
            "hub_seed": "0.0",
            "notch_enabled": True,
            "notch_arc_elems": "6",
            "ar_threshold": "25.0",
            "design_torque": "200.0",
            "analysis_enabled": False,
            "create_job": True,
            "submit_job": False,
            "analysis_torque": "200.0",
            "friction": "0.15",
            "cpus": "1",
            "fva_enabled": False,
            "fva_backend": din6892.BACKEND_METHOD_A_HYBRID_HEX,
            "fva_torque": "1256.0",
            "fva_cycles": "20",
            "fva_vcrit": "0.5",
            "fva_strict_no_job": True,
            "fva_create_job": False,
            "fva_submit_solver": False,
            "fva_mesh_size": "0.8",
            "fva_matching_tolerance": "0.000001",
            "fva_shaft_model": din6892.SHAFT_MODEL_COMBINED,
            "fva_hub_model": din6892.HUB_MODEL_UML,
            "fva_key_model": din6892.MODEL_ELASTIC_IDEAL_PLASTIC,
            "matlab_mode": "OFF",
            "matlab_executable": "matlab",
            "matlab_timeout": "300",
            "din_enabled": True,
            "din_method": din6892.METHOD_B_CURRENT,
            "fva_variant": "VB1",
            "fva_material": "C45N_C45N",
            "fva_apply_variant": False,
            "din_load_cycles": "10000",
            "din_load_ratio": "0.0",
            "din_nw": "",
            "din_upf": "18.0",
            "din_xi": "0.0",
            "din_klambda": "1.0",
            "din_kr": "1.0",
            # Blank = resolve from DIN 6892 Table 2 for the declared material
            # class. Writing 1.0 here would silently defeat that lookup.
            "din_fh": "",
            "din_fs": "",
            "din_safety": "1.2",
            "din_key_count": "1",
            "din_phi": "1.0",
            "din_v": "0.5",
            "din_depth_policy": din6892.DEPTH_POLICY_EQUATION_9,
            "din_load_derivation": din6892.LOAD_DERIVATION_REAR,
            "din_ka": "1.0",
            "din_torque_nominal": "",
            "din_torque_applied": "",
            "din_fl": "",
            "din_torque_peak": "",
            "din_torque_required": "",
            "din_method_c_variant": din6892.METHOD_C_VARIANT_DIN,
            "method_a_cycles": "0",
            "method_a_unloaded": False,
            "method_a_step": "",
            "method_a_frame": "",
            "method_a_csv": "",
            "standard_geometry": "DIN_6885_1_2021",
            "standard_strength": "DIN_6892",
            "standard_fatigue": "DIN_743",
            "standard_fit": "DIN_EN_ISO_286",
            "standard_friction": "DIN_7190_1",
            "save_cae": True,
            "make_preview": True,
            "compile_pdf": True,
        }
        bool_keys = {key for key, value in defaults.items() if isinstance(value, bool)}
        for key, value in defaults.items():
            self.vars[key] = (tk.BooleanVar(value=value) if key in bool_keys
                              else tk.StringVar(value=str(value)))
        self.language_var = tk.StringVar(
            value=i18n.LANGUAGE_LABELS[self.locale])

    # ------------------------------------------------------------------- shell
    def _build_shell(self):
        header = tk.Frame(self.root, bg=COLORS["navy"], height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = ttk.Frame(header, style="Card.TFrame")
        title.configure(style="TFrame")
        title.pack(side="left", fill="y", padx=24, pady=14)
        title.configure(style="TFrame")
        # ttk backgrounds cannot be switched per-instance on every theme.
        hero = tk.Frame(header, bg=COLORS["navy"])
        hero.place(x=24, y=12)
        tk.Label(hero, text=APP_TITLE, bg=COLORS["navy"], fg="white",
                 font=("Segoe UI Semibold", 19)).pack(anchor="w")
        tk.Label(hero, text="DIN-traceable key-joint automation for Abaqus",
                 bg=COLORS["navy"], fg="#bfdbfe",
                 font=("Segoe UI", 9)).pack(anchor="w")
        badges = tk.Frame(header, bg=COLORS["navy"])
        badges.pack(side="right", padx=22, pady=17)
        for text, color in (("NORMATIVE", "#166534"),
                            ("CORE-SCREENING", "#1d4ed8"),
                            ("FVA-RESEARCH", "#92400e")):
            tk.Label(badges, text=text, bg=color, fg="white",
                     padx=9, pady=4, font=("Segoe UI Semibold", 8)).pack(
                         side="left", padx=3)

        body = ttk.Frame(self.root, padding=(18, 14, 18, 0))
        body.pack(fill="both", expand=True)
        toolbar = ttk.Frame(body)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Preset").pack(side="left")
        self.preset = tk.StringVar(value=i18n.preset_label(
            self._selected_preset_id, self.translator))
        self.preset_combo = ttk.Combobox(
            toolbar, textvariable=self.preset,
            values=tuple(i18n.preset_label(item, self.translator)
                         for item in core.PRESETS),
            width=42, state="readonly")
        self.preset_combo.pack(side="left", padx=(6, 4))
        self.preset_combo.bind("<<ComboboxSelected>>", self._preset_selected)
        ttk.Button(toolbar, text="Aplicar", command=self.apply_preset,
                   style="Secondary.TButton").pack(side="left")
        ttk.Label(toolbar, text="Idioma").pack(side="left", padx=(18, 5))
        self.language_combo = ttk.Combobox(
            toolbar, textvariable=self.language_var,
            values=tuple(i18n.LANGUAGE_LABELS[code]
                         for code in i18n.SUPPORTED_LOCALES),
            width=11, state="readonly")
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self._language_changed)
        ttk.Button(toolbar, text="Cargar JSON", command=self.load_json,
                   style="Secondary.TButton").pack(side="right", padx=3)
        ttk.Button(toolbar, text="Guardar configuración", command=self.save_json,
                   style="Secondary.TButton").pack(side="right", padx=3)
        ttk.Button(toolbar, text="Restablecer", command=self.load_defaults,
                   style="Secondary.TButton").pack(side="right", padx=3)

        self.notebook = ttk.Notebook(body)
        self.notebook.pack(fill="both", expand=True)
        self.project_tab = ttk.Frame(self.notebook, padding=12)
        self.geometry_tab = ttk.Frame(self.notebook, padding=12)
        self.mesh_tab = ttk.Frame(self.notebook, padding=12)
        self.analysis_tab = ttk.Frame(self.notebook, padding=12)
        self.din6892_tab = ttk.Frame(self.notebook, padding=12)
        self.run_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.project_tab, text="1  Proyecto")
        self.notebook.add(self.geometry_tab, text="2  Geometría DIN")
        self.notebook.add(self.mesh_tab, text="3  Malla y materiales")
        self.notebook.add(self.analysis_tab, text="4  Análisis")
        self.notebook.add(self.din6892_tab, text="5  DIN 6892 / FVA")
        self.notebook.add(self.run_tab, text="6  Ejecutar y evidencias")
        self._build_project_tab()
        self._build_geometry_tab()
        self._build_mesh_tab()
        self._build_analysis_tab()
        self._build_din6892_tab()
        self._build_run_tab()

        action = ttk.Frame(self.root, padding=(18, 10, 18, 12))
        action.pack(fill="x")
        self.status_var = tk.StringVar(
            value=self.tr(self._status_state[0], **self._status_state[1]))
        self.status_label = tk.Label(action, textvariable=self.status_var,
                                     bg=COLORS["bg"], fg=COLORS["muted"],
                                     font=("Segoe UI Semibold", 9), anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        ttk.Button(action, text="Validar", command=self.validate_form,
                   style="Secondary.TButton").pack(side="right", padx=4)
        self.stop_button = ttk.Button(action, text="Detener", command=self.stop_run,
                                      style="Danger.TButton", state="disabled")
        self.stop_button.pack(side="right", padx=4)
        self.build_button = ttk.Button(action, text="GENERAR PROYECTO",
                                       command=self.start_build,
                                       style="Accent.TButton")
        self.build_button.pack(side="right", padx=4)

    # --------------------------------------------------------------- tab utils
    def _card(self, parent, title, row=0, column=0, columnspan=1, sticky="nsew"):
        frame = ttk.LabelFrame(parent, text=title, padding=14,
                               style="Card.TLabelframe")
        frame.grid(row=row, column=column, columnspan=columnspan,
                   sticky=sticky, padx=6, pady=6)
        return frame

    def _field(self, parent, row, label, key, unit="", width=18, state="normal"):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(
            row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=self.vars[key], width=width,
                          state=state)
        entry.grid(row=row, column=1, sticky="ew", padx=(12, 5), pady=4)
        if unit:
            ttk.Label(parent, text=unit, style="Muted.Card.TLabel").grid(
                row=row, column=2, sticky="w")
        parent.columnconfigure(1, weight=1)
        entry.bind("<FocusOut>", lambda _event: self.schedule_refresh())
        entry.bind("<Return>", lambda _event: self.refresh_derived())
        return entry

    def _browse_dir(self):
        selected = filedialog.askdirectory(initialdir=self.vars["base_dir"].get())
        if selected:
            self.vars["base_dir"].set(selected)

    def _browse_abaqus(self):
        selected = filedialog.askopenfilename(
            title=self.tr("gui.file.select_abaqus"),
            filetypes=((self.tr("gui.file.abaqus_launcher"), "*.bat *.cmd *.exe"),
                       (self.tr("gui.file.all"), "*.*")), initialdir=r"C:\SIMULIA")
        if selected:
            self.vars["abaqus_cmd"].set(selected)

    # --------------------------------------------------------------- project tab
    def _build_project_tab(self):
        tab = self.project_tab
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        left = self._card(tab, "Identidad del proyecto", 0, 0)
        self._field(left, 0, "Nombre del proyecto", "project_name")
        self._field(left, 1, "Nombre del modelo Abaqus", "model_name")
        self._field(left, 2, "Autor / equipo", "author")
        ttk.Label(left, text="Cada ejecución crea una carpeta nueva con fecha y hora.",
                  style="Muted.Card.TLabel", wraplength=420).grid(
                      row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        right = self._card(tab, "Integración y ubicación", 0, 1)
        self._field(right, 0, "Directorio base", "base_dir")
        ttk.Button(right, text="…", width=3, command=self._browse_dir).grid(
            row=0, column=3, padx=(2, 0))
        self._field(right, 1, "Comando de Abaqus", "abaqus_cmd")
        ttk.Button(right, text="…", width=3, command=self._browse_abaqus).grid(
            row=1, column=3, padx=(2, 0))
        ttk.Button(right, text="Detectar Abaqus", command=lambda: self.vars[
            "abaqus_cmd"].set(detect_abaqus())).grid(row=2, column=1, sticky="w", pady=6)

        layout = self._card(tab, "Estructura reproducible creada automáticamente", 1, 0, 2)
        tree = self.tr("gui.static.project_tree")
        tk.Label(layout, text=tree, justify="left", anchor="w", bg=COLORS["card"],
                 fg="#334155", font=("Cascadia Mono", 9)).pack(fill="x")
        opts = ttk.Frame(layout, style="Card.TFrame")
        opts.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(opts, text="Guardar CAE", variable=self.vars["save_cae"]).pack(side="left")
        ttk.Checkbutton(opts, text="Crear capturas", variable=self.vars["make_preview"]).pack(side="left", padx=18)
        ttk.Checkbutton(opts, text="Compilar PDF si hay LaTeX", variable=self.vars["compile_pdf"]).pack(side="left")

    # -------------------------------------------------------------- geometry tab
    def _build_geometry_tab(self):
        tab = self.geometry_tab
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        inputs = self._card(tab, "Parámetros independientes", 0, 0)
        row = 0
        ttk.Label(inputs, text="Forma de chaveta", style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=4)
        form = ttk.Combobox(inputs, textvariable=self.vars["form"],
                            values=("A", "B", "AB"), state="readonly", width=16)
        form.grid(row=row, column=1, sticky="ew", padx=(12, 5)); row += 1
        form.bind("<<ComboboxSelected>>", lambda _e: self.refresh_derived())
        ttk.Label(inputs, text="Ranura", style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=4)
        groove = ttk.Combobox(inputs, textvariable=self.vars["groove_form"],
                              values=("N1",), state="readonly", width=16)
        groove.grid(row=row, column=1, sticky="ew", padx=(12, 5)); row += 1
        self._field(inputs, row, "Diámetro de eje d1", "D", "mm"); row += 1
        self._field(inputs, row, "Relación L / d1", "L_over_D"); row += 1
        self._field(inputs, row, "Longitud total de ranura", "slot_total_length", "mm"); row += 1
        self._field(inputs, row, "Offset inicial", "z0_offset", "mm"); row += 1
        self._field(inputs, row, "Radio extremo (0 = b/2)", "R_cap", "mm"); row += 1
        self._field(inputs, row, "Radio de fondo r2", "r2", "mm"); row += 1
        self._field(inputs, row, "Holgura ranura de eje", "slot_clearance", "mm"); row += 1
        ttk.Separator(inputs).grid(row=row, column=0, columnspan=3, sticky="ew", pady=8); row += 1
        self._field(inputs, row, "Longitud nominal l (0 = auto)", "key_length", "mm"); row += 1
        self._field(inputs, row, "Chaflán de chaveta c", "key_chamfer", "mm"); row += 1
        ttk.Checkbutton(inputs, text="Ajustar l a la serie DIN que cabe",
                        variable=self.vars["key_snap"], command=self.refresh_derived).grid(
                            row=row, column=0, columnspan=3, sticky="w", pady=4); row += 1
        ttk.Separator(inputs).grid(row=row, column=0, columnspan=3, sticky="ew", pady=8); row += 1
        self._field(inputs, row, "Longitud de cubo", "hub_length", "mm"); row += 1
        self._field(inputs, row, "D_cubo / d_eje", "hub_ratio"); row += 1
        self._field(inputs, row, "Radio techo cubo r1", "hub_r1", "mm"); row += 1
        self._field(inputs, row, "Holgura total del cubo", "hub_clearance", "mm")

        derived_card = self._card(tab, "Resultado derivado y trazabilidad", 0, 1)
        badgebar = tk.Frame(derived_card, bg=COLORS["card"])
        badgebar.pack(fill="x", pady=(0, 8))
        self.geometry_badge = tk.Label(badgebar, text="NORMATIVE", bg="#166534",
                                       fg="white", padx=9, pady=4,
                                       font=("Segoe UI Semibold", 8))
        self.geometry_badge.pack(side="left")
        tk.Label(badgebar, text="DIN 6885-1:2021-11 · rango 6 < d1 ≤ 500 mm",
                 bg=COLORS["card"], fg=COLORS["muted"],
                 font=("Segoe UI", 8)).pack(side="left", padx=9)
        self.derived_text = tk.Text(derived_card, wrap="word", relief="flat",
                                    bg="#f8fafc", fg=COLORS["text"],
                                    font=("Cascadia Mono", 9), padx=12, pady=12)
        self.derived_text.pack(fill="both", expand=True)
        self.derived_text.tag_configure("heading", font=("Segoe UI Semibold", 11),
                                        foreground=COLORS["blue2"])
        self.derived_text.tag_configure("good", foreground=COLORS["good"])
        self.derived_text.tag_configure("warn", foreground=COLORS["warn"])
        self.derived_text.tag_configure("bad", foreground=COLORS["bad"])
        self.derived_text.configure(state="disabled")
        note = ttk.Label(derived_card,
                         text="C–J y N2/N3 se bloquean hasta implementar sus taladros, chaflanes y cortadores; no se sustituye silenciosamente otra forma.",
                         style="Muted.Card.TLabel", wraplength=520)
        note.pack(fill="x", pady=(8, 0))

    # ---------------------------------------------------------------- mesh tab
    def _build_mesh_tab(self):
        tab = self.mesh_tab
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        mesh = self._card(tab, "Selección automática y malla", 0, 0)
        ttk.Label(mesh, text="Template preguardado", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", pady=4)
        self.mesh_template_combo = ttk.Combobox(
            mesh, textvariable=self.vars["mesh_template"],
            values=tuple(core.mesh_template_names()), state="readonly", width=28)
        self.mesh_template_combo.grid(row=0, column=1, sticky="ew", padx=12)
        self.mesh_template_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._mesh_template_changed(apply_defaults=True))
        ttk.Label(mesh, text="Modo", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=4)
        mode = ttk.Combobox(mesh, textvariable=self.vars["mesh_selection"],
                            values=("auto", "fixed"), state="readonly")
        mode.grid(row=1, column=1, sticky="ew", padx=12)
        mode.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        self._field(mesh, 2, "Máximo de candidatos/pieza", "mesh_max_attempts")
        ttk.Label(mesh, text="Receta fija (vacío = primera)",
                  style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        fixed = ttk.Combobox(
            mesh, textvariable=self.vars["mesh_fixed_recipe"],
            values=("",) + tuple(sorted(core.MESH_RECIPE_CATALOG.keys())),
            state="readonly")
        fixed.grid(row=3, column=1, sticky="ew", padx=12)
        fixed.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        ttk.Checkbutton(
            mesh, text="Bloquear build si falla el quality gate del template",
            variable=self.vars["mesh_fail_quality"],
            command=self.refresh_derived).grid(
                row=4, column=0, columnspan=3, sticky="w", pady=(8, 4))
        self.mesh_template_info = tk.StringVar(value="")
        tk.Label(mesh, textvariable=self.mesh_template_info, bg=COLORS["card"],
                 fg=COLORS["blue2"], justify="left", anchor="w",
                 wraplength=455, font=("Segoe UI", 8)).grid(
                     row=5, column=0, columnspan=3, sticky="ew", pady=(4, 10))
        ttk.Separator(mesh).grid(row=6, column=0, columnspan=3,
                                 sticky="ew", pady=(2, 8))
        ttk.Label(mesh, text="Orden solicitado", style="Card.TLabel").grid(
            row=7, column=0, sticky="w", pady=4)
        ttk.Combobox(mesh, textvariable=self.vars["element_order"],
                     values=("linear", "quadratic"), state="readonly").grid(
                         row=7, column=1, sticky="ew", padx=12)
        ttk.Label(mesh, text="Hexaedro lineal", style="Card.TLabel").grid(
            row=8, column=0, sticky="w", pady=4)
        ttk.Combobox(mesh, textvariable=self.vars["hex_code"],
                     values=("C3D8", "C3D8I", "C3D8R"), state="readonly").grid(
                         row=8, column=1, sticky="ew", padx=12)
        self._field(mesh, 9, "Seed eje (0 = auto)", "shaft_seed", "mm")
        self._field(mesh, 10, "Seed chaveta (0 = auto)", "key_seed", "mm")
        self._field(mesh, 11, "Seed cubo (0 = auto)", "hub_seed", "mm")
        self._field(mesh, 12, "Umbral reparación AR", "ar_threshold")
        ttk.Checkbutton(mesh, text="Refinamiento local de entalla",
                        variable=self.vars["notch_enabled"],
                        command=self.refresh_derived).grid(
                            row=13, column=0, columnspan=3, sticky="w",
                            pady=(10, 4))
        self._field(mesh, 14, "Elementos sobre arco r2", "notch_arc_elems")
        ttk.Label(
            mesh,
            text=("AUTO compara candidatos completos por pieza y conserva todos "
                  "los intentos. C3D8R sólo se admite si el usuario lo solicita; "
                  "ningún template lo elige automáticamente."),
            style="Muted.Card.TLabel", wraplength=455).grid(
                row=15, column=0, columnspan=3, sticky="w", pady=(10, 0))

        mats = self._card(tab, "Materiales y criterio rápido", 0, 1)
        tk.Label(mats, text="C45 presets", bg=COLORS["card"], fg=COLORS["text"],
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(mats, text=("E = 210 000 MPa   ·   ν = 0.30\n"
                             "ρ = 7.85×10⁻⁹ t/mm³   ·   Re(ref) = 430 MPa"),
                 bg=COLORS["card"], fg="#334155", justify="left",
                 font=("Cascadia Mono", 9), pady=12).pack(anchor="w")
        ttk.Separator(mats).pack(fill="x", pady=8)
        ttk.Label(mats, text="Par para screening de presión",
                  style="Card.TLabel").pack(anchor="w")
        ttk.Entry(mats, textvariable=self.vars["design_torque"], width=18).pack(
            anchor="w", pady=5)
        tk.Label(mats, text="CORE-SCREENING", bg="#1d4ed8", fg="white",
                 padx=9, pady=4, font=("Segoe UI Semibold", 8)).pack(
                     anchor="w", pady=(8, 4))
        ttk.Label(
            mats,
            text=("El cálculo uniforme de presión es una comprobación de "
                  "plausibilidad. No es DIN 6892 Método B completo."),
            style="Muted.Card.TLabel", wraplength=430).pack(anchor="w")

    def _mesh_template_changed(self, apply_defaults=False):
        template_id = self.vars["mesh_template"].get().strip().upper()
        template = core.MESH_TEMPLATES.get(template_id, {})
        if apply_defaults and template:
            self.vars["mesh_selection"].set(template.get("selection", "auto"))
            self.vars["mesh_max_attempts"].set(template.get("max_attempts", 1))
            self.vars["mesh_fixed_recipe"].set("")
            self.vars["mesh_fail_quality"].set(
                bool(template.get("fail_on_quality", True)))
        effective_order = template.get("element_order", "inherit")
        order_text = (self.vars["element_order"].get()
                      if effective_order == "inherit" else effective_order)
        description = i18n.mesh_template_description(
            template_id, self.translator,
            template.get("description", self.tr("gui.mesh.unknown_template")))
        gate = self.tr("gui.mesh_gate.blocking") if self.vars[
            "mesh_fail_quality"].get() else self.tr("gui.mesh_gate.hard_only")
        self.mesh_template_info.set(self.tr(
            "gui.mesh_info", description=description,
            algorithm=core.MESH_ALGORITHM_VERSION, order=order_text,
            attempts=(self.vars["mesh_max_attempts"].get() or
                      template.get("max_attempts")), gate=gate))
        self.refresh_derived()

    # ------------------------------------------------------------- analysis tab
    def _build_analysis_tab(self):
        tab = self.analysis_tab
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        generic = self._card(tab, "Análisis torsional genérico", 0, 0)
        ttk.Checkbutton(generic, text="Añadir contacto y paso torsional",
                        variable=self.vars["analysis_enabled"], command=self._analysis_mode_changed).grid(
                            row=0, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(generic, text="Crear Job",
                        variable=self.vars["create_job"]).grid(row=1, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(generic, text="Enviar al solver",
                        variable=self.vars["submit_job"]).grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        self._field(generic, 3, "Par aplicado", "analysis_torque", "N·m")
        self._field(generic, 4, "Fricción Coulomb", "friction")
        self._field(generic, 5, "CPU", "cpus")
        ttk.Label(generic,
                  text="Los archivos del solver se escriben exclusivamente en jobs/. Antes de citar tensiones, comprobar convergencia, equilibrio y contacto.",
                  style="Muted.Card.TLabel", wraplength=430).grid(
                      row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))

        research = self._card(tab, "Preset FVA 600 III — investigación", 0, 1)
        tk.Label(research, text="FVA-RESEARCH", bg="#92400e", fg="white",
                 padx=9, pady=4, font=("Segoe UI Semibold", 8)).grid(
                     row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Checkbutton(research,
                        text="Activar backend numérico Método A",
                        variable=self.vars["fva_enabled"], command=self._fva_mode_changed).grid(
                            row=1, column=0, columnspan=3, sticky="w", pady=4)
        self._field(research, 2, "Par máximo", "fva_torque", "N·m")
        self._field(research, 3, "Ciclos del modelo", "fva_cycles", "LW")
        ttk.Separator(research).grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        info = ("El backend conectado genera Shaft–Key–Hub, contacto finite-sliding, "
                "interferencia escalonada y mallas verificadas en las interfaces.\n\n"
                "El valor recomendado es 20 LW (mínimo 10). Crear Job y ejecutar "
                "solver son opciones separadas y permanecen desactivadas.\n\n"
                "Criterio de investigación: vcrit = 0.5 · factor recomendado S = 1.2.")
        ttk.Label(research, text=info, style="Muted.Card.TLabel",
                  wraplength=440, justify="left").grid(
                      row=5, column=0, columnspan=3, sticky="w")

    # --------------------------------------------------------- DIN 6892 / FVA tab
    def _build_din6892_tab(self):
        tab = self.din6892_tab
        for column in range(3):
            tab.columnconfigure(column, weight=1)
        tab.rowconfigure(1, weight=1)

        selection = self._card(tab, "Método y configuración FVA", 0, 0)
        ttk.Checkbutton(
            selection, text="Activar cálculo DIN 6892",
            variable=self.vars["din_enabled"], command=self.refresh_derived).grid(
                row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(selection, text="Método", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=4)
        method_combo = ttk.Combobox(
            selection, textvariable=self.vars["din_method"],
            values=din6892.METHOD_IDS, state="readonly", width=24)
        method_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(12, 0))
        method_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        ttk.Label(selection, text="Variante FVA", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=4)
        variant_combo = ttk.Combobox(
            selection, textvariable=self.vars["fva_variant"],
            values=tuple(sorted(din6892.FVA_VARIANTS)), state="readonly", width=16)
        variant_combo.grid(row=2, column=1, sticky="ew", padx=(12, 5))
        variant_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        ttk.Button(selection, text="Aplicar geometría", command=self._apply_fva_variant,
                   style="Secondary.TButton").grid(row=2, column=2, sticky="ew")
        ttk.Label(selection, text="Par de materiales", style="Card.TLabel").grid(
            row=3, column=0, sticky="w", pady=4)
        material_combo = ttk.Combobox(
            selection, textvariable=self.vars["fva_material"],
            values=tuple(sorted(din6892.MATERIAL_CATALOG)), state="readonly", width=28)
        material_combo.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(12, 0))
        material_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        ttk.Checkbutton(
            selection, text="Exigir coincidencia geométrica con VB seleccionada",
            variable=self.vars["fva_apply_variant"], command=self.refresh_derived).grid(
                row=4, column=0, columnspan=3, sticky="w", pady=4)
        self._field(selection, 5, "Ciclos de carga", "din_load_cycles")
        self._field(selection, 6, "Razón de carga R", "din_load_ratio")
        self._field(selection, 7, "Inversiones de sentido N_W", "din_nw")
        self._field(selection, 8, "U_PF chaveta–ranura", "din_upf", "µm")
        self._field(selection, 9, "ξ eje–cubo", "din_xi", "‰")
        ttk.Label(
            selection,
            text=("N_W vacío = se deduce de R: R ≥ 0 es par pulsante sin cambio "
                  "de flanco (f_W = 1); R < 0 alterna y cuenta un cambio por ciclo."),
            style="Muted.Card.TLabel", wraplength=360).grid(
                row=10, column=0, columnspan=3, sticky="w", pady=(4, 0))

        factors = self._card(tab, "Factores y seguridad", 1, 0)
        self._field(factors, 0, "K_λ", "din_klambda")
        self._field(factors, 1, "K_R", "din_kr")
        self._field(factors, 2, "f_H (vacío = Tabla 2)", "din_fh")
        self._field(factors, 3, "f_S (vacío = Tabla 2)", "din_fs")
        self._field(factors, 4, "Factor de seguridad", "din_safety")
        self._field(factors, 5, "Número de chavetas i", "din_key_count")
        self._field(factors, 6, "Reparto φ", "din_phi")
        self._field(factors, 7, "Volumen relativo v", "din_v")
        ttk.Label(factors, text="Derivación de carga (K_λ)",
                  style="Card.TLabel").grid(row=8, column=0, sticky="w", pady=4)
        derivation_combo = ttk.Combobox(
            factors, textvariable=self.vars["din_load_derivation"],
            values=din6892.LOAD_DERIVATION_POSITIONS, state="readonly", width=16)
        derivation_combo.grid(row=8, column=1, columnspan=2, sticky="ew",
                              padx=(12, 0))
        derivation_combo.bind("<<ComboboxSelected>>",
                              lambda _event: self.refresh_derived())
        ttk.Label(factors, text="Profundidad portante t1tr",
                  style="Card.TLabel").grid(row=9, column=0, sticky="w", pady=4)
        depth_combo = ttk.Combobox(
            factors, textvariable=self.vars["din_depth_policy"],
            values=din6892.DEPTH_POLICIES, state="readonly", width=16)
        depth_combo.grid(row=9, column=1, columnspan=2, sticky="ew", padx=(12, 0))
        depth_combo.bind("<<ComboboxSelected>>",
                         lambda _event: self.refresh_derived())
        tk.Label(factors, text="USER-INPUT", bg="#7f1d1d", fg="white",
                 padx=9, pady=4, font=("Segoe UI Semibold", 8)).grid(
                     row=10, column=0, sticky="w", pady=(8, 2))
        ttk.Label(
            factors,
            text=("K_λ, K_R y φ deben proceder de norma licenciada, ensayo o "
                  "decisión trazable. EQUATION_9 mantiene la ecuación transcrita; "
                  "GEOMETRIC/CONSERVATIVE usan la altura real del flanco."),
            style="Muted.Card.TLabel", wraplength=360).grid(
                row=11, column=0, columnspan=3, sticky="w", pady=(4, 0))

        loading = self._card(tab, "Cargas y comprobación B / C", 2, 0)
        self._field(loading, 0, "K_A aplicación", "din_ka")
        self._field(loading, 1, "M_t nominal", "din_torque_nominal", "N m")
        self._field(loading, 2, "M_teq aplicado", "din_torque_applied", "N m")
        self._field(loading, 3, "f_L picos", "din_fl")
        self._field(loading, 4, "M_t pico aplicado", "din_torque_peak", "N m")
        self._field(loading, 5, "M_t requerido (dim. C)", "din_torque_required",
                    "N m")
        ttk.Label(loading, text="Variante Método C", style="Card.TLabel").grid(
            row=6, column=0, sticky="w", pady=4)
        variant_c_combo = ttk.Combobox(
            loading, textvariable=self.vars["din_method_c_variant"],
            values=tuple(sorted(din6892.METHOD_C_VARIANTS)), state="readonly",
            width=16)
        variant_c_combo.grid(row=6, column=1, columnspan=2, sticky="ew",
                             padx=(12, 0))
        variant_c_combo.bind("<<ComboboxSelected>>",
                             lambda _event: self.refresh_derived())
        ttk.Label(
            loading,
            text=("M_teq = K_A · M_t nominal si no se indica M_teq. f_L activa "
                  "p_max,zul = f_L · p_zul. M_t requerido devuelve la longitud "
                  "portante y la longitud normalizada DIN 6885 necesarias."),
            style="Muted.Card.TLabel", wraplength=360).grid(
                row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))

        evidence = self._card(tab, "Método A — evidencia volumétrica externa", 0, 1)
        self._field(evidence, 0, "Ciclos evaluados", "method_a_cycles")
        self._field(evidence, 1, "Step de origen", "method_a_step")
        self._field(evidence, 2, "Frame descargado", "method_a_frame")
        ttk.Checkbutton(
            evidence, text="Confirmo que el frame está descargado",
            variable=self.vars["method_a_unloaded"], command=self.refresh_derived).grid(
                row=3, column=0, columnspan=3, sticky="w", pady=4)
        self._field(evidence, 4, "CSV importado", "method_a_csv", state="readonly")
        ttk.Button(evidence, text="Importar CSV x_mm,z_mm,opening_um",
                   command=self._import_method_a_csv,
                   style="Secondary.TButton").grid(
                       row=5, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        ttk.Label(
            evidence,
            text="El importador integra ΔV y conserva SHA-256. Model Builder no afirma haber resuelto el ODB externo.",
            style="Muted.Card.TLabel", wraplength=370).grid(
                row=6, column=0, columnspan=3, sticky="w", pady=(6, 8))
        ttk.Separator(evidence).grid(
            row=7, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(evidence, text="MATLAB opcional", style="Card.TLabel").grid(
            row=8, column=0, sticky="w", pady=4)
        matlab_mode = ttk.Combobox(
            evidence, textvariable=self.vars["matlab_mode"],
            values=("OFF", "EXPORT", "RUN"), state="readonly", width=16)
        matlab_mode.grid(row=8, column=1, columnspan=2, sticky="ew", padx=(12, 0))
        matlab_mode.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        self._field(evidence, 9, "Ejecutable MATLAB", "matlab_executable")
        self._field(evidence, 10, "Timeout MATLAB", "matlab_timeout", "s")
        self.matlab_button = ttk.Button(
            evidence, text="Exportar/ejecutar MATLAB",
            command=self._run_method_a_matlab,
            style="Secondary.TButton")
        self.matlab_button.grid(
            row=11, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        ttk.Label(
            evidence,
            text="Python conserva la autoridad; EXPORT crea un bundle auditable y RUN es explícito, sin shell.",
            style="Muted.Card.TLabel", wraplength=370).grid(
                row=12, column=0, columnspan=3, sticky="w", pady=(6, 0))

        backend = self._card(tab, "Realización CAE Método A", 1, 1)
        ttk.Checkbutton(
            backend, text="Generar modelo Método A híbrido/conectado",
            variable=self.vars["fva_enabled"], command=self._fva_mode_changed).grid(
                row=0, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(backend, text="Backend", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=4)
        backend_combo = ttk.Combobox(
            backend, textvariable=self.vars["fva_backend"],
            values=(din6892.BACKEND_METHOD_A_HYBRID_HEX,
                    din6892.BACKEND_METHOD_A_CONNECTED,
                    din6892.BACKEND_LEGACY_D40),
            state="readonly", width=31)
        backend_combo.grid(row=1, column=1, columnspan=2,
                           sticky="ew", padx=(12, 0))
        backend_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        self._field(backend, 2, "Ciclos del modelo", "fva_cycles", "LW")
        self._field(backend, 3, "Par máximo", "fva_torque", "N·m")
        self._field(backend, 4, "Criterio vcrit", "fva_vcrit")
        self._field(backend, 5, "Tamaño objetivo en contacto", "fva_mesh_size", "mm")
        self._field(backend, 6, "Tolerancia de matching", "fva_matching_tolerance", "mm")
        model_values = (din6892.SHAFT_MODEL_COMBINED,
                        din6892.HUB_MODEL_UML,
                        din6892.MODEL_ELASTIC_IDEAL_PLASTIC,
                        din6892.MODEL_LINEAR_ELASTIC)
        for row, label, key, values in (
                (7, "Modelo del eje", "fva_shaft_model",
                 (model_values[0], model_values[2], model_values[3])),
                (8, "Modelo del cubo", "fva_hub_model",
                 (model_values[1], model_values[2], model_values[3])),
                (9, "Modelo de la chaveta", "fva_key_model",
                 (model_values[2], model_values[3]))):
            ttk.Label(backend, text=label, style="Card.TLabel").grid(
                row=row, column=0, sticky="w", pady=3)
            combo = ttk.Combobox(
                backend, textvariable=self.vars[key], values=values,
                state="readonly", width=31)
            combo.grid(row=row, column=1, columnspan=2,
                       sticky="ew", padx=(12, 0))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        ttk.Checkbutton(
            backend, text="Modo seguro NOJOB",
            variable=self.vars["fva_strict_no_job"], command=self.refresh_derived).grid(
                row=10, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(
            backend, text="Crear Job Método A",
            variable=self.vars["fva_create_job"], command=self.refresh_derived).grid(
                row=11, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(
            backend, text="Enviar Método A al solver",
            variable=self.vars["fva_submit_solver"], command=self.refresh_derived).grid(
                row=12, column=0, columnspan=3, sticky="w", pady=3)
        tk.Label(backend,
                 text="METHOD_A_NUMERICAL_SETUP · MATCHING VERIFIED AT BUILD",
                 bg="#92400e", fg="white", padx=9, pady=4,
                 font=("Segoe UI Semibold", 8)).grid(
                     row=13, column=0, columnspan=3, sticky="w", pady=(8, 4))
        ttk.Label(
            backend,
            text="El modelo queda listo para resolver; Método A sólo se completa con frame descargado, ΔV, convergencia, equilibrio, contacto y DIN 743 independiente.",
            style="Muted.Card.TLabel", wraplength=370).grid(
                row=14, column=0, columnspan=3, sticky="w", pady=(4, 0))

        registry = self._card(tab, "Normas seleccionadas y soporte", 0, 2)
        selectors = (
            ("Geometría", "standard_geometry", ("DIN_6885_1_2021", "DIN_6888")),
            ("Resistencia", "standard_strength", ("DIN_6892",)),
            ("Fatiga", "standard_fatigue", ("DIN_743",)),
            ("Ajustes", "standard_fit", ("DIN_EN_ISO_286",)),
            ("Cierre por fricción", "standard_friction", ("DIN_7190_1",)),
        )
        for row, (label, key, values) in enumerate(selectors):
            ttk.Label(registry, text=label, style="Card.TLabel").grid(
                row=row, column=0, sticky="w", pady=3)
            combo = ttk.Combobox(registry, textvariable=self.vars[key],
                                 values=values, state="readonly", width=23)
            combo.grid(row=row, column=1, sticky="ew", padx=(8, 0))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_derived())
        registry.columnconfigure(1, weight=1)
        self.standard_registry_text = tk.Text(
            registry, height=8, wrap="word", relief="flat", bg="#f8fafc",
            fg=COLORS["text"], font=("Cascadia Mono", 8), padx=8, pady=8)
        self.standard_registry_text.grid(
            row=len(selectors), column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.standard_registry_text.configure(state="disabled")

        result = self._card(tab, "Resultado DIN 6892 / FVA", 1, 2)
        self.din_result_text = tk.Text(
            result, height=13, wrap="word", relief="flat", bg="#f8fafc",
            fg=COLORS["text"], font=("Cascadia Mono", 9), padx=10, pady=10)
        self.din_result_text.pack(fill="both", expand=True)
        self.din_result_text.tag_configure(
            "heading", font=("Segoe UI Semibold", 10), foreground=COLORS["blue2"])
        self.din_result_text.tag_configure("good", foreground=COLORS["good"])
        self.din_result_text.tag_configure("warn", foreground=COLORS["warn"])
        self.din_result_text.tag_configure("bad", foreground=COLORS["bad"])
        self.din_result_text.configure(state="disabled")

    # ------------------------------------------------------------------ run tab
    def _build_run_tab(self):
        tab = self.run_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        status = self._card(tab, "Estado de ejecución", 0, 0)
        self.run_title = tk.StringVar(
            value=self.tr(self._run_title_state[0], **self._run_title_state[1]))
        tk.Label(status, textvariable=self.run_title, bg=COLORS["card"],
                 fg=COLORS["text"], font=("Segoe UI Semibold", 14)).pack(anchor="w")
        self.run_path = tk.StringVar(
            value=self.tr(self._run_path_state[0], **self._run_path_state[1]))
        tk.Label(status, textvariable=self.run_path, bg=COLORS["card"],
                 fg=COLORS["muted"], font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=4)
        self.progress = ttk.Progressbar(status, mode="indeterminate")
        self.progress.pack(fill="x", pady=(8, 4))
        buttons = ttk.Frame(status, style="Card.TFrame")
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Abrir proyecto", command=self.open_project,
                   style="Secondary.TButton").pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="Abrir informe", command=self.open_report,
                   style="Secondary.TButton").pack(side="left", padx=4)
        ttk.Button(buttons, text="Abrir modelo", command=self.open_model,
                   style="Secondary.TButton").pack(side="left", padx=4)

        logcard = self._card(tab, "Log combinado", 1, 0)
        logcard.rowconfigure(0, weight=1)
        logcard.columnconfigure(0, weight=1)
        self.log = tk.Text(logcard, bg=COLORS["log"], fg=COLORS["logfg"],
                           insertbackground="white", relief="flat", wrap="word",
                           font=("Cascadia Mono", 8), padx=10, pady=10)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(logcard, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    # ------------------------------------------------------------- collect/apply
    def _params_from_form(self):
        # Normalize the original document first so schema 5 cannot be hidden by
        # schema-6 defaults and unexposed fields survive a round trip.
        source = copy.deepcopy(self._loaded_params or core.default_params())
        p = core.normalize_params(source)
        i18n.set_param_language(p, self.locale)
        D = _float(self.vars["D"].get(), "Diámetro d1")
        row = core.din6885_row(D)
        rcap_user = _float(self.vars["R_cap"].get(), "R_cap")
        rcap = rcap_user if rcap_user > 0 else row["b"] / 2.0
        slot_total = _float(self.vars["slot_total_length"].get(),
                            "Longitud total de ranura")
        dz = slot_total - 2.0 * rcap
        if dz <= 0:
            raise InputValueError(
                "slot_too_short", "Longitud total de ranura",
                minimum="%.3f" % (2.0 * rcap))
        p.update({
            "schema_version": core.SCHEMA_VERSION,
            "model_name": sanitize_name(self.vars["model_name"].get(), "PARAM_MODEL"),
            "save_cae": bool(self.vars["save_cae"].get()),
            "make_preview": bool(self.vars["make_preview"].get()),
            "compliance_mode": "normative",
            "key_form": self.vars["form"].get(),
            "groove_form": self.vars["groove_form"].get(),
            "hub_type": self.vars["hub_type"].get(),
            "element_order": self.vars["element_order"].get(),
            "linear_hex_code": self.vars["hex_code"].get(),
            "ar_repair_threshold": _float(self.vars["ar_threshold"].get(), "Umbral AR"),
        })
        p["mesh"].update({
            "template": self.vars["mesh_template"].get().strip().upper(),
            "selection": self.vars["mesh_selection"].get().strip().lower(),
            "algorithm_version": core.MESH_ALGORITHM_VERSION,
            "max_attempts": _int(
                self.vars["mesh_max_attempts"].get(), "Máximo de candidatos", 1),
            "fixed_recipe": (self.vars["mesh_fixed_recipe"].get().strip().upper()
                             if self.vars["mesh_selection"].get().strip().lower() == "fixed"
                             else ""),
            "fail_on_quality": bool(self.vars["mesh_fail_quality"].get()),
        })
        p["shaft"].update({
            "diameter_mm": D,
            "D": D,
            "L_over_D": _float(self.vars["L_over_D"].get(), "L/d1"),
            "dz": dz,
            "z0_offset": _float(self.vars["z0_offset"].get(), "Offset inicial"),
            "R_cap": rcap_user,
            "r2": _float(self.vars["r2"].get(), "r2"),
            "slot_clearance": _float(self.vars["slot_clearance"].get(), "Holgura de eje"),
            "seed": _float(self.vars["shaft_seed"].get(), "Seed de eje"),
        })
        p["key"].update({
            "l": _float(self.vars["key_length"].get(), "Longitud de chaveta"),
            "c": _float(self.vars["key_chamfer"].get(), "Chaflán c"),
            "snap_length_to_din": bool(self.vars["key_snap"].get()),
            "seed": _float(self.vars["key_seed"].get(), "Seed de chaveta"),
        })
        hub_outer_ratio = _float(
            self.vars["hub_ratio"].get(), "D_cubo/d_eje")
        if hub_outer_ratio <= 0.0:
            raise InputValueError("hub_ratio_nonpositive", "D_cubo/d_eje", minimum="0")
        p["hub"].update({
            "L_hub": _float(self.vars["hub_length"].get(), "Longitud de cubo"),
            "QA_shaft_over_outer": 1.0 / hub_outer_ratio,
            "hub_outer_over_shaft": hub_outer_ratio,
            "r1": _float(self.vars["hub_r1"].get(), "r1"),
            "groove_clearance": _float(self.vars["hub_clearance"].get(), "Holgura de cubo"),
            "seed": _float(self.vars["hub_seed"].get(), "Seed de cubo"),
        })
        p["notch"].update({
            "enabled": bool(self.vars["notch_enabled"].get()),
            "arc_elems": _int(self.vars["notch_arc_elems"].get(), "Elementos de arco", 1),
        })
        p["design_check"].update({
            "enabled": True,
            "evidence_badge": core.EVIDENCE_CORE_SCREENING,
            "method_label": "Uniform-bearing pressure screening (not DIN 6892 Method B)",
            "T_nom": _float(self.vars["design_torque"].get(), "Par de screening"),
        })
        analysis_enabled = bool(self.vars["analysis_enabled"].get())
        create_job = bool(self.vars["create_job"].get()) or bool(self.vars["submit_job"].get())
        p["analysis"].update({
            "enabled": analysis_enabled,
            "create_job": create_job,
            "submit": bool(self.vars["submit_job"].get()),
            "T_apply": _float(self.vars["analysis_torque"].get(), "Par de análisis"),
            "friction": _float(self.vars["friction"].get(), "Fricción"),
            "cpus": _int(self.vars["cpus"].get(), "CPU", 1),
        })
        din_cfg = p["din6892"]
        method_a = din_cfg.setdefault("method_a", {})
        method_a.update({
            "cycles": _int(self.vars["method_a_cycles"].get(), "Ciclos evaluados", 0),
            "unloaded_frame_verified": bool(self.vars["method_a_unloaded"].get()),
            "source_frame_identified": bool(
                self.vars["method_a_step"].get().strip() and
                self.vars["method_a_frame"].get().strip()),
            "source_step": self.vars["method_a_step"].get().strip(),
            "source_frame": self.vars["method_a_frame"].get().strip(),
        })
        din_cfg.update({
            "enabled": bool(self.vars["din_enabled"].get()),
            "method": self.vars["din_method"].get().strip().upper(),
            "variant_id": self.vars["fva_variant"].get().strip().upper(),
            "material_pair": self.vars["fva_material"].get().strip().upper(),
            "apply_variant_geometry": bool(self.vars["fva_apply_variant"].get()),
            "load_cycles": _int(self.vars["din_load_cycles"].get(), "Ciclos de carga", 1),
            "load_ratio_R": _float(self.vars["din_load_ratio"].get(), "Razón de carga R"),
            # Blank N_W lets the engine derive the load direction reversals from
            # the load ratio instead of misreading the cycle count as N_W.
            "N_W": _opt_float(self.vars["din_nw"].get(),
                              "Inversiones de sentido N_W"),
            "UPF_um": _float(self.vars["din_upf"].get(), "U_PF chaveta–ranura"),
            "xi_per_mille": _float(self.vars["din_xi"].get(), "ξ eje–cubo"),
            "K_lambda": _float(self.vars["din_klambda"].get(), "K_λ"),
            "K_R": _float(self.vars["din_kr"].get(), "K_R"),
            # Blank f_H/f_S must stay None so DIN 6892 Table 2 supplies them for
            # the declared material class; writing 1.0 would defeat the lookup.
            "f_H": _opt_float(self.vars["din_fh"].get(), "f_H"),
            "f_S": _opt_float(self.vars["din_fs"].get(), "f_S"),
            "safety_factor": _float(self.vars["din_safety"].get(), "Factor de seguridad"),
            "key_count": _int(self.vars["din_key_count"].get(), "Número de chavetas i", 1),
            "phi": _float(self.vars["din_phi"].get(), "Reparto φ"),
            "v": _float(self.vars["din_v"].get(), "Volumen relativo v"),
            "bearing_depth_policy": self.vars[
                "din_depth_policy"].get().strip().upper(),
            "load_derivation_position": self.vars[
                "din_load_derivation"].get().strip().upper(),
            "K_A": _float(self.vars["din_ka"].get(), "K_A aplicación"),
            "torque_nominal_Nm": _opt_float(
                self.vars["din_torque_nominal"].get(), "M_t nominal"),
            "torque_applied_Nm": _opt_float(
                self.vars["din_torque_applied"].get(), "M_teq aplicado"),
            "f_L": _opt_float(self.vars["din_fl"].get(), "f_L picos"),
            "torque_peak_applied_Nm": _opt_float(
                self.vars["din_torque_peak"].get(), "M_t pico aplicado"),
            "torque_required_Nm": _opt_float(
                self.vars["din_torque_required"].get(), "M_t requerido"),
            "method_c_variant": self.vars[
                "din_method_c_variant"].get().strip().upper(),
        })
        selected = p["standards"].setdefault("selected", {})
        selected.update({
            "geometry": self.vars["standard_geometry"].get(),
            "strength": self.vars["standard_strength"].get(),
            "fatigue": self.vars["standard_fatigue"].get(),
            "fit": self.vars["standard_fit"].get(),
            "friction_closure": self.vars["standard_friction"].get(),
        })
        fva_enabled = bool(self.vars["fva_enabled"].get())
        backend_id = self.vars["fva_backend"].get().strip()
        legacy_backend = backend_id == din6892.BACKEND_LEGACY_D40
        hybrid_backend = backend_id == din6892.BACKEND_METHOD_A_HYBRID_HEX
        if hybrid_backend:
            p["element_order"] = "quadratic"
            p["quadratic_hex_code"] = "C3D20R"
            p["mesh"].update({
                "template": "FVA_METHOD_A_HYBRID",
                "selection": "fixed",
                "fixed_recipe": "HEX_DOMINATED",
                "algorithm_version": core.MESH_ALGORITHM_VERSION,
                "max_attempts": 1,
                "fail_on_quality": True})
        fva_cfg = p["fva_600_iii"]
        fva_cfg.update({
            "enabled": fva_enabled,
            "evidence_badge": core.EVIDENCE_FVA_RESEARCH,
            "backend": backend_id,
            "backend_capability": (
                "LEGACY_PARTIAL_VB1_C45_1LW_NOJOB" if legacy_backend else
                "METHOD_A_HYBRID_HEX_MATCHED_OPTIONAL_JOB" if hybrid_backend else
                "METHOD_A_CONNECTED_MATCHED_OPTIONAL_JOB"),
            "variant_id": din_cfg["variant_id"],
            "material_pair": din_cfg["material_pair"],
            "requested_method": din_cfg["method"],
            "workflow": ("pre_solve_regression" if legacy_backend
                         else "method_a_numerical"),
            "method": ("research_method_a_setup" if legacy_backend
                       else "din6892_method_a_fva600"),
            "is_complete_method_a": False,
            "cycles": _int(self.vars["fva_cycles"].get(), "Ciclos del modelo", 1),
            "method_a_min_cycles": 10,
            "strict_no_job": bool(self.vars["fva_strict_no_job"].get()),
            "v_crit": _float(self.vars["fva_vcrit"].get(), "Criterio vcrit"),
            "recommended_safety_factor": 1.2,
            "torque_Nm": _float(self.vars["fva_torque"].get(), "Par FVA"),
        })
        fva_cfg.setdefault("mesh_matching", {}).update({
            "required": True,
            "target_size_mm": _float(
                self.vars["fva_mesh_size"].get(), "Tamaño objetivo en contacto"),
            "tolerance_mm": _float(
                self.vars["fva_matching_tolerance"].get(), "Tolerancia de matching"),
            "verify_after_meshing": True,
        })
        fva_cfg.setdefault("material_models", {}).update({
            "shaft": self.vars["fva_shaft_model"].get().strip().upper(),
            "hub": self.vars["fva_hub_model"].get().strip().upper(),
            "key": self.vars["fva_key_model"].get().strip().upper(),
        })
        fva_cfg.setdefault("execution", {}).update({
            "create_job": bool(self.vars["fva_create_job"].get()),
            "submit_solver": bool(self.vars["fva_submit_solver"].get()),
        })
        p.setdefault("matlab", {}).update({
            "mode": self.vars["matlab_mode"].get().strip().upper(),
            "executable": self.vars["matlab_executable"].get().strip(),
            "timeout_s": _int(self.vars["matlab_timeout"].get(), "Timeout MATLAB", 1),
        })
        d = core.derive(p)
        issues = core.validate(p, d)
        return p, d, issues

    def apply_params(self, params):
        p = core.normalize_params(copy.deepcopy(params or core.default_params()))
        self._loaded_params = copy.deepcopy(p)
        sh, ky, hu = p["shaft"], p["key"], p["hub"]
        me = p.get("mesh", {}) or {}
        din_cfg = p.get("din6892", {}) or {}
        method_a = din_cfg.get("method_a", {}) or {}
        postprocess = method_a.get("postprocess") or {}
        provenance = postprocess.get("provenance") or {}
        standards = (p.get("standards", {}) or {}).get("selected", {}) or {}
        fva_cfg = p.get("fva_600_iii", {}) or {}
        fva_matching = fva_cfg.get("mesh_matching", {}) or {}
        fva_models = fva_cfg.get("material_models", {}) or {}
        fva_execution = fva_cfg.get("execution", {}) or {}
        matlab_cfg = p.get("matlab", {}) or {}
        D = float(sh.get("diameter_mm", sh.get("D", 40.0)))
        row = core.din6885_row(D)
        rcap = float(sh.get("R_cap", 0.0) or 0.0) or row["b"] / 2.0
        slot_total = float(sh.get("dz", 38.0)) + 2.0 * rcap
        values = {
            "model_name": p.get("model_name", "PARAM_MODEL"),
            "form": p.get("key_form", "A"),
            "groove_form": p.get("groove_form", "N1"),
            "D": sh.get("diameter_mm", sh.get("D", 40.0)), "L_over_D": sh.get("L_over_D", 3.0),
            "slot_total_length": slot_total, "z0_offset": sh.get("z0_offset", 5.0),
            "R_cap": sh.get("R_cap", 0.0), "r2": sh.get("r2", 0.25),
            "slot_clearance": sh.get("slot_clearance", 0.0),
            "key_length": ky.get("l", 0.0), "key_chamfer": ky.get("c", 0.8),
            "key_snap": ky.get("snap_length_to_din", True),
            "hub_length": hu.get("L_hub", 38.0),
            "hub_ratio": hu.get("hub_outer_over_shaft",
                                1.0 / float(hu.get("QA_shaft_over_outer", 0.5))),
            "hub_r1": hu.get("r1", 0.25),
            "hub_clearance": hu.get("groove_clearance", 0.0215),
            "hub_type": p.get("hub_type", "cylindrical"),
            "mesh_template": me.get("template", "HEX_CERTIFIED"),
            "mesh_selection": me.get("selection", "auto"),
            "mesh_max_attempts": me.get("max_attempts", 3),
            "mesh_fixed_recipe": me.get("fixed_recipe", ""),
            "mesh_fail_quality": me.get("fail_on_quality", True),
            "element_order": p.get("element_order", "quadratic"),
            "hex_code": p.get("linear_hex_code", "C3D8"),
            "shaft_seed": sh.get("seed", 0.0), "key_seed": ky.get("seed", 0.0),
            "hub_seed": hu.get("seed", 0.0),
            "notch_enabled": p["notch"].get("enabled", True),
            "notch_arc_elems": p["notch"].get("arc_elems", 6),
            "ar_threshold": p.get("ar_repair_threshold", 25.0),
            "design_torque": p["design_check"].get("T_nom", 200.0),
            "analysis_enabled": p["analysis"].get("enabled", False),
            "create_job": p["analysis"].get("create_job", False),
            "submit_job": p["analysis"].get("submit", False),
            "analysis_torque": p["analysis"].get("T_apply", 200.0),
            "friction": p["analysis"].get("friction", 0.15),
            "cpus": p["analysis"].get("cpus", 1),
            "din_enabled": din_cfg.get("enabled", True),
            "din_method": din_cfg.get("method", din6892.METHOD_B_CURRENT),
            "fva_variant": din_cfg.get("variant_id", "VB1"),
            "fva_material": din_cfg.get("material_pair", "C45N_C45N"),
            "fva_apply_variant": din_cfg.get("apply_variant_geometry", False),
            "din_load_cycles": din_cfg.get("load_cycles", 10000),
            "din_load_ratio": din_cfg.get("load_ratio_R", 0.0),
            "din_nw": _blank_if_none(din_cfg.get("N_W")),
            "din_upf": din_cfg.get("UPF_um", 18.0),
            "din_xi": din_cfg.get("xi_per_mille", 0.0),
            "din_klambda": din_cfg.get("K_lambda", 1.0),
            "din_kr": din_cfg.get("K_R", 1.0),
            # None must come back as a blank field, otherwise reopening a file
            # would turn "resolve from Table 2" into a hard f_S = f_H = 1.0.
            "din_fh": _blank_if_none(din_cfg.get("f_H")),
            "din_fs": _blank_if_none(din_cfg.get("f_S")),
            "din_safety": din_cfg.get("safety_factor", 1.2),
            "din_key_count": din_cfg.get("key_count", 1),
            "din_phi": din_cfg.get("phi", 1.0),
            "din_v": din_cfg.get("v", 0.5),
            "din_depth_policy": din_cfg.get(
                "bearing_depth_policy", din6892.DEPTH_POLICY_EQUATION_9),
            "din_load_derivation": din_cfg.get(
                "load_derivation_position", din6892.LOAD_DERIVATION_REAR),
            "din_ka": din_cfg.get("K_A", 1.0),
            "din_torque_nominal": _blank_if_none(din_cfg.get("torque_nominal_Nm")),
            "din_torque_applied": _blank_if_none(din_cfg.get("torque_applied_Nm")),
            "din_fl": _blank_if_none(din_cfg.get("f_L")),
            "din_torque_peak": _blank_if_none(
                din_cfg.get("torque_peak_applied_Nm")),
            "din_torque_required": _blank_if_none(
                din_cfg.get("torque_required_Nm")),
            "din_method_c_variant": din_cfg.get(
                "method_c_variant", din6892.METHOD_C_VARIANT_DIN),
            "method_a_cycles": method_a.get("cycles", 0),
            "method_a_unloaded": method_a.get("unloaded_frame_verified", False),
            "method_a_step": (method_a.get("source_step") or
                              provenance.get("source_step", "")),
            "method_a_frame": (method_a.get("source_frame") or
                               provenance.get("source_frame", "")),
            "method_a_csv": provenance.get("path", ""),
            "standard_geometry": standards.get("geometry", "DIN_6885_1_2021"),
            "standard_strength": standards.get("strength", "DIN_6892"),
            "standard_fatigue": standards.get("fatigue", "DIN_743"),
            "standard_fit": standards.get("fit", "DIN_EN_ISO_286"),
            "standard_friction": standards.get("friction_closure", "DIN_7190_1"),
            "fva_enabled": fva_cfg.get("enabled", False),
            "fva_backend": fva_cfg.get(
                "backend", din6892.BACKEND_METHOD_A_HYBRID_HEX),
            "fva_torque": fva_cfg.get("torque_Nm", 1256.0),
            "fva_cycles": fva_cfg.get("cycles", 20),
            "fva_vcrit": fva_cfg.get("v_crit", 0.5),
            "fva_strict_no_job": fva_cfg.get("strict_no_job", True),
            "fva_create_job": fva_execution.get("create_job", False),
            "fva_submit_solver": fva_execution.get("submit_solver", False),
            "fva_mesh_size": fva_matching.get("target_size_mm", 0.8),
            "fva_matching_tolerance": fva_matching.get("tolerance_mm", 1.0e-6),
            "fva_shaft_model": fva_models.get(
                "shaft", din6892.SHAFT_MODEL_COMBINED),
            "fva_hub_model": fva_models.get("hub", din6892.HUB_MODEL_UML),
            "fva_key_model": fva_models.get(
                "key", din6892.MODEL_ELASTIC_IDEAL_PLASTIC),
            "matlab_mode": matlab_cfg.get("mode", "OFF"),
            "matlab_executable": matlab_cfg.get("executable", "matlab"),
            "matlab_timeout": matlab_cfg.get("timeout_s", 300),
            "save_cae": p.get("save_cae", True),
            "make_preview": p.get("make_preview", True),
        }
        for key, value in values.items():
            self.vars[key].set(value)
        self._set_language(i18n.locale_from_params(p))

    # --------------------------------------------------------------- validation
    def schedule_refresh(self):
        if self._refresh_after:
            self.root.after_cancel(self._refresh_after)
        self._refresh_after = self.root.after(180, self.refresh_derived)

    def refresh_derived(self):
        self._refresh_after = None
        self.derived_text.configure(state="normal")
        self.derived_text.delete("1.0", "end")
        try:
            params, derived, issues = self._params_from_form()
            badge = derived.get("geometry_badge", core.EVIDENCE_USER_OVERRIDE)
            self.geometry_badge.configure(
                text=badge,
                bg="#166534" if badge == core.EVIDENCE_NORMATIVE else "#b91c1c")
            self.derived_text.insert(
                "end", self.tr("gui.derived.din_heading") + "\n", "heading")
            self.derived_text.insert("end", self.tr(
                "gui.derived.din_values",
                D=derived["D"], band0=derived["din_band"][0],
                band1=derived["din_band"][1], b=derived["b"], h=derived["h"],
                t1=derived["t1"], t1tol=derived["t1_tol_plus"],
                t2=derived["t2"], d2=derived["din_d2_ref"],
                r1min=derived["r1_din_range"][0],
                r1max=derived["r1_din_range"][1],
                r2min=derived["r2_din_range"][0],
                r2max=derived["r2_din_range"][1],
                rz=derived["roughness_rz_max_um"]))
            self.derived_text.insert(
                "end", self.tr("gui.derived.length_heading") + "\n", "heading")
            self.derived_text.insert("end", self.tr(
                "gui.derived.length_values", form=derived["form"],
                designation=derived["key_designation"],
                nominal=derived["key_nominal_length"],
                badge=derived["key_length_badge"],
                slot=derived["slot_total_length"],
                bearing=derived["load_bearing_length"],
                offset=derived["key_axial_center_offset"]))
            self.derived_text.insert(
                "end", self.tr("gui.derived.hub_heading") + "\n", "heading")
            self.derived_text.insert("end", self.tr(
                "gui.derived.hub_values",
                ratio=derived["hub_outer_over_shaft"],
                inverse=float(derived.get("shaft_over_hub") or 0.0),
                outer=derived["d_a"], wall=derived["hub_wall_left"],
                pshaft=derived.get("p_shaft", 0.0),
                phub=derived.get("p_hub", 0.0),
                torque=derived.get("T_perm", 0.0)))
            plan = core.resolve_mesh_plan(params, derived)
            description = i18n.mesh_template_description(
                plan["template"], self.translator, plan.get("description", ""))
            gate = (self.tr("gui.mesh_gate.blocking") if plan["fail_on_quality"]
                    else self.tr("gui.mesh_gate.hard_only"))
            self.derived_text.insert(
                "end", self.tr("gui.derived.mesh_heading") + "\n", "heading")
            self.derived_text.insert("end", self.tr(
                "gui.derived.mesh_values", template=plan["template"],
                algorithm=plan["algorithm_version"], description=description,
                selection=plan["selection"], order=plan["element_order"],
                profile=i18n.element_profile_label(
                    plan["element_profile"], self.translator), gate=gate))
            for part in ("Shaft", "Key", "Hub", "Bushing"):
                candidates = plan["parts"][part]["candidates"]
                self.derived_text.insert(
                    "end", "%s: %s\n" % (
                        part, " → ".join(item["recipe_id"] for item in candidates)))
            self.derived_text.insert("end", self.tr("gui.derived.hard_gates"))
            errors = core.errors(issues)
            warnings = core.warnings_(issues)
            self.derived_text.insert(
                "end", self.tr("gui.derived.validation",
                               errors=len(errors), warnings=len(warnings)),
                "bad" if errors else ("warn" if warnings else "good"))
            for issue in issues:
                localized = i18n.localize_issue(issue, self.translator)
                tag = "bad" if issue["level"] == "error" else (
                    "warn" if issue["level"] == "warn" else "good")
                self.derived_text.insert("end", "[%s] %s: %s\n" % (
                    localized["presentation_level"], localized["code"],
                    localized["presentation_message"]), tag)
            if not issues:
                self.derived_text.insert(
                    "end", self.tr("gui.derived.no_issues"), "good")
            self._render_din_panels(derived, issues)
            self._set_status(
                "gui.status.validation", errors=len(errors), warnings=len(warnings))
        except Exception as exc:
            self.geometry_badge.configure(text="BLOCKED", bg=COLORS["bad"])
            self.derived_text.insert(
                "end", self.tr("gui.derived.blocked"), "bad")
            detail = self._error_text(exc)
            self.derived_text.insert("end", detail, "bad")
            self._set_status("gui.status.invalid", detail=detail)
        finally:
            self.derived_text.configure(state="disabled")

    def _render_din_panels(self, derived, issues):
        if not hasattr(self, "din_result_text"):
            return
        registry = derived.get("standards_registry") or din6892.standard_registry()
        self.standard_registry_text.configure(state="normal")
        self.standard_registry_text.delete("1.0", "end")
        for standard_id in sorted(registry):
            item = registry[standard_id]
            title = self.tr("standard.%s.title" % standard_id,
                            default=item.get("title", standard_id))
            implementation = self.tr(
                "standard.implementation.%s" % item.get("implementation", ""),
                default=item.get("implementation", ""))
            self.standard_registry_text.insert(
                "end", "%s · %s\n  %s\n" %
                (standard_id, implementation, title))
        self.standard_registry_text.configure(state="disabled")

        record = derived.get("din6892") or {}
        requested = record.get("requested") or {}
        calculated = record.get("calculation") or {}
        backend = (record.get("realized") or {}).get("realized") or {}
        material = (record.get("derived") or {}).get("material") or {}
        matlab_cfg = requested.get("matlab") or {}
        matlab_result = matlab_cfg.get("last_result") or {}
        self.din_result_text.configure(state="normal")
        self.din_result_text.delete("1.0", "end")
        self.din_result_text.insert(
            "end", self.tr("gui.din.result.requested_heading") + "\n", "heading")
        self.din_result_text.insert("end", self.tr(
            "gui.din.result.requested",
            method=requested.get("method", "--"),
            variant=requested.get("variant_id", "--"),
            material=requested.get("material_pair", "--")))
        self.din_result_text.insert(
            "end", self.tr("gui.din.result.derived_heading") + "\n", "heading")
        torque_allowable = calculated.get("torque_allowable_Nm")
        torque_design = calculated.get("torque_design_Nm")
        self.din_result_text.insert("end", self.tr(
            "gui.din.result.derived",
            status=record.get("status", "--"),
            material_source=material.get("source_id", "--"),
            allowable=("--" if torque_allowable is None else "%.6g" % torque_allowable),
            design=("--" if torque_design is None else "%.6g" % torque_design),
            equations=", ".join(str(value) for value in calculated.get("equations", [])) or "--"),
            "good" if calculated and record.get("status") not in ("INVALID_INPUT",) else "warn")
        volume = calculated.get("volume") or {}
        if volume:
            self.din_result_text.insert("end", self.tr(
                "gui.din.result.volume",
                delta="%.6g" % volume.get("delta_volume_mm3", 0.0),
                theoretical="%.6g" % volume.get("V_theo_mm3", 0.0),
                v="%.6g" % volume.get("v", 0.0),
                criterion=str(calculated.get("criterion_met"))))
        self.din_result_text.insert(
            "end", self.tr("gui.din.result.realized_heading") + "\n", "heading")
        self.din_result_text.insert("end", self.tr(
            "gui.din.result.realized",
            status=backend.get("status", "NOT_REQUESTED"),
            matching=backend.get("matching", "NOT_APPLICABLE"),
            job=str(backend.get("creates_job", False)),
            solver=str(backend.get("submits_solver", False))),
            "warn" if backend.get("status") == "LEGACY_PARTIAL" else "good")
        self.din_result_text.insert(
            "end", self.tr("gui.din.result.matlab_heading") + "\n", "heading")
        comparison = matlab_result.get("comparison") or {}
        match_value = ("--" if not comparison else
                       str(comparison.get("all_match")))
        self.din_result_text.insert("end", self.tr(
            "gui.din.result.matlab",
            mode=matlab_cfg.get("mode", "OFF"),
            status=matlab_result.get("status", "NOT_REQUESTED"),
            executed=str(matlab_result.get("executed", False)),
            match=match_value,
            bundle=matlab_result.get("bundle_path") or "--",
            sha256=matlab_result.get("manifest_sha256") or "--"),
            "warn" if matlab_result.get("status") in (
                "COMPLETED_MISMATCH", "TIMEOUT", "EXECUTABLE_NOT_FOUND",
                "EXECUTION_ERROR", "PROCESS_FAILED", "RESULT_MISSING",
                "RESULT_INVALID", "RESULT_ERROR") else "good")
        self.din_result_text.insert(
            "end", self.tr("gui.din.result.matlab_authority") + "\n", "warn")
        din_codes = set(item.get("code") for item in record.get("issues", []))
        relevant = [item for item in issues
                    if item.get("code") in din_codes or
                    item.get("code", "").startswith((
                        "din6892_", "fva_", "standard_", "method_a_", "matlab_"))]
        if relevant:
            self.din_result_text.insert(
                "end", self.tr("gui.din.result.issues_heading") + "\n", "heading")
            for issue in relevant:
                localized = i18n.localize_issue(issue, self.translator)
                tag = "bad" if issue.get("level") == "error" else "warn"
                self.din_result_text.insert(
                    "end", "[%s] %s: %s\n" %
                    (localized["presentation_level"], localized["code"],
                     localized["presentation_message"]), tag)
        self.din_result_text.configure(state="disabled")

    def validate_form(self):
        try:
            _params, _derived, issues = self._params_from_form()
            errors = core.errors(issues)
            warnings = core.warnings_(issues)
            if errors:
                messagebox.showerror(
                    self.tr("gui.dialog.validation_blocked.title"),
                    "\n\n".join("%s — %s" % (
                        item["code"], i18n.localize_issue(
                            item, self.translator)["presentation_message"])
                                 for item in errors))
            else:
                messagebox.showinfo(
                    self.tr("gui.dialog.validation_complete.title"),
                    self.tr("gui.dialog.validation_complete.message",
                            warnings=len(warnings)))
            self.refresh_derived()
            return not errors
        except Exception as exc:
            messagebox.showerror(
                self.tr("gui.dialog.invalid.title"), self._error_text(exc))
            return False

    # ------------------------------------------------------------- file actions
    def load_defaults(self):
        path = resource_path(DEFAULTS_NAME)
        try:
            with open(path, "r", encoding="utf-8") as stream:
                self.apply_params(json.load(stream))
        except Exception:
            self.apply_params(core.default_params())
        self._set_status("gui.status.defaults_loaded")

    def apply_preset(self):
        self._selected_preset_id = self._preset_id_from_display(self.preset.get())
        p = core.default_params()
        core.deep_update(p, copy.deepcopy(core.PRESETS.get(
            self._selected_preset_id, {})))
        i18n.set_param_language(p, self.locale)
        self.apply_params(p)
        self._set_status(
            "gui.status.preset_applied",
            preset=i18n.preset_label(self._selected_preset_id, self.translator))

    def load_json(self):
        path = filedialog.askopenfilename(
            filetypes=((self.tr("gui.file.json"), "*.json"),
                       (self.tr("gui.file.all"), "*.*")))
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                self.apply_params(json.load(stream))
            self._set_status("gui.status.loaded", path=path)
        except Exception as exc:
            messagebox.showerror(
                self.tr("gui.dialog.load_failed.title"), self._error_text(exc))

    def save_json(self):
        try:
            params, _derived, _issues = self._params_from_form()
        except Exception as exc:
            messagebox.showerror(
                self.tr("gui.dialog.invalid.title"), self._error_text(exc))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=((self.tr("gui.file.json"), "*.json"),),
            initialdir=self.vars["base_dir"].get(), initialfile="model_config.json")
        if path:
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(params, stream, indent=2, sort_keys=True, ensure_ascii=False)
                stream.write("\n")
            self._set_status("gui.status.saved", path=path)

    # --------------------------------------------------------------- run flow
    def start_build(self):
        if ((self.worker and self.worker.is_alive()) or
                (self._matlab_worker and self._matlab_worker.is_alive())):
            messagebox.showinfo(
                self.tr("gui.dialog.busy.title"),
                self.tr("gui.dialog.busy.message"))
            return
        try:
            params, _derived, issues = self._params_from_form()
        except Exception as exc:
            messagebox.showerror(
                self.tr("gui.dialog.invalid.title"), self._error_text(exc))
            return
        errors = core.errors(issues)
        if errors:
            messagebox.showerror(
                self.tr("gui.dialog.validation_blocked.title"),
                "\n\n".join("%s — %s" % (
                    item["code"], i18n.localize_issue(
                        item, self.translator)["presentation_message"])
                             for item in errors))
            if any(item.get("code", "").startswith(
                    ("din6892_", "fva_", "standard_", "method_a_"))
                   for item in errors):
                self.notebook.select(self.din6892_tab)
            else:
                self.notebook.select(self.geometry_tab)
            return
        base = self.vars["base_dir"].get().strip()
        if not base:
            messagebox.showerror(
                self.tr("gui.dialog.project.title"),
                self.tr("gui.dialog.project.base_required"))
            return
        try:
            workspace = ProjectWorkspace.create(
                base, self.vars["project_name"].get(), params["model_name"],
                core.BUILDER_VERSION, author=self.vars["author"].get(),
                technical_contract_path=resource_path(CONTRACT_NAME))
            params_path, _payload = workspace.write_params(params)
        except Exception as exc:
            messagebox.showerror(
                self.tr("gui.dialog.project_create_failed.title"),
                self._error_text(exc))
            return
        self.current_workspace = workspace
        self.runner = SubprocessRunner(self.vars["abaqus_cmd"].get())
        engine = resource_path(ENGINE_NAME)
        self._log_records = []
        self.log.delete("1.0", "end")
        self._append_user_log("gui.log.project", path=workspace.root)
        self._append_user_log("gui.log.params", path=params_path)
        self._append_user_log("gui.log.engine", path=engine)
        self._append_user_log("gui.log.technical_notice")
        self._set_run_title("gui.run.generating")
        self._set_run_path(workspace.root)
        self._set_status("gui.status.running", path=workspace.jobs)
        self.progress.start(12)
        self.build_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.notebook.select(self.run_tab)
        compile_pdf = bool(self.vars["compile_pdf"].get())
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(workspace, engine, params_path, params, compile_pdf), daemon=True)
        self.worker.start()

    def _run_worker(self, workspace, engine, params_path, params, compile_pdf):
        try:
            result = self.runner.run(
                workspace, engine, params_path,
                on_output=lambda line: self.root.after(0, self._append_log, line))
            self.root.after(
                0, lambda: self._append_user_log(
                    "gui.log.abaqus_result", code=result.return_code,
                    seconds=result.seconds))
            report = generate_report(
                workspace, compile_pdf=compile_pdf)
            workspace.scan_artifacts()
            expected = workspace.expected_paths(params["model_name"])
            missing = []
            contract_failures = []
            if not os.path.isfile(expected["audit_json"]):
                missing.append("generated/PARAM_BUILD_AUDIT.json")
            if not os.path.isfile(expected["build_result"]):
                missing.append("generated/BUILD_RESULT.json")
            if params.get("save_cae") and not os.path.isfile(expected["cae"]):
                missing.append("model/%s.cae" % params["model_name"])
            if params.get("make_preview"):
                images = [name for name in os.listdir(workspace.screenshots)
                          if name.lower().endswith(".png")]
                if not images:
                    missing.append("screenshots/*.png")
            if not os.path.isfile(report["tex"]):
                missing.append("reports/report.tex")

            build_result = {}
            audit = {}
            try:
                if os.path.isfile(expected["build_result"]):
                    with open(expected["build_result"], "r", encoding="utf-8") as stream:
                        build_result = json.load(stream)
                if os.path.isfile(expected["audit_json"]):
                    with open(expected["audit_json"], "r", encoding="utf-8") as stream:
                        audit = json.load(stream)
            except Exception as exc:
                contract_failures.append(self.tr(
                    "gui.failure.unreadable_json", detail=str(exc)))

            if not isinstance(build_result, dict) or build_result.get("ok") is not True:
                contract_failures.append(self.tr("gui.failure.build_result"))
            if not isinstance(audit, dict) or audit.get("verdict") != "OK":
                verdict = audit.get("verdict") if isinstance(audit, dict) else None
                contract_failures.append(self.tr(
                    "gui.failure.audit_verdict", verdict=verdict))
            fva_mode = bool((params.get("fva_600_iii") or {}).get("enabled", False))
            quality = (audit.get("mesh_quality") or
                       build_result.get("mesh_quality") or {})
            if not fva_mode:
                if quality.get("passed") is not True:
                    contract_failures.append(self.tr(
                        "gui.failure.quality",
                        status=quality.get("status", "MISSING"),
                        score=float(quality.get("score", 0.0) or 0.0)))
                if quality.get("hard_passed") is not True:
                    contract_failures.append(self.tr("gui.failure.hard_gates"))
                expected_plan = core.resolve_mesh_plan(params)
                requested_template = expected_plan["template"]
                realised_plan = audit.get("mesh_plan") or {}
                realised_template = realised_plan.get(
                    "template", build_result.get("mesh_template"))
                if realised_template != requested_template:
                    contract_failures.append(self.tr(
                        "gui.failure.template", actual=repr(realised_template),
                        expected=repr(requested_template)))
                if build_result.get("mesh_algorithm_version") != core.MESH_ALGORITHM_VERSION:
                    contract_failures.append(self.tr(
                        "gui.failure.algorithm",
                        expected=core.MESH_ALGORITHM_VERSION))
                if realised_plan.get("element_order") != expected_plan["element_order"]:
                    contract_failures.append(self.tr(
                        "gui.failure.order",
                        actual=repr(realised_plan.get("element_order")),
                        expected=repr(expected_plan["element_order"])))
                expected_profile = expected_plan["element_profile"]
                realised_profile = (realised_plan.get("element_profile") or
                                    build_result.get("element_profile") or {})
                if (realised_profile.get("primary") != expected_profile["primary"] or
                        realised_profile.get("fallback") != expected_profile["fallback"]):
                    contract_failures.append(self.tr(
                        "gui.failure.profile",
                        primary=repr(realised_profile.get("primary")),
                        fallback=repr(realised_profile.get("fallback")),
                        expected=i18n.element_profile_label(
                            expected_profile, self.translator)))
                for failure in core.validate_realized_element_profile(
                        expected_plan, audit.get("parts") or {}):
                    contract_failures.append(self.tr(
                        "gui.failure.element_profile", detail=failure))
            if quality:
                self.root.after(
                    0, lambda: self._append_user_log(
                        "gui.log.quality", status=quality.get("status"),
                        score=float(quality.get("score", 0.0) or 0.0),
                        hard=quality.get("hard_passed"),
                        passed=quality.get("passed")))
            evidence_failures = missing + contract_failures
            success = result.ok and not evidence_failures
            workspace.set_status(
                "COMPLETED" if success else "FAILED",
                "Validated deliverables and quality gate complete" if success else
                "Missing/failed evidence: %s" % ", ".join(evidence_failures),
                return_code=result.return_code,
                deliverables_verified=not evidence_failures,
                missing_deliverables=missing,
                contract_failures=contract_failures,
                mesh_quality=quality,
            )
            self.root.after(
                0, self._finish_run, success, result, report,
                evidence_failures, None)
        except Exception as exc:
            details = traceback.format_exc()
            try:
                workspace.set_status("FAILED", str(exc))
                # A failure report still records the structured input and logs.
                report = generate_report(
                    workspace, compile_pdf=compile_pdf)
            except Exception:
                report = None
            self.root.after(0, self._append_log, "\n[ERROR]\n%s\n" % details)
            self.root.after(0, self._finish_run, False, None, report, [], exc)

    def _finish_run(self, success, result, report, missing, error):
        self.progress.stop()
        self.build_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if error:
            detail = self._error_text(error)
            self._set_run_title("gui.run.failed")
            self._set_status("gui.status.failed", detail=detail)
            messagebox.showerror(
                APP_TITLE,
                self.tr("gui.dialog.run_failed.message", detail=detail))
            return
        if success:
            self._set_run_title("gui.run.completed")
            report_kind = (self.tr("gui.report.pdf_compiled")
                           if report and report.get("compiled")
                           else self.tr("gui.report.latex_generated"))
            self._set_status("gui.status.completed", report=report_kind)
            messagebox.showinfo(
                self.tr("gui.dialog.project_complete.title"),
                self.tr(
                    "gui.dialog.project_complete.message",
                    path=self.current_workspace.root,
                    report_message=report.get("message") if report else ""))
        else:
            self._set_run_title("gui.run.incomplete")
            reason = (", ".join(missing) if missing else self.tr(
                "gui.failure.abaqus_code",
                code=result.return_code if result else self.tr("common.unknown")))
            self._set_status("gui.status.incomplete", reason=reason)
            messagebox.showwarning(
                self.tr("gui.dialog.project_incomplete.title"), reason)

    def stop_run(self):
        if self.runner and self.runner.cancel():
            self._append_user_log("gui.log.stop")
            self._set_status("gui.status.cancel_requested")

    # --------------------------------------------------------------- open paths
    def _open(self, path):
        try:
            if not path or not os.path.exists(path):
                raise OSError(self.tr("gui.open.missing", path=path))
            os.startfile(path)
        except Exception as exc:
            messagebox.showinfo(
                self.tr("gui.dialog.open.title"), str(exc))

    def open_project(self):
        self._open(self.current_workspace.root if self.current_workspace else None)

    def open_report(self):
        if not self.current_workspace:
            return self._open(None)
        paths = self.current_workspace.expected_paths()
        self._open(paths["report_pdf"] if os.path.isfile(paths["report_pdf"])
                   else paths["report_tex"])

    def open_model(self):
        if not self.current_workspace:
            return self._open(None)
        self._open(self.current_workspace.expected_paths()["cae"])

    # --------------------------------------------------------------- misc modes
    def _apply_fva_variant(self):
        try:
            variant_id = self.vars["fva_variant"].get().strip().upper()
            variant = din6892.variant(variant_id)
            row = core.din6885_row(variant["d_w_mm"])
            derived_variant = din6892.derive_variant(
                variant_id, row["b"],
                _float(self.vars["din_upf"].get(), "U_PF chaveta–ranura"),
                _float(self.vars["fva_torque"].get(), "Par FVA"))
            nominal = derived_variant["key_nominal_length_mm"]
            slot_total = nominal if variant["key_form"] == "A" else nominal + row["b"]
            self.vars["D"].set(variant["d_w_mm"])
            self.vars["form"].set(variant["key_form"])
            self.vars["slot_total_length"].set(slot_total)
            self.vars["R_cap"].set("0.0")
            self.vars["key_length"].set(nominal)
            self.vars["key_snap"].set(False)
            self.vars["hub_length"].set(derived_variant["ltr_mm"])
            self.vars["hub_ratio"].set(derived_variant["hub_outer_over_shaft"])
            self.vars["din_load_ratio"].set(variant["load_ratio_R"])
            self.vars["din_xi"].set(variant["xi_per_mille"])
            self.vars["fva_apply_variant"].set(True)
            self._set_status("gui.status.variant_applied", variant=variant_id)
            self.refresh_derived()
        except Exception as exc:
            messagebox.showerror(
                self.tr("gui.dialog.invalid.title"), self._error_text(exc))

    def _import_method_a_csv(self):
        path = filedialog.askopenfilename(
            title=self.tr("gui.din.csv.select"),
            filetypes=((self.tr("gui.din.csv.files"), "*.csv"),
                       (self.tr("gui.file.all"), "*.*")))
        if not path:
            return
        try:
            params, derived, _issues = self._params_from_form()
            effective = derived["din6892"]["derived"]["effective_bearing_depth"]
            result = fva_postprocess.process_csv(
                path,
                derived["load_bearing_length"],
                effective["t1tr_mm"],
                _float(self.vars["din_upf"].get(), "U_PF chaveta–ranura"),
                _float(self.vars["fva_vcrit"].get(), "Criterio vcrit"),
                bool(self.vars["method_a_unloaded"].get()),
                _int(self.vars["method_a_cycles"].get(), "Ciclos evaluados", 0),
                self.vars["method_a_step"].get(),
                self.vars["method_a_frame"].get())
            attached = fva_postprocess.attach_result_to_params(params, result)
            self.apply_params(attached)
            self.notebook.select(self.din6892_tab)
            self._set_status(
                "gui.status.csv_imported",
                v="%.6g" % result["volume"]["v"],
                sha256=result["provenance"]["sha256"][:12])
            messagebox.showinfo(
                self.tr("gui.din.csv.imported_title"),
                self.tr("gui.din.csv.imported_message",
                        delta="%.6g" % result["integration"]["delta_volume_mm3"],
                        v="%.6g" % result["volume"]["v"],
                        complete=str(result["method_a_evidence_complete"]),
                        sha256=result["provenance"]["sha256"]))
        except Exception as exc:
            messagebox.showerror(
                self.tr("gui.din.csv.failed_title"), self._error_text(exc))

    def _run_method_a_matlab(self):
        if self._matlab_worker and self._matlab_worker.is_alive():
            messagebox.showinfo(
                self.tr("gui.dialog.busy.title"),
                self.tr("gui.dialog.busy.message"))
            return
        try:
            params, _derived, issues = self._params_from_form()
            matlab_cfg = params.get("matlab") or {}
            mode = str(matlab_cfg.get("mode", "OFF")).strip().upper()
            if mode == "OFF":
                result = fva_matlab.export_or_run(
                    matlab_cfg, "", {}, default_parent=None)
                self._finish_method_a_matlab(params, result)
                return
            errors = core.errors(issues)
            if errors:
                raise fva_matlab.MatlabIntegrationError(
                    "MATLAB exchange is blocked by %d validation error(s)" %
                    len(errors))
            postprocess = (((params.get("din6892") or {}).get("method_a") or {})
                           .get("postprocess") or {})
            source_csv = (postprocess.get("provenance") or {}).get("path")
            if not postprocess or not source_csv:
                raise fva_matlab.MatlabIntegrationError(
                    "Import a validated Method-A opening CSV before MATLAB exchange")
            default_parent = (self.current_workspace.generated
                              if self.current_workspace else
                              os.path.dirname(os.path.abspath(source_csv)))
            self.matlab_button.configure(state="disabled")
            self._set_status("gui.status.matlab_running", mode=mode)
            self._matlab_worker = threading.Thread(
                target=self._matlab_exchange_worker,
                args=(params, matlab_cfg, source_csv, postprocess,
                      default_parent), daemon=True)
            self._matlab_worker.start()
        except Exception as exc:
            self._finish_method_a_matlab_error(str(exc))

    def _matlab_exchange_worker(self, params, matlab_cfg, source_csv,
                                postprocess, default_parent):
        try:
            result = fva_matlab.export_or_run(
                matlab_cfg, source_csv, postprocess,
                default_parent=default_parent)
        except Exception as exc:
            self.root.after(
                0, lambda detail=str(exc):
                self._finish_method_a_matlab_error(detail))
            return
        self.root.after(
            0, lambda payload=params, exchange=result:
            self._finish_method_a_matlab(payload, exchange))

    def _finish_method_a_matlab(self, params, result):
        self._matlab_worker = None
        if hasattr(self, "matlab_button"):
            self.matlab_button.configure(state="normal")
        attached = fva_matlab.attach_result_to_params(params, result)
        self.apply_params(attached)
        if self.current_workspace:
            for artifact in result.get("artifacts") or []:
                path = artifact.get("absolute_path")
                if path and os.path.isfile(path):
                    self.current_workspace.register_artifact(
                        path, "matlab_%s" % artifact.get("role", "artifact"),
                        core.EVIDENCE_FVA_RESEARCH,
                        metadata={
                            "sha256": artifact.get("sha256"),
                            "python_authoritative": True,
                        })
        comparison = result.get("comparison") or {}
        match = "--" if not comparison else str(comparison.get("all_match"))
        self._set_status(
            "gui.status.matlab_complete", mode=result.get("mode"),
            status=result.get("status"), match=match)
        self._append_user_log(
            "gui.log.matlab_complete", mode=result.get("mode"),
            status=result.get("status"),
            bundle=result.get("bundle_path") or "--")
        message = self.tr(
            "gui.din.matlab.result_message",
            mode=result.get("mode"), status=result.get("status"),
            executed=str(result.get("executed", False)), match=match,
            bundle=result.get("bundle_path") or "--",
            sha256=result.get("manifest_sha256") or "--")
        successful = result.get("status") in (
            "SKIPPED_OFF", "EXPORTED", "COMPLETED_MATCH")
        if successful:
            messagebox.showinfo(
                self.tr("gui.din.matlab.result_title"), message)
        else:
            detail = result.get("error")
            if detail:
                message += "\n\n" + self.tr(
                    "gui.din.matlab.error_detail", detail=detail)
            messagebox.showwarning(
                self.tr("gui.din.matlab.warning_title"), message)

    def _finish_method_a_matlab_error(self, detail):
        self._matlab_worker = None
        if hasattr(self, "matlab_button"):
            self.matlab_button.configure(state="normal")
        self._set_status("gui.status.matlab_failed", detail=detail)
        messagebox.showerror(
            self.tr("gui.din.matlab.failed_title"),
            self.tr("gui.din.matlab.error_detail", detail=detail))

    def _analysis_mode_changed(self):
        if not self.vars["analysis_enabled"].get():
            self.vars["submit_job"].set(False)
        if self.vars["analysis_enabled"].get():
            self.vars["fva_enabled"].set(False)
        self.refresh_derived()

    def _fva_mode_changed(self):
        if self.vars["fva_enabled"].get():
            self.vars["analysis_enabled"].set(False)
            self.vars["create_job"].set(False)
            self.vars["submit_job"].set(False)
            backend = self.vars["fva_backend"].get().strip()
            if backend == din6892.BACKEND_LEGACY_D40:
                self.vars["model_name"].set(
                    "D40_FVA600_RESEARCH_PRESOLVE_1LW_NOJOB")
            else:
                self.vars["model_name"].set(
                    "D40_FVA600_METHOD_A_MATCHED")
            self._set_status("gui.status.fva")
        self.refresh_derived()

    def _append_log(self, text):
        self._log_records.append(("raw", str(text)))
        self.log.insert("end", text)
        self.log.see("end")

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                    self.tr("gui.dialog.active_run.title"),
                    self.tr("gui.dialog.active_run.message")):
                return
            if self.runner:
                self.runner.cancel()
        self.root.destroy()


def run_self_test():
    """Non-interactive 4.2 source/package contract check.

    The test exercises pure calculations, migration, CSV persistence and report
    rendering only. It must never start Abaqus, create a Job or invoke LaTeX.
    """
    import tempfile
    from project_workspace import (
        PARAMETER_SCHEMA_VERSION, WORKSPACE_SCHEMA_VERSION,
        migrate_workspace_manifest)
    from report_generator import render_latex, tex_escape

    def assert_close(actual, expected, tolerance=1.0e-9, label="value"):
        if abs(float(actual) - float(expected)) > tolerance:
            raise RuntimeError("%s %.15g != %.15g" %
                               (label, float(actual), float(expected)))

    def expect_value_error(callable_, text):
        try:
            callable_()
        except ValueError as exc:
            if text and text.lower() not in str(exc).lower():
                raise RuntimeError("Unexpected validation error: %s" % exc)
            return
        raise RuntimeError("Expected ValueError containing %r" % text)

    if core.BUILDER_VERSION != "4.2" or core.SCHEMA_VERSION != 6:
        raise RuntimeError("Packaged identity is not Model Builder 4.2/schema 6")
    if PARAMETER_SCHEMA_VERSION != 6 or WORKSPACE_SCHEMA_VERSION != 2:
        raise RuntimeError("Workspace/parameter schema identity is stale")

    required_resources = (
        ENGINE_NAME, CORE_NAME, "din6892_methods.py", "fva600_postprocess.py",
        "fva600_matlab.py", "fva600_method_a_backend.py",
        "fva600_odb_extract.py", "fva600_d40_v3_nojob.py", DEFAULTS_NAME,
        "params_fva600_method_a_20lw_nojob.json",
        "params_fva600_research_presolve_1lw.json", CONTRACT_NAME,
        REPORT_MARKER_NAME)
    for required in required_resources:
        if not os.path.isfile(resource_path(required)):
            raise RuntimeError("Packaged resource missing: %s" % required)

    # Catalog parity, Unicode/fallback, and every stable validation code.
    catalog_dir = resource_path(I18N_DIRNAME)
    catalog_check = i18n.validate_catalogs(catalog_dir)
    if tuple(catalog_check["locales"]) != i18n.SUPPORTED_LOCALES:
        raise RuntimeError("Packaged i18n locales are incomplete or reordered")
    for key in ("gui.static.tab_din6892", "report.section.din6892",
                "report.din.realized.status", "standard.DIN_6892.title"):
        if key not in catalog_check["keys"]:
            raise RuntimeError("Required localized 4.2 key is missing: %s" % key)
    spanish = i18n.Translator("es", catalog_dir)
    german = i18n.Translator("de", catalog_dir)
    fallback_key = "gui.static.apply"
    german.catalogs["de"].pop(fallback_key)
    if german.t(fallback_key) != spanish.t(fallback_key):
        raise RuntimeError("Safe de -> es fallback did not resolve a missing key")
    localized_probe = i18n.localize_issue(
        {"level": "error", "code": "D_nonpositive", "msg": "canonical"},
        i18n.Translator("de", catalog_dir))
    if (localized_probe.get("canonical_message") != "canonical" or
            localized_probe.get("presentation_message") == "canonical"):
        raise RuntimeError("Localized issue presentation lost its canonical message")
    source_text = []
    for source_name in (CORE_NAME, "din6892_methods.py"):
        with open(resource_path(source_name), "r", encoding="utf-8") as stream:
            source_text.append(stream.read())
    validation_source = "\n".join(source_text)
    issue_codes = set(re.findall(
        r"\b[EWI]\(\s*['\"]([^'\"]+)", validation_source))
    issue_codes.update(re.findall(
        r"['\"]code['\"]\s*:\s*['\"]([^'\"]+)", validation_source))
    missing_issue_keys = sorted(
        code for code in issue_codes
        if "validation.%s" % code not in catalog_check["keys"])
    if missing_issue_keys:
        raise RuntimeError("Validation codes lack localized presentation: %s" %
                           ", ".join(missing_issue_keys))

    # Defaults, companion preset, contract, and marker identity.
    with open(resource_path(DEFAULTS_NAME), "r", encoding="utf-8") as stream:
        packaged_defaults = json.load(stream)
    params = core.default_params()
    if (packaged_defaults != params or params.get("schema_version") != 6 or
            params.get("project", {}).get("language") != i18n.DEFAULT_LOCALE):
        raise RuntimeError(
            "Packaged params_default.json differs from schema-6 core defaults "
            "or does not default project.language to es")
    with open(resource_path(CONTRACT_NAME), "r", encoding="utf-8") as stream:
        contract = json.load(stream)
    if (contract.get("builder_version") != "4.2" or
            contract.get("builder_schema") != 6 or
            contract.get("contract_version") != 4):
        raise RuntimeError("Packaged technical contract identity is stale")
    with open(resource_path(REPORT_MARKER_NAME), "r", encoding="utf-8") as stream:
        if "Model Builder 4.2" not in stream.read():
            raise RuntimeError("Packaged report ownership marker is stale")
    preset_path = resource_path("params_fva600_research_presolve_1lw.json")
    with open(preset_path, "r", encoding="utf-8") as stream:
        preset = core.normalize_params(json.load(stream))
    preset_derived = core.derive(preset)
    if core.errors(core.validate(preset, preset_derived)):
        raise RuntimeError("Packaged FVA companion has hard validation errors")
    preset_backend = preset_derived["din6892"]["realized"]["realized"]
    if (preset["din6892"]["method"] != din6892.METHOD_A or
            preset["fva_600_iii"]["variant_id"] != "VB1" or
            preset["fva_600_iii"]["material_pair"] != "C45N_C45N" or
            preset["fva_600_iii"]["cycles"] != 1 or
            preset_backend.get("status") != "LEGACY_PARTIAL"):
        raise RuntimeError("Packaged FVA companion lost its guarded capability")
    method_a_preset_path = resource_path(
        "params_fva600_method_a_20lw_nojob.json")
    with open(method_a_preset_path, "r", encoding="utf-8") as stream:
        method_a_preset = core.normalize_params(json.load(stream))
    method_a_preset_derived = core.derive(method_a_preset)
    if core.errors(core.validate(method_a_preset, method_a_preset_derived)):
        raise RuntimeError("Packaged connected Method-A preset has hard errors")
    method_a_execution = method_a_preset["fva_600_iii"]["execution"]
    if (method_a_preset["fva_600_iii"]["backend"] !=
            din6892.BACKEND_METHOD_A_HYBRID_HEX or
            method_a_preset["fva_600_iii"]["cycles"] != 20 or
            not method_a_preset["fva_600_iii"]["strict_no_job"] or
            method_a_execution.get("create_job") or
            method_a_execution.get("submit_solver")):
        raise RuntimeError("Packaged connected Method-A preset lost NOJOB/20-LW identity")

    # Formal schema 5 -> 6 migration, aliases, idempotence and future rejection.
    legacy = core.default_params()
    legacy["schema_version"] = 5
    legacy["shaft"].pop("diameter_mm", None)
    legacy["shaft"]["D"] = 60.0
    legacy["hub"].pop("QA_shaft_over_outer", None)
    legacy["hub"]["hub_outer_over_shaft"] = 2.5
    legacy.pop("din6892", None)
    legacy.pop("standards", None)
    migrated = core.normalize_params(legacy)
    if (migrated["schema_version"] != 6 or
            migrated["shaft"]["diameter_mm"] != 60.0 or
            migrated["hub"]["QA_shaft_over_outer"] != 0.4 or
            migrated.get("_migration", {}).get("source_schema") != 5):
        raise RuntimeError("Schema 5 -> 6 migration lost canonical geometry")
    if core.normalize_params(copy.deepcopy(migrated)) != migrated:
        raise RuntimeError("Schema migration is not idempotent")
    expect_value_error(
        lambda: core.normalize_params({"schema_version": 7}), "future")
    alias_conflict = core.default_params()
    alias_conflict["shaft"]["diameter_mm"] = 42.0
    alias_conflict["shaft"]["D"] = 41.0
    expect_value_error(
        lambda: core.normalize_params(alias_conflict), "conflicting")
    workspace_v1 = {
        "workspace_schema_version": 1,
        "directories": {"input": "input", "jobs": "jobs"}}
    workspace_v2 = migrate_workspace_manifest(workspace_v1)
    if (workspace_v2["workspace_schema_version"] != 2 or
            workspace_v2["directories"] != workspace_v1["directories"] or
            not workspace_v2["workspace_migration"]["artifact_paths_preserved"]):
        raise RuntimeError("Workspace schema 1 -> 2 migration changed paths")
    expect_value_error(
        lambda: migrate_workspace_manifest({"workspace_schema_version": 3}),
        "future")

    # DIN/FVA catalogs and golden calculations.
    expected_methods = (
        din6892.METHOD_A, din6892.METHOD_B_CURRENT,
        din6892.METHOD_B_FVA, din6892.METHOD_C)
    if tuple(din6892.METHOD_IDS) != expected_methods:
        raise RuntimeError("DIN 6892 method catalog is incomplete or reordered")
    if sorted(din6892.FVA_VARIANTS) != ["VB%d" % index for index in range(1, 9)]:
        raise RuntimeError("FVA VB1..VB8 catalog is incomplete")
    if len(din6892.STANDARD_REGISTRY) != 8:
        raise RuntimeError("Standards registry must contain eight explicit entries")
    c45 = din6892.material_properties("C45N_C45N", 40)
    high_strength = din6892.material_properties(
        "42CRMO4QT_42CRMO4QT", 40)
    if (c45["shaft"]["Re_MPa"] != 377.0 or
            high_strength["shaft"]["Re_MPa"] != 849.0 or
            c45["interpolated"] or high_strength["interpolated"]):
        raise RuntimeError("FVA discrete material catalog changed unexpectedly")
    expect_value_error(
        lambda: din6892.material_properties("C45N_C45N", 25),
        "no interpolation")
    method_c = din6892.method_c_preliminary({
        "Re_min_MPa": 300.0, "d_w_mm": 40.0, "h_mm": 8.0,
        "t1_mm": 5.0, "ltr_mm": 38.0, "key_count": 1,
        "phi": 1.0, "safety_factor": 1.2})
    assert_close(method_c["torque_allowable_Nm"], 615.6, label="Method C")
    assert_close(method_c["torque_design_Nm"], 513.0, label="Method C design")
    # Equation 26 is normalised at the research criterion v = 0.5, so the ratio
    # f_Sv(1.0)/f_Sv(0.5) must reproduce the support factors the FVA report
    # measured at both criticality levels. This checks the transcription against
    # the source rather than against itself.
    calibration = din6892.volume_support_factor_calibration()
    if not calibration["validated"]:
        raise RuntimeError(
            "Equation 26 does not reproduce the measured f_S(v=1)/f_S(v=0.5) "
            "ratios (worst deviation %.3f %%)"
            % calibration["worst_deviation_percent"])
    assert_close(calibration["predicted_ratio"], 1.37, tolerance=1.0e-12,
                 label="f_Sv ratio")

    # DIN 6892 Table 2 support and hardness factors, with the standard's own rule
    # that the smaller f_S applies when the material is not known.
    if (din6892.table2_support_factors("shaft")["f_S_range"] != [1.3, 1.7] or
            din6892.table2_support_factors("hub")["f_S_range"] != [1.5, 1.5] or
            din6892.table2_support_factors("key")["f_S_range"] != [1.1, 1.4] or
            din6892.table2_support_factors("shaft")["f_S"] != 1.3 or
            din6892.table2_support_factors(
                "hub", "CASE_HARDENED_STEEL")["f_H"] != 1.15 or
            din6892.table2_support_factors(
                "hub", "LAMELLAR_CAST_IRON")["f_H_available"]):
        raise RuntimeError("DIN 6892 Table 2 support factors changed unexpectedly")
    expect_value_error(
        lambda: din6892.table2_support_factors("shaft", "UNOBTANIUM"),
        "Unknown shaft material class")

    # Equation 10 defines phi only for one or two keys, and the two-key value
    # depends on whether the allowable or the peak pressure is evaluated.
    if (din6892.default_load_share_phi(1) != 1.0 or
            din6892.default_load_share_phi(2, "p_zul") != 0.75 or
            din6892.default_load_share_phi(2, "p_max") != 0.90):
        raise RuntimeError("DIN 6892 equation 10 load share changed unexpectedly")
    expect_value_error(lambda: din6892.default_load_share_phi(3), "i = 1 or i = 2")

    # Equations 11 and 12 are closed form and must be implemented, not guessed.
    assert_close(din6892.hub_equivalent_diameter(80.0, 165.0, 21.0, 38.0)["D_ers_mm"],
                 96.21747699, tolerance=1.0e-6, label="D_ers eq. 11")
    closure = din6892.friction_closure_factor(1440.0, 800.0)
    assert_close(closure["K_Req_din"], 1.0 - 0.5 * 800.0 / 1440.0,
                 tolerance=1.0e-12, label="K_Req eq. 12")
    if closure["K_R"] != 1.0 or not closure["fva_correction_applied"]:
        raise RuntimeError("The FVA correction K_R = 1 is not applied by default")

    # Equation 9 must use the chamfer the joint really has. Evaluating it with
    # s1 = 0 overstates t1tr and inflates every Method B/C torque.
    base_record = core.derive(core.default_params())["din6892"]
    effective = base_record["derived"]["effective_bearing_depth"]
    if base_record["derived"]["chamfer_s1_source"] != "GEOMETRY_KEY_CHAMFER":
        raise RuntimeError("Equation 9 lost the geometric chamfer s1")
    assert_close(effective["inputs"]["chamfer_s1_mm"], 0.8, tolerance=1.0e-12,
                 label="eq. 9 chamfer s1")
    assert_close(effective["t1tr_mm"], 5.141491287186, tolerance=1.0e-9,
                 label="t1tr eq. 9")
    # The transcribed equation 9 ADDS the chord correction and therefore exceeds
    # the real shaft flank height. Both values must be reported so the
    # discrepancy is auditable instead of hidden inside one number.
    assert_close(effective["t1tr_geometric_mm"], 2.758508712814,
                 tolerance=1.0e-9, label="t1tr flank geometry")
    assert_close(effective["chord_correction_mm"], 1.191491287186,
                 tolerance=1.0e-9, label="eq. 9 chord correction")
    if effective["agrees"] or effective["surface"] != "CONVEX_SHAFT":
        raise RuntimeError("The equation-9 flank-height cross-check disappeared")
    # The hub keyway sits in a concave bore, where the same algebraic form with a
    # PLUS sign is geometrically correct, and the top clearance g_c is removed.
    hub_effective = base_record["derived"]["hub_effective_bearing_depth"]
    assert_close(hub_effective["t2tr_mm"], 3.141491287186, tolerance=1.0e-9,
                 label="t2tr hub flank")
    if hub_effective["surface"] != "CONCAVE_HUB_BORE":
        raise RuntimeError("The hub bearing depth lost its bore geometry")
    # Equation 8 for all three implemented DIN 6885 forms, and its inverse.
    if (din6892.bearing_length(50.0, 12.0, "A")["ltr_mm"] != 38.0 or
            din6892.bearing_length(50.0, 12.0, "B")["ltr_mm"] != 50.0 or
            din6892.bearing_length(50.0, 12.0, "AB")["ltr_mm"] != 44.0 or
            din6892.nominal_key_length(38.0, 12.0, "A")[
                "key_nominal_length_mm"] != 50.0):
        raise RuntimeError("DIN 6892 equation 8 changed unexpectedly")

    # Equation 3 is driven by N_W, the number of LOAD DIRECTION reversals, not by
    # the load cycle count: f_W penalises the key alternately bearing on both
    # keyway flanks, which a purely pulsating torque never does.
    pulsating = din6892.load_reversal_count(10000, 0.0)
    alternating = din6892.load_reversal_count(10000, -1.0)
    unknown = din6892.load_reversal_count(10000, None)
    explicit = din6892.load_reversal_count(10000, 0.0, 1.0e6)
    if (pulsating["N_W"] != 0.0 or
            pulsating["source"] != din6892.REVERSAL_SOURCE_DERIVED_PULSATING or
            alternating["N_W"] != 10000.0 or
            alternating["source"] !=
            din6892.REVERSAL_SOURCE_DERIVED_ALTERNATING or
            unknown["source"] !=
            din6892.REVERSAL_SOURCE_UNKNOWN_DIRECTION or
            explicit["N_W"] != 1.0e6 or
            explicit["source"] != din6892.REVERSAL_SOURCE_EXPLICIT):
        raise RuntimeError("The N_W derivation of equation 3 changed unexpectedly")
    if din6892.load_reversal_factor(0.0)["f_W"] != 1.0:
        raise RuntimeError("Without load direction reversals f_W must stay 1")
    assert_close(din6892.load_reversal_factor(10000)["f_W"], 0.7962143411069944,
                 tolerance=1.0e-12, label="f_W eq. 3")

    # Method B current: per-component yield strength, per-component Table 2
    # factors AND per-component bearing depth. The hub governs this D40 C45+N
    # joint and it is checked on its OWN flank height t2tr, not on t1tr.
    b_current = core.default_params()
    b_current["din6892"]["method"] = din6892.METHOD_B_CURRENT
    current_record = core.derive(b_current)["din6892"]
    current_calc = current_record["calculation"]
    assert_close(current_calc["torque_allowable_Nm"], 999.1827188023801,
                 tolerance=1.0e-8, label="B-DIN C45")
    assert_close(current_calc["torque_design_Nm"], 832.6522656686501,
                 tolerance=1.0e-8, label="B-DIN C45 design")
    if (current_calc["governing_component"] != "hub" or
            sorted(row["name"] for row in current_calc["components"]) !=
            ["hub", "key", "shaft"]):
        raise RuntimeError("Method B current lost its per-component bearing check")
    by_name = dict((row["name"], row) for row in current_calc["components"])
    if (by_name["shaft"]["f_S"] != 1.3 or by_name["hub"]["f_S"] != 1.5 or
            by_name["key"]["f_S"] != 1.1 or
            by_name["shaft"]["f_S_provenance"] != "DIN-METHOD"):
        raise RuntimeError("Method B current does not take f_S from Table 2")
    # Each part on its own flank: shaft on t1tr, hub on t2tr, key on the smaller
    # of the two because the key flank carries the same pressure as the keyway.
    if (by_name["shaft"]["bearing_depth_symbol"] != "t1tr" or
            by_name["hub"]["bearing_depth_symbol"] != "t2tr" or
            by_name["key"]["bearing_depth_symbol"] != "t2tr" or
            any(row["bearing_depth_is_fallback"]
                for row in current_calc["components"])):
        raise RuntimeError("Method B current does not use per-component depths")
    assert_close(by_name["hub"]["bearing_depth_mm"], 3.141491287186,
                 tolerance=1.0e-9, label="hub bearing depth")
    assert_close(by_name["shaft"]["torque_allowable_Nm"], 1027.4782913141062 *
                 (5.141491287186004 / 2.7585087128139962),
                 tolerance=1.0e-6, label="shaft torque scales with depth")
    # A purely pulsating torque has no load direction reversal, so f_W = 1.
    if current_calc["f_W"] != 1.0 or current_calc["load_reversal_count"][
            "N_W"] != 0.0:
        raise RuntimeError("A pulsating Method B check must not be penalised by f_W")
    if current_calc["status"] != din6892.STATUS_PROVISIONAL_FACTORS:
        raise RuntimeError("The neutral K_lambda placeholder must stay provisional")
    # The licensed K_lambda reading is gated against the diagram bounds.
    domain = current_calc["K_lambda_domain"]
    assert_close(domain["Q_A_shaft_over_hub"], 0.5, tolerance=1.0e-12,
                 label="Q_A for K_lambda")
    if (not domain["K_lambda_inside_diagram"] or
            not domain["Q_A_inside_diagram"] or
            not domain["ltr_over_dw_inside_diagram"] or
            domain["load_derivation_position"] !=
            din6892.LOAD_DERIVATION_REAR):
        raise RuntimeError("The K_lambda diagram domain gate is not evaluated")
    codes = [item["code"] for item in current_record["issues"]]
    if ("din6892_bearing_depth_optimistic" not in codes or
            "din6892_load_reversal_derived" not in codes):
        raise RuntimeError("The bearing-depth and N_W findings are not reported")

    # The selectable bearing-depth policy must reach the shaft check without
    # touching the hub, whose plus sign is geometrically correct.
    b_geometric = core.default_params()
    b_geometric["din6892"]["method"] = din6892.METHOD_B_CURRENT
    b_geometric["din6892"]["bearing_depth_policy"] = \
        din6892.DEPTH_POLICY_GEOMETRIC
    geometric_calc = core.derive(b_geometric)["din6892"]["calculation"]
    geometric_rows = dict((row["name"], row)
                          for row in geometric_calc["components"])
    assert_close(geometric_rows["shaft"]["torque_allowable_Nm"],
                 1027.4782913141062, tolerance=1.0e-8,
                 label="B-DIN geometric shaft torque")
    assert_close(geometric_rows["hub"]["torque_allowable_Nm"],
                 999.1827188023801, tolerance=1.0e-8,
                 label="B-DIN geometric hub torque")
    if (geometric_calc["bearing_depth_policy"]["policy_applied"] !=
            din6892.DEPTH_POLICY_GEOMETRIC or
            geometric_rows["key"]["bearing_depth_symbol"] != "t1tr"):
        raise RuntimeError("The bearing depth policy is not applied per component")

    # Without a hub depth the hub falls back to the shaft depth, which is
    # optimistic and has to be reported rather than silently accepted.
    fallback_inputs = {
        "d_w_mm": 40.0, "ltr_mm": 38.0, "t1tr_mm": 5.141491287186,
        "K_lambda": 1.0, "K_R": 1.0, "load_ratio_R": 0.0,
        "safety_factor": 1.2, "h_mm": 8.0, "t1_mm": 5.0,
        "components": [{"name": "shaft", "Re_MPa": 377.0, "Rm_MPa": 676.0},
                       {"name": "hub", "Re_MPa": 279.0},
                       {"name": "key", "Re_MPa": 928.0}],
        "material_classes": {"shaft": din6892.DEFAULT_MATERIAL_CLASS,
                             "hub": din6892.DEFAULT_MATERIAL_CLASS,
                             "key": din6892.DEFAULT_MATERIAL_CLASS}}
    fallback_calc = din6892.evaluate(din6892.METHOD_B_CURRENT, fallback_inputs)
    if (fallback_calc["bearing_depths"]["hub_depth_available"] or
            not dict((row["name"], row)
                     for row in fallback_calc["components"])["hub"][
                         "bearing_depth_is_fallback"] or
            "din6892_hub_bearing_depth_missing" not in
            [item["code"] for item in din6892.validate_configuration(
                din6892.METHOD_B_CURRENT, fallback_inputs)]):
        raise RuntimeError("The missing hub bearing depth is not reported")

    # The application factor, the peak-pressure branch and both safeties.
    b_peak = core.default_params()
    b_peak["din6892"]["method"] = din6892.METHOD_B_CURRENT
    b_peak["din6892"]["f_L"] = 1.5
    b_peak["din6892"]["torque_applied_Nm"] = 800.0
    peak_calc = core.derive(b_peak)["din6892"]["calculation"]
    assert_close(peak_calc["torque_peak_allowable_Nm"], 1498.7740782035703,
                 tolerance=1.0e-8, label="B-DIN peak torque")
    assert_close(peak_calc["safety_S_Feq"], 999.1827188023801 / 800.0,
                 tolerance=1.0e-10, label="S_Feq eq. 1")
    b_application = core.default_params()
    b_application["din6892"]["method"] = din6892.METHOD_B_CURRENT
    b_application["din6892"]["K_A"] = 1.25
    b_application["din6892"]["torque_nominal_Nm"] = 400.0
    b_application["din6892"]["f_L"] = 1.5
    b_application["din6892"]["torque_peak_applied_Nm"] = 800.0
    application_calc = core.derive(b_application)["din6892"]["calculation"]
    assert_close(application_calc["torque_equivalent_Nm"], 500.0,
                 tolerance=1.0e-12, label="M_teq = K_A * M_t,nom")
    assert_close(application_calc["safety_S_Feq"], 999.1827188023801 / 500.0,
                 tolerance=1.0e-10, label="S_Feq from K_A chain")
    assert_close(application_calc["safety_S_Fmax"],
                 1498.7740782035703 / 800.0, tolerance=1.0e-10,
                 label="S_Fmax peak branch")
    # p_eq of equation 6 must be the exact inverse of the allowable torque.
    assert_close(application_calc["utilisation_eq"],
                 1.0 / application_calc["safety_S_Feq"], tolerance=1.0e-12,
                 label="p_eq consistency")

    # Alternating torque: the same joint loses capacity through f_W.
    b_alternating = core.default_params()
    b_alternating["din6892"]["method"] = din6892.METHOD_B_CURRENT
    b_alternating["din6892"]["load_ratio_R"] = -1.0
    alternating_calc = core.derive(b_alternating)["din6892"]["calculation"]
    assert_close(alternating_calc["torque_allowable_Nm"], 795.5636100967324,
                 tolerance=1.0e-8, label="B-DIN alternating")
    assert_close(alternating_calc["f_W"], 0.7962143411069944,
                 tolerance=1.0e-12, label="B-DIN alternating f_W")

    # The FVA reformulation is a SHAFT keyway criterion: Re and Rm are the
    # shaft's, and the other components are reported as not covered.
    b_fva_c45 = core.default_params()
    b_fva_c45["din6892"]["method"] = din6892.METHOD_B_FVA
    c45_calc = core.derive(b_fva_c45)["din6892"]["calculation"]
    assert_close(c45_calc["torque_allowable_Nm"], 2464.86648545341,
                 tolerance=1.0e-8, label="B-FVA C45")
    assert_close(c45_calc["f_WS"], 676.0 / 377.0, tolerance=1.0e-12,
                 label="B-FVA C45 f_WS")
    if (c45_calc["governing_component"] != "shaft" or
            c45_calc["criterion"] != "SHAFT_KEYWAY_RELATIVE_OPENING_VOLUME" or
            sorted(c45_calc["components_not_covered"]) != ["hub", "key"]):
        raise RuntimeError("B-FVA is not evaluated as a shaft keyway criterion")
    b_fva_high = core.default_params()
    b_fva_high["din6892"]["method"] = din6892.METHOD_B_FVA
    b_fva_high["din6892"]["material_pair"] = "42CRMO4QT_42CRMO4QT"
    assert_close(core.derive(b_fva_high)["din6892"]["calculation"][
                     "torque_allowable_Nm"], 3531.5291370741784,
                 tolerance=1.0e-8, label="B-FVA 42CrMo")

    # Method C keeps the published 10 % reduction by default and offers the FVA
    # equation 32 proposal without it.
    c_din = core.default_params()
    c_din["din6892"]["method"] = din6892.METHOD_C
    c_din_calc = core.derive(c_din)["din6892"]["calculation"]
    assert_close(c_din_calc["torque_allowable_Nm"], 572.508, tolerance=1.0e-9,
                 label="Method C published DIN")
    # Equation 31 works with h - t1 = t2 - g_c, so the clearance stays visible.
    assert_close(c_din_calc["engaged_height_mm"], 3.0, tolerance=1.0e-12,
                 label="Method C engaged height")
    assert_close(c_din_calc["engaged_height"]["top_clearance_gc_mm"], 0.3,
                 tolerance=1.0e-12, label="Method C top clearance")
    c_fva = core.default_params()
    c_fva["din6892"]["method"] = din6892.METHOD_C
    c_fva["din6892"]["method_c_variant"] = din6892.METHOD_C_VARIANT_FVA
    c_fva_calc = core.derive(c_fva)["din6892"]["calculation"]
    assert_close(c_fva_calc["torque_allowable_Nm"], 636.12, tolerance=1.0e-9,
                 label="Method C FVA variant")
    if c_fva_calc["variant_f_S"] != 1.0 or c_fva_calc["badge"] != "FVA-RESEARCH":
        raise RuntimeError("The Method C FVA variant lost its identity")

    # Method C is a SIZING method: the inverse must reproduce the requirement.
    c_sizing = core.default_params()
    c_sizing["din6892"]["method"] = din6892.METHOD_C
    c_sizing["din6892"]["torque_required_Nm"] = 700.0
    c_sizing_record = core.derive(c_sizing)["din6892"]
    sizing = c_sizing_record["calculation"]["sizing"]
    assert_close(sizing["ltr_required_mm"], 55.75467941059339,
                 tolerance=1.0e-9, label="Method C required l_tr")
    assert_close(sizing["key_nominal_length_required_mm"], 67.75467941059338,
                 tolerance=1.0e-9, label="Method C required key length")
    assert_close(
        c_sizing_record["calculation"]["torque_per_bearing_mm_Nm"] *
        sizing["ltr_required_mm"] / sizing["safety_factor"], 700.0,
        tolerance=1.0e-9, label="Method C sizing round trip")
    if (not sizing["exceeds_design_limit"] or
            "din6892_method_c_sizing_too_long" not in
            [item["code"] for item in c_sizing_record["issues"]]):
        raise RuntimeError("An over-long Method C sizing result is not reported")

    # Method C must stay on the safe side of Method B, and the opposite case has
    # to be said out loud instead of left in a table.
    consistency = (current_record.get("companions") or {}).get("consistency") or {}
    assert_close(consistency["method_c_over_method_b"], 0.5729762827425676,
                 tolerance=1.0e-9, label="Method C over Method B")
    if not consistency["method_c_is_conservative"]:
        raise RuntimeError("The Method C / Method B consistency check is broken")
    b_high_lambda = core.default_params()
    b_high_lambda["din6892"]["method"] = din6892.METHOD_B_CURRENT
    b_high_lambda["din6892"]["K_lambda"] = 3.4
    high_lambda_codes = [item["code"]
                         for item in core.derive(b_high_lambda)["din6892"]["issues"]]
    if ("din6892_k_lambda_outside_diagram" not in high_lambda_codes or
            "din6892_method_c_not_conservative" not in high_lambda_codes):
        raise RuntimeError(
            "An out-of-diagram K_lambda must be flagged and must reveal that "
            "Method C is no longer conservative")

    # The measured reference results of the report must stay retrievable.
    vb1 = din6892.reference_results("VB1", "C45N_C45N")
    if (vb1["f_S_experiment"] != 1.72 or vb1["torque_experiment_Nm"] != 1440.0 or
            vb1["simulation_overestimate_percent"] != 19.0):
        raise RuntimeError("FVA reference results changed unexpectedly")
    # Every analytical method must be available next to the primary one.
    companions = (current_record.get("companions") or {}).get("results") or {}
    if sorted(companions) != [din6892.METHOD_B_FVA, din6892.METHOD_C]:
        raise RuntimeError("Analytical companion methods are not evaluated")
    for name, item in companions.items():
        if not item.get("torque_allowable_Nm"):
            raise RuntimeError("Companion %s produced no torque" % name)
    # Switching the FVA material catalogue off must fall back and say so, never
    # return INVALID_INPUT with an empty issue list.
    b_fva_model = core.default_params()
    b_fva_model["din6892"]["method"] = din6892.METHOD_B_FVA
    b_fva_model["din6892"]["use_fva_material_data"] = False
    model_record = core.derive(b_fva_model)["din6892"]
    if (model_record["status"] == "INVALID_INPUT" or
            not model_record["calculation"] or
            "din6892_material_source_not_fva" not in
            [item["code"] for item in model_record["issues"]]):
        raise RuntimeError("B-FVA without FVA material data degrades silently")
    method_a_pending = core.default_params()
    method_a_pending["din6892"]["method"] = din6892.METHOD_A
    pending_record = core.derive(method_a_pending)["din6892"]
    if (pending_record["status"] != "EXTERNAL_RESULT_REQUIRED" or
            any(item["level"] == "error" for item in pending_record["issues"])):
        raise RuntimeError("Method A without CSV is not honestly pending")

    # Backend capability must block every unsupported dimension independently.
    backend_request = {
        "enabled": True, "backend": din6892.BACKEND_LEGACY_D40,
        "requested_method": din6892.METHOD_A, "variant_id": "VB1",
        "material_pair": "C45N_C45N", "cycles": 1,
        "strict_no_job": True}
    backend_ok = din6892.assess_backend_request(backend_request)
    if (not backend_ok["executable"] or
            backend_ok["realized"]["status"] != "LEGACY_PARTIAL" or
            backend_ok["realized"]["matching"] != "NOT_VERIFIED"):
        raise RuntimeError("Legacy backend baseline capability changed")
    rejection_cases = (
        ("requested_method", din6892.METHOD_B_CURRENT,
         "fva_backend_method_unsupported"),
        ("variant_id", "VB2", "fva_backend_variant_unsupported"),
        ("material_pair", "42CRMO4QT_42CRMO4QT",
         "fva_backend_material_unsupported"),
        ("cycles", 10, "fva_backend_cycles_unsupported"),
        ("strict_no_job", False, "fva_backend_nojob_required"),
    )
    for field, value, expected_code in rejection_cases:
        request = copy.deepcopy(backend_request)
        request[field] = value
        assessment = din6892.assess_backend_request(request)
        codes = set(item["code"] for item in assessment["issues"])
        if assessment["executable"] or expected_code not in codes:
            raise RuntimeError("Backend did not block %s=%r with %s" %
                               (field, value, expected_code))
    woodruff = core.default_params()
    woodruff["standards"]["selected"]["geometry"] = "DIN_6888"
    woodruff_derived = core.derive(woodruff)
    woodruff_codes = set(item["code"] for item in
                         core.validate(woodruff, woodruff_derived))
    if "standard_not_implemented" not in woodruff_codes:
        raise RuntimeError("DIN 6888 selection was not blocked")

    # Defaults and legacy mesh-policy checks.
    derived = core.derive(copy.deepcopy(params))
    if core.errors(core.validate(copy.deepcopy(params), derived)):
        raise RuntimeError("Default parameter validation failed")
    expected_templates = (
        "HEX_CERTIFIED", "FVA_METHOD_A_HYBRID",
        "AUTO_BALANCED", "QUALITY_CRITICAL", "FAST_PREVIEW",
        "HEX_DOMINANT", "QUADRATIC_ACCURACY", "ROBUST_FALLBACK")
    if (tuple(core.mesh_template_names()) != expected_templates or
            len(core.mesh_template_catalog()) != 8 or len(core.DIN6885) != 26):
        raise RuntimeError("DIN/mesh packaging catalog changed unexpectedly")
    for name in expected_templates:
        probe = core.default_params()
        probe["mesh"] = {"template": name,
                         "algorithm_version": core.MESH_ALGORITHM_VERSION}
        plan = core.resolve_mesh_plan(probe)
        if not all(plan["parts"][part]["candidates"] for part in core.MESH_PARTS):
            raise RuntimeError("Template %s has an empty piece plan" % name)
    inherit_probe = core.default_params()
    inherit_probe["element_order"] = "quadratic"
    inherit_probe["mesh"] = {"template": "FAST_PREVIEW",
                              "algorithm_version": core.MESH_ALGORITHM_VERSION}
    if core.resolve_mesh_plan(inherit_probe)["element_order"] != "quadratic":
        raise RuntimeError("FAST_PREVIEW changed the requested element order")
    quadratic_plan = core.resolve_mesh_plan(dict(
        core.default_params(), mesh={"template": "QUADRATIC_ACCURACY",
                                     "algorithm_version": core.MESH_ALGORITHM_VERSION}))
    if core.validate_realized_element_profile(
            quadratic_plan, {"Shaft": {"elements": 1, "types": {"C3D20R": 1}}}):
        raise RuntimeError("Quadratic realised-profile validation failed")
    if not core.validate_realized_element_profile(
            quadratic_plan, {"Shaft": {"elements": 1, "types": {"C3D8": 1}}}):
        raise RuntimeError("Wrong realised element order was not rejected")
    quality = {"hard_passed": True, "status": "PASS", "score": 90.0,
               "metrics": {"hex_pct": 90.0, "warnings": 0,
                           "ar_bulk_worst": 4.0, "elements": 1000}}
    early = {"recipe": {"recipe_id": "EARLY"}, "quality": copy.deepcopy(quality)}
    late = {"recipe": {"recipe_id": "LATE"}, "quality": copy.deepcopy(quality)}
    early["quality"]["metrics"]["seconds"] = 100.0
    late["quality"]["metrics"]["seconds"] = 0.1
    if core.select_best_mesh_candidate([early, late])["selected_index"] != 0:
        raise RuntimeError("Wall-clock time changed the deterministic recipe tie break")

    # CSV integration, persistence/provenance, negative fixtures, core attach,
    # and trilingual requested/derived/realised report rendering.
    with tempfile.TemporaryDirectory(prefix="model_builder_42_selftest_") as temp_dir:
        method_a_params = core.default_params()
        method_a_params["din6892"]["method"] = din6892.METHOD_A
        pre = core.derive(method_a_params)
        ltr = pre["load_bearing_length"]
        t1tr = pre["din6892"]["derived"]["effective_bearing_depth"]["t1tr_mm"]
        upf = method_a_params["din6892"]["UPF_um"]
        opening = 0.4 * upf
        csv_path = os.path.join(temp_dir, "opening.csv")
        with open(csv_path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("x_mm,z_mm,opening_um\n")
            for x, z in ((0.0, 0.0), (ltr, 0.0),
                         (0.0, t1tr), (ltr, t1tr)):
                stream.write("%.12g,%.12g,%.12g\n" % (x, z, opening))
        result = fva_postprocess.process_csv(
            csv_path, ltr, t1tr, upf, 0.5, True, 10,
            "MethodA", "Unloaded-10")
        assert_close(result["volume"]["v"], 0.4, tolerance=1.0e-10,
                     label="Method A relative volume")
        assert_close(result["coverage"]["grid_over_expected"], 1.0,
                     tolerance=1.0e-10, label="CSV coverage")
        if (not result["method_a_evidence_complete"] or
                result["criterion_met"] is not True):
            raise RuntimeError("Complete Method-A CSV evidence was not recognized")
        result_path = os.path.join(temp_dir, "opening_result.json")
        fva_postprocess.write_result_json(result_path, result)
        loaded_result = fva_postprocess.read_result_json(result_path)
        if loaded_result != result:
            raise RuntimeError("Persisted Method-A result changed on round trip")
        if not fva_postprocess.verify_source_provenance(loaded_result)["verified"]:
            raise RuntimeError("Method-A source provenance did not reverify")
        bad_provenance = copy.deepcopy(loaded_result)
        bad_provenance["provenance"]["sha256"] = "0" * 64
        if fva_postprocess.verify_source_provenance(bad_provenance)["verified"]:
            raise RuntimeError("Tampered Method-A provenance was accepted")
        attached = fva_postprocess.attach_result_to_params(
            method_a_params, loaded_result)
        if attached["fva_600_iii"]["enabled"]:
            raise RuntimeError("Importing external evidence enabled the CAE backend")
        assessed = core.derive(attached)
        assessed_issues = core.validate(attached, assessed)
        if core.errors(assessed_issues):
            raise RuntimeError("Attached Method-A result has hard core errors")
        assessed_record = assessed["din6892"]
        if (assessed_record["status"] != "ASSESSED" or
                assessed_record["calculation"]["criterion_met"] is not True):
            raise RuntimeError("Attached Method-A result was not assessed")

        # MATLAB remains an optional companion. Exercise EXPORT and all RUN
        # process outcomes with a monkeypatched subprocess; never invoke MATLAB.
        expect_value_error(
            lambda: fva_matlab.normalize_config({
                "mode": "EXPORT", "entry_function": "bad();system"}),
            "identifier")
        off_dir = os.path.join(temp_dir, "matlab-off-must-not-exist")
        off_result = fva_matlab.export_or_run({
            "mode": "OFF", "bundle_dir": off_dir,
            "entry_function": "fva600_method_a_bundle"}, "", {})
        if off_result["status"] != "SKIPPED_OFF" or os.path.exists(off_dir):
            raise RuntimeError("MATLAB OFF created or executed an artifact")
        export_dir = os.path.join(temp_dir, "matlab-export")
        export_cfg = {
            "mode": "EXPORT", "bundle_dir": export_dir,
            "entry_function": "fva600_method_a_bundle", "timeout_s": 7}
        exported = fva_matlab.export_or_run(
            export_cfg, csv_path, loaded_result)
        bundle_check = fva_matlab.verify_bundle(exported)
        if (exported["status"] != "EXPORTED" or
                not bundle_check["verified"] or
                len(exported.get("artifacts") or []) != 5):
            raise RuntimeError("Auditable MATLAB EXPORT bundle failed")
        with open(os.path.join(export_dir, "fva600_method_a_bundle.m"),
                  "r", encoding="utf-8") as stream:
            matlab_source = stream.read()
        if ("function fva600_method_a_bundle()" not in matlab_source or
                "Python remains authoritative" not in matlab_source):
            raise RuntimeError("MATLAB bundle function lost identity/authority")
        first_manifest_hash = exported["manifest_sha256"]
        repeated_export = fva_matlab.export_or_run(
            export_cfg, csv_path, loaded_result)
        if repeated_export["manifest_sha256"] != first_manifest_hash:
            raise RuntimeError("MATLAB EXPORT is not deterministic")

        original_subprocess_run = fva_matlab.subprocess.run

        class MatlabCompleted(object):
            returncode = 0

        def write_fake_matlab_result(cwd, delta_volume=None):
            with open(os.path.join(cwd, "method_a_input.json"),
                      "r", encoding="utf-8") as stream:
                matlab_input = json.load(stream)
            python_volume = loaded_result["volume"]
            payload = {
                "result_schema_version": 1,
                "producer": "MATLAB",
                "status": "OK",
                "source_sha256": matlab_input["source_sha256"],
                "delta_volume_mm3": (
                    loaded_result["integration"]["delta_volume_mm3"]
                    if delta_volume is None else delta_volume),
                "V_theo_mm3": python_volume["V_theo_mm3"],
                "v": python_volume["v"],
                "v_crit": python_volume["v_crit"],
                "criterion_met": python_volume["criterion_met"],
            }
            with open(os.path.join(cwd, "matlab_result.json"),
                      "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)

        run_cfg = {
            "mode": "RUN", "executable": "fake-matlab",
            "entry_function": "fva600_method_a_bundle", "timeout_s": 7,
            "bundle_dir": os.path.join(temp_dir, "matlab-run-match")}
        try:
            def fake_match(command, **kwargs):
                if (command != ["fake-matlab", "-batch",
                                "fva600_method_a_bundle()"] or
                        kwargs.get("shell") is not False or
                        kwargs.get("timeout") != 7.0):
                    raise RuntimeError("Unsafe or unexpected MATLAB command")
                write_fake_matlab_result(kwargs["cwd"])
                return MatlabCompleted()

            fva_matlab.subprocess.run = fake_match
            matched = fva_matlab.export_or_run(
                run_cfg, csv_path, loaded_result)
            if (matched["status"] != "COMPLETED_MATCH" or
                    not matched["comparison"]["all_match"] or
                    not matched["python_authoritative"]):
                raise RuntimeError("Matching MATLAB cross-check failed")

            def fake_mismatch(_command, **kwargs):
                write_fake_matlab_result(kwargs["cwd"], delta_volume=99.0)
                return MatlabCompleted()

            fva_matlab.subprocess.run = fake_mismatch
            mismatch_cfg = copy.deepcopy(run_cfg)
            mismatch_cfg["bundle_dir"] = os.path.join(
                temp_dir, "matlab-run-mismatch")
            mismatch = fva_matlab.export_or_run(
                mismatch_cfg, csv_path, loaded_result)
            if (mismatch["status"] != "COMPLETED_MISMATCH" or
                    mismatch["comparison"]["all_match"] or
                    not mismatch["python_authoritative"]):
                raise RuntimeError("MATLAB mismatch changed or hid Python authority")

            def fake_timeout(command, **kwargs):
                raise fva_matlab.subprocess.TimeoutExpired(
                    command, kwargs["timeout"])

            fva_matlab.subprocess.run = fake_timeout
            timeout_cfg = copy.deepcopy(run_cfg)
            timeout_cfg["bundle_dir"] = os.path.join(
                temp_dir, "matlab-run-timeout")
            timed_out = fva_matlab.export_or_run(
                timeout_cfg, csv_path, loaded_result)
            if timed_out["status"] != "TIMEOUT":
                raise RuntimeError("MATLAB timeout was not preserved")

            def fake_missing(command, **_kwargs):
                raise FileNotFoundError(2, "missing executable", command[0])

            fva_matlab.subprocess.run = fake_missing
            missing_cfg = copy.deepcopy(run_cfg)
            missing_cfg["bundle_dir"] = os.path.join(
                temp_dir, "matlab-run-missing")
            missing_executable = fva_matlab.export_or_run(
                missing_cfg, csv_path, loaded_result)
            if missing_executable["status"] != "EXECUTABLE_NOT_FOUND":
                raise RuntimeError("Missing MATLAB executable was not preserved")
        finally:
            fva_matlab.subprocess.run = original_subprocess_run

        attached["matlab"].update(run_cfg)
        attached = fva_matlab.attach_result_to_params(attached, matched)
        persisted_post = attached["din6892"]["method_a"]["postprocess"]
        if (persisted_post.get("volume") != loaded_result.get("volume") or
                (persisted_post.get("provenance_verification") or {}).get(
                    "verified") is not True or
                attached["matlab"]["last_result"]["python_authoritative"] is not True):
            raise RuntimeError("MATLAB attachment changed the authoritative Python result")

        invalid_csv = {
            "missing.csv": "x_mm,z_mm,bad\n0,0,1\n1,0,1\n0,1,1\n1,1,1\n",
            "duplicate.csv": (
                "x_mm,z_mm,opening_um\n0,0,1\n1,0,1\n0,1,1\n0,0,1\n"),
            "negative.csv": (
                "x_mm,z_mm,opening_um\n0,0,-1\n1,0,1\n0,1,1\n1,1,1\n"),
            "nonrect.csv": (
                "x_mm,z_mm,opening_um\n0,0,1\n1,0,1\n0,1,1\n2,1,1\n"),
        }
        for filename, content in invalid_csv.items():
            bad_path = os.path.join(temp_dir, filename)
            with open(bad_path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
            try:
                fva_postprocess.process_csv(
                    bad_path, ltr, t1tr, upf, 0.5, True, 10,
                    "MethodA", "Unloaded-10")
            except fva_postprocess.PostprocessError:
                pass
            else:
                raise RuntimeError("Malformed CSV was accepted: %s" % filename)

        for locale in i18n.SUPPORTED_LOCALES:
            localized_params = copy.deepcopy(attached)
            i18n.set_param_language(localized_params, locale)
            localized_derived = core.derive(localized_params)
            localized_issues = core.validate(localized_params, localized_derived)
            translator = i18n.Translator(locale, catalog_dir)
            report_data = {
                "generated_at": "2026-09-11T12:00:00+00:00",
                "language": locale,
                "project": {
                    "project_name": "Self-test", "project_id": "self-test",
                    "model_name": localized_params.get("model_name"),
                    "builder_version": core.BUILDER_VERSION,
                    "root": temp_dir, "author": "Model Builder self-test"},
                "audit": {
                    "verdict": "PASS", "issues": localized_issues,
                    "checks": [], "parts": {}, "mesh_quality": {}},
                "params": localized_params,
                "derived": localized_derived,
                "badges": ["DIN-METHOD", "FVA-RESEARCH", "USER-INPUT",
                            "NOT-IMPLEMENTED"],
                "screenshots": [],
            }
            latex = render_latex(report_data, temp_dir)
            required_text = (
                translator.t("report.section.din6892"),
                translator.t("report.section.standards"),
                translator.t("report.din.requested.method"),
                translator.t("report.din.derived.status"),
                translator.t("report.din.realized.status"),
                translator.t("report.din.evidence.csv_sha256"),
                translator.t("report.din.matlab.status"),
                translator.t("report.din.matlab.manifest_sha256"),
                translator.t("report.din.matlab.authority_value"),
                matched["manifest_sha256"],
                "DIN-METHOD", "FVA-RESEARCH", "USER-INPUT",
                "NOT-IMPLEMENTED")
            missing = [text for text in required_text
                       if tex_escape(text) not in latex]
            if missing:
                raise RuntimeError("%s report lacks 4.2 evidence: %r" %
                                   (locale, missing))
    return True


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.15)
    except tk.TclError:
        pass
    ModelBuilderApp(root)
    root.mainloop()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        try:
            run_self_test()
        except Exception as exc:
            try:
                if getattr(sys, "stderr", None):
                    sys.stderr.write("Model Builder self-test failed: %s\n" % exc)
            except Exception:
                pass
            raise SystemExit(2)
        raise SystemExit(0)
    main()
