@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM  Model Builder 4.2 clean release build
REM  - CPython build tools run in a fresh local venv under release_staging
REM  - Python user-site, PYTHONPATH and PYTHONHOME are disabled
REM  - PyInstaller 6.22.2 and hooks 2026.7 are pinned in that venv
REM  - source + immutable 4.1 SHA-256 snapshot precedes the build
REM  - build/work files go to release_staging, never historical dist
REM  - publication is restricted to release\ModelBuilder_4.2
REM  - release\ModelBuilder_4.1* must remain byte-for-byte unchanged
REM  - no Abaqus result or licensed DIN/FVA document is copied
REM ============================================================

set "ROOT=%CD%"
set "STAGE=%ROOT%\release_staging"
set "BUILD_VENV=%STAGE%\build_venv"
set "BUILD_PY=%BUILD_VENV%\Scripts\python.exe"
set "STAGE_EXE=%STAGE%\dist\ModelBuilder.exe"
set "SOURCE_SNAPSHOT=%STAGE%\source_snapshot.json"
set "RELEASE=%ROOT%\release\ModelBuilder_4.2"
set "ZIP=%ROOT%\release\ModelBuilder_4.2.zip"
set "ZIP_SUM=%ROOT%\release\ModelBuilder_4.2.zip.sha256"
set "PROTECTED_41=%ROOT%\release\ModelBuilder_4.1"
set "PROTECTED_41_ZIP=%ROOT%\release\ModelBuilder_4.1.zip"
set "PROTECTED_41_SUM=%ROOT%\release\ModelBuilder_4.1.zip.sha256"

if not exist "%PROTECTED_41%\" (
    echo [ERROR] Protected ModelBuilder_4.1 directory is missing.
    exit /b 1
)
if not exist "%PROTECTED_41_ZIP%" (
    echo [ERROR] Protected ModelBuilder_4.1.zip is missing.
    exit /b 1
)
if not exist "%PROTECTED_41_SUM%" (
    echo [ERROR] Protected ModelBuilder_4.1.zip.sha256 is missing.
    exit /b 1
)

REM Never let a network/profile user-site contaminate the parent interpreter or
REM PyInstaller's isolated child processes. PIP_CONFIG_FILE=NUL also prevents a
REM profile-level pip configuration from redirecting installation into P:.
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONUSERBASE="
set "PYTHONNOUSERSITE=1"
set "PIP_CONFIG_FILE=NUL"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"

set "BOOTSTRAP_PY="
where py >nul 2>nul && set "BOOTSTRAP_PY=py -3"
if not defined BOOTSTRAP_PY (
    where python >nul 2>nul && set "BOOTSTRAP_PY=python"
)
if not defined BOOTSTRAP_PY (
    echo [ERROR] Python 3 was not found on PATH.
    exit /b 1
)

%BOOTSTRAP_PY% -I -c "import struct,sys; raise SystemExit(0 if sys.version_info >= (3,9) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo [ERROR] Packaging requires 64-bit Python 3.9 or newer.
    exit /b 1
)

for %%F in (
    "ModelBuilder.spec"
    "version_info.txt"
    "model_builder_gui.py"
    "model_builder_i18n.py"
    "i18n\es.json"
    "i18n\en.json"
    "i18n\de.json"
    "build_parametric_model.py"
    "keyjoint_core.py"
    "din6892_methods.py"
    "fva600_postprocess.py"
    "fva600_matlab.py"
    "fva600_method_a_backend.py"
    "fva600_odb_extract.py"
    "project_workspace.py"
    "abaqus_runner.py"
    "report_generator.py"
    "fva600_d40_v3_nojob.py"
    "params_default.json"
    "params_fva600_method_a_20lw_nojob.json"
    "params_fva600_research_presolve_1lw.json"
    "technical_contract.json"
    "TECHNICAL_TRACEABILITY.md"
    "report_template.tex"
    "README.md"
    "make_release.py"
    "make_exe.bat"
    "run_builder.bat"
    "..\src\d40_hex_conical_master.py"
    "..\src\d40_hex_conical_master_v3_refined_hex_nojob.py"
    "..\sources\shaft_with_keywayyt.py"
) do (
    if not exist "%%~F" (
        echo [ERROR] Required build input is missing: %%~F
        exit /b 1
    )
)

if exist "%STAGE%" rmdir /s /q "%STAGE%"
if exist "%STAGE%" (
    echo [ERROR] Could not reset release staging: %STAGE%
    exit /b 1
)
mkdir "%STAGE%"
if errorlevel 1 exit /b 1

echo [1/6] Creating isolated local Python environment
%BOOTSTRAP_PY% -I -m venv "%BUILD_VENV%"
if errorlevel 1 (
    echo [ERROR] Could not create the isolated build environment.
    exit /b 1
)
if not exist "%BUILD_PY%" (
    echo [ERROR] Isolated Python was not created: %BUILD_PY%
    exit /b 1
)

echo [2/6] Installing pinned packaging tools locally
"%BUILD_PY%" -I -m pip install --no-input --disable-pip-version-check --only-binary=:all: "pyinstaller==6.22.2" "pyinstaller-hooks-contrib==2026.7"
if errorlevel 1 (
    echo [ERROR] Could not install the pinned packaging tools in the local venv.
    exit /b 1
)

echo [3/6] Verifying isolation and compiling Python sources
"%BUILD_PY%" -I -c "import importlib.metadata as m,site,sys; bad=[p for p in sys.path if str(p).lower().startswith('p:') or str(p).startswith(chr(92)*2)]; assert sys.prefix != sys.base_prefix; assert site.ENABLE_USER_SITE is False; assert m.version('pyinstaller') == '6.22.2'; assert m.version('pyinstaller-hooks-contrib') == '2026.7'; assert not bad,bad; print('Build Python:',sys.executable); print('PyInstaller:',m.version('pyinstaller')); print('PyInstaller hooks:',m.version('pyinstaller-hooks-contrib')); print('User site enabled:',site.ENABLE_USER_SITE); print('Remote sys.path entries:',bad)"
if errorlevel 1 (
    echo [ERROR] Build Python is not isolated from user or remote site-packages.
    exit /b 1
)
"%BUILD_PY%" -I -m py_compile model_builder_gui.py model_builder_i18n.py project_workspace.py abaqus_runner.py report_generator.py make_release.py keyjoint_core.py din6892_methods.py fva600_postprocess.py fva600_matlab.py fva600_method_a_backend.py fva600_odb_extract.py build_parametric_model.py fva600_d40_v3_nojob.py
if errorlevel 1 (
    echo [ERROR] Python source compilation failed.
    exit /b 1
)

echo [4/6] Recording guarded source and immutable 4.1 hashes
"%BUILD_PY%" -s make_release.py --write-source-snapshot "%SOURCE_SNAPSHOT%"
if errorlevel 1 (
    echo [ERROR] Source identity, defaults, contract, preset, or 4.1 guard failed.
    exit /b 1
)
if not exist "%SOURCE_SNAPSHOT%" exit /b 1

echo [5/6] Building ModelBuilder.exe in isolated staging
"%BUILD_PY%" -I -m PyInstaller --noconfirm --clean --distpath "%STAGE%\dist" --workpath "%STAGE%\build" ModelBuilder.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)
if not exist "%STAGE_EXE%" (
    echo [ERROR] Staged ModelBuilder.exe was not produced.
    exit /b 1
)

echo [6/6] Verifying source, protected 4.1, self-test, and 4.2 whitelist
"%BUILD_PY%" -s make_release.py --exe "%STAGE_EXE%" --source-snapshot "%SOURCE_SNAPSHOT%" --output "%RELEASE%"
if errorlevel 1 (
    echo [ERROR] 4.2 publication failed; protected 4.1 must remain unchanged.
    exit /b 1
)

if not exist "%RELEASE%\ModelBuilder.exe" exit /b 1
if not exist "%RELEASE%\BUILD_MANIFEST.json" exit /b 1
if not exist "%RELEASE%\SHA256SUMS.txt" exit /b 1
if not exist "%ZIP%" exit /b 1
if not exist "%ZIP_SUM%" exit /b 1
if not exist "%PROTECTED_41%\" exit /b 1
if not exist "%PROTECTED_41_ZIP%" exit /b 1
if not exist "%PROTECTED_41_SUM%" exit /b 1

echo.
echo ============================================================
echo  CLEAN MODEL BUILDER 4.2 RELEASE CREATED
echo  Build environment: local venv; user-site and remote paths disabled.
for %%F in ("%RELEASE%\ModelBuilder.exe") do echo  EXE: %%~fF  [%%~zF bytes]
echo  DIR: %RELEASE%
echo  ZIP: %ZIP%
echo  SUM: %ZIP_SUM%
echo  PROTECTED: ModelBuilder_4.1 verified unchanged by SHA-256 snapshot.
echo  Share only the 4.2 ZIP or complete 4.2 release directory.
echo ============================================================
exit /b 0
