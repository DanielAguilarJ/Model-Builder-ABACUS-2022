# -*- coding: utf-8 -*-
"""Create a clean, auditable Model Builder 4.2 release from a whitelist.

The historical ``dist`` directory is never read recursively or deleted. Before
packaging, the source snapshot also fingerprints every protected Model Builder
4.1 release file. Publication is permitted only to ModelBuilder_4.2 and fails if
source input or any protected 4.1 artifact changes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import keyjoint_core as core
import model_builder_i18n as i18n

PRODUCT = "Model Builder"
VERSION = "4.2"
SCHEMA_VERSION = 6
RELEASE_DIRNAME = "ModelBuilder_4.2"
PROTECTED_RELEASE_VERSION = "4.1"
PROTECTED_RELEASE_PATHS = (
    "release/ModelBuilder_4.1",
    "release/ModelBuilder_4.1.zip",
    "release/ModelBuilder_4.1.zip.sha256",
)

SOURCE_FILES = {
    "README.md": "README.md",
    "TECHNICAL_TRACEABILITY.md": "TECHNICAL_TRACEABILITY.md",
    "technical_contract.json": "technical_contract.json",
    "params_default.json": "params_default.json",
    "params_fva600_method_a_20lw_nojob.json":
        "params_fva600_method_a_20lw_nojob.json",
    "params_fva600_research_presolve_1lw.json":
        "params_fva600_research_presolve_1lw.json",
}

# Every file that can affect the one-file executable or its released contract.
# Paths are relative to parametric_builder; parent paths stay within the project.
BUILD_INPUT_FILES = (
    "ModelBuilder.spec",
    "version_info.txt",
    "model_builder_gui.py",
    "model_builder_i18n.py",
    "i18n/es.json",
    "i18n/en.json",
    "i18n/de.json",
    "build_parametric_model.py",
    "keyjoint_core.py",
    "din6892_methods.py",
    "fva600_postprocess.py",
    "fva600_matlab.py",
    "fva600_method_a_backend.py",
    "fva600_odb_extract.py",
    "project_workspace.py",
    "abaqus_runner.py",
    "report_generator.py",
    "fva600_d40_v3_nojob.py",
    "params_default.json",
    "params_fva600_method_a_20lw_nojob.json",
    "params_fva600_research_presolve_1lw.json",
    "technical_contract.json",
    "TECHNICAL_TRACEABILITY.md",
    "report_template.tex",
    "README.md",
    "make_release.py",
    "make_exe.bat",
    "run_builder.bat",
    "../src/d40_hex_conical_master.py",
    "../src/d40_hex_conical_master_v3_refined_hex_nojob.py",
    "../sources/shaft_with_keywayyt.py",
)

GENERATED_FILES = {"BUILD_MANIFEST.json", "SHA256SUMS.txt"}
DENIED_SUFFIXES = {
    ".cae", ".odb", ".inp", ".jnl", ".rec", ".lck", ".dat", ".msg",
    ".sta", ".sim", ".prt", ".com", ".py", ".pyc", ".pyo",
}
DENIED_NAMES = {
    "params.json", "PARAM_BUILD_AUDIT.txt", "PARAM_BUILD_AUDIT.json",
    "BUILD_RESULT.json", "abaqus.rpy", "abaqus.rpy.1", "abaqus.rpy.2",
    "source_snapshot.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(path: Path, root: Path) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _source_record(path: Path, project_root: Path) -> dict:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(project_root.resolve())
    except ValueError:
        raise ValueError("Build input escapes the project root: %s" % resolved)
    return {
        "path": relative.as_posix(),
        "size_bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    os.replace(str(temporary), str(path))


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _pyinstaller_version() -> str:
    try:
        from importlib import metadata
        return metadata.version("pyinstaller")
    except Exception:
        return "unknown"


def _protected_release_records(source_root: Path) -> list[dict]:
    """Fingerprint all immutable 4.1 payload, archive, and checksum files."""
    records = []
    for relative in PROTECTED_RELEASE_PATHS:
        target = (source_root / relative).resolve()
        try:
            target.relative_to(source_root.resolve())
        except ValueError:
            raise ValueError("Protected release path escapes source root: %s" % target)
        if target.is_dir():
            files = sorted(
                (item for item in target.rglob("*") if item.is_file()),
                key=lambda item: item.relative_to(source_root).as_posix().lower(),
            )
            if not files:
                raise RuntimeError("Protected release directory is empty: %s" % target)
            records.extend(_record(item, source_root) for item in files)
        elif target.is_file():
            records.append(_record(target, source_root))
        else:
            raise FileNotFoundError("Protected 4.1 artifact is missing: %s" % target)
    records.sort(key=lambda item: item["path"].lower())
    return records


def _verify_protected_release(source_root: Path, snapshot: dict) -> dict:
    protected = snapshot.get("protected_historical_release") or {}
    if (protected.get("version") != PROTECTED_RELEASE_VERSION or
            protected.get("immutable") is not True):
        raise RuntimeError("Source snapshot lacks the immutable 4.1 release guard")
    before = dict((item.get("path"), item)
                  for item in protected.get("files", []))
    current_records = _protected_release_records(source_root)
    current = dict((item["path"], item) for item in current_records)
    if set(before) != set(current):
        added = sorted(set(current) - set(before))
        removed = sorted(set(before) - set(current))
        raise RuntimeError(
            "Protected 4.1 release file set changed; added=%r removed=%r" %
            (added, removed))
    changed = []
    for name in sorted(current):
        old = before[name]
        new = current[name]
        if (old.get("sha256") != new["sha256"] or
                int(old.get("size_bytes", -1)) != new["size_bytes"]):
            changed.append(name)
    if changed:
        raise RuntimeError(
            "Protected 4.1 release changed; publication is forbidden: %s" %
            ", ".join(changed))
    return {
        "version": PROTECTED_RELEASE_VERSION,
        "status": "verified-unchanged",
        "file_count": len(current_records),
        "files": current_records,
    }


def _validate_source_identity(source_root: Path) -> None:
    """Validate release identity and both guarded FVA companion presets.

    This is a source/schema audit only.  It never imports Abaqus, builds a CAE,
    creates a Job, submits a solver, or opens an ODB.
    """
    if core.BUILDER_VERSION != VERSION or core.SCHEMA_VERSION != SCHEMA_VERSION:
        raise RuntimeError(
            "Core identity %s/schema %s does not match release %s/schema %s" %
            (core.BUILDER_VERSION, core.SCHEMA_VERSION, VERSION, SCHEMA_VERSION))
    defaults = _read_json(source_root / "params_default.json")
    if defaults != core.default_params():
        raise RuntimeError("params_default.json differs from keyjoint_core.default_params()")
    catalog_check = i18n.validate_catalogs(str(source_root / "i18n"))
    if tuple(catalog_check["locales"]) != i18n.SUPPORTED_LOCALES:
        raise RuntimeError("Canonical i18n locales are incomplete or reordered")
    if defaults.get("project", {}).get("language") != i18n.DEFAULT_LOCALE:
        raise RuntimeError("Default project language is not Spanish")

    legacy_raw = _read_json(
        source_root / "params_fva600_research_presolve_1lw.json")
    if int(legacy_raw.get("schema_version", -1)) != SCHEMA_VERSION:
        raise RuntimeError("Legacy FVA companion does not use parameter schema 6")
    if legacy_raw.get("project", {}).get("language") not in i18n.SUPPORTED_LOCALES:
        raise RuntimeError("Legacy FVA companion has no supported project.language")
    legacy = core.normalize_params(legacy_raw)
    legacy_derived = core.derive(legacy)
    legacy_errors = core.errors(core.validate(legacy, legacy_derived))
    legacy_backend = ((legacy_derived.get("din6892") or {}).get("realized") or {}).get(
        "realized", {})
    if (legacy_errors or legacy["din6892"].get("method") != "A_FE_VOLUME" or
            legacy["fva_600_iii"].get("variant_id") != "VB1" or
            legacy["fva_600_iii"].get("material_pair") != "C45N_C45N" or
            int(legacy["fva_600_iii"].get("cycles", -1)) != 1 or
            not legacy["fva_600_iii"].get("strict_no_job") or
            legacy.get("analysis", {}).get("create_job") or
            legacy.get("analysis", {}).get("submit") or
            legacy_backend.get("status") != "LEGACY_PARTIAL" or
            legacy_backend.get("creates_job") or
            legacy_backend.get("submits_solver") or
            legacy_backend.get("complete_method_a")):
        raise RuntimeError(
            "Legacy FVA companion is not the guarded VB1/C45/1LW/NOJOB preset")

    connected_raw = _read_json(
        source_root / "params_fva600_method_a_20lw_nojob.json")
    if int(connected_raw.get("schema_version", -1)) != SCHEMA_VERSION:
        raise RuntimeError("Connected FVA companion does not use parameter schema 6")
    if connected_raw.get("project", {}).get("language") not in i18n.SUPPORTED_LOCALES:
        raise RuntimeError("Connected FVA companion has no supported project.language")
    connected = core.normalize_params(connected_raw)
    connected_derived = core.derive(connected)
    connected_errors = core.errors(core.validate(connected, connected_derived))
    connected_cfg = connected.get("fva_600_iii") or {}
    connected_analysis = connected.get("analysis") or {}
    connected_execution = connected_cfg.get("execution") or {}
    connected_matching = connected_cfg.get("mesh_matching") or {}
    connected_models = connected_cfg.get("material_models") or {}
    connected_backend = ((connected_derived.get("din6892") or {}).get(
        "realized") or {}).get("realized", {})
    if (connected_errors or
            connected.get("din6892", {}).get("method") != "A_FE_VOLUME" or
            connected.get("din6892", {}).get("apply_variant_geometry") is not True or
            connected_cfg.get("backend") != "method_a_hybrid_hex_v2" or
            connected_cfg.get("backend_capability") !=
            "METHOD_A_HYBRID_HEX_MATCHED_OPTIONAL_JOB" or
            connected_cfg.get("variant_id") != "VB1" or
            connected_cfg.get("material_pair") != "C45N_C45N" or
            int(connected_cfg.get("cycles", -1)) != 20 or
            int(connected_cfg.get("method_a_min_cycles", -1)) != 10 or
            connected_cfg.get("strict_no_job") is not True or
            connected_analysis.get("enabled") or
            connected_analysis.get("create_job") or
            connected_analysis.get("submit") or
            connected_execution.get("create_job") or
            connected_execution.get("submit_solver") or
            connected_matching.get("required") is not True or
            connected_matching.get("verify_after_meshing") is not True or
            abs(float(connected_matching.get("target_size_mm", 0.0)) - 0.8) > 1.0e-12 or
            abs(float(connected_matching.get("tolerance_mm", 0.0)) - 1.0e-6) > 1.0e-15 or
            connected_models.get("shaft") != "CHABOCHE_LEMAITRE_COMBINED" or
            connected_models.get("hub") != "UML_RAMBERG_OSGOOD" or
            connected_models.get("key") != "ELASTIC_IDEAL_PLASTIC" or
            connected_backend.get("status") != "METHOD_A_HYBRID_HEX_SETUP" or
            connected_backend.get("matching") != "VERIFY_AT_BUILD" or
            connected_backend.get("creates_job") or
            connected_backend.get("submits_solver") or
            connected_backend.get("complete_method_a")):
        raise RuntimeError(
            "Connected FVA companion lost its guarded VB1/C45/20LW/matching/NOJOB identity")

    contract = _read_json(source_root / "technical_contract.json")
    if (contract.get("builder_version") != VERSION or
            int(contract.get("builder_schema", -1)) != SCHEMA_VERSION or
            int(contract.get("contract_version", -1)) != 4):
        raise RuntimeError("technical_contract.json identity is stale")
    policy = contract.get("distribution_policy") or {}
    if (policy.get("release_target") != "release/ModelBuilder_4.2" or
            policy.get("immutable_historical_release") !=
            "release/ModelBuilder_4.1"):
        raise RuntimeError("technical_contract.json release guard is stale")
    required_companions = {
        "README.md", "TECHNICAL_TRACEABILITY.md", "technical_contract.json",
        "params_default.json", "params_fva600_research_presolve_1lw.json",
        "params_fva600_method_a_20lw_nojob.json", "BUILD_MANIFEST.json",
        "SHA256SUMS.txt",
    }
    if not required_companions.issubset(set(policy.get("mandatory_companions") or [])):
        raise RuntimeError(
            "technical_contract.json omits a mandatory 4.2 release companion")
    connected_contract = ((contract.get("fva_catalog") or {}).get(
        "connected_backend") or {})
    contract_matching = connected_contract.get("matching") or {}
    if (connected_contract.get("id") != "method_a_connected_mesh_v1" or
            int(connected_contract.get("minimum_cycles", -1)) != 10 or
            int(connected_contract.get("recommended_cycles", -1)) != 20 or
            connected_contract.get("complete_method_a") is not False or
            contract_matching.get("status_before_build") != "VERIFY_AT_BUILD" or
            abs(float(contract_matching.get("kernel_coordinate_floor_mm", 0.0)) -
                5.0e-5) > 1.0e-15):
        raise RuntimeError(
            "technical_contract.json connected-backend contract is incomplete")


def write_source_snapshot(source_root: Path, output: Path) -> dict:
    source_root = source_root.resolve()
    project_root = source_root.parent.resolve()
    _validate_source_identity(source_root)
    inputs = []
    for relative in BUILD_INPUT_FILES:
        path = (source_root / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError("Required build input is missing: %s" % path)
        inputs.append(_source_record(path, project_root))
    inputs.sort(key=lambda item: item["path"].lower())
    protected_files = _protected_release_records(source_root)
    snapshot = {
        "snapshot_schema": 2,
        "product": PRODUCT,
        "product_version": VERSION,
        "parameter_schema": SCHEMA_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_revision": os.environ.get(
            "MODEL_BUILDER_SOURCE_REVISION", "unrecorded-local"),
        "hash_algorithm": "sha256",
        "inputs": inputs,
        "protected_historical_release": {
            "version": PROTECTED_RELEASE_VERSION,
            "immutable": True,
            "paths": list(PROTECTED_RELEASE_PATHS),
            "files": protected_files,
        },
    }
    _write_json(output.resolve(), snapshot)
    return snapshot


def _verify_source_snapshot(source_root: Path, snapshot_path: Path) -> dict:
    source_root = source_root.resolve()
    project_root = source_root.parent.resolve()
    _validate_source_identity(source_root)
    if not snapshot_path.is_file():
        raise FileNotFoundError("Pre-build source snapshot is missing: %s" % snapshot_path)
    snapshot = _read_json(snapshot_path)
    if (snapshot.get("product_version") != VERSION or
            int(snapshot.get("parameter_schema", -1)) != SCHEMA_VERSION or
            int(snapshot.get("snapshot_schema", -1)) != 2):
        raise RuntimeError("Pre-build source snapshot has the wrong release identity")
    recorded = dict((item.get("path"), item) for item in snapshot.get("inputs", []))
    expected = {}
    for relative in BUILD_INPUT_FILES:
        path = (source_root / relative).resolve()
        current = _source_record(path, project_root)
        expected[current["path"]] = current
    if set(recorded) != set(expected):
        raise RuntimeError("Pre-build source snapshot input set does not match the build")
    changed = []
    for name in sorted(expected):
        before = recorded[name]
        after = expected[name]
        if (before.get("sha256") != after["sha256"] or
                int(before.get("size_bytes", -1)) != after["size_bytes"]):
            changed.append(name)
    if changed:
        raise RuntimeError(
            "Source changed after the pre-build snapshot; rebuild required: %s" %
            ", ".join(changed))
    _verify_protected_release(source_root, snapshot)
    return snapshot


def _safe_reset_release_dir(source_root: Path, output: Path) -> None:
    expected = (source_root / "release" / RELEASE_DIRNAME).resolve()
    protected = (source_root / "release" / "ModelBuilder_4.1").resolve()
    if output.resolve() == protected or protected in output.resolve().parents:
        raise ValueError("Refusing to modify protected ModelBuilder_4.1 artifacts")
    if output.resolve() != expected:
        raise ValueError(
            "Refusing to clean an unexpected output directory. Expected: %s" % expected)
    if output.exists():
        shutil.rmtree(str(output))
    output.mkdir(parents=True)


def _run_packaged_self_test(executable: Path) -> dict:
    started = dt.datetime.now(dt.timezone.utc)
    completed = subprocess.run(
        [str(executable), "--self-test"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        check=False,
    )
    elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
    output = completed.stdout.decode("utf-8", errors="replace")[-4000:]
    if completed.returncode != 0:
        raise RuntimeError(
            "Packaged self-test failed with code %d:\n%s" %
            (completed.returncode, output))
    return {
        "status": "passed",
        "return_code": completed.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "scope": (
            "Model Builder 4.2/schema 6 identity and 5->6 migration; DIN 6892/FVA "
            "catalogs and golden calculations; CSV postprocessing; six versioned "
            "mesh templates; packaged engine/core/defaults/contract; canonical "
            "Spanish/English/German catalogs and trilingual reports. Does not "
            "start Abaqus, run a solver, or compile LaTeX"
        ),
    }


def _copy_whitelist(source_root: Path, executable: Path, output: Path) -> None:
    shutil.copy2(str(executable), str(output / "ModelBuilder.exe"))
    for source_name, target_name in SOURCE_FILES.items():
        source = source_root / source_name
        if not source.is_file():
            raise FileNotFoundError("Required release input is missing: %s" % source)
        shutil.copy2(str(source), str(output / target_name))


def _verify_whitelist(output: Path) -> None:
    expected = {"ModelBuilder.exe"} | set(SOURCE_FILES.values()) | GENERATED_FILES
    actual = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*") if path.is_file()
    }
    unexpected = sorted(actual - expected)
    missing = sorted(expected - actual)
    denied = sorted(
        name for name in actual
        if Path(name).suffix.lower() in DENIED_SUFFIXES or Path(name).name in DENIED_NAMES
    )
    if unexpected or missing or denied:
        raise RuntimeError(
            "Release whitelist failure; unexpected=%r missing=%r denied=%r" %
            (unexpected, missing, denied))


def create_release(source_root: Path, executable: Path, output: Path,
                   snapshot_path: Path) -> dict:
    source_root = source_root.resolve()
    executable = executable.resolve()
    output = output.resolve()
    if not executable.is_file():
        raise FileNotFoundError("Fresh ModelBuilder.exe was not found: %s" % executable)

    snapshot = _verify_source_snapshot(source_root, snapshot_path.resolve())
    self_test = _run_packaged_self_test(executable)
    _safe_reset_release_dir(source_root, output)
    _copy_whitelist(source_root, executable, output)
    protected_check = _verify_protected_release(source_root, snapshot)

    payload_files = sorted(
        (path for path in output.iterdir() if path.is_file()),
        key=lambda item: item.name.lower(),
    )
    manifest = {
        "manifest_schema": 3,
        "product": PRODUCT,
        "product_version": VERSION,
        "parameter_schema": SCHEMA_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "build_environment": {
            "python": platform.python_version(),
            "python_architecture": platform.architecture()[0],
            "platform": platform.platform(),
            "pyinstaller": _pyinstaller_version(),
            "source_revision": snapshot.get("source_revision", "unrecorded-local"),
        },
        "build_provenance": {
            "snapshot_created_at_utc": snapshot.get("created_at_utc"),
            "hash_algorithm": "sha256",
            "source_inputs": snapshot.get("inputs", []),
            "packaged_executable": _record(output / "ModelBuilder.exe", output),
            "verified_unchanged_after_build": True,
            "protected_historical_release": protected_check,
        },
        "validation": {
            "packaged_self_test": self_test,
            "abaqus_integration": {
                "status": "no-4.2-solver-run",
                "runtime_compatibility": "Abaqus 2022 / Python 2.7",
                "historical_4_1_nojob_cases": [
                    "D40 Form A AUTO_BALANCED linear",
                    "D25 Form B AUTO_BALANCED linear",
                    "D50 Form AB QUADRATIC_ACCURACY",
                    "D40 tapered FAST_PREVIEW with Bushing",
                ],
                "evidence_bundled": False,
                "limitation": (
                    "Historical 4.1 NOJOB regressions support the inherited geometry/"
                    "mesh foundation. They are not relabelled as a 4.2 solver run or "
                    "exact FVA specimen validation"
                ),
            },
        },
        "distribution_policy": {
            "whitelist_only": True,
            "release_target": RELEASE_DIRNAME,
            "protected_release_4_1_verified_unchanged": True,
            "abaqus_and_latex_not_bundled": True,
            "licensed_din_fva_documents_not_bundled": True,
            "historical_dist_not_read_or_modified": True,
            "run_specific_validation_artifacts_not_bundled": True,
        },
        "files": [_record(path, output) for path in payload_files],
    }
    manifest_path = output / "BUILD_MANIFEST.json"
    _write_json(manifest_path, manifest)

    checksum_targets = sorted(
        (path for path in output.iterdir() if path.is_file()),
        key=lambda item: item.name.lower(),
    )
    sums_path = output / "SHA256SUMS.txt"
    with sums_path.open("w", encoding="ascii", newline="\n") as stream:
        for path in checksum_targets:
            stream.write("%s  %s\n" % (_sha256(path), path.name))

    _verify_whitelist(output)

    zip_path = output.parent / (output.name + ".zip")
    if zip_path.exists():
        zip_path.unlink()
    archive = Path(shutil.make_archive(
        str(output.parent / output.name),
        "zip",
        root_dir=str(output.parent),
        base_dir=output.name,
    ))
    zip_sum_path = Path(str(archive) + ".sha256")
    with zip_sum_path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("%s  %s\n" % (_sha256(archive), archive.name))

    final_protected_check = _verify_protected_release(source_root, snapshot)
    result = {
        "release_directory": str(output),
        "zip": str(archive),
        "zip_checksum_file": str(zip_sum_path),
        "zip_sha256": _sha256(archive),
        "zip_size_bytes": archive.stat().st_size,
        "executable_sha256": _sha256(output / "ModelBuilder.exe"),
        "executable_size_bytes": (output / "ModelBuilder.exe").stat().st_size,
        "file_count": len([path for path in output.iterdir() if path.is_file()]),
        "source_input_count": len(snapshot.get("inputs", [])),
        "protected_4_1": final_protected_check,
        "self_test": self_test,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main() -> int:
    source_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-source-snapshot",
        help="Write guarded source and protected-4.1 fingerprint JSON, then exit",
    )
    parser.add_argument("--exe", help="Freshly built ModelBuilder.exe")
    parser.add_argument("--source-snapshot", help="Pre-build snapshot to verify")
    parser.add_argument(
        "--output",
        default=str(source_root / "release" / RELEASE_DIRNAME),
        help="Must be the guarded release/ModelBuilder_4.2 directory",
    )
    args = parser.parse_args()
    if args.write_source_snapshot:
        snapshot = write_source_snapshot(
            source_root, Path(args.write_source_snapshot))
        print(json.dumps({
            "snapshot": args.write_source_snapshot,
            "inputs": len(snapshot["inputs"]),
            "protected_4_1_files": len(
                snapshot["protected_historical_release"]["files"]),
            "status": "created",
        }, sort_keys=True))
        return 0
    if not args.exe or not args.source_snapshot:
        parser.error("--exe and --source-snapshot are required for publication")
    create_release(source_root, Path(args.exe), Path(args.output),
                   Path(args.source_snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
