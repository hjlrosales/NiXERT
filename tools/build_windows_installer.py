"""Build the Windows standalone bundle and the per-user NiX ERT installer.

Three steps, all explicit:

1. A dedicated build environment ``.venv-build`` gets the project's own declared
   dependencies plus PyInstaller, so the bundle contains only what the desktop
   shell needs. Freezing the interpreter you develop in would sweep in every
   unrelated package installed on the machine.
2. PyInstaller freezes ``nix_ert.app.main`` into a one-folder bundle under
   ``dist/NiX ERT`` using ``packaging/windows/nix_ert.spec``.
3. Inno Setup compiles ``packaging/windows/nix_ert.iss`` into a single
   ``dist/installer/NiX-ERT-<version>-win64-setup.exe`` that installs for the
   current user only.

No version is duplicated: it comes from ``nix_ert.__version__`` and is passed to
both tools on the command line. A missing tool, a failed step, or a missing
artifact is reported as an error instead of being skipped.

Usage::

    python tools/build_windows_installer.py                  # bundle + installer
    python tools/build_windows_installer.py --bundle-only
    python tools/build_windows_installer.py --installer-only  # reuse the bundle
    python tools/build_windows_installer.py --no-venv        # freeze the current interpreter
    python tools/build_windows_installer.py --clean          # delete build output
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "windows" / "nix_ert.spec"
ISS = ROOT / "packaging" / "windows" / "nix_ert.iss"
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pyinstaller"
BUILD_VENV = ROOT / ".venv-build"
BUNDLE_NAME = "NiX ERT"
BUNDLE_DIR = DIST / BUNDLE_NAME
BUNDLE_EXE = BUNDLE_DIR / f"{BUNDLE_NAME}.exe"
INSTALLER_DIR = DIST / "installer"

_ISCC_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
)


class BuildError(RuntimeError):
    """Raised when a build step cannot be performed as specified."""


def app_version() -> str:
    sys.path.insert(0, str(ROOT))
    try:
        from nix_ert import __version__
    except ImportError as exc:  # pragma: no cover - broken checkout
        raise BuildError(f"cannot read the application version: {exc}") from exc
    finally:
        sys.path.pop(0)
    version = str(__version__).strip()
    if not version or version == "0.0.0":
        raise BuildError("nix_ert.__version__ is empty; refusing to build an unversioned installer")
    return version


def _run(command: list[str], label: str) -> None:
    print(f"[{label}] {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=str(ROOT))
    if completed.returncode != 0:
        raise BuildError(f"{label} failed with exit code {completed.returncode}")


def build_interpreter(use_venv: bool) -> str:
    """Return the interpreter PyInstaller should freeze from."""
    if not use_venv:
        try:
            import PyInstaller  # noqa: F401
        except ImportError as exc:
            raise BuildError(
                "PyInstaller is not installed in the current interpreter: run "
                "`python -m pip install pyinstaller`"
            ) from exc
        return sys.executable

    python = BUILD_VENV / "Scripts" / "python.exe"
    if not python.is_file():
        _run([sys.executable, "-m", "venv", str(BUILD_VENV)], "venv")
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], "venv-pip")
    _run(
        [str(python), "-m", "pip", "install", "-e", f"{ROOT}[visualization]", "pyinstaller"],
        "venv-deps",
    )
    return str(python)


def pyinstaller_command(python: str) -> list[str]:
    return [python, "-m", "PyInstaller"]


def inno_compiler() -> Path:
    override = os.environ.get("INNO_SETUP_ISCC")
    if override:
        candidate = Path(override)
        if not candidate.is_file():
            raise BuildError(f"INNO_SETUP_ISCC does not point at a file: {candidate}")
        return candidate
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    for candidate in _ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise BuildError(
        "Inno Setup 6 compiler (ISCC.exe) was not found. Install it with "
        "`winget install --id JRSoftware.InnoSetup` or set INNO_SETUP_ISCC."
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_bundle(python: str) -> Path:
    command = pyinstaller_command(python) + [
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
        str(SPEC),
    ]
    _run(command, "bundle")
    if not BUNDLE_EXE.is_file():
        raise BuildError(f"PyInstaller did not produce {BUNDLE_EXE}")
    return BUNDLE_EXE


def build_installer(version: str) -> Path:
    compiler = inno_compiler()
    command = [
        str(compiler),
        f"/DMyAppVersion={version}",
        f"/DBundleDir={BUNDLE_DIR}",
        f"/DOutputDir={INSTALLER_DIR}",
        str(ISS),
    ]
    _run(command, "installer")
    expected = INSTALLER_DIR / f"NiX-ERT-{version}-win64-setup.exe"
    if not expected.is_file():
        raise BuildError(f"Inno Setup did not produce {expected}")
    return expected


def clean() -> None:
    for path in (DIST, ROOT / "build"):
        if path.exists():
            shutil.rmtree(path)
            print(f"removed {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle-only", action="store_true", help="build the PyInstaller bundle only")
    parser.add_argument("--installer-only", action="store_true", help="compile the installer from an existing bundle")
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="freeze the current interpreter instead of .venv-build (it must hold only the app's dependencies)",
    )
    parser.add_argument("--clean", action="store_true", help="delete build/ and dist/ and exit")
    args = parser.parse_args(argv)

    if args.clean:
        clean()
        return 0
    if args.bundle_only and args.installer_only:
        parser.error("--bundle-only and --installer-only are mutually exclusive")
    if sys.platform != "win32":
        raise BuildError("this packaging pipeline targets Windows only")

    try:
        version = app_version()
        if not args.installer_only:
            python = build_interpreter(use_venv=not args.no_venv)
            print(f"freezing from: {python}")
            exe = build_bundle(python)
            print(f"bundle: {exe} ({exe.stat().st_size} bytes)")
        elif not BUNDLE_EXE.is_file():
            raise BuildError(f"no bundle at {BUNDLE_EXE}; build it first without --installer-only")
        if args.bundle_only:
            return 0
        installer = build_installer(version)
    except BuildError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 2

    print(f"installer: {installer}")
    print(f"size: {installer.stat().st_size} bytes")
    print(f"sha256: {sha256(installer)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
