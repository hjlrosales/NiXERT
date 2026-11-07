# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows standalone NiX ERT desktop bundle.

The bundle is one application: the Qt desktop shell in ``nix_ert.app.main``.
It is built from the same sources the test suite runs against and never
downloads anything at build time, so the frozen executable and the checkout
cannot diverge silently.

Build it through ``tools/build_windows_installer.py`` rather than calling
PyInstaller directly, so the paths stay consistent with the Inno Setup script.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]  # packaging/windows -> repository root

# Optional-only or unrelated packages. Excluding them keeps the bundle small
# without removing anything the desktop shell imports.
EXCLUDES = [
    # Nothing the desktop shell imports needs these at runtime. PyInstaller
    # otherwise collects the legacy pkg_resources runtime hook, which aborts
    # startup because its vendored appdirs shim is not bundled.
    "pkg_resources",
    "setuptools",
    "_distutils_hack",
    "tkinter",
    "pytest",
    "IPython",
    # Model/data-processing stacks that share a machine with the app but are
    # never imported by it. A developer workstation usually has them; the
    # desktop shell does not, so they are left out of the installer.
    "torch",
    "functorch",
    "torchvision",
    "torchaudio",
    "transformers",
    "tokenizers",
    "safetensors",
    "huggingface_hub",
    "spacy",
    "spacy_loggers",
    "thinc",
    "blis",
    "cymem",
    "murmurhash",
    "preshed",
    "srsly",
    "weasel",
    "confection",
    "catalogue",
    "sudachipy",
    "sudachidict_core",
    "nltk",
    "numba",
    "llvmlite",
    "librosa",
    "soundfile",
    "av",
    "einops",
    "cv2",
    "sklearn",
    "tensorflow",
    "keras",
    "jax",
    "jaxlib",
    "onnxruntime",
    "mkl",
    "mkl_service",
    "daal4py",
    "scikit_learn_intelex",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdfWidgets",
]

a = Analysis(
    [str(ROOT / "nix_ert" / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NiX ERT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NiX ERT",
)
