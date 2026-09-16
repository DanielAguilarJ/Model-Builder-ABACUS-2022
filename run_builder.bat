@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Convenience launcher for Model Builder 4.2.
REM It never launches historical dist or the protected ModelBuilder_4.1 release.
if exist "release\ModelBuilder_4.2\ModelBuilder.exe" (
    start "" "release\ModelBuilder_4.2\ModelBuilder.exe"
    exit /b 0
)

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] The clean ModelBuilder_4.2 release and Python launcher are absent.
    echo Build 4.2 with make_exe.bat or install Python 3.9+ with Tkinter.
    echo Protected ModelBuilder_4.1 artifacts are intentionally not used as fallback.
    exit /b 1
)

py -3 -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo [ERROR] Source mode requires Python 3.9 or newer with Tkinter.
    exit /b 1
)

py -3 model_builder_gui.py
exit /b %ERRORLEVEL%
