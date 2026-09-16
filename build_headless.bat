@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM  LEGACY FLAT-OUTPUT REPRODUCTION ONLY
REM
REM  This bypasses the v4 ProjectWorkspace/SubprocessRunner flow. Abaqus may
REM  write CAE, audit, replay and solver files beside the source or output_dir.
REM  It is intentionally excluded from the shareable release.
REM
REM  Supported v4 users should run ModelBuilder.exe so every execution receives
REM  project.json plus input/generated/model/jobs/screenshots/reports/logs.
REM ============================================================

if /I not "%~1"=="--legacy-flat" (
    echo [BLOCKED] This launcher uses the legacy flat-output path.
    echo.
    echo Use ModelBuilder.exe for isolated v4 projects.
    echo To reproduce an old flat run explicitly:
    echo   build_headless.bat --legacy-flat params_default.json
    exit /b 2
)

set "PARAMS=%~2"
if not defined PARAMS set "PARAMS=params_default.json"
if not exist "%PARAMS%" (
    echo [ERROR] Parameter file not found: %PARAMS%
    echo Copy and edit params_default.json explicitly; no file is copied silently.
    exit /b 1
)

where abaqus >nul 2>nul
if errorlevel 1 (
    echo [ERROR] abaqus was not found on PATH.
    echo Use the v4 GUI to browse to the full abaqus.bat or abq20xx.bat path.
    exit /b 1
)

echo [WARNING] Running legacy flat-output mode with: %PARAMS%
abaqus cae noGUI=build_parametric_model.py -- "%PARAMS%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [ERROR] Abaqus exited with code %RC%.
exit /b %RC%
