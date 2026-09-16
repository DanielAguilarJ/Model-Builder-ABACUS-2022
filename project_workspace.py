# -*- coding: utf-8 -*-
"""Isolated, reproducible project workspaces for Model Builder.

This module is used by the normal Python 3 GUI, not by the Abaqus kernel.
Every build receives a new project root and fixed artifact directories so job
files can never leak beside the executable.
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import re
import shutil
import unicodedata
import uuid

import keyjoint_core as core

WORKSPACE_SCHEMA_VERSION = 2
PARAMETER_SCHEMA_VERSION = core.SCHEMA_VERSION
DIRECTORY_NAMES = (
    "input",
    "generated",
    "model",
    "jobs",
    "screenshots",
    "reports",
    "logs",
)


def _utc_now():
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _atomic_json(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    os.replace(temporary, path)


def sanitize_name(value, fallback="keyjoint"):
    """Create a portable Windows folder/model slug without hiding collisions."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip(" ._-")
    text = re.sub(r"_+", "_", text)
    return (text or fallback)[:72]


def default_projects_root():
    documents = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(documents):
        documents = os.path.expanduser("~")
    return os.path.join(documents, "ModelBuilder Projects")


def migrate_workspace_manifest(manifest):
    """Migrate workspace schema 1 to 2 without changing artifact paths."""
    if not isinstance(manifest, dict):
        raise ValueError("Workspace manifest must be a JSON object.")
    try:
        source = int(manifest.get("workspace_schema_version", 1))
    except (TypeError, ValueError):
        raise ValueError("workspace_schema_version must be an integer.")
    if source > WORKSPACE_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported future workspace schema %d; expected at most %d."
            % (source, WORKSPACE_SCHEMA_VERSION))
    if source < 1:
        raise ValueError("Unsupported workspace schema %d." % source)
    result = copy.deepcopy(manifest)
    if source == 1:
        result["workspace_schema_version"] = WORKSPACE_SCHEMA_VERSION
        result.setdefault("language", "es")
        result.setdefault("configuration", {})
        result["configuration"].setdefault(
            "parameter_schema_version", PARAMETER_SCHEMA_VERSION)
        result["workspace_migration"] = {
            "source_schema": 1,
            "target_schema": WORKSPACE_SCHEMA_VERSION,
            "artifact_paths_preserved": True,
        }
    return result


class ProjectWorkspace(object):
    """Owns one immutable directory layout and its mutable project manifest."""

    def __init__(self, root, manifest):
        self.root = os.path.abspath(root)
        self.manifest = manifest
        self.manifest_path = os.path.join(self.root, "project.json")
        for name in DIRECTORY_NAMES:
            setattr(self, name, os.path.join(self.root, name))

    @classmethod
    def create(cls, base_dir, project_name, model_name, builder_version,
               author="", technical_contract_path=None):
        base = os.path.abspath(os.path.expandvars(os.path.expanduser(base_dir)))
        if not base:
            raise ValueError("A project base directory is required.")
        os.makedirs(base, exist_ok=True)
        if not os.path.isdir(base):
            raise ValueError("Project base is not a directory: %s" % base)

        slug = sanitize_name(project_name)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        root = os.path.join(base, "%s_%s" % (slug, stamp))
        suffix = 1
        candidate = root
        while os.path.exists(candidate):
            candidate = "%s_%02d" % (root, suffix)
            suffix += 1
        root = candidate
        os.makedirs(root)
        for name in DIRECTORY_NAMES:
            os.makedirs(os.path.join(root, name))

        project_id = str(uuid.uuid4())
        created = _utc_now()
        manifest = {
            "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
            "project_id": project_id,
            "project_name": str(project_name or slug),
            "project_slug": slug,
            "model_name": sanitize_name(model_name, "PARAM_MODEL"),
            "author": str(author or ""),
            "builder_version": str(builder_version),
            "language": "es",
            "created_at": created,
            "updated_at": created,
            "status": "CREATED",
            "root": root,
            "directories": dict((name, name) for name in DIRECTORY_NAMES),
            "configuration": {
                "parameter_schema_version": PARAMETER_SCHEMA_VERSION,
            },
            "run": {"started_at": None, "finished_at": None,
                    "return_code": None, "message": ""},
            "artifacts": [],
            "reports": {},
        }
        workspace = cls(root, manifest)
        workspace.save_manifest()
        if technical_contract_path and os.path.isfile(technical_contract_path):
            target = os.path.join(workspace.input, "technical_contract.json")
            shutil.copy2(technical_contract_path, target)
            workspace.register_artifact(target, "technical_contract", "NORMATIVE")
        return workspace

    @classmethod
    def open(cls, root):
        root = os.path.abspath(root)
        path = os.path.join(root, "project.json")
        with open(path, "r", encoding="utf-8") as stream:
            manifest = migrate_workspace_manifest(json.load(stream))
        workspace = cls(root, manifest)
        workspace.ensure_layout()
        workspace.save_manifest()
        return workspace

    def ensure_layout(self):
        os.makedirs(self.root, exist_ok=True)
        for name in DIRECTORY_NAMES:
            os.makedirs(getattr(self, name), exist_ok=True)

    def save_manifest(self):
        self.manifest["root"] = self.root
        self.manifest["updated_at"] = _utc_now()
        _atomic_json(self.manifest_path, self.manifest)

    def set_status(self, status, message="", **run_values):
        self.manifest["status"] = str(status)
        run = self.manifest.setdefault("run", {})
        if message:
            run["message"] = str(message)
        run.update(run_values)
        self.save_manifest()

    def prepare_params(self, params):
        """Return normalized schema-6 parameters with absolute artifact routes."""
        payload = core.normalize_params(copy.deepcopy(params))
        payload["schema_version"] = PARAMETER_SCHEMA_VERSION
        payload["model_name"] = sanitize_name(
            payload.get("model_name") or self.manifest.get("model_name"),
            "PARAM_MODEL")
        project_data = payload.get("project") or {}
        language = str(project_data.get("language", "es")).strip().lower()
        if language not in ("es", "en", "de"):
            language = "es"
        payload["project"] = {
            "id": self.manifest["project_id"],
            "name": self.manifest["project_name"],
            "root": self.root,
            "manifest": self.manifest_path,
            "language": language,
        }
        self.manifest["language"] = language
        payload["artifacts"] = {
            "input_dir": self.input,
            "generated_dir": self.generated,
            "model_dir": self.model,
            "jobs_dir": self.jobs,
            "screenshots_dir": self.screenshots,
            "reports_dir": self.reports,
            "logs_dir": self.logs,
        }
        # Backward-compatible engine field; never used as solver cwd.
        payload["output_dir"] = self.generated
        self.manifest["model_name"] = payload["model_name"]
        self.manifest["configuration"] = {
            "params": os.path.join("input", "params.json"),
            "artifact_routes_absolute": True,
            "language": language,
            "parameter_schema_version": PARAMETER_SCHEMA_VERSION,
            "normalization": copy.deepcopy(payload.get("_migration", {})),
        }
        return payload

    def write_params(self, params, filename="params.json"):
        payload = self.prepare_params(params)
        path = os.path.join(self.input, filename)
        _atomic_json(path, payload)
        self.register_artifact(path, "input_parameters", "USER-OVERRIDE")
        return path, payload

    def register_artifact(self, path, kind, evidence_badge=None, metadata=None):
        absolute = os.path.abspath(path)
        try:
            relative = os.path.relpath(absolute, self.root)
            if relative.startswith(".."):
                relative = absolute
        except ValueError:
            relative = absolute
        records = self.manifest.setdefault("artifacts", [])
        record = {
            "kind": str(kind),
            "path": relative.replace("\\", "/"),
            "exists": os.path.isfile(absolute),
            "size_bytes": os.path.getsize(absolute) if os.path.isfile(absolute) else 0,
        }
        if evidence_badge:
            record["evidence_badge"] = str(evidence_badge)
        if metadata:
            record["metadata"] = metadata
        records[:] = [item for item in records
                      if not (item.get("kind") == record["kind"] and
                              item.get("path") == record["path"])]
        records.append(record)
        self.save_manifest()
        return record

    def scan_artifacts(self):
        mapping = {
            "input": "input",
            "generated": "generated",
            "model": "abaqus_model",
            "jobs": "solver_file",
            "screenshots": "screenshot",
            "reports": "report",
            "logs": "log",
        }
        for dirname, kind in mapping.items():
            root = getattr(self, dirname)
            for current, _dirs, files in os.walk(root):
                for filename in sorted(files):
                    self.register_artifact(os.path.join(current, filename), kind)
        return list(self.manifest.get("artifacts", []))

    def relative(self, path):
        return os.path.relpath(os.path.abspath(path), self.root).replace("\\", "/")

    def expected_paths(self, model_name=None):
        model = sanitize_name(model_name or self.manifest.get("model_name"), "PARAM_MODEL")
        return {
            "params": os.path.join(self.input, "params.json"),
            "audit_json": os.path.join(self.generated, "PARAM_BUILD_AUDIT.json"),
            "audit_text": os.path.join(self.generated, "PARAM_BUILD_AUDIT.txt"),
            "build_result": os.path.join(self.generated, "BUILD_RESULT.json"),
            "cae": os.path.join(self.model, model + ".cae"),
            "report_tex": os.path.join(self.reports, "report.tex"),
            "report_pdf": os.path.join(self.reports, "report.pdf"),
            "abaqus_log": os.path.join(self.logs, "abaqus.log"),
        }
