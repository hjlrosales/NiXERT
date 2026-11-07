# HOWTO: build and use NiX ERT

This is the plain-language guide for someone who just wants to get the program
running and click through a survey. It explains what to install, how to start
the desktop app, and what each step does. Technical background lives in
[`docs/`](docs/) and [`README.md`](README.md); this file stays practical.

NiX ERT is a desktop program for two kinds of resistivity work:

- **ERT** (electrical resistivity tomography) — many four-electrode readings
  along a line, turned into a 2D resistivity model.
- **VES** (vertical electrical sounding) — a sounding curve built by widening
  the electrode spread, fitted with a layered-earth (1D) model.

It can also export a report from the open project. Everything runs locally; the
app does not need an internet connection.

> **Read this before trusting a number.** This is scientific software, but it is
> not yet externally validated. See
> [What it does not do](#14-what-it-does-not-do) at the end before you use a
> result in a real deliverable.

---

## 1. What you need

- **Python 3.10 or newer** (3.11 is what the project is currently developed
  and tested on).
- **pip** (comes with Python).
- A normal desktop session (Windows, macOS, or Linux). The user interface is
  built with Qt through PySide6.
- A few minutes for the first install.

Check your Python:

```bash
python --version
```

If that says 3.9 or older, install a newer Python first.

---

## 2. Set up the program (first time only)

Open a terminal in the folder that contains `pyproject.toml` (the project root).

### 2a. Create a private Python environment

This keeps NiX ERT's libraries separate from the rest of your computer.

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows, Git Bash
source .venv/Scripts/activate

# Windows, PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`.

### 2b. Install the program and its libraries

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[visualization,test]"
```

What that does:

- `-e` means "editable": the app runs from this folder, so pulling changes and
  restarting is enough.
- The four required libraries (NumPy, pandas, SciPy, PySide6) are installed
  automatically.
- `visualization` adds matplotlib, which the optional PDF export uses.
- `test` adds pytest, which you need only if you want to run the test suite.

You only repeat section 2 if you move the folder or delete `.venv`.

---

## 3. Start the app

With the environment active, from the project root:

```bash
python -m nix_ert.app.main
```

Or, because the install in step 2b registers a command:

```bash
nix-ert
```

A window titled `NiX ERT` (with the version number) opens with six tabs:

| Tab | What it is for |
|---|---|
| Project / Import | Create/open a project, add surveys, import ERT data |
| LS2 Connection | Offline status check for the ABEM Terrameter LS2 instrument |
| QC / Process / Invert / Visualize | The main ERT workflow |
| Interpret / Report | Add notes and export a report |
| VES | Paste a sounding curve, fit a layered-earth model |
| Assistant | Ask questions about the open project (local, advisory) |

---

## 4. Make a project

1. Menu **Project → New Project…**
2. Choose a folder. Use a fresh folder for a new project — that folder becomes
   the project folder.
3. Type a project name.

NiX ERT creates `project.nixert.sqlite3` in that folder. This database holds the
project's structure and processing state. Imported raw files are copied,
untouched, into a managed `raw/` area inside the same project folder.

To come back later, use **Project → Open Project…** and pick that
`.sqlite3` file. **Project → Close Project** releases it.

> Do not edit the project database by hand or move imported raw files out of the
> project. The app checks that they are still present and unchanged, and a
> report will refuse to build if they are not.

### Add a survey

On the **Project / Import** tab:

1. Click **Add survey**.
2. Give it a name (for example `Line 1`).
3. Pick the type: `ERT`, `3D ERT`, or `VES`.

A project can hold many surveys. Click a survey in the list to work on it; the
buttons enable or disable themselves based on what that survey type supports
(for example, DAT import is ERT-only, and VES is handled on the VES tab).

---

## 5. Bring in data

### 5a. ERT: import a DAT file

Select an ERT survey, then click **Import DAT** and choose the file.

The supported DAT dialect is deliberately narrow. It has three one-line headers,
an optional fourth line for topography, then the measurement rows:

```text
6
1
Wenner
0
1 2 3 4 100
1 3 4 6 120
2 4 5 6 90
1 4 2 3 110
2 5 3 4 105
3 6 4 5 95
```

In order, those header lines mean: the number of measurement rows (`6`), the
electrode spacing in metres (`1`), the array type (a name such as `Wenner`, or a
code `1`–`6`), and the number of topography rows (`0`; leave the line out when
there are none). Each remaining row is `A B M N apparent_resistivity`.

Rules the app enforces instead of guessing:

- Electrodes are numbered from 1; positions are calculated as
  `(number - 1) × spacing` with zero elevation. Topography rows are recorded
  with the source, but they do not change that geometry convention.
- Lines starting with `#`, `;`, or `!` are comments and are ignored.
- The row count must match the header count.
- A row may also start with an index (`index A B M N rho …`) or carry extra
  electrical columns (resistance, current, voltage), but a width that could be
  read either way is rejected rather than silently shifted.
- Zero or negative resistivities are kept and shown so you can make a visible
  QC decision; they are not quietly deleted.
- Importing the exact same file twice into the same survey is refused.

If a file is rejected, the message names the line and the reason. This importer
has **not** been proven against every real RES2DINV/LS2 export; files that differ
from the dialect above are rejected on purpose (see
[`docs/dat-import.md`](docs/dat-import.md)).

You can also click **Inspect Barugo ERT Sample** / **Inspect Barugo VES Sample**
if you have those ABEM project databases. Those buttons only *read and summarise*
the vendor file — nothing is imported, converted, or treated as NiX ERT data.

### 5b. VES: paste or load a sounding curve

1. Add (or select) a survey of type `VES`.
2. Open the **VES** tab.
3. Paste rows into the box (for example by opening a small CSV/text file and
   copying its contents). There is no VES file-open button in this build. The
   format is one point per line:

   ```text
   AB/2,MN/2,resistance[,apparent_resistivity]
   10,2,3
   20,2,4
   30,2,5.5
   ```

   - `AB/2` and `MN/2` are Schlumberger half-spacings in metres.
   - The third column is the measured resistance in ohms.
   - The optional fourth column is an apparent resistivity in ohm-metres. If it
     is present it is used as-is; if it is missing, the app calculates it from
     the resistance and the Schlumberger geometry.
   - A header row is allowed when the first two cells are `AB/2` and `MN/2`.
   - Rows with too few columns or blank fields, invalid geometry (`AB/2` not
     greater than `MN/2`), extra columns, and non-positive numbers are refused
     with the line number.

4. Click **Load VES curve**. This validates the rows and remembers the input's
   fingerprint.
5. Click **Persist VES curve** to save the curve as a version snapshot in the
   project. Until you do, the curve is only held in the window.
6. Click **Run 1D inversion** to fit a two-layer starting model (100 and
   20 Ω·m, with a 5 m first layer) to the curve. The fitted resistivities,
   thicknesses, and RMS are shown and saved as another version. The starting
   model is fixed by this tab in the current build; it is a starting point for
   the fit, not a constraint on the answer.

---

## 6. Work through the ERT steps

Open the **QC / Process / Invert / Visualize** tab with an ERT survey selected.
Do these in order; the workflow refuses steps that do not make sense yet.

1. **QC summary / flag** — counts total, active, flagged, excluded, invalid,
   and duplicate readings, and marks suspicious rows as `FLAGGED`. Nothing is
   changed or deleted; a flag is a request for a human to look.
2. **Inspect measurements** — lists each persisted reading with its source row,
   A/B/M/N, resistance, apparent resistivity, status, and the reason for any flag.
3. **Process active data** — freezes the current active/excluded selection into a
   processing version. Raw data is never modified.
4. **Run 2D baseline inversion** — starts a small bounded 2D inversion in the
   background. Progress appears in the output box. **Cancel inversion** stops it
   safely: a partial result is never saved, and the last good version stays.
   If the working data or electrode geometry changes while it runs, the result is
   discarded rather than committed against different inputs.
5. **Visualize selected 2D model** — reports a text summary of the saved model:
   cells, resistivity range, iterations, RMS, convergence, and display range.
   In this build it does not draw a picture.
6. **Inspect 3D output status** — says whether a persisted 3D model exists. The
   desktop workflow does not create a 3D inversion, and it will not pretend a 2D
   model is 3D.

The status line at the top of the tab always shows the project, survey, counts,
and the standing limitations of the view you are looking at.

### What the words mean

- **Resistivity** (Ω·m) is how strongly the ground opposes current. High values
  suggest dry rock or sand; low values suggest clay, water-bearing soil, or
  another conductive material. Resistivity is not a unique identifier of a
  material.
- **RMS** is the mismatch between measured and modelled data. Lower is a closer
  fit, but a low RMS does not make a model true or unique.
- **Baseline inversion** means a deliberately simple, bounded solver. It is not
  RES2DINV and is not claimed to match it.

---

## 7. Save the result as a report

Open the **Interpret / Report** tab.

1. Optionally type interpretation notes. They are included as your notes and are
   labelled as interpretation, not as measured fact.
2. Pick an **Export format**:

   | Choice | File | What you get |
   |---|---|---|
   | HTML report | `.html` | The canonical, printable report |
   | PDF report | `.pdf` | Text-only rendering; needs matplotlib |
   | CSV data export | `.csv` | Flat `section,record,item,value` rows |
   | JSON manifest | `.json` | Machine-readable report manifest |

3. Click **Export current project report…**, choose where to save, and confirm.

Notes on exporting:

- The suggested name uses the chosen extension. If you type a supported
  extension yourself (`myreport.csv`), that wins, because the writer decides by
  extension. An unsupported extension (`.docx`) is refused instead of being
  silently turned into HTML.
- The output box reports the written path, the format's role, and a SHA-256
  "content digest". The same project data always produces the same digest, and
  re-exporting identical data produces identical bytes.
- HTML and JSON are the authoritative artifacts. The PDF is a plain text
  flattening: tables become text and images are not embedded. If matplotlib is
  missing, the PDF export tells you instead of failing silently.
- A report includes project and survey identity, QC summary, inversion
  parameters and convergence, source file hashes, software version, and the
  limitations. Missing pieces are stated as missing — it does not invent
  conclusions.
- Each export is also recorded in the project's report history, with the model
  version and input hashes used.
- A report can be produced without an inverted model; it is then a
  project-state summary, not a model report. The report says so.

There is no separate "save" action: the project database is updated as you work.
Reports and raw imports are the files written outside the database.

---

## 8. The other tabs

### Assistant

Type a question such as "what QC issues are there?" and press Enter. The
assistant is a local, deterministic, read-only analyser: it does not call a cloud
model, does not change the project, and its answers are advisory observations,
not geological conclusions.

### LS2 Connection

This tab exists so the app can report instrument connection status honestly.

- **Check USB** / **Check Wi-Fi** try the real path, which is intentionally
  disabled: the LS2 communication protocol is undocumented here, so no
  acquisition, settings change, port scan, or VNC session happens.
- **Run MOCK/TEST USB** / **Run MOCK/TEST Wi-Fi** run a simulated
  Connect → Detect → Identify → Verify sequence so the future workflow can be
  inspected without hardware.

Do not expect to collect data through this tab in this build.

---

## 9. Where your files go

| What | Where |
|---|---|
| Project database | `project.nixert.sqlite3` in the folder you chose |
| Imported raw files | a managed `raw/` directory beside that database, copies only |
| Reports | wherever you save them |
| App preferences / recent projects | `~/.nix-ert` (`%USERPROFILE%\.nix-ert` on Windows) |
| Logs | `~/.nix-ert/logs` |

Raw imports are immutable: QC, processing, inversion, and reporting never
rewrite them. Delete a project by closing it and deleting its folder — but only
after exporting anything you need.

---

## 10. Run the tests (optional, but a good sanity check)

From the project root, with the environment active:

```bash
python -m pytest
```

or, as the README suggests:

```bash
python -m unittest discover -s tests -v
```

The suite covers the parsers, QC, forward and inverse calculations, report
bytes, the desktop export flow, and the benchmark admission rules. The current
suite is 465 tests and takes about two minutes on a normal laptop.

On a machine with no display (for example a build server), the Qt test needs an
offscreen display:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest
```

Do not "fix" a failing test by loosening it. A failure usually means a scientific
or file-format contract changed.

---

## 11. Command-line helpers

These do not need the desktop window.

### Build a benchmark case from real data

The benchmark tool admits and executes external reference comparisons. It is for
supplying evidence, not for creating it: a candidate is refused unless it has
licensed bytes, a recorded SHA-256, stated geometry, an independent reference
result, and a justified tolerance.

```bash
# Check a registry manifest without running anything
python tools/run_external_benchmark.py --manifest registry.json --admit-only

# Turn a DAT file into a 2D case (no hand-written JSON)
python tools/run_external_benchmark.py --manifest registry.json \
    --case-from-dat ert-protocol=line.dat --emit-case ert-protocol=case.json

# Turn a VES sounding file into a VES case
python tools/run_external_benchmark.py --manifest registry.json \
    --case-from-ves ves-protocol=sounding.csv --emit-case ves-protocol=case.json

# Admit and execute, recording the comparison into the manifest
python tools/run_external_benchmark.py --manifest registry.json \
    --case candidate-protocol=case.json
```

The `--emit-case` step is worth doing: it writes the exact payload that will be
executed, so you can inspect it before a result is recorded. The DAT conversion
also takes its mesh resolution from the protocol's frozen `mesh_assumptions`, so
the manifest must supply `nz` (and optionally `depth`). See
[`docs/benchmark_execution.md`](docs/benchmark_execution.md) for the manifest
format, case format, refusal codes, and exit codes.

The repository ships **no** benchmark manifest and no admissible external
dataset, so this tool cannot currently mark any qualification gate as passed.

### Regenerate the frozen report output

`tests/golden/report_fixture.html` and `.csv` are byte-for-byte expectations. If
you deliberately change report structure or wording, regenerate them and review
the diff:

```bash
python tools/regenerate_report_goldens.py
```

Never regenerate just to make a failing test pass.

---

## 12. Install it like a normal program (optional)

Sections 2 and 3 run NiX ERT from this folder, which is what you want while the
project is changing. If you would rather have it in the Start menu like any
other program — including on a computer where Python is not installed — build
the Windows installer.

### 12a. Build the installer

Two extra tools are needed once:

```bash
python -m pip install pyinstaller
winget install --id JRSoftware.InnoSetup
```

Then, from the project root:

```bash
python tools/build_windows_installer.py
```

This takes a few minutes and does three things:

1. creates a private build environment in `.venv-build` holding only the
   libraries the program itself uses;
2. freezes the program into `dist/NiX ERT/` — a folder you can also just copy to
   another PC and run;
3. wraps that folder into one setup file:
   `dist/installer/NiX-ERT-0.1.0-win64-setup.exe` (the version comes from the
   program itself).

Useful switches:

| Command | What it does |
|---|---|
| `--bundle-only` | freeze the program, but skip the setup file |
| `--installer-only` | rebuild only the setup file from an existing `dist/NiX ERT` |
| `--clean` | delete `build/` and `dist/` |

### 12b. Install it

Double-click the setup file and follow the wizard. It installs for your user
account only, so Windows never asks for an administrator password and nothing
outside your own profile changes. You get:

- `%LOCALAPPDATA%\Programs\NiX ERT` — the program itself;
- a **NiX ERT** entry in the Start menu, plus an uninstall entry;
- a desktop shortcut, if you tick that box.

The same install without any clicking, from a terminal:

```bash
MSYS2_ARG_CONV_EXCL='*' \
  "dist/installer/NiX-ERT-0.1.0-win64-setup.exe" \
  /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

The `MSYS2_ARG_CONV_EXCL='*'` part matters in Git Bash: without it the shell
rewrites `/VERYSILENT` into a file path and the wizard opens instead of running
silently.

**The installer is not signed.** Windows SmartScreen may warn the first time you
run it — that is normal for a program built on your own computer. To remove NiX
ERT later, use the Start menu's uninstall entry or **Settings → Apps → NiX ERT**.
Your projects, settings, and logs are not deleted: they live in the folders you
chose and in `~/.nix-ert`.

### 12c. A Python package instead

If you only need an installable wheel and Python is already present:

```bash
python -m pip wheel . --no-deps -w dist
python -m pip install dist/nix_ert-0.1.0-py3-none-any.whl
```

The version in the file name comes from `pyproject.toml`. Dependencies still need
to be installed separately (`numpy`, `pandas`, `scipy`, `PySide6`), and
matplotlib remains optional for PDF export.

More detail is in [`docs/installer.md`](docs/installer.md).

---

## 13. Troubleshooting

**`ModuleNotFoundError: No module named 'PySide6'` (or numpy/pandas/scipy)**
The environment is not active or dependencies are missing. Activate `.venv` and
run `python -m pip install -e ".[visualization,test]"`.

**Nothing happens when I run `python -m nix_ert.app.main`**
Run it from the project root and confirm the environment is active. If the import
fails, Python prints the reason; the app does not hide startup errors.

**On Linux: `qt.qpa.plugin: could not load the Qt platform plugin "xcb"`**
Qt needs the usual desktop libraries (for example `libxcb-cursor0`) or a running
display. Install the distribution packages, or use `QT_QPA_PLATFORM=offscreen`
when you only need the tests.

**"Select an ERT survey first" / greyed-out buttons**
Click a survey in the list. DAT import and the QC/process buttons apply only to
`ERT` and `3D ERT` surveys; VES uses its own tab.

**"Import DAT failed"**
The file does not match the documented dialect. Check the header order, the
matched row count, the array name, and the column count. The error message names
the line.

**Report export says "unsupported report export format"**
The selected file name ends in something other than `.html`, `.htm`, `.pdf`,
`.csv`, or `.json`. Pick one of the offered formats or remove the extension.

**PDF fails and mentions matplotlib**
Install the visualization extra: `python -m pip install -e ".[visualization]"`.
HTML and JSON need no extra packages.

**A report refuses to build because a source file is missing or changed**
Keep imported files inside the project's managed raw area and do not edit them.
Re-import the original file into a new survey if the copy is genuinely lost.

**The project will not open**
NiX ERT fails closed on databases that are incomplete, malformed, or newer than
it understands. Do not hand-edit the SQLite file. Keep a backup and use a version
of the app that matches the project, or start a new project.

**"VES rows" errors**
Each data row needs `AB/2`, `MN/2`, and a positive resistance; `AB/2` must be
greater than `MN/2`; at most four columns are allowed. Add a header row only if
its first two cells really are `AB/2` and `MN/2`.

---

## 14. What it does not do

This matters as much as what it does:

- **No external scientific validation yet.** The repository contains internal
  synthetic checks, but no licensed independent benchmark dataset. The external
  reference gate is `NOT VALIDATED`.
- **No RES2DINV equivalence.** The 2D and 3D inversions are bounded numerical
  baselines with documented limitations, not industry-standard solver clones.
- **Not unique geology.** Resistivity models have non-unique solutions, and VES
  layered-earth fits are non-unique too. Treat every model as one plausible
  answer that needs professional interpretation.
- **No true 3D inversion in the desktop app.** Pseudosection depth is a display
  proxy, model depth is flat-coordinate depth (not elevation), and the 3D action
  only reports whether a persisted 3D model exists.
- **No live instrument control.** LS2 hardware communication is blocked pending
  official protocol documentation; only offline status and mock sequences exist.
- **No automatic vendor import.** The ABEM/Barugo files can be inspected
  read-only, but they are not imported through guessed schema mappings.
- **Reports are deliverables, not proof.** They record what was done and what is
  missing; they are not a certification.

If you need a result for a real engineering decision, treat this build as a
transparent workbench and have a qualified geophysicist review the data, the
settings, and the interpretation.

---

## Quick reference

```bash
# one-time setup
python -m venv .venv
source .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[visualization,test]"

# start the desktop app
python -m nix_ert.app.main

# run the tests
python -m pytest

# benchmark helpers
python tools/run_external_benchmark.py --help

# refresh frozen report bytes after a deliberate change
python tools/regenerate_report_goldens.py
```
