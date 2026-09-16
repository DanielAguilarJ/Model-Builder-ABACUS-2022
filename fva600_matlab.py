# -*- coding: utf-8 -*-
"""Auditable optional MATLAB companion for FVA 600 III Method A.

This Python-3-only module exports the already validated external opening CSV
and its authoritative Python post-processing result.  ``EXPORT`` only creates
a deterministic bundle.  ``RUN`` additionally invokes MATLAB with an argument
list, ``shell=False`` and a finite timeout.  MATLAB is always a numerical
cross-check: its result never replaces the Python value used by Model Builder.
"""
from __future__ import annotations

import copy
import errno
import hashlib
import json
import math
import os
import re
import subprocess

import fva600_postprocess as fva_postprocess

BUNDLE_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 1
INTEGRATION_VERSION = "fva600-matlab-1.0"
MODES = ("OFF", "EXPORT", "RUN")
ENTRY_FUNCTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
DEFAULT_ABS_TOLERANCE = 1.0e-10
DEFAULT_REL_TOLERANCE = 1.0e-9


class MatlabIntegrationError(ValueError):
    """Raised when a MATLAB exchange request is structurally invalid."""


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_text(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    os.replace(temporary, path)


def _json_text(payload):
    return json.dumps(
        payload, indent=2, sort_keys=True, ensure_ascii=False,
        allow_nan=False) + "\n"


def _atomic_json(path, payload):
    _atomic_text(path, _json_text(payload))
    return path


def _file_record(path, bundle_dir, role):
    absolute = os.path.abspath(path)
    return {
        "path": os.path.relpath(absolute, bundle_dir).replace("\\", "/"),
        "role": str(role),
        "size_bytes": os.path.getsize(absolute),
        "sha256": _sha256(absolute),
    }


def _number(value, label, positive=False, allow_zero=False):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise MatlabIntegrationError("%s must be numeric" % label)
    if not math.isfinite(number):
        raise MatlabIntegrationError("%s must be finite" % label)
    if positive and (number < 0.0 if allow_zero else number <= 0.0):
        raise MatlabIntegrationError("%s must be %s" % (
            label, "non-negative" if allow_zero else "positive"))
    return number


def validate_entry_function(value):
    """Return a safe MATLAB function identifier or raise.

    Limiting the value to one MATLAB identifier prevents command injection in
    the ``-batch`` expression and guarantees that its file remains in-bundle.
    """
    entry = str(value or "").strip()
    if not ENTRY_FUNCTION_RE.match(entry):
        raise MatlabIntegrationError(
            "matlab.entry_function must be an ASCII MATLAB identifier "
            "of at most 63 characters")
    return entry


def normalize_config(config):
    config = copy.deepcopy(config or {})
    mode = str(config.get("mode", "OFF") or "OFF").strip().upper()
    if mode not in MODES:
        raise MatlabIntegrationError("matlab.mode must be OFF, EXPORT or RUN")
    entry = validate_entry_function(
        config.get("entry_function", "fva600_method_a_bundle"))
    try:
        timeout = float(config.get("timeout_s", 300) or 0)
    except (TypeError, ValueError):
        raise MatlabIntegrationError("matlab.timeout_s must be numeric")
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise MatlabIntegrationError("matlab.timeout_s must be positive")
    executable = str(config.get("executable", "matlab") or "").strip()
    if len(executable) >= 2 and executable[0] == executable[-1] == '"':
        executable = executable[1:-1]
    if mode == "RUN" and not executable:
        raise MatlabIntegrationError(
            "matlab.executable is required when matlab.mode=RUN")
    if "\x00" in executable or "\r" in executable or "\n" in executable:
        raise MatlabIntegrationError("matlab.executable contains invalid characters")
    return {
        "mode": mode,
        "executable": executable,
        "timeout_s": timeout,
        "bundle_dir": str(config.get("bundle_dir", "") or "").strip(),
        "entry_function": entry,
        "keep_bundle": bool(config.get("keep_bundle", True)),
    }


def _validate_python_result(result, csv_path):
    if not isinstance(result, dict):
        raise MatlabIntegrationError("Python postprocess result must be an object")
    if int(result.get("result_schema_version", -1)) != 1:
        raise MatlabIntegrationError("Unsupported Python postprocess result schema")
    if result.get("postprocessor_version") != fva_postprocess.POSTPROCESSOR_VERSION:
        raise MatlabIntegrationError("Python postprocessor version is not supported")
    integration = result.get("integration") or {}
    volume = result.get("volume") or {}
    inputs = volume.get("inputs") or {}
    required = {
        "delta_volume_mm3": integration.get("delta_volume_mm3"),
        "V_theo_mm3": volume.get("V_theo_mm3"),
        "v": volume.get("v"),
        "v_crit": volume.get("v_crit"),
        "ltr_mm": inputs.get("ltr_mm"),
        "t1tr_mm": inputs.get("t1tr_mm"),
        "UPF_um": inputs.get("UPF_um"),
    }
    for label, value in required.items():
        required[label] = _number(
            value, "python_result.%s" % label,
            positive=label not in ("delta_volume_mm3", "v"),
            allow_zero=label in ("delta_volume_mm3", "v"))
    provenance = result.get("provenance") or {}
    absolute = os.path.abspath(os.path.expanduser(os.path.expandvars(csv_path)))
    if not os.path.isfile(absolute):
        raise MatlabIntegrationError("Source CSV does not exist: %s" % absolute)
    actual_hash = _sha256(absolute)
    expected_hash = str(provenance.get("sha256", "") or "")
    if expected_hash and actual_hash.lower() != expected_hash.lower():
        raise MatlabIntegrationError(
            "Source CSV SHA-256 differs from the authoritative Python result")
    expected_size = provenance.get("size_bytes")
    if expected_size is not None and os.path.getsize(absolute) != int(expected_size):
        raise MatlabIntegrationError(
            "Source CSV size differs from the authoritative Python result")
    required["criterion_met"] = bool(volume.get("criterion_met"))
    required["source_csv"] = absolute
    required["source_sha256"] = actual_hash
    required["source_size_bytes"] = os.path.getsize(absolute)
    return required


def _canonical_csv(source_path, target_path):
    _absolute, _headers, rows = fva_postprocess.read_opening_csv(source_path)
    lines = ["x_mm,z_mm,opening_um"]
    for item in sorted(rows, key=lambda row: (row["x_mm"], row["z_mm"])):
        lines.append("%.17g,%.17g,%.17g" % (
            float(item["x_mm"]), float(item["z_mm"]),
            float(item["opening_um"])))
    _atomic_text(target_path, "\n".join(lines) + "\n")
    return len(rows)


def _matlab_source(entry_function):
    template = r'''function __ENTRY__()
% FVA 600 III Method A cross-check generated by Model Builder 4.2.
% Python remains authoritative; this function only reproduces the integration.
root_dir = fileparts(mfilename('fullpath'));
result_path = fullfile(root_dir, 'matlab_result.json');
try
    input_data = jsondecode(fileread(fullfile(root_dir, 'method_a_input.json')));
    table_data = readtable(fullfile(root_dir, 'opening.csv'));
    required = {'x_mm', 'z_mm', 'opening_um'};
    for required_index = 1:numel(required)
        if ~ismember(required{required_index}, table_data.Properties.VariableNames)
            error('ModelBuilder:MissingColumn', ...
                'opening.csv is missing column %s', required{required_index});
        end
    end
    x = double(table_data.x_mm(:));
    z = double(table_data.z_mm(:));
    opening_um = double(table_data.opening_um(:));
    if numel(x) < 4 || numel(x) ~= numel(z) || numel(x) ~= numel(opening_um)
        error('ModelBuilder:InvalidGrid', 'At least four complete rows are required');
    end
    if any(~isfinite(x)) || any(~isfinite(z)) || any(~isfinite(opening_um))
        error('ModelBuilder:NonFinite', 'The opening grid must contain finite values');
    end
    if any(opening_um < 0)
        error('ModelBuilder:NegativeOpening', 'opening_um cannot be negative');
    end
    xs = sort(unique(x));
    zs = sort(unique(z));
    if numel(xs) < 2 || numel(zs) < 2 || numel(x) ~= numel(xs) * numel(zs)
        error('ModelBuilder:NonRectangular', 'The opening grid must be rectangular');
    end
    opening_mm = nan(numel(zs), numel(xs));
    for point_index = 1:numel(x)
        ix = find(xs == x(point_index), 1);
        iz = find(zs == z(point_index), 1);
        if ~isnan(opening_mm(iz, ix))
            error('ModelBuilder:DuplicatePoint', 'Duplicate opening-grid coordinate');
        end
        opening_mm(iz, ix) = opening_um(point_index) / 1000.0;
    end
    if any(isnan(opening_mm(:)))
        error('ModelBuilder:MissingPoint', 'The opening grid has missing coordinates');
    end
    delta_volume_mm3 = 0.0;
    for ix = 1:(numel(xs) - 1)
        dx = xs(ix + 1) - xs(ix);
        for iz = 1:(numel(zs) - 1)
            dz = zs(iz + 1) - zs(iz);
            corner_mean = 0.25 * (...
                opening_mm(iz, ix) + opening_mm(iz, ix + 1) + ...
                opening_mm(iz + 1, ix) + opening_mm(iz + 1, ix + 1));
            delta_volume_mm3 = delta_volume_mm3 + corner_mean * dx * dz;
        end
    end
    V_theo_mm3 = double(input_data.ltr_mm) * ...
        double(input_data.t1tr_mm) * double(input_data.UPF_um) / 1000.0;
    v = delta_volume_mm3 / V_theo_mm3;
    output = struct();
    output.result_schema_version = 1;
    output.producer = 'MATLAB';
    output.integration_version = 'fva600-matlab-1.0';
    output.status = 'OK';
    output.source_sha256 = input_data.source_sha256;
    output.delta_volume_mm3 = delta_volume_mm3;
    output.V_theo_mm3 = V_theo_mm3;
    output.v = v;
    output.v_crit = double(input_data.v_crit);
    output.criterion_met = (v <= output.v_crit);
    output.point_count = numel(x);
    write_json(result_path, output);
catch exception
    failure = struct();
    failure.result_schema_version = 1;
    failure.producer = 'MATLAB';
    failure.integration_version = 'fva600-matlab-1.0';
    failure.status = 'ERROR';
    failure.identifier = exception.identifier;
    failure.message = exception.message;
    write_json(result_path, failure);
    rethrow(exception);
end
end

function write_json(path, payload)
fid = fopen(path, 'w');
if fid < 0
    error('ModelBuilder:WriteFailed', 'Could not write %s', path);
end
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid, jsonencode(payload), 'char');
fwrite(fid, sprintf('\n'), 'char');
end
'''
    return template.replace("__ENTRY__", entry_function)


def _resolve_bundle_dir(config, source_csv, python_result, default_parent):
    explicit = config["bundle_dir"]
    base = os.path.abspath(default_parent or os.path.dirname(source_csv))
    if explicit:
        expanded = os.path.expanduser(os.path.expandvars(explicit))
        bundle = expanded if os.path.isabs(expanded) else os.path.join(base, expanded)
        return os.path.abspath(bundle)
    result_fingerprint = hashlib.sha256(
        (config["entry_function"] + "\n" + _json_text(python_result)).encode("utf-8")
    ).hexdigest()
    source_hash = _sha256(source_csv)
    bundle_id = hashlib.sha256(
        (source_hash + result_fingerprint).encode("ascii")).hexdigest()[:12]
    return os.path.join(base, "fva600_method_a_%s" % bundle_id)


def _write_manifest(bundle_dir, manifest):
    path = os.path.join(bundle_dir, "manifest.json")
    _atomic_json(path, manifest)
    return path


def export_bundle(config, csv_path, python_result, default_parent=None):
    """Create an auditable MATLAB bundle without executing MATLAB."""
    normalized = normalize_config(config)
    if normalized["mode"] == "OFF":
        raise MatlabIntegrationError("OFF mode does not export a bundle")
    values = _validate_python_result(python_result, csv_path)
    source_csv = values["source_csv"]
    bundle_dir = _resolve_bundle_dir(
        normalized, source_csv, python_result, default_parent)
    if os.path.exists(bundle_dir) and not os.path.isdir(bundle_dir):
        raise MatlabIntegrationError("MATLAB bundle path is not a directory: %s" % bundle_dir)
    os.makedirs(bundle_dir, exist_ok=True)

    entry_name = normalized["entry_function"] + ".m"
    known_runtime = ("matlab_result.json", "matlab_stdout.log")
    for filename in known_runtime:
        stale = os.path.join(bundle_dir, filename)
        if os.path.isfile(stale):
            os.remove(stale)

    canonical_path = os.path.join(bundle_dir, "opening.csv")
    point_count = _canonical_csv(source_csv, canonical_path)
    input_payload = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "integration_version": INTEGRATION_VERSION,
        "source_sha256": values["source_sha256"],
        "source_size_bytes": values["source_size_bytes"],
        "point_count": point_count,
        "ltr_mm": values["ltr_mm"],
        "t1tr_mm": values["t1tr_mm"],
        "UPF_um": values["UPF_um"],
        "v_crit": values["v_crit"],
        "python_authoritative": True,
    }
    input_path = os.path.join(bundle_dir, "method_a_input.json")
    python_path = os.path.join(bundle_dir, "python_result.json")
    script_path = os.path.join(bundle_dir, entry_name)
    _atomic_json(input_path, input_payload)
    _atomic_json(python_path, python_result)
    _atomic_text(script_path, _matlab_source(normalized["entry_function"]))

    input_records = {}
    for path, role in (
            (canonical_path, "canonical_opening_csv"),
            (input_path, "method_a_input"),
            (python_path, "authoritative_python_result"),
            (script_path, "matlab_entry_function")):
        record = _file_record(path, bundle_dir, role)
        input_records[record["path"]] = record
    manifest = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "integration_version": INTEGRATION_VERSION,
        "producer": "Model Builder 4.2",
        "mode": normalized["mode"],
        "entry_function": normalized["entry_function"],
        "python_authoritative": True,
        "authority_note": (
            "MATLAB is an optional cross-check and never replaces the "
            "authoritative Python Method-A result."),
        "source": {
            "path": source_csv,
            "size_bytes": values["source_size_bytes"],
            "sha256": values["source_sha256"],
        },
        "inputs": input_records,
        "runtime": {"executed": False, "status": "NOT_EXECUTED"},
        "outputs": {},
    }
    manifest_path = _write_manifest(bundle_dir, manifest)
    return {
        "config": normalized,
        "values": values,
        "bundle_dir": bundle_dir,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "paths": {
            "opening_csv": canonical_path,
            "method_a_input": input_path,
            "python_result": python_path,
            "matlab_script": script_path,
            "matlab_result": os.path.join(bundle_dir, "matlab_result.json"),
            "matlab_log": os.path.join(bundle_dir, "matlab_stdout.log"),
        },
    }


def _read_matlab_result(path):
    if not os.path.isfile(path):
        return None, "RESULT_MISSING", "MATLAB did not create matlab_result.json"
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, ValueError) as exc:
        return None, "RESULT_INVALID", "Invalid matlab_result.json: %s" % exc
    if not isinstance(payload, dict):
        return None, "RESULT_INVALID", "matlab_result.json must contain an object"
    if int(payload.get("result_schema_version", -1)) != RESULT_SCHEMA_VERSION:
        return None, "RESULT_INVALID", "Unsupported MATLAB result schema"
    if payload.get("producer") != "MATLAB" or payload.get("status") != "OK":
        return payload, "RESULT_ERROR", str(payload.get("message") or
                                             "MATLAB reported an error")
    for key in ("delta_volume_mm3", "V_theo_mm3", "v", "v_crit"):
        try:
            value = float(payload.get(key))
        except (TypeError, ValueError):
            return payload, "RESULT_INVALID", "%s is not numeric" % key
        if not math.isfinite(value):
            return payload, "RESULT_INVALID", "%s is not finite" % key
    return payload, None, ""


def compare_results(python_result, matlab_result,
                    absolute_tolerance=DEFAULT_ABS_TOLERANCE,
                    relative_tolerance=DEFAULT_REL_TOLERANCE):
    """Compare MATLAB output to Python while retaining Python authority."""
    python_volume = python_result.get("volume") or {}
    python_integration = python_result.get("integration") or {}
    expected = {
        "delta_volume_mm3": float(python_integration["delta_volume_mm3"]),
        "V_theo_mm3": float(python_volume["V_theo_mm3"]),
        "v": float(python_volume["v"]),
        "v_crit": float(python_volume["v_crit"]),
    }
    quantities = {}
    all_match = True
    for key in sorted(expected):
        python_value = expected[key]
        matlab_value = float(matlab_result[key])
        difference = abs(matlab_value - python_value)
        tolerance = max(
            float(absolute_tolerance),
            float(relative_tolerance) * max(abs(python_value), abs(matlab_value)))
        matches = difference <= tolerance
        all_match = all_match and matches
        quantities[key] = {
            "python": python_value,
            "matlab": matlab_value,
            "absolute_difference": difference,
            "relative_difference": (
                difference / max(abs(python_value), abs(matlab_value))
                if max(abs(python_value), abs(matlab_value)) > 0.0 else 0.0),
            "tolerance": tolerance,
            "matches": matches,
        }
    criterion_matches = (
        bool(python_volume.get("criterion_met")) ==
        bool(matlab_result.get("criterion_met")))
    source_matches = str(matlab_result.get("source_sha256", "")).lower() == str(
        (python_result.get("provenance") or {}).get("sha256", "")).lower()
    all_match = all_match and criterion_matches and source_matches
    return {
        "all_match": all_match,
        "absolute_tolerance": float(absolute_tolerance),
        "relative_tolerance": float(relative_tolerance),
        "criterion_matches": criterion_matches,
        "source_sha256_matches": source_matches,
        "quantities": quantities,
        "python_authoritative": True,
    }


def _finalize_export(exported, status, executed, return_code=None,
                     error_message="", matlab_payload=None, comparison=None,
                     command=None):
    bundle_dir = exported["bundle_dir"]
    paths = exported["paths"]
    manifest = exported["manifest"]
    runtime = {
        "executed": bool(executed),
        "status": status,
        "return_code": return_code,
        "error": str(error_message or ""),
        "command": list(command or []),
        "shell": False if command else None,
        "timeout_s": exported["config"]["timeout_s"],
    }
    manifest["runtime"] = runtime
    outputs = {}
    for path, role in (
            (paths["matlab_result"], "matlab_result"),
            (paths["matlab_log"], "matlab_stdout_log")):
        if os.path.isfile(path):
            record = _file_record(path, bundle_dir, role)
            outputs[record["path"]] = record
    manifest["outputs"] = outputs
    if comparison is not None:
        manifest["comparison"] = comparison
    manifest_path = _write_manifest(bundle_dir, manifest)
    manifest_hash = _sha256(manifest_path)
    artifacts = []
    for record in list(manifest["inputs"].values()) + list(outputs.values()):
        item = copy.deepcopy(record)
        item["absolute_path"] = os.path.join(
            bundle_dir, record["path"].replace("/", os.sep))
        artifacts.append(item)
    artifacts.append({
        "path": "manifest.json",
        "absolute_path": manifest_path,
        "role": "matlab_bundle_manifest",
        "size_bytes": os.path.getsize(manifest_path),
        "sha256": manifest_hash,
    })
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "integration_version": INTEGRATION_VERSION,
        "mode": exported["config"]["mode"],
        "status": status,
        "executed": bool(executed),
        "return_code": return_code,
        "bundle_path": bundle_dir,
        "bundle_retained": True,
        "keep_bundle_requested": exported["config"]["keep_bundle"],
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_hash,
        "entry_function": exported["config"]["entry_function"],
        "command": list(command or []),
        "shell": False if command else None,
        "timeout_s": exported["config"]["timeout_s"],
        "python_authoritative": True,
        "authority_note": (
            "Python remains authoritative; MATLAB is an optional numerical "
            "cross-check only."),
        "comparison": comparison,
        "matlab_result": matlab_payload,
        "error": str(error_message or ""),
        "artifacts": artifacts,
    }


def export_or_run(config, csv_path, python_result, default_parent=None):
    """Apply OFF, EXPORT or RUN and return a persistable structured result.

    Runtime failures (missing executable, timeout, non-zero return code, absent
    or malformed JSON) are returned as statuses so the GUI/report can preserve
    provenance.  Invalid configuration or incompatible source evidence raises
    :class:`MatlabIntegrationError` before execution.
    """
    normalized = normalize_config(config)
    if normalized["mode"] == "OFF":
        return {
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "integration_version": INTEGRATION_VERSION,
            "mode": "OFF",
            "status": "SKIPPED_OFF",
            "executed": False,
            "bundle_path": None,
            "manifest_path": None,
            "manifest_sha256": None,
            "python_authoritative": True,
            "authority_note": (
                "Python remains authoritative; MATLAB exchange was disabled."),
            "comparison": None,
            "error": "",
            "artifacts": [],
        }

    exported = export_bundle(
        normalized, csv_path, python_result, default_parent=default_parent)
    if normalized["mode"] == "EXPORT":
        return _finalize_export(exported, "EXPORTED", False)

    command = [normalized["executable"], "-batch",
               normalized["entry_function"] + "()"]
    log_path = exported["paths"]["matlab_log"]
    return_code = None
    try:
        with open(log_path, "w", encoding="utf-8", newline="\n") as log:
            log.write("Model Builder MATLAB command (shell=False): %r\n" % command)
            log.flush()
            completed = subprocess.run(
                command, cwd=exported["bundle_dir"], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, shell=False,
                timeout=normalized["timeout_s"], check=False)
            return_code = int(completed.returncode)
    except subprocess.TimeoutExpired as exc:
        return _finalize_export(
            exported, "TIMEOUT", True, error_message=str(exc), command=command)
    except OSError as exc:
        missing = getattr(exc, "errno", None) == errno.ENOENT or getattr(
            exc, "winerror", None) in (2, 3)
        return _finalize_export(
            exported, "EXECUTABLE_NOT_FOUND" if missing else "EXECUTION_ERROR",
            True, error_message=str(exc), command=command)

    matlab_payload, result_error, detail = _read_matlab_result(
        exported["paths"]["matlab_result"])
    if return_code != 0:
        return _finalize_export(
            exported, "PROCESS_FAILED", True, return_code=return_code,
            error_message=detail or "MATLAB returned a non-zero exit code",
            matlab_payload=matlab_payload, command=command)
    if result_error:
        return _finalize_export(
            exported, result_error, True, return_code=return_code,
            error_message=detail, matlab_payload=matlab_payload, command=command)
    comparison = compare_results(python_result, matlab_payload)
    status = "COMPLETED_MATCH" if comparison["all_match"] else "COMPLETED_MISMATCH"
    return _finalize_export(
        exported, status, True, return_code=return_code,
        matlab_payload=matlab_payload, comparison=comparison, command=command)


def attach_result_to_params(params, result):
    """Attach exchange metadata without changing the Python Method-A result."""
    if not isinstance(params, dict):
        raise MatlabIntegrationError("params must be an object")
    if not isinstance(result, dict):
        raise MatlabIntegrationError("MATLAB exchange result must be an object")
    if int(result.get("result_schema_version", -1)) != RESULT_SCHEMA_VERSION:
        raise MatlabIntegrationError("Unsupported MATLAB exchange result schema")
    payload = copy.deepcopy(params)
    matlab = payload.setdefault("matlab", {})
    matlab["last_result"] = copy.deepcopy(result)
    return payload


def verify_bundle(result):
    """Re-hash a retained bundle and every manifest input/output record."""
    result = result or {}
    manifest_path = result.get("manifest_path")
    expected_manifest_hash = result.get("manifest_sha256")
    if not manifest_path or not os.path.isfile(manifest_path):
        return {"verified": False, "reason": "MANIFEST_MISSING", "files": {}}
    actual_manifest_hash = _sha256(manifest_path)
    try:
        with open(manifest_path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, ValueError) as exc:
        return {"verified": False, "reason": "MANIFEST_INVALID",
                "error": str(exc), "files": {}}
    bundle_dir = os.path.dirname(os.path.abspath(manifest_path))
    checks = {}
    for group in ("inputs", "outputs"):
        for relative, record in (manifest.get(group) or {}).items():
            path = os.path.abspath(os.path.join(
                bundle_dir, relative.replace("/", os.sep)))
            inside = os.path.commonpath((bundle_dir, path)) == bundle_dir
            exists = inside and os.path.isfile(path)
            size_matches = exists and os.path.getsize(path) == int(
                record.get("size_bytes", -1))
            hash_matches = exists and _sha256(path) == record.get("sha256")
            checks[relative] = {
                "inside_bundle": inside,
                "exists": exists,
                "size_matches": size_matches,
                "sha256_matches": hash_matches,
                "verified": inside and exists and size_matches and hash_matches,
            }
    manifest_matches = actual_manifest_hash == expected_manifest_hash
    return {
        "verified": manifest_matches and all(
            item["verified"] for item in checks.values()),
        "reason": "MATCH" if manifest_matches and all(
            item["verified"] for item in checks.values()) else "BUNDLE_CHANGED",
        "manifest_sha256_matches": manifest_matches,
        "actual_manifest_sha256": actual_manifest_hash,
        "files": checks,
    }
