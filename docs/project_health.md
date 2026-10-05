# Local project health check

Run this command from the repository root in Windows PowerShell:

```powershell
.\scripts\project_health.ps1
```

The default run checks Ruff, ESLint and Prettier formatting, then executes the
complete local Python test suite with `.venv\Scripts\python.exe -m pytest tests -q`,
`npm test` and `npm run build` in `frontend`, and `git diff --check` from the
repository root. These are the
software checks used by the existing `test_full_system.ps1` and CI workflow,
with the local diff check added. The repository check also inspects staged changes
and the latest commit, following CI's whitespace gate. Numeric library thread
limits and the headless
Matplotlib backend match CI. It does not call GitHub Actions or install packages.

The command checks for virtualenv Python and Ruff, npm, the frontend directory and its
installed Vite dependency, and Git. Missing tools mark their dependent checks
**NOT RUN** with a reason. Each check runs independently, so a Python failure
does not prevent the frontend checks or final report. Successful checks have
short summaries; failed checks show their exit code and final diagnostic lines.
Run the indicated command directly for its complete failure log.

## Report sections

| Section | Meaning |
| --- | --- |
| Environment | Local tools and dependencies needed for the full check. |
| Software | Actual outcomes for Ruff, ESLint, Prettier check, Python tests, frontend tests, build and diff check. |
| Data evidence | Statuses projected from `readiness()` and its validated audit trail. |
| Production | First heat-map source gate, accepted ML grid and accepted XGBoost model. |
| Summary | Independent software and production outcomes. |
| Next blockers | Names returned by `first_heat_map_blockers`; ward GIS is not a first-build blocker. |

The small `scripts/project_health.py` helper calls the existing
`backend.app.data_intake.readiness.readiness()` function. It uses the same
`SOURCE_IDS` as the production heat-map build and projects only selected audit
and source statuses. The Sentinel intake display is **PENDING** when the saved
audit records pending acquisition; its underlying FAIL remains visible in the
audit viewer. A successful extreme diagnostic investigation displays
**REVIEWED**. Missing or inconsistent readiness evidence produces
**PRODUCTION READINESS UNKNOWN**.

For the grid, the helper calls the backend's `_real_grid()` validator. That
rejects demo metadata and checks the real Parquet schema and row count. For the
model, it first checks the artifact digest recorded in metadata, then calls the
map's `_bundle()` validator and the API's `model_metrics()` validator. These
require a compatible real grid, XGBoost model contract and spatial-validation
metadata. File existence alone never makes either artifact READY. Legacy files
in this repository are rejected. When required sources are pending, these
artifacts display **BLOCKED**. If sources are ready but present artifacts fail
validation, the report displays **INVALID / REVIEW**.

**Software READY does not mean production climate data is complete.**
**Production data being pending does not mean the software test suite failed.**
The command exits **0** only after all seven software checks pass and the
health helper succeeds, even when production sources are still pending. It
exits **1** for a failed or unrun software check, missing essential environment,
or an unusable health helper. It does not return a nonzero code solely because
Sentinel or municipal-boundary evidence is pending.

The check never runs source audits, source downloads, geospatial processing,
model training, or production publication. Normal pytest temporary fixtures
and the ignored Vite build directory may be written by the software checks.
Source files, verification states and production artifacts are not modified.

## Synthetic tests

`tests/test_project_health.py` exercises dynamic blocker counts, Sentinel and
boundary statuses, reporting-only ward GIS, missing evidence, software failures,
and rejection of present but unaccepted grid/model fixtures. Run it with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_health.py -q
```
