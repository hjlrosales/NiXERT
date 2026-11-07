# NiX ERT

NiX ERT is an offline desktop application for transparent, reproducible
electrical resistivity tomography (ERT) and vertical electrical sounding
(VES) workflows.

It is designed around one rule: raw survey data stays immutable. Quality
control decisions, processing metadata, inversion settings, and derived
results are stored separately so a workflow can be reviewed and reproduced.

## Features

- Persistent project and survey management
- RES2DINV-style DAT import with non-destructive quality control
- Apparent-resistivity processing and VES workflows
- Baseline 2D and 3D inversion workflows
- Pseudosection, 2D model, and 3D volume visualization
- Electrode coordinates, topography, and DEM support
- Versioned processing results and technical report generation
- Qualification tools, benchmark fixtures, and a local advisory AI assistant

See [ROADMAP.md](ROADMAP.md) for the implementation history, current
limitations, and planned work.

## Requirements

- Python 3.10 or later
- Windows, Linux, or macOS for development
- PySide6 for the desktop interface

The project metadata declares the runtime dependencies in
[`pyproject.toml`](pyproject.toml).

## Installation

Clone the repository and install it in a virtual environment:

```bash
git clone https://github.com/hjlrosales/NiXERT.git
cd NiXERT
python -m venv .venv
```

Activate the environment on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Or on Linux and macOS:

```bash
source .venv/bin/activate
```

Then install NiX ERT with its test dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[test,visualization]"
```

## Usage

Launch the desktop application with either command:

```bash
nix-ert
```

```bash
python -m nix_ert.app.main
```

Additional workflow notes are available in [HOWTO.md](HOWTO.md), while the
technical documentation is under [`docs/`](docs/).

## Development

Run the automated test suite:

```bash
python -m pytest
```

Build the per-user Windows installer with:

```bash
python tools/build_windows_installer.py
```

The installer uses a PyInstaller one-folder bundle compiled by Inno Setup.
See [docs/installer.md](docs/installer.md) for prerequisites and details.

## Project status

NiX ERT is under active development. Its internal qualification fixtures and
small-case baselines are not a claim of equivalence with proprietary inversion
software. External benchmark validation, field-scale performance
qualification, and production-grade inversion qualification remain ongoing.

Direct Terrameter LS2 communication is intentionally disabled until official
protocol documentation and validated device fixtures are available. Existing
ABEM database tooling is read-only and does not guess undocumented vendor
schema mappings.

## License

NiX ERT is available for non-commercial use under the custom terms in
[LICENSE](LICENSE). Commercial use requires a separate written license from
the copyright holder.
