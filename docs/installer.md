# Windows installer packaging

This document describes how the NiX ERT desktop application becomes a normal
Windows program: a single `NiX-ERT-<version>-win64-setup.exe` that installs for
the current user without administrator rights and without Python on the target
machine.

Packaging changes no science. The installer ships the same desktop shell the
test suite runs against, and the external benchmark gate, the LS2 communication
blocker, and the ABEM importer readiness state are exactly as described in the
rest of the documentation: the installer bundles no dataset, no reference
result, and no qualification claim.

## Files

| Path | Role |
|---|---|
| `packaging/windows/nix_ert.spec` | PyInstaller one-folder bundle of `nix_ert.app.main` |
| `packaging/windows/nix_ert.iss` | Inno Setup script for the per-user installer |
| `tools/build_windows_installer.py` | Orchestrates both steps, single-sources the version |

## What the installer contains

- The application package `nix_ert` and the Python runtime it needs.
- The libraries the shell actually imports: Qt (PySide6/shiboken6), NumPy,
  SciPy, pandas, matplotlib and their dependencies.
- Nothing else. `pkg_resources`/`setuptools`, `tkinter`, `pytest`, the unused Qt
  modules (WebEngine, Qml, Quick, Charts, Multimedia, 3D) and the ML/NLP stacks
  that a developer machine often has installed (torch, transformers, spacy,
  nltk, numba, llvmlite, librosa, …) are excluded explicitly, so the bundle
  contains only what the desktop shell imports.

The installer adds no data files, no sample projects, no benchmark registry, and
no vendor fixtures. User projects, configuration, and logs stay outside the
install directory, under `%LOCALAPPDATA%` (Qt) and `~/.nix-ert` (config, logs),
and uninstalling does not touch them.

## Building

```bash
python -m pip install pyinstaller          # once, in the building interpreter
winget install --id JRSoftware.InnoSetup   # once, provides ISCC.exe
python tools/build_windows_installer.py
```

The script:

1. creates `.venv-build` and installs the project's own declared dependencies
   (`pip install -e ".[visualization]"`) plus PyInstaller, so the bundle is
   frozen from a clean environment rather than from whatever else the developer
   has installed;
2. runs PyInstaller with `packaging/windows/nix_ert.spec` into `dist/NiX ERT`;
3. runs `ISCC.exe` with `MyAppVersion`, `BundleDir`, and `OutputDir` taken from
   `nix_ert.__version__` and this repository, so no version or path is
   duplicated in a second place.

Options: `--bundle-only`, `--installer-only` (reuse an existing bundle),
`--clean`, and `--no-venv` (freeze the current interpreter instead of
`.venv-build`; that interpreter must then hold only the application's
dependencies).

Failures are reported and not skipped: a missing PyInstaller, a missing
`ISCC.exe` (set `INNO_SETUP_ISCC` to override the search), an empty version, a
non-Windows platform, a failed step, or a missing artifact all end the build
with a non-zero exit code.

## Installing and uninstalling

```powershell
# interactive: double-click the setup file
# silent (Git Bash needs the argument-conversion override, see below)
MSYS2_ARG_CONV_EXCL='*' dist/installer/NiX-ERT-0.1.0-win64-setup.exe \
    /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

`PrivilegesRequired=lowest` means the install target is
`%LOCALAPPDATA%\Programs\NiX ERT`, the uninstall entry is written under
`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall`, an administrator
prompt is never raised, and no machine-wide state is modified. The Start menu
gets **NiX ERT** and an uninstall entry; a desktop shortcut is offered but not
preselected.

In Git Bash, `/VERYSILENT` and friends are rewritten into Windows paths by the
shell unless `MSYS2_ARG_CONV_EXCL='*'` is set, which silently turns a silent
install into an interactive wizard. This is a shell quoting rule, not a
property of the installer.

## Verified behavior

For the artifact recorded in `changelog.md`:

- the frozen executable and the installed executable both start, create the
  window titled `NiX ERT <version>`, and write `~/.nix-ert/logs/nix-ert.log`;
- the bundle contains no `pkg_resources`, torch, spacy, nltk, transformers,
  numba, llvmlite, or MKL payload;
- the installed tree, the Start menu shortcuts, and the uninstaller
  (`unins000.exe`) exist after a silent per-user install.

## Limitations

- The installer is **not code-signed**, so Windows SmartScreen may warn on first
  run and the publisher is shown as unknown.
- There is no installer CI: the artifact is built on a developer machine, and
  the library versions it ships are the ones that machine installs from
  `pyproject.toml`. The suite is run against those versions, but nothing yet
  freezes them in a lock file.
- The build was exercised on 64-bit Windows only; the Inno script allows
  x64-compatible architectures and the PyInstaller bundle is not tested on ARM64
  or 32-bit Windows.
- Packaging does not change qualification status: the external benchmark gate
  remains `NOT VALIDATED`, `importer_ready = false`, and physical LS2
  communication remains blocked.
