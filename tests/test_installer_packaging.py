"""Consistency checks for the Windows packaging pipeline.

These tests never build an installer — that needs PyInstaller and Inno Setup, and
runs for minutes. They pin the properties the build depends on: the spec freezes
the real entry point and excludes the unused stacks, the Inno script is a
per-user install driven by build-time parameters, the two files agree on the
artifact name, the version has exactly one source, and the build script refuses
impossible requests instead of half-building.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

import nix_ert

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "windows" / "nix_ert.spec"
ISS = ROOT / "packaging" / "windows" / "nix_ert.iss"


def _load_build_module():
    spec = importlib.util.spec_from_file_location(
        "build_windows_installer", ROOT / "tools" / "build_windows_installer.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build():
    return _load_build_module()


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def iss_text() -> str:
    return ISS.read_text(encoding="utf-8")


def test_packaging_files_exist():
    assert SPEC.is_file()
    assert ISS.is_file()


def test_spec_freezes_the_desktop_entry_point(spec_text):
    assert '"nix_ert" / "app" / "main.py"' in spec_text
    assert 'pathex=[str(ROOT)]' in spec_text
    assert 'name="NiX ERT"' in spec_text
    assert "console=False" in spec_text


def test_spec_excludes_the_unused_optional_stacks(spec_text):
    # pkg_resources is the one that broke startup: its collected runtime hook
    # needs a vendored appdirs that is not bundled. The rest keep a developer
    # machine's ML/NLP packages out of the installer.
    for name in ("pkg_resources", "setuptools", "tkinter", "pytest", "torch", "spacy", "nltk", "llvmlite"):
        assert f'"{name}"' in spec_text


def test_spec_keeps_the_libraries_the_shell_imports(spec_text):
    excluded = {line.strip().strip(',').strip('"') for line in spec_text.splitlines()}
    for name in ("numpy", "scipy", "pandas", "matplotlib", "PySide6"):
        assert name not in excluded


def test_installer_is_a_per_user_install(iss_text):
    assert "PrivilegesRequired=lowest" in iss_text
    assert "DefaultDirName={autopf}\\{#MyAppName}" in iss_text
    assert "AppId={{7E1B9D2C-4C4A-4C0B-9C41-7A5E2F6B8D10}" in iss_text


def test_installer_takes_its_version_and_paths_from_the_build(iss_text):
    assert "#ifndef MyAppVersion" in iss_text
    assert "#ifndef BundleDir" in iss_text
    assert "#ifndef OutputDir" in iss_text
    assert "Source: \"{#BundleDir}\\*\"" in iss_text


def test_installer_and_build_agree_on_the_setup_file_name(iss_text, build):
    # build_windows_installer.py looks for exactly this file after ISCC runs.
    assert "OutputBaseFilename=NiX-ERT-{#MyAppVersion}-win64-setup" in iss_text
    assert f"NiX-ERT-{{version}}-win64-setup.exe" in (
        ROOT / "tools" / "build_windows_installer.py"
    ).read_text(encoding="utf-8")


def test_build_paths_live_under_the_project_root(build):
    assert build.ROOT == ROOT
    assert build.BUNDLE_EXE == ROOT / "dist" / "NiX ERT" / "NiX ERT.exe"
    assert build.INSTALLER_DIR == ROOT / "dist" / "installer"
    assert build.BUILD_VENV == ROOT / ".venv-build"


def test_version_has_a_single_source(build):
    assert build.app_version() == nix_ert.__version__


def test_an_unversioned_installer_is_refused(build, monkeypatch):
    monkeypatch.setattr(nix_ert, "__version__", "0.0.0")
    with pytest.raises(build.BuildError):
        build.app_version()


def test_conflicting_build_modes_are_rejected(build):
    with pytest.raises(SystemExit) as excinfo:
        build.main(["--bundle-only", "--installer-only"])
    assert excinfo.value.code == 2


def test_a_missing_pyinstaller_is_reported_not_ignored(build, monkeypatch):
    monkeypatch.setitem(sys.modules, "PyInstaller", None)
    with pytest.raises(build.BuildError) as excinfo:
        build.build_interpreter(use_venv=False)
    assert "PyInstaller is not installed" in str(excinfo.value)


def test_a_missing_inno_compiler_is_reported_not_ignored(build, monkeypatch):
    monkeypatch.delenv("INNO_SETUP_ISCC", raising=False)
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    monkeypatch.setattr(build, "_ISCC_CANDIDATES", ())
    with pytest.raises(build.BuildError) as excinfo:
        build.inno_compiler()
    assert "Inno Setup 6 compiler" in str(excinfo.value)


def test_the_inno_override_must_point_at_a_file(build, monkeypatch, tmp_path):
    monkeypatch.setenv("INNO_SETUP_ISCC", str(tmp_path / "missing-ISCC.exe"))
    with pytest.raises(build.BuildError):
        build.inno_compiler()
    compiler = tmp_path / "ISCC.exe"
    compiler.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("INNO_SETUP_ISCC", str(compiler))
    assert build.inno_compiler() == compiler


def test_real_locator_finds_no_compiler_only_when_none_is_installed(build):
    # Informational: the machine running the suite may or may not have ISCC.
    try:
        found = build.inno_compiler()
    except build.BuildError:
        assert shutil.which("ISCC") is None
    else:
        assert found.is_file()
