# -*- coding: utf-8 -*-
"""Runtime localization for the Model Builder Python 3 presentation layer.

Technical identifiers, JSON keys, evidence badges and validation codes stay
canonical.  This module translates only presentation text.  It is deliberately
not imported by ``keyjoint_core.py`` or the Abaqus Python 2.7 runtime.
"""
from __future__ import annotations

import json
import os
import re
import string
import sys

SUPPORTED_LOCALES = ("es", "en", "de")
DEFAULT_LOCALE = "es"
FALLBACK_LOCALES = ("es", "en")
LANGUAGE_LABELS = {
    "es": "Español",
    "en": "English",
    "de": "Deutsch",
}


class CatalogError(RuntimeError):
    """Raised when a canonical catalog is missing or structurally invalid."""


def normalize_locale(value):
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "español": "es", "spanish": "es", "es": "es",
        "english": "en", "englisch": "en", "en": "en",
        "deutsch": "de", "german": "de", "de": "de",
    }
    if text in aliases:
        return aliases[text]
    primary = text.split("-", 1)[0]
    return primary if primary in SUPPORTED_LOCALES else DEFAULT_LOCALE


def catalog_directory(explicit=None):
    """Resolve UTF-8 JSON catalogs in source and PyInstaller one-file builds."""
    candidates = []
    if explicit:
        candidates.append(os.path.abspath(explicit))
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(os.path.join(bundle, "i18n"))
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "i18n"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n"))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return candidates[0]


def _read_catalog(directory, locale):
    path = os.path.join(directory, "%s.json" % locale)
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("locale") != locale:
        raise CatalogError("Catalog %s declares locale %r" % (path, payload.get("locale")))
    strings = payload.get("strings")
    if not isinstance(strings, dict) or not strings:
        raise CatalogError("Catalog %s has no non-empty strings object" % path)
    invalid = sorted(key for key, value in strings.items()
                     if not isinstance(key, str) or not isinstance(value, str))
    if invalid:
        raise CatalogError("Catalog %s contains non-string entries: %s" %
                           (path, ", ".join(invalid)))
    return payload


def _placeholders(value):
    names = set()
    try:
        for _literal, field, _format_spec, _conversion in string.Formatter().parse(value):
            if field:
                names.add(field.split(".", 1)[0].split("[", 1)[0])
    except ValueError as exc:
        raise CatalogError("Invalid format string %r: %s" % (value, exc))
    return names


def validate_catalogs(directory=None):
    """Validate locale presence, key parity, placeholder parity and Unicode."""
    directory = catalog_directory(directory)
    payloads = dict((locale, _read_catalog(directory, locale))
                    for locale in SUPPORTED_LOCALES)
    reference = payloads[DEFAULT_LOCALE]["strings"]
    reference_keys = set(reference)
    problems = []
    for locale in SUPPORTED_LOCALES:
        strings = payloads[locale]["strings"]
        keys = set(strings)
        missing = sorted(reference_keys - keys)
        extra = sorted(keys - reference_keys)
        if missing or extra:
            problems.append("%s missing=%r extra=%r" % (locale, missing, extra))
            continue
        for key in sorted(reference_keys):
            expected = _placeholders(reference[key])
            actual = _placeholders(strings[key])
            if actual != expected:
                problems.append("%s:%s placeholders=%r expected=%r" %
                                (locale, key, sorted(actual), sorted(expected)))
            if "\ufffd" in strings[key]:
                problems.append("%s:%s contains Unicode replacement character" %
                                (locale, key))
    if problems:
        raise CatalogError("Catalog parity failed: " + "; ".join(problems))
    probe = reference.get("i18n.unicode_probe", "")
    if not all(mark in probe for mark in ("á", "ñ", "ü", "≤", "→")):
        raise CatalogError("Spanish Unicode probe is incomplete")
    return {
        "directory": directory,
        "locales": list(SUPPORTED_LOCALES),
        "key_count": len(reference_keys),
        "keys": sorted(reference_keys),
    }


class Translator(object):
    """Small safe translator with deterministic Spanish/English fallback."""

    def __init__(self, locale=DEFAULT_LOCALE, directory=None):
        self.directory = catalog_directory(directory)
        self.catalogs = {}
        self.load_errors = {}
        for code in SUPPORTED_LOCALES:
            try:
                self.catalogs[code] = _read_catalog(self.directory, code)["strings"]
            except (OSError, ValueError, CatalogError) as exc:
                self.load_errors[code] = str(exc)
        if not any(code in self.catalogs for code in FALLBACK_LOCALES):
            raise CatalogError("Neither Spanish nor English catalog could be loaded from %s" %
                               self.directory)
        self.locale = normalize_locale(locale)
        self._rebuild_reverse_index()

    def _rebuild_reverse_index(self):
        self._reverse = {}
        for code in SUPPORTED_LOCALES:
            for key, value in self.catalogs.get(code, {}).items():
                self._reverse.setdefault(value, key)

    def set_locale(self, locale):
        requested = normalize_locale(locale)
        if requested not in self.catalogs:
            requested = next((code for code in FALLBACK_LOCALES
                              if code in self.catalogs), DEFAULT_LOCALE)
        self.locale = requested
        return requested

    def fallback_chain(self):
        chain = []
        for code in (self.locale,) + FALLBACK_LOCALES:
            if code not in chain and code in self.catalogs:
                chain.append(code)
        return chain

    def t(self, key, default=None, **values):
        template = None
        for code in self.fallback_chain():
            if key in self.catalogs[code]:
                template = self.catalogs[code][key]
                break
        if template is None:
            template = default if default is not None else key
        if not values:
            return template
        try:
            return template.format(**values)
        except (KeyError, ValueError, IndexError):
            fallback = default if default is not None else template
            return str(fallback)

    def translate_text(self, text):
        """Translate an exact static widget value through its stable catalog key."""
        key = self._reverse.get(str(text))
        return self.t(key, default=text) if key else text

    def language_label(self, locale=None):
        return LANGUAGE_LABELS[normalize_locale(locale or self.locale)]


def locale_from_params(params, default=DEFAULT_LOCALE):
    project = (params or {}).get("project") or {}
    return normalize_locale(project.get("language", default))


def set_param_language(params, locale):
    project = params.setdefault("project", {})
    project["language"] = normalize_locale(locale)
    return params


def localize_issue(issue, translator):
    """Return presentation text while preserving code and canonical_message."""
    item = dict(issue or {})
    code = str(item.get("code", "unknown"))
    canonical = item.get("canonical_message", item.get("msg", ""))
    item["canonical_message"] = canonical
    item["presentation_message"] = translator.t(
        "validation.%s" % code,
        default=translator.t("validation.unknown", code=code),
    )
    item["presentation_level"] = translator.t(
        "level.%s" % str(item.get("level", "info")).lower(),
        default=str(item.get("level", "info")).upper(),
    )
    return item


def mesh_template_description(template_id, translator, canonical=""):
    return translator.t("mesh_template.%s.description" % str(template_id).upper(),
                        default=canonical)


def element_profile_label(profile, translator):
    profile = profile or {}
    return translator.t(
        "mesh.profile", primary=profile.get("primary", "--"),
        fallback=profile.get("fallback", "--"))


def preset_label(preset_id, translator):
    return translator.t("preset.%s" % str(preset_id), default=str(preset_id))


def source_scope(source_id, translator, canonical=""):
    return translator.t("source_scope.%s" % str(source_id), default=canonical)


def localize_quality_reason(reason, translator):
    text = str(reason or "")
    if ": " in text:
        part, details = text.split(": ", 1)
    else:
        part, details = "--", text
    localized = []
    for detail in details.split("; "):
        exact = {
            "mesh has no elements": "quality_reason.no_elements",
            "expected fillet refinement was not detected":
                "quality_reason.fillet_missing",
            "selected recipe was not reproducible within declared tolerances":
                "quality_reason.not_reproducible",
        }.get(detail)
        if exact:
            localized.append(translator.t(exact))
            continue
        patterns = (
            (r"^(\d+) failed element\(s\)$",
             "quality_reason.failed_elements", ("count",)),
            (r"^expected one connected component, found (\d+)$",
             "quality_reason.components", ("count",)),
            (r"^element hard budget exceeded \((\d+) > (\d+)\)$",
             "quality_reason.hard_budget", ("actual", "limit")),
            (r"^quality score ([0-9.]+) below warning threshold$",
             "quality_reason.low_score", ("score",)),
        )
        translated = None
        for pattern, key, names in patterns:
            match = re.match(pattern, detail)
            if match:
                translated = translator.t(
                    key, **dict(zip(names, match.groups())))
                break
        localized.append(translated or translator.t(
            "quality_reason.canonical_detail", detail=detail))
    return translator.t(
        "quality_reason.part", part=part, detail="; ".join(localized))


def verdict_text(code, translator):
    technical = str(code or "UNKNOWN").upper()
    explanation = translator.t("verdict.%s" % technical,
                               default=translator.t("verdict.UNKNOWN"))
    return "%s — %s" % (technical, explanation)


def localize_check_label(label, translator):
    """Translate known fit-check presentation while retaining numeric data."""
    text = str(label or "")
    form_match = re.match(r"^key length vs keyway \(Form ([^)]+)\)$", text)
    if form_match:
        return translator.t("check.key_length_vs_keyway", form=form_match.group(1))
    key = {
        "shaft OD vs hub bore": "check.shaft_od_vs_hub_bore",
        "key base vs keyway floor": "check.key_base_vs_floor",
        "shaft keyway flank/side": "check.shaft_flank",
        "hub groove flank/side": "check.hub_flank",
        "key top vs groove roof (g_c)": "check.key_top_vs_roof",
        "hub length vs keyway span": "check.hub_length_vs_span",
        "plain shaft after keyway": "check.plain_shaft_after_keyway",
        "chamfer c vs root fillet r2": "check.chamfer_vs_fillet",
        "-> bottom chamfer clearance": "check.bottom_chamfer_clearance",
        "-> top chamfer clearance": "check.top_chamfer_clearance",
        "straight flank left on key": "check.straight_flank",
        "hub wall left above keyway": "check.hub_wall",
    }.get(text.strip())
    return translator.t(key, default=text) if key else text


def localize_check_note(note, translator):
    text = str(note or "")
    exact = {
        "gap>=0 (0 = line-to-line seat)": "check_note.line_to_line",
        "should be ~0": "check_note.approx_zero",
        ">=0 (0 = tight fit, DIN P9/h9)": "check_note.tight_fit",
        ">=0": "check_note.nonnegative",
        "gap>=0": "check_note.gap_nonnegative",
        "info only": "check_note.info_only",
        "= (c - r2)/sqrt(2)": "check_note.bottom_formula",
        "vs hub roof fillet r1": "check_note.vs_roof_fillet",
        "= h - 2c, load-carrying height": "check_note.load_height",
        "= d_a/2 - (R + t2); raise Q_A if <= 0": "check_note.hub_wall_formula",
    }
    if text in exact:
        return translator.t(exact[text], default=text)
    patterns = (
        (r"^l <= (.+)$", "check_note.length_limit", "limit"),
        (r"^room for the end BC \(want >= D/4 = (.+)\)$",
         "check_note.end_bc_room", "limit"),
        (r"^need c >= r2 = (.+)$", "check_note.chamfer_limit", "limit"),
    )
    for pattern, key, name in patterns:
        match = re.match(pattern, text)
        if match:
            return translator.t(key, **{name: match.group(1)})
    return translator.t("check_note.canonical_detail", detail=text)
