# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the self-contained Model Builder 4.2 distribution."""
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
PROJECT = ROOT.parent

datas = [
    (str(ROOT / 'build_parametric_model.py'), '.'),
    (str(ROOT / 'keyjoint_core.py'), '.'),
    (str(ROOT / 'din6892_methods.py'), '.'),
    (str(ROOT / 'fva600_postprocess.py'), '.'),
    (str(ROOT / 'fva600_matlab.py'), '.'),
    (str(ROOT / 'fva600_method_a_backend.py'), '.'),
    (str(ROOT / 'fva600_odb_extract.py'), '.'),
    (str(ROOT / 'fva600_d40_v3_nojob.py'), '.'),
    (str(ROOT / 'params_default.json'), '.'),
    (str(ROOT / 'params_fva600_method_a_20lw_nojob.json'), '.'),
    (str(ROOT / 'params_fva600_research_presolve_1lw.json'), '.'),
    (str(ROOT / 'technical_contract.json'), '.'),
    (str(ROOT / 'TECHNICAL_TRACEABILITY.md'), '.'),
    (str(ROOT / 'report_template.tex'), '.'),
    (str(ROOT / 'i18n' / 'es.json'), 'i18n'),
    (str(ROOT / 'i18n' / 'en.json'), 'i18n'),
    (str(ROOT / 'i18n' / 'de.json'), 'i18n'),
    (str(ROOT / 'README.md'), '.'),
    (str(PROJECT / 'src' / 'd40_hex_conical_master.py'), 'fva_backend/src'),
    (str(PROJECT / 'src' / 'd40_hex_conical_master_v3_refined_hex_nojob.py'),
     'fva_backend/src'),
    (str(PROJECT / 'sources' / 'shaft_with_keywayyt.py'),
     'fva_backend/sources'),
]

a = Analysis(
    ['model_builder_gui.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ModelBuilder',
    version=str(ROOT / 'version_info.txt'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
