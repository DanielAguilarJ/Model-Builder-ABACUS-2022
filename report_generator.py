# -*- coding: utf-8 -*-
"""Generate a self-contained LaTeX report from structured build JSON."""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess

import keyjoint_core as core
import model_builder_i18n as i18n

BADGE_COLORS = {
    "NORMATIVE": "1B5E20",
    "DIN-METHOD": "0B5394",
    "FVA-RESEARCH": "8A4B08",
    "USER-INPUT": "7F1D1D",
    "NOT-IMPLEMENTED": "4B5563",
    "LITERATURE": "4A148C",
    "CORE-SCREENING": "0D47A1",
    "USER-OVERRIDE": "B71C1C",
}


def _read_json(path, default=None):
    if not path or not os.path.isfile(path):
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def _write_json(path, payload):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    os.replace(temporary, path)


def tex_escape(value):
    text = str(value if value is not None else "")
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
        "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
        "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
        "≤": r"$\leq$", "≥": r"$\geq$", "→": r"$\rightarrow$",
        "×": r"$\times$", "·": r"\textperiodcentered{}", "°": r"\textdegree{}",
        "–": "--", "—": "---", "−": r"$-$",
    }
    return "".join(replacements.get(char, char) for char in text)


def _fmt(value, translator=None):
    if value is None:
        return "--"
    if isinstance(value, bool):
        if translator:
            return translator.t("common.yes") if value else translator.t("common.no")
        return "yes" if value else "no"
    if isinstance(value, float):
        magnitude = abs(value)
        if magnitude and (magnitude >= 1.0e5 or magnitude < 1.0e-3):
            return "%.5g" % value
        return ("%.6f" % value).rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple)):
        return ", ".join(_fmt(item, translator) for item in value)
    if isinstance(value, dict):
        return "; ".join("%s=%s" % (key, _fmt(value[key], translator))
                         for key in sorted(value))
    return str(value)


def _badge(name):
    name = str(name or "USER-OVERRIDE")
    color = BADGE_COLORS.get(name, BADGE_COLORS["USER-OVERRIDE"])
    return (r"\colorbox[HTML]{%s}{\textcolor{white}{\sffamily\bfseries\scriptsize %s}}"
            % (color, tex_escape(name)))


def _table_rows(mapping, keys=None, translator=None):
    rows = []
    selected = keys or sorted(mapping)
    for key in selected:
        if key not in mapping:
            continue
        value = mapping[key]
        if isinstance(value, (dict, list, tuple)) and key not in (
                "din_band", "r1_din_range", "r2_din_range"):
            continue
        rows.append("%s & %s \\\\" % (
            tex_escape(key), tex_escape(_fmt(value, translator))))
    empty = translator.t("report.empty.no_data") if translator else "No data"
    return "\n".join(rows) or "%s & -- \\\\" % tex_escape(empty)


def _find_screenshots(workspace):
    images = []
    for current, _directories, files in os.walk(workspace.screenshots):
        for filename in sorted(files):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                images.append(os.path.join(current, filename))
    return images


def _relative_tex_path(path, report_dir):
    return os.path.relpath(path, report_dir).replace("\\", "/")


def _figure_blocks(images, report_dir, translator):
    blocks = []
    for index, image in enumerate(images, 1):
        relative = _relative_tex_path(image, report_dir)
        name = os.path.splitext(os.path.basename(image))[0].replace("_", " ")
        caption = translator.t("report.figure.caption", name=name)
        blocks.append(
            "\n".join((
                r"\begin{figure}[H]",
                r"\centering",
                r"\includegraphics[width=0.94\textwidth]{\detokenize{%s}}" % relative,
                r"\caption{%s}" % tex_escape(caption),
                r"\label{fig:model-%d}" % index,
                r"\end{figure}",
            )))
    return "\n\n".join(blocks) or (
        r"\begin{quote}\textit{%s}\end{quote}" % tex_escape(
            translator.t("report.empty.no_screenshots")))


def _issues_rows(issues, translator):
    if not issues:
        return "INFO & none & %s \\\\" % tex_escape(
            translator.t("report.empty.no_issues"))
    rows = []
    for issue in issues:
        localized = i18n.localize_issue(issue, translator)
        rows.append("%s & %s & %s \\\\" % (
            tex_escape(localized["presentation_level"]),
            tex_escape(localized["code"]),
            tex_escape(localized["presentation_message"])))
    return "\n".join(rows)


def _checks_rows(checks, translator):
    if not checks:
        return "-- & -- & -- & %s \\\\" % tex_escape(
            translator.t("report.empty.no_checks"))
    rows = []
    for item in checks:
        flag = item.get("flag", "")
        rows.append("%s & %s & %s & %s \\\\" % (
            tex_escape(i18n.localize_check_label(
                item.get("label", ""), translator)),
            tex_escape(_fmt(item.get("value"), translator)),
            tex_escape(i18n.verdict_text(flag, translator)),
            tex_escape(i18n.localize_check_note(
                item.get("note", ""), translator))))
    return "\n".join(rows)


def _reproduction_summary(item, translator):
    if item.get("winner_reproduced") is None:
        return translator.t("common.not_recorded")
    fields = [
        "%s=%s" % (translator.t("report.reproduction.regenerated"),
                    _fmt(item.get("winner_reproduced"), translator)),
        "%s=%s" % (translator.t("report.reproduction.tolerance"),
                    _fmt(item.get("winner_reproduction_match"), translator)),
        "%s=%s" % (translator.t("report.reproduction.exact"),
                    _fmt(item.get("winner_signature_exact"), translator)),
    ]
    deltas = item.get("winner_reproduction_deltas") or {}
    if deltas:
        fields.append("%s: %s" % (
            translator.t("report.reproduction.deltas"),
            _fmt(deltas, translator)))
    if item.get("winner_reproduction_error"):
        fields.append("%s: %s" % (
            translator.t("report.reproduction.error"),
            item.get("winner_reproduction_error")))
    return "; ".join(fields)


def _parts_rows(parts, translator):
    """One compact row per final, reproduced piece mesh."""
    if not parts:
        return r"-- & -- & -- & -- & -- & -- & -- & -- & -- & -- & -- \\"
    rows = []
    for name in sorted(parts):
        item = parts[name]
        quality = item.get("quality") or {}
        recipe = item.get("selected_recipe") or {}
        if isinstance(recipe, dict):
            recipe = recipe.get("recipe_id", "--")
        attempt_index = item.get("selected_attempt_index")
        attempt = ("%d/%d" % (int(attempt_index) + 1,
                               len(item.get("attempts") or []))
                   if attempt_index is not None else "--")
        rows.append("%s & %s & %s & %s & %s & %s & %s & %s & %s & %s & %s \\\\" % (
            tex_escape(name),
            tex_escape(i18n.verdict_text(quality.get("status", "MISSING"),
                                         translator)),
            tex_escape(_fmt(quality.get("score"), translator)), tex_escape(recipe),
            tex_escape(attempt), tex_escape(_fmt(item.get("nodes"), translator)),
            tex_escape(_fmt(item.get("elements"), translator)),
            tex_escape(_fmt(item.get("hex_pct"), translator)),
            tex_escape(_fmt(item.get("warnings"), translator)),
            tex_escape(_fmt(item.get("ar_bulk_worst"), translator)),
            tex_escape(_reproduction_summary(item, translator))))
    return "\n".join(rows)


def _build_provenance_rows(audit, translator):
    provenance = audit.get("build_provenance") or {}
    rows = []
    for item in provenance.get("runtime_inputs") or []:
        rows.append("%s & %s & %s & %s \\\\" % (
            tex_escape(item.get("role", "--")),
            tex_escape(_fmt(item.get("size_bytes"), translator)),
            tex_escape(item.get("sha256", "--")),
            tex_escape(item.get("path", "--"))))
    return "\n".join(rows) or "-- & -- & -- & %s \\\\" % tex_escape(
        translator.t("report.empty.no_provenance"))


def _attempt_rows(parts, translator):
    """Complete candidate history; exceptions remain visible and auditable."""
    rows = []
    for part in sorted(parts or {}):
        for index, attempt in enumerate(parts[part].get("attempts") or [], 1):
            recipe = attempt.get("recipe") or {}
            quality = attempt.get("quality") or {}
            metrics = attempt.get("metrics") or {}
            error = attempt.get("exception") or ""
            if len(error) > 120:
                error = error[:117] + "..."
            rows.append("%s & %d & %s & %s & %s & %s & %s & %s & %s & %s \\\\" % (
                tex_escape(part), index,
                tex_escape(recipe.get("recipe_id", "--")),
                tex_escape(recipe.get("control_strategy", "--")),
                tex_escape(i18n.verdict_text(
                    quality.get("status", "FAIL"), translator)),
                tex_escape(_fmt(quality.get("score"), translator)),
                tex_escape(_fmt(metrics.get("elements"), translator)),
                tex_escape(_fmt(metrics.get("hex_pct"), translator)),
                tex_escape(_fmt(metrics.get("failed"), translator)),
                tex_escape(error or "--")))
    return "\n".join(rows) or (
        "-- & -- & -- & -- & -- & -- & -- & -- & -- & %s \\\\" %
        tex_escape(translator.t("report.empty.no_attempts")))


def _quality_reasons(summary, translator):
    reasons = summary.get("reasons") or []
    if not reasons:
        return r"\textit{%s}" % tex_escape(
            translator.t("report.empty.no_quality_reasons"))
    return "\n".join(
        r"\begin{itemize}\item %s\end{itemize}" % tex_escape(
            i18n.localize_quality_reason(item, translator))
        for item in reasons)


def _mesh_policy_rows(plan, translator):
    rows = []
    for part in sorted((plan.get("parts") or {}).keys()):
        policy = plan["parts"][part]
        candidates = ", ".join(item.get("recipe_id", "")
                               for item in policy.get("candidates") or [])
        targets = policy.get("targets") or {}
        budgets = policy.get("budgets") or {}
        rows.append("%s & %s & %s & %s & %s & %s \\\\" % (
            tex_escape(part), tex_escape(candidates),
            tex_escape(_fmt(targets.get("min_hex_pct"), translator)),
            tex_escape(_fmt(targets.get("max_bulk_ar"), translator)),
            tex_escape(_fmt(budgets.get("soft_elements"), translator)),
            tex_escape(_fmt(budgets.get("hard_elements"), translator))))
    return "\n".join(rows) or r"-- & -- & -- & -- & -- & -- \\"


def _din6892_rows(record, translator):
    record = record or {}
    requested = record.get("requested") or {}
    derived = record.get("derived") or {}
    calculation = record.get("calculation") or {}
    backend = (record.get("realized") or {}).get("realized") or {}
    effective = derived.get("effective_bearing_depth") or {}
    material = derived.get("material") or {}
    post = (((derived.get("calculation_inputs") or {}).get("postprocess")) or {})
    provenance = post.get("provenance") or {}
    matlab = requested.get("matlab") or {}
    matlab_result = matlab.get("last_result") or {}
    matlab_comparison = matlab_result.get("comparison") or {}
    comparison_value = (matlab_comparison.get("all_match")
                        if matlab_comparison else None)
    factor_audit = calculation.get("factor_audit") or {}
    if not factor_audit:
        factor_status = None
    elif factor_audit.get("conclusive"):
        factor_status = "licensed factors supplied or acknowledged"
    else:
        factor_status = ("provisional; neutral 1.0 placeholders: %s" %
                         ", ".join(factor_audit.get("placeholder_factors") or []))
    skipped = calculation.get("components_skipped") or []
    skipped_text = ", ".join(str(item.get("name")) for item in skipped) or None

    # Per-component bearing check: which flank height each part was checked on
    # and which torque that produced. This is the row an engineer needs to see
    # why the hub and not the shaft governs.
    def component_text():
        rows_out = []
        for row in calculation.get("components") or []:
            depth = row.get("bearing_depth_mm")
            piece = "%s Re=%s" % (row.get("name"), _fmt(row.get("Re_MPa"), translator))
            if row.get("f_S") is not None:
                piece += " f_S=%s" % _fmt(row.get("f_S"), translator)
            if depth is not None:
                piece += " %s=%s mm" % (row.get("bearing_depth_symbol", "t_tr"),
                                        _fmt(depth, translator))
            if row.get("torque_allowable_Nm") is not None:
                piece += " -> %s N m" % _fmt(row.get("torque_allowable_Nm"),
                                             translator)
            if row.get("bearing_depth_is_fallback"):
                piece += " (fallback)"
            rows_out.append(piece)
        return "; ".join(rows_out) or None

    policy = calculation.get("bearing_depth_policy") or {}
    if not policy:
        depth_text = None
    else:
        depth_text = "%s: eq.9 %s mm" % (
            policy.get("policy_applied", "EQUATION_9"),
            _fmt(policy.get("t1tr_equation9_mm"), translator))
        if policy.get("t1tr_geometric_mm") is not None:
            depth_text += ", geometric %s mm" % _fmt(
                policy.get("t1tr_geometric_mm"), translator)
        depth_text += ", used %s mm" % _fmt(policy.get("t1tr_mm"), translator)

    reversal = calculation.get("load_reversal_count") or {}
    if not reversal:
        reversal_text = None
    else:
        reversal_text = "N_W = %s (%s), f_W = %s" % (
            _fmt(reversal.get("N_W"), translator), reversal.get("source"),
            _fmt(calculation.get("f_W"), translator))

    k_lambda_domain = calculation.get("K_lambda_domain") or {}
    if not k_lambda_domain or k_lambda_domain.get("error"):
        k_lambda_text = k_lambda_domain.get("error")
    else:
        k_lambda_text = ("K_lambda = %s, %s diagram, Q_A = %s, l_tr/d_w = %s" % (
            _fmt(k_lambda_domain.get("K_lambda"), translator),
            k_lambda_domain.get("load_derivation_position"),
            _fmt(k_lambda_domain.get("Q_A_shaft_over_hub"), translator),
            _fmt(k_lambda_domain.get("ltr_over_dw"), translator)))

    # The Method C length sizing lives on the Method C calculation, which is a
    # companion whenever another method is primary. Read it from wherever it is.
    companion_results = (record.get("companions") or {}).get("results") or {}
    sizing = calculation.get("sizing") or (
        ((companion_results.get("C_PRELIMINARY") or {}).get("calculation")
         or {}).get("sizing")) or {}
    if sizing.get("status") == "SIZED":
        sizing_text = ("M_t,req = %s N m -> l_tr = %s mm, key length = %s mm" % (
            _fmt(sizing.get("torque_required_Nm"), translator),
            _fmt(sizing.get("ltr_required_mm"), translator),
            _fmt(sizing.get("key_nominal_length_required_mm"), translator)))
    elif sizing:
        sizing_text = "%s: %s" % (sizing.get("status"), sizing.get("reason"))
    else:
        sizing_text = None

    companions = companion_results
    consistency = (record.get("companions") or {}).get("consistency") or {}
    if consistency.get("method_c_over_method_b") is None:
        consistency_text = None
    else:
        consistency_text = ("M_t,C / M_t,B = %s (%s)" % (
            _fmt(consistency.get("method_c_over_method_b"), translator),
            "conservative" if consistency.get("method_c_is_conservative")
            else "NOT conservative"))

    def companion_text(method_id):
        item = companions.get(method_id)
        if not item:
            return None
        value = item.get("torque_allowable_Nm")
        if value is None:
            return "%s: %s" % (item.get("status", "n/a"),
                              item.get("reason", "not evaluated"))
        return ("M_t,zul = %.2f N m; M_t,design = %.2f N m; governing %s; %s" %
                (float(value), float(item.get("torque_design_Nm") or 0.0),
                 item.get("governing_component", "n/a"),
                 item.get("status", "n/a")))

    rows = (
        ("requested.method", requested.get("method")),
        ("requested.variant", requested.get("variant_id")),
        ("requested.material", requested.get("material_pair")),
        ("requested.load_ratio", requested.get("load_ratio_R")),
        ("requested.upf", requested.get("UPF_um")),
        ("requested.xi", requested.get("xi_per_mille")),
        ("derived.status", record.get("status")),
        ("derived.material_source", material.get("source_id")),
        ("derived.t1tr", effective.get("t1tr_mm")),
        ("derived.t2tr", (derived.get("hub_effective_bearing_depth") or {}).get(
            "t2tr_mm")),
        ("derived.bearing_depth_policy", depth_text),
        ("derived.load_reversal", reversal_text),
        ("derived.k_lambda_domain", k_lambda_text),
        ("derived.allowable_torque", calculation.get("torque_allowable_Nm")),
        ("derived.design_torque", calculation.get("torque_design_Nm")),
        ("derived.governing_component", calculation.get("governing_component")),
        ("derived.components", component_text()),
        ("derived.p_zul", calculation.get("p_zul_MPa")),
        ("derived.p_eq_zul", calculation.get("p_eq_zul_MPa")),
        ("derived.p_eq", calculation.get("p_eq_MPa")),
        ("derived.safety_S_Feq", calculation.get(
            "safety_S_Feq", calculation.get("safety_S_F"))),
        ("derived.peak_torque", calculation.get("torque_peak_allowable_Nm")),
        ("derived.safety_S_Fmax", calculation.get("safety_S_Fmax")),
        ("derived.method_c_sizing", sizing_text),
        ("derived.factor_status", factor_status),
        ("derived.components_skipped", skipped_text),
        ("derived.equations", calculation.get("equations")),
        ("companion.B_DIN_CURRENT", companion_text("B_DIN_CURRENT")),
        ("companion.B_FVA_2025", companion_text("B_FVA_2025")),
        ("companion.C_PRELIMINARY", companion_text("C_PRELIMINARY")),
        ("companion.consistency", consistency_text),
        ("realized.status", backend.get("status", "NOT_REQUESTED")),
        ("realized.matching", backend.get("matching", "NOT_APPLICABLE")),
        ("realized.creates_job", backend.get("creates_job", False)),
        ("realized.submits_solver", backend.get("submits_solver", False)),
        ("evidence.csv_sha256", provenance.get("sha256")),
        ("evidence.source_step", provenance.get("source_step")),
        ("evidence.source_frame", provenance.get("source_frame")),
        ("matlab.mode", matlab.get("mode", "OFF")),
        ("matlab.status", matlab_result.get("status", "NOT_REQUESTED")),
        ("matlab.executed", matlab_result.get("executed", False)),
        ("matlab.bundle", matlab_result.get("bundle_path")),
        ("matlab.manifest_sha256", matlab_result.get("manifest_sha256")),
        ("matlab.comparison", comparison_value),
        ("matlab.authority", translator.t(
            "report.din.matlab.authority_value")),
        ("matlab.error", matlab_result.get("error")),
    )
    return "\n".join("%s & %s \\\\" % (
        tex_escape(translator.t("report.din.%s" % key, default=key)),
        tex_escape(_fmt(value, translator))) for key, value in rows)


def _standards_rows(params, derived, translator):
    selected = ((params.get("standards") or {}).get("selected") or {})
    registry = derived.get("standards_registry") or {}
    rows = []
    for role in sorted(selected):
        standard_id = selected[role]
        item = registry.get(standard_id) or {}
        title = translator.t("standard.%s.title" % standard_id,
                             default=item.get("title", "--"))
        implementation = translator.t(
            "standard.implementation.%s" % item.get("implementation", ""),
            default=item.get("implementation", "--"))
        rows.append("%s & %s & %s & %s & %s \\\\" % (
            tex_escape(translator.t("standard.role.%s" % role, default=role)),
            tex_escape(standard_id), _badge(item.get("badge")),
            tex_escape(implementation), tex_escape(title)))
    return "\n".join(rows) or r"-- & -- & -- & -- & -- \\"


def build_report_data(workspace, audit_path=None):
    expected = workspace.expected_paths()
    audit_path = audit_path or expected["audit_json"]
    audit = _read_json(audit_path)
    params = audit.get("params") or _read_json(expected["params"])
    derived = audit.get("derived") or params.get("_derived") or {}
    if not derived and params:
        try:
            probe = json.loads(json.dumps(params))
            derived = core.derive(probe)
        except Exception:
            derived = {}
    badges = []
    provenance = derived.get("provenance") or audit.get("traceability") or {}
    for item in provenance.values() if isinstance(provenance, dict) else []:
        badge = item.get("badge") if isinstance(item, dict) else None
        if badge and badge not in badges:
            badges.append(badge)
    for badge in (derived.get("geometry_badge"), derived.get("design_check_badge")):
        if badge and badge not in badges:
            badges.append(badge)
    din_record = derived.get("din6892") or {}
    calculation = din_record.get("calculation") or {}
    for badge in (calculation.get("badge"),
                  ((din_record.get("derived") or {}).get("material") or {}).get("badge")):
        if badge and badge not in badges:
            badges.append(badge)
    standard_registry = derived.get("standards_registry") or {}
    selected_standards = ((params.get("standards") or {}).get("selected") or {})
    for standard_id in selected_standards.values():
        badge = (standard_registry.get(standard_id) or {}).get("badge")
        if badge and badge not in badges:
            badges.append(badge)
    if not badges:
        badges = ["USER-OVERRIDE"]
    language = i18n.locale_from_params(
        params, default=(workspace.manifest.get("language") or i18n.DEFAULT_LOCALE))
    return {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "language": language,
        "project": workspace.manifest,
        "audit_path": audit_path,
        "audit": audit,
        "params": params,
        "derived": derived,
        "badges": badges,
        "screenshots": _find_screenshots(workspace),
    }


def render_latex(data, report_dir):
    translator = i18n.Translator(data.get("language", i18n.DEFAULT_LOCALE))
    project = data["project"]
    audit = data["audit"]
    params = data["params"]
    derived = data["derived"]
    badges = " ".join(_badge(item) for item in data["badges"])
    model_name = audit.get("model") or params.get("model_name") or project.get("model_name")
    verdict = audit.get("verdict") or ("NO AUDIT" if not audit else "UNKNOWN")
    screenshots = data["screenshots"]
    parts = audit.get("parts") or audit.get("mesh") or {}
    mesh_plan = audit.get("mesh_plan") or {}
    if not mesh_plan and params:
        try:
            mesh_plan = core.resolve_mesh_plan(json.loads(json.dumps(params)), derived)
        except Exception:
            mesh_plan = {}
    mesh_quality = audit.get("mesh_quality") or {}
    selected_geometry = (
        "D", "b", "h", "t1", "t1_tol_plus", "t2", "din_d2_ref",
        "form", "key_nominal_length", "slot_total_length",
        "load_bearing_length", "L", "L_hub", "hub_outer_over_shaft",
        "shaft_over_hub", "r1_din_range", "r2_din_range", "geometry_badge")
    traceability = derived.get("provenance") or audit.get("traceability") or {}
    trace_rows = []
    if isinstance(traceability, dict):
        for source_id in sorted(traceability):
            item = traceability[source_id]
            if not isinstance(item, dict):
                continue
            canonical_scope = item.get("scope", item.get("source", ""))
            trace_rows.append("%s & %s & %s \\\\" % (
                tex_escape(source_id), _badge(item.get("badge")),
                tex_escape(i18n.source_scope(
                    source_id, translator, canonical_scope))))
    if not trace_rows:
        trace_rows.append("-- & \\badgeUser & %s \\\\" % tex_escape(
            translator.t("report.empty.no_traceability")))

    template = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[%(babel)s]{babel}
\usepackage{geometry,graphicx,booktabs,longtable,array,float,xcolor,hyperref}
\geometry{margin=2.1cm}
\hypersetup{hidelinks}
\renewcommand{\arraystretch}{1.18}
\newcommand{\badgeUser}{\colorbox[HTML]{B71C1C}{\textcolor{white}{\scriptsize USER-OVERRIDE}}}
\title{\textbf{%(report_title)s}\\[4pt]\large %(model)s}
\author{%(author)s}
\date{%(date)s}
\begin{document}
\maketitle
\begin{center}%(badges)s\end{center}
\begin{abstract}
%(abstract)s
\end{abstract}
\renewcommand{\contentsname}{%(contents)s}
\tableofcontents

\section{%(section_project)s}
\begin{tabular}{@{}ll@{}}
\toprule
%(col_project)s & %(project)s \\
%(col_project_id)s & %(project_id)s \\
%(col_model)s & %(model)s \\
%(col_builder)s & %(builder)s \\
%(col_generated)s & %(generated)s \\
%(col_workspace)s & \detokenize{%(workspace)s} \\
\bottomrule
\end{tabular}

\subsection{%(section_provenance)s}
%(provenance_text)s
\scriptsize
\begin{longtable}{@{}p{0.13\textwidth}rp{0.42\textwidth}p{0.32\textwidth}@{}}
\toprule %(col_role)s & %(col_bytes)s & SHA-256 & %(col_runtime_path)s \\
\midrule\endhead
%(provenance_rows)s
\bottomrule
\end{longtable}
\normalsize

\section{%(section_scope)s}
%(badges)s

%(scope_text)s

\begin{longtable}{@{}p{0.24\textwidth}p{0.19\textwidth}p{0.49\textwidth}@{}}
\toprule %(col_source_id)s & %(col_badge)s & %(col_scope)s \\
\midrule\endhead
%(trace_rows)s
\bottomrule
\end{longtable}

\section{%(section_geometry)s}
\begin{longtable}{@{}p{0.46\textwidth}p{0.46\textwidth}@{}}
\toprule %(col_quantity)s & %(col_value)s \\
\midrule\endhead
%(geometry_rows)s
\bottomrule
\end{longtable}

\section{%(section_din6892)s}
%(din_scope_text)s

\begin{longtable}{@{}p{0.42\textwidth}p{0.50\textwidth}@{}}
\toprule %(col_quantity)s & %(col_value)s \\
\midrule\endhead
%(din6892_rows)s
\bottomrule
\end{longtable}

\subsection{%(section_standards)s}
\scriptsize
\begin{longtable}{@{}p{0.12\textwidth}p{0.20\textwidth}p{0.15\textwidth}p{0.18\textwidth}p{0.29\textwidth}@{}}
\toprule %(col_standard_role)s & %(col_standard_id)s & %(col_badge)s & %(col_implementation)s & %(col_scope)s \\
\midrule\endhead
%(standards_rows)s
\bottomrule
\end{longtable}
\normalsize

\section{%(section_validation)s}
\begin{longtable}{@{}p{0.10\textwidth}p{0.22\textwidth}p{0.60\textwidth}@{}}
\toprule %(col_level)s & %(col_code)s & %(col_message)s \\
\midrule\endhead
%(issue_rows)s
\bottomrule
\end{longtable}

\section{%(section_mesh)s}
%(mesh_text)s

%(mesh_ranking_text)s

\subsection{%(section_policy)s}
\scriptsize
\begin{longtable}{@{}p{0.09\textwidth}p{0.35\textwidth}rrrr@{}}
\toprule %(col_part)s & %(col_candidates)s & %(col_min_hex)s & %(col_max_ar)s & %(col_soft_budget)s & %(col_hard_budget)s \\
\midrule\endhead
%(mesh_policy_rows)s
\bottomrule
\end{longtable}
\normalsize

\subsection{%(section_selected_meshes)s}
\resizebox{\textwidth}{!}{%%
\begin{tabular}{@{}lllclrrrrrp{0.36\textwidth}@{}}
\toprule %(col_part)s & %(col_status)s & %(col_score)s & %(col_recipe)s & %(col_attempt)s & %(col_nodes)s & %(col_elements)s & %(col_hex)s & %(col_warnings)s & %(col_bulk_ar)s & %(col_reproduction)s \\
\midrule
%(part_rows)s
\bottomrule
\end{tabular}}

%(quality_reasons)s

\subsection{%(section_history)s}
\scriptsize
\begin{longtable}{@{}llp{0.13\textwidth}p{0.17\textwidth}rrrrrp{0.20\textwidth}@{}}
\toprule %(col_part)s & %(col_number)s & %(col_recipe)s & %(col_strategy)s & %(col_status)s & %(col_score)s & %(col_elements)s & %(col_hex)s & %(col_failed)s & %(col_exception)s \\
\midrule\endhead
%(attempt_rows)s
\bottomrule
\end{longtable}
\normalsize

\section{%(section_checks)s}
\begin{longtable}{@{}p{0.34\textwidth}p{0.13\textwidth}p{0.20\textwidth}p{0.25\textwidth}@{}}
\toprule %(col_check)s & %(col_value)s & %(col_flag)s & %(col_note)s \\
\midrule\endhead
%(check_rows)s
\bottomrule
\end{longtable}

\section{%(section_evidence)s}
%(figures)s

\section{%(section_deliverables)s}
%(deliverables_text)s

\section{%(section_limitations)s}
\begin{enumerate}
%(limitations)s
\end{enumerate}
\end{document}
"""
    def lt(key, **kwargs):
        return tex_escape(translator.t(key, **kwargs))

    mesh_profile_data = mesh_plan.get("element_profile") or core.mesh_element_profile(
        mesh_plan.get("element_order", "linear"),
        mesh_plan.get("linear_hex_code", "C3D8"))
    mesh_profile = i18n.element_profile_label(mesh_profile_data, translator)
    verdict_display = i18n.verdict_text(verdict, translator)
    mesh_status = i18n.verdict_text(
        mesh_quality.get("status", "MISSING"), translator)
    mesh_text = translator.t(
        "report.mesh_text", template=mesh_plan.get("template", "--"),
        algorithm=mesh_plan.get("algorithm_version", core.MESH_ALGORITHM_VERSION),
        selection=mesh_plan.get("selection", "--"),
        order=mesh_plan.get("element_order", "--"), profile=mesh_profile,
        status=mesh_status, score=_fmt(mesh_quality.get("score"), translator),
        hard=_fmt(mesh_quality.get("hard_passed"), translator),
        passed=_fmt(mesh_quality.get("passed"), translator))
    limitations = "\n".join(
        r"\item %s" % tex_escape(item.strip())
        for item in translator.t("report.limitations").split("|") if item.strip())
    values = {
        "babel": translator.t("report.babel"),
        "report_title": lt("report.title"),
        "model": tex_escape(model_name),
        "author": tex_escape(project.get("author") or
                             translator.t("report.author_default")),
        "date": tex_escape(data["generated_at"][:10]),
        "badges": badges,
        "abstract": lt("report.abstract", verdict=verdict_display),
        "contents": lt("report.toc"),
        "section_project": lt("report.section.project"),
        "section_provenance": lt("report.section.provenance"),
        "provenance_text": lt("report.provenance_text"),
        "section_scope": lt("report.section.scope"),
        "scope_text": lt("report.scope_text"),
        "section_geometry": lt("report.section.geometry"),
        "section_din6892": lt("report.section.din6892"),
        "din_scope_text": lt("report.din.scope_text"),
        "section_standards": lt("report.section.standards"),
        "section_validation": lt("report.section.validation"),
        "section_mesh": lt("report.section.mesh"),
        "mesh_text": tex_escape(mesh_text),
        "mesh_ranking_text": lt("report.mesh_ranking_text"),
        "section_policy": lt("report.section.policy"),
        "section_selected_meshes": lt("report.section.selected_meshes"),
        "section_history": lt("report.section.history"),
        "section_checks": lt("report.section.checks"),
        "section_evidence": lt("report.section.evidence"),
        "section_deliverables": lt("report.section.deliverables"),
        "deliverables_text": lt("report.deliverables_text"),
        "section_limitations": lt("report.section.limitations"),
        "limitations": limitations,
        "col_project": lt("report.col.project"),
        "col_project_id": lt("report.col.project_id"),
        "col_model": lt("report.col.model"),
        "col_builder": lt("report.col.builder"),
        "col_generated": lt("report.col.generated"),
        "col_workspace": lt("report.col.workspace"),
        "col_role": lt("report.col.role"),
        "col_bytes": lt("report.col.bytes"),
        "col_runtime_path": lt("report.col.runtime_path"),
        "col_source_id": lt("report.col.source_id"),
        "col_badge": lt("report.col.badge"),
        "col_scope": lt("report.col.scope"),
        "col_standard_role": lt("report.col.standard_role"),
        "col_standard_id": lt("report.col.standard_id"),
        "col_implementation": lt("report.col.implementation"),
        "col_quantity": lt("report.col.quantity"),
        "col_value": lt("report.col.value"),
        "col_level": lt("report.col.level"),
        "col_code": lt("report.col.code"),
        "col_message": lt("report.col.message"),
        "col_part": lt("report.col.part"),
        "col_candidates": lt("report.col.candidates"),
        "col_min_hex": lt("report.col.min_hex"),
        "col_max_ar": lt("report.col.max_ar"),
        "col_soft_budget": lt("report.col.soft_budget"),
        "col_hard_budget": lt("report.col.hard_budget"),
        "col_status": lt("report.col.status"),
        "col_score": lt("report.col.score"),
        "col_recipe": lt("report.col.recipe"),
        "col_attempt": lt("report.col.attempt"),
        "col_nodes": lt("report.col.nodes"),
        "col_elements": lt("report.col.elements"),
        "col_hex": lt("report.col.hex"),
        "col_warnings": lt("report.col.warnings"),
        "col_bulk_ar": lt("report.col.bulk_ar"),
        "col_reproduction": lt("report.col.reproduction"),
        "col_number": lt("report.col.number"),
        "col_strategy": lt("report.col.strategy"),
        "col_failed": lt("report.col.failed"),
        "col_exception": lt("report.col.exception"),
        "col_check": lt("report.col.check"),
        "col_flag": lt("report.col.flag"),
        "col_note": lt("report.col.note"),
        "project": tex_escape(project.get("project_name", "")),
        "project_id": tex_escape(project.get("project_id", "")),
        "builder": tex_escape(project.get("builder_version", "")),
        "generated": tex_escape(data["generated_at"]),
        "workspace": workspace_path_for_tex(project.get("root", "")),
        "provenance_rows": _build_provenance_rows(audit, translator),
        "trace_rows": "\n".join(trace_rows),
        "geometry_rows": _table_rows(
            derived, selected_geometry, translator),
        "din6892_rows": _din6892_rows(derived.get("din6892") or {}, translator),
        "standards_rows": _standards_rows(params, derived, translator),
        "issue_rows": _issues_rows(audit.get("issues") or [], translator),
        "mesh_policy_rows": _mesh_policy_rows(mesh_plan, translator),
        "part_rows": _parts_rows(parts, translator),
        "attempt_rows": _attempt_rows(parts, translator),
        "quality_reasons": _quality_reasons(mesh_quality, translator),
        "check_rows": _checks_rows(audit.get("checks") or [], translator),
        "figures": _figure_blocks(screenshots, report_dir, translator),
    }
    return template % values


def workspace_path_for_tex(path):
    return str(path or "").replace("\\", "/").replace("{", "").replace("}", "")


def compile_latex(tex_path, locale=i18n.DEFAULT_LOCALE, timeout=180):
    translator = i18n.Translator(locale)
    report_dir = os.path.dirname(os.path.abspath(tex_path))
    log_path = os.path.join(report_dir, "latex_build.log")
    latexmk = shutil.which("latexmk")
    pdflatex = shutil.which("pdflatex")
    if latexmk:
        commands = [[latexmk, "-pdf", "-interaction=nonstopmode",
                     "-halt-on-error", os.path.basename(tex_path)]]
        compiler = "latexmk"
    elif pdflatex:
        base = [pdflatex, "-interaction=nonstopmode", "-halt-on-error",
                os.path.basename(tex_path)]
        commands = [base, base]
        compiler = "pdflatex"
    else:
        with open(log_path, "w", encoding="utf-8") as stream:
            stream.write(translator.t("report.compile.no_compiler_log"))
        return {"compiled": False, "compiler": None, "return_code": None,
                "pdf": None, "log": log_path,
                "message": translator.t("report.compile.no_compiler")}
    return_code = 0
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write(translator.t("report.compile.start", compiler=compiler))
        log.flush()
        for command in commands:
            completed = subprocess.run(
                command, cwd=report_dir, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, shell=False, timeout=timeout,
                check=False, text=True, encoding="utf-8", errors="replace")
            return_code = completed.returncode
            if return_code:
                break
    pdf_path = os.path.splitext(tex_path)[0] + ".pdf"
    compiled = return_code == 0 and os.path.isfile(pdf_path)
    return {"compiled": compiled, "compiler": compiler,
            "return_code": return_code, "pdf": pdf_path if compiled else None,
            "log": log_path,
            "message": translator.t("report.compile.success" if compiled else
                                    "report.compile.failed")}


def generate_report(workspace, audit_path=None, compile_pdf=True):
    workspace.ensure_layout()
    data = build_report_data(workspace, audit_path)
    translator = i18n.Translator(data["language"])
    data_path = os.path.join(workspace.reports, "report_data.json")
    serializable = dict(data)
    serializable["screenshots"] = [workspace.relative(path)
                                   for path in data["screenshots"]]
    _write_json(data_path, serializable)
    tex_path = os.path.join(workspace.reports, "report.tex")
    latex = render_latex(data, workspace.reports)
    with open(tex_path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(latex)
    result = compile_latex(tex_path, data["language"]) if compile_pdf else {
        "compiled": False, "compiler": None, "return_code": None,
        "pdf": None, "log": None,
        "message": translator.t("report.compile.disabled")}
    result.update({"tex": tex_path, "data": data_path,
                   "screenshots": len(data["screenshots"])})
    workspace.manifest["reports"] = {
        "tex": workspace.relative(tex_path),
        "pdf": workspace.relative(result["pdf"]) if result.get("pdf") else None,
        "data": workspace.relative(data_path),
        "compiled": bool(result.get("compiled")),
        "compiler": result.get("compiler"),
        "language": data["language"],
        "message": result.get("message"),
    }
    workspace.save_manifest()
    workspace.register_artifact(tex_path, "latex_report")
    workspace.register_artifact(data_path, "report_data")
    if result.get("pdf"):
        workspace.register_artifact(result["pdf"], "pdf_report")
    if result.get("log"):
        workspace.register_artifact(result["log"], "latex_log")
    return result
