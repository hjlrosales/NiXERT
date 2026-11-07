# M19 reproducibility and release qualification result

**Assessment date:** 2026-09-15  
**Procedure:** `m19-release-qualification-v1`  
**Assessment:** **QUALIFIED_FOR_SUPPORTED_OFFLINE_WORKFLOW**

This result qualifies the tested supported offline workflow only. It does not
mean NiX ERT is production-grade geological software, does not establish
RES2DINV equivalence, and does not validate field-scale performance or LS2
hardware communication.

## Environment

- Python 3.11.9
- Windows-10-10.0.26200-SP0
- AMD64
- Intel64 Family 6 Model 198 Stepping 2, GenuineIntel
- NiX ERT version `0.1.0`

## Qualification datasets

| Dataset | Classification | Source/hash | Result |
|---|---|---|---|
| `internal-dat-lifecycle-v1` | Internal deterministic DAT fixture | `9bbd89666b8d061fd5cd99926d6394664cc7961d04d7a181569da88541df4c98` | Project/import/QC/process/2D inversion/report/reopen path reproducible |
| `ves-layered-internal-v1` | Internal synthetic | Generated deterministic fixture; no external hash | Finite forward/inversion behavior validated by existing qualification tests |
| `ert-2d-anomaly-internal-v1` | Internal synthetic | Generated deterministic fixture; no external hash | Finite forward/inversion behavior validated by existing qualification tests |
| `ert-3d-anomaly-internal-v1` | Internal synthetic | Generated deterministic fixture; no external hash | Finite forward/inversion behavior validated by existing qualification tests |

The Barugo files were not used as NiX workflow inputs. They remain read-only
vendor data and retain their previously verified hashes:

- ERT: `057674127c923842510ee5e8af6082fed88ef152438f3752ca681d5f2f6d47af`
- VES: `97eec29b3f9870092f9674e54b560df20f9df2130ac18778ff29161757d09e51`

## Reproducibility results

The automated M19 lifecycle repeatedly executed:

```text
Project → Import → QC → Processing → Inversion → Model selection → Report
```

Two reports generated from the same persisted project/model state had equivalent
structured project, survey, QC, inversion, interpretation, appendix, and state-
fingerprint data. Generated timestamps and output filenames were intentionally
excluded from the equivalence comparison.

Verified behaviors:

- source hash remains equal to the managed raw copy;
- processing and inversion versions retain the selected survey and source state;
- the report contains the selected version and state fingerprint;
- changing working measurement status marks the model/report provenance stale;
- invalid empty input is rejected without creating measurements;
- cancellation completes without committing a partial result;
- existing lifecycle tests verify close/reopen, source inspection, model
  inspection, report generation, and managed-source path rejection.

## Measured performance

Measurements use `tracemalloc` peak Python allocations and `time.perf_counter`.
They are observations, not pass/fail thresholds. Native allocations and
field-scale performance were not measured.

### Supported workflow baseline

| Operation | Size | Time (s) | Peak Python bytes |
|---|---:|---:|---:|
| DAT import | 83 source bytes | 0.005806 | 44,707 |
| QC | 6 observations | 0.000575 | 13,332 |
| Processing snapshot | 6 observations | 0.002614 | 17,446 |
| 2D inversion, one iteration | 6 observations / 18 cells | 0.228566 | 174,315 |
| HTML report | 6 observations | 0.005072 | 78,640 |

### Scientific fixture baseline

| Operation | Size | Time (s) | Peak Python bytes |
|---|---:|---:|---:|
| VES forward | 8 observations | 0.075494 | 17,608 |
| VES inversion, 20 evaluations | 8 observations | 14.911569 | 54,243 |
| 2D forward | 6 observations / 18 cells | 0.005565 | 29,979 |
| 2D inversion, one iteration | 6 observations / 18 cells | 0.218245 | 138,034 |
| 3D forward | 2 observations / 16 cells | 0.010745 | 31,699 |
| 3D inversion, one iteration | 2 observations / 16 cells | 0.337185 | 123,389 |

The VES inversion measurement is the most expensive measured small fixture
operation. Medium, large, and stress-scale cases remain unmeasured and are not
claimed qualified.

## Desktop acceptance

The PySide6 application startup/close smoke passed. The desktop shell exposes
project/import, workflow, interpretation/report, Assistant, and LS2 tabs. The
LS2 panel starts in disconnected state and default USB/Wi-Fi providers remain
fail-closed. No hardware, serial interface, network service, VNC session, or
acquisition path was accessed.

Headless lifecycle tests cover the supported scientific workflow. UI rendering
of every result is not a substitute for scientific validation; interactive
manual acceptance remains limited to the available offline project workflow.

## Test results

- M19 focused tests: **5 passed**
- Full suite: **128 passed**
- Compilation: `python -m compileall -q nix_ert tests` passed
- PySide6 startup/close and LS2 panel smoke: passed
- Existing Barugo inspection/semantic/intermediate tests: passed
- Original Barugo source hashes: unchanged

## Limitations and blocked capabilities

- No independent published, commercial, or field benchmark was available.
- Internal synthetic fixtures are not external validation and do not model all
  field noise or geological non-uniqueness.
- Medium/large/stress-scale performance remains unmeasured.
- Native memory allocations are not included in `tracemalloc` values.
- Topography-aware inversion, uncertainty/resolution analysis, advanced/true 3D
  inversion, IP inversion, GPU acceleration, and automatic geological
  classification remain outside this qualification.
- Geological interpretations remain advisory; no geological certainty is
  claimed.
- Barugo ABEM → NiX importer remains **NOT READY** pending authoritative vendor
  semantics and conformance fixtures.
- M15 physical LS2 validation remains **PENDING**; direct LS2 communication is
  still fail-closed.

## Release decision

NiX ERT is **qualified for the tested supported offline workflow** with the
limitations above. It is **not declared production-grade geological software**.
The next milestone should be selected only after considering independent
reference data, larger performance cases, and the unresolved Barugo/LS2
external dependencies.
