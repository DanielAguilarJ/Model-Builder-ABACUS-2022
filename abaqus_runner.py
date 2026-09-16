# -*- coding: utf-8 -*-
"""Safe subprocess adapter for launching the Model Builder Abaqus engine."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import threading
import time


class AbaqusRunResult(object):
    def __init__(self, return_code, command, seconds, log_path, cancelled=False):
        self.return_code = int(return_code)
        self.command = list(command)
        self.seconds = float(seconds)
        self.log_path = log_path
        self.cancelled = bool(cancelled)

    @property
    def ok(self):
        return self.return_code == 0 and not self.cancelled


def detect_abaqus():
    """Return the first plausible Abaqus launcher without executing it."""
    for name in ("abaqus", "abq2026", "abq2025", "abq2024", "abq2023",
                 "abq2022", "abq2021", "abq2020"):
        hit = shutil.which(name)
        if hit:
            return os.path.abspath(hit)
    names = ("abaqus.bat", "abq2026.bat", "abq2025.bat", "abq2024.bat",
             "abq2023.bat", "abq2022.bat", "abq2021.bat", "abq2020.bat")
    bases = (r"C:\SIMULIA\Commands", r"C:\SIMULIA",
             r"C:\Program Files\SIMULIA", r"C:\Program Files\Dassault Systemes")
    for base in bases:
        for name in names:
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                return candidate
    for base in bases:
        if not os.path.isdir(base):
            continue
        for pattern in ("**/abaqus.bat", "**/abq20*.bat"):
            hits = glob.glob(os.path.join(base, pattern), recursive=True)
            if hits:
                return os.path.abspath(sorted(hits)[-1])
    return "abaqus"


def _reject_control_characters(values):
    for value in values:
        if "\r" in value or "\n" in value or "\x00" in value:
            raise ValueError("Command arguments may not contain control characters.")


def build_abaqus_command(abaqus_command, engine_path, params_path):
    """Build an argv list. ``shell=True`` is deliberately never used.

    Windows batch launchers require cmd.exe, so they are passed as a quoted
    command line to ``cmd /d /s /c`` while Popen itself remains shell-free.
    """
    abaqus_command = str(abaqus_command or "abaqus").strip().strip('"')
    engine_path = os.path.abspath(engine_path)
    params_path = os.path.abspath(params_path)
    values = [abaqus_command, engine_path, params_path]
    _reject_control_characters(values)
    args = [abaqus_command, "cae", "noGUI=" + engine_path, "--", params_path]
    suffix = os.path.splitext(abaqus_command)[1].lower()
    if os.name == "nt" and (suffix in (".bat", ".cmd") or
                             not os.path.splitext(abaqus_command)[1]):
        comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        return [comspec, "/d", "/s", "/c", subprocess.list2cmdline(args)]
    return args


class SubprocessRunner(object):
    """One cancellable Abaqus run whose cwd is always the project's jobs dir."""

    def __init__(self, abaqus_command=None):
        self.abaqus_command = abaqus_command or detect_abaqus()
        self._process = None
        self._lock = threading.Lock()
        self._cancelled = False

    @property
    def running(self):
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def run(self, workspace, engine_path, params_path, on_output=None):
        engine_path = os.path.abspath(engine_path)
        params_path = os.path.abspath(params_path)
        if not os.path.isfile(engine_path):
            raise FileNotFoundError("Abaqus engine not found: %s" % engine_path)
        if not os.path.isfile(params_path):
            raise FileNotFoundError("Parameter JSON not found: %s" % params_path)
        workspace.ensure_layout()
        command = build_abaqus_command(self.abaqus_command, engine_path, params_path)
        log_path = os.path.join(workspace.logs, "abaqus.log")
        environment = os.environ.copy()
        environment["MODEL_BUILDER_PROJECT_ROOT"] = workspace.root
        environment["MODEL_BUILDER_ENGINE_PATH"] = engine_path
        environment["MODEL_BUILDER_RUNTIME_DIR"] = os.path.dirname(engine_path)
        environment["MODEL_BUILDER_PARAMS_PATH"] = params_path
        environment["PYTHONIOENCODING"] = "utf-8"
        started = time.time()
        self._cancelled = False
        workspace.set_status("RUNNING", "Abaqus model generation started",
                             started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        with open(log_path, "w", encoding="utf-8", errors="replace",
                  newline="\n") as log:
            log.write("COMMAND: %s\n" % subprocess.list2cmdline(command))
            log.write("WORKDIR: %s\n\n" % workspace.jobs)
            log.flush()
            process = subprocess.Popen(
                command,
                cwd=workspace.jobs,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
                shell=False,
                creationflags=creationflags,
            )
            with self._lock:
                self._process = process
            assert process.stdout is not None
            for line in iter(process.stdout.readline, ""):
                log.write(line)
                log.flush()
                if on_output:
                    on_output(line)
            process.stdout.close()
            return_code = process.wait()
        with self._lock:
            self._process = None
        seconds = time.time() - started
        status = "CANCELLED" if self._cancelled else (
            "ABAQUS_COMPLETED" if return_code == 0 else "FAILED")
        workspace.set_status(
            status,
            "Abaqus exited with code %d" % return_code,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            return_code=return_code,
            elapsed_seconds=round(seconds, 3),
            command=command,
        )
        workspace.register_artifact(log_path, "abaqus_log")
        return AbaqusRunResult(return_code, command, seconds, log_path,
                               self._cancelled)

    def cancel(self):
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return False
        self._cancelled = True
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                check=False,
            )
        else:
            process.terminate()
        return True
