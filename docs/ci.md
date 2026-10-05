# Software continuous integration

The `GreenPulse CI` workflow is defined in [ci.yml](../.github/workflows/ci.yml).
It runs on pushes to `main`, pull requests targeting `main`, and manual dispatch.
It requests only `contents: read`, uses official GitHub actions, persists no checkout
credentials, uses no repository secrets, and does not deploy, push or upload datasets.

## Jobs and runtime

| Job ID | GitHub check name | Purpose |
| --- | --- | --- |
| `repository-checks` | Repository checks | Working-tree whitespace plus the latest commit diff (full PR diff against the target parent for PR merge checkouts) |
| `quality` | Code quality | Ruff, ESLint and check-only Prettier before test jobs |
| `python-tests` | Python tests | Source-audit fixtures followed by every remaining Python test |
| `frontend` | Frontend tests & build | Lockfile installation, frontend unit tests and Vite production compilation |

All jobs run on `ubuntu-24.04`. `quality` needs `repository-checks`; both test
jobs need `quality`, and the frontend build follows its tests. Ruff is installed
from the pinned test requirements with `--no-deps`, so quality checks do not
install the scientific runtime stack. Frontend quality uses `npm ci`. ESLint
and Prettier only check files; CI never formats the checkout. Software failures
are blocking. There are no
non-blocking test steps. Concurrency cancels superseded runs on the same ref.
Python and frontend jobs finish with `git diff --check` and `git diff --exit-code HEAD`,
even after a failed step. These detect changes to tracked files without failing on
ignored caches, temporary fixtures or `frontend/dist`.

Python **3.14** matches the documented project interpreter. The scientific
requirement pins resolve to compatible CPython 3.14 Linux wheels in a pip dry run.
Node **24 LTS** satisfies Vite 8's declared `^20.19.0 || >=22.12.0` engine range.
See the [Node release schedule](https://nodejs.org/en/about/previous-releases).

A single pip invocation installs the SHAP chain, optimizer and test requirements.
The SHAP chain already includes XGBoost, ML, data and base requirements; pip resolves
the shared dependencies once. Scientific/runtime pins are unchanged; Ruff is a
test-only requirement. Setup-python caches
pip downloads using all `backend/requirements*.txt` files as the cache input.
The tracked `frontend/package-lock.json` supports `npm ci`; setup-node caches
npm downloads keyed by that lockfile.

## Code-quality policy

- Ruff 0.16.10 checks Python under `backend/`, `scripts/` and `tests/` with
  Python 3.14 syntax. `E4`, `E7`, `E9`, `F` and `I` catch import placement/order,
  syntax and common correctness issues. The one `E402` exception in the heat-map
  build script is necessary because it inserts the repository root into
  `sys.path` before importing the backend. The `B` set was evaluated but deferred:
  25 existing `zip` calls need a behavior review before enforcing explicit
  strictness. Ruff does not format Python in this workflow.
- ESLint 9.39.5 uses a flat config with browser globals for application files
  and Node globals for tests and configuration. Core recommended rules catch
  undefined and unused names, unreachable code and duplicate cases; React
  rules account for JSX imports, Hook use/dependencies and refresh exports.
  ESLint 9 matches the current React plugin peer range; an ESLint 10 upgrade
  should follow plugin compatibility review.
- Prettier 3.9.9 checks `App`, shared components, services, utilities and their
  tests, plus the entry point and frontend configuration. Large route pages and
  the stylesheet are outside this first formatting baseline: formatting them
  would add several thousand unrelated line changes. ESLint still checks every
  JS/JSX file, including those pages. `npm run format` is a local write command;
  CI runs `format:check` only.

Tool defaults exclude dependency, build, virtualenv, cache, data, model and
temporary directories. No satellite rasters or generated provenance reports
are linted.

## Dataset independence

Every checkout disables LFS (`lfs: false`, `GIT_LFS_SKIP_SMUDGE=1`) and uses shallow
history. Raster pointers are sufficient; real Landsat files are never audited in CI.
The explicitly named **Source audit tests** step runs:

```sh
python -m pytest -q tests/test_landsat_source_audit.py tests/test_landsat_processing_audit.py tests/test_landsat_extreme_audit.py tests/test_sentinel_source_audit.py
```

The rest of the suite runs without repeating those files:

```sh
python -m pytest tests -q \
  --ignore=tests/test_landsat_source_audit.py \
  --ignore=tests/test_landsat_processing_audit.py \
  --ignore=tests/test_landsat_extreme_audit.py \
  --ignore=tests/test_sentinel_source_audit.py
```

These two steps cover the complete suite. Fixtures use temporary locations; no
source verification status or production audit report is written. Small synthetic
model fits are part of the existing software tests; no production model is trained.
HTTP tests use the in-process test client, not a deployed backend or satellite service.

Runtime production preflight is intentionally **omitted**: an LFS pointer is not
a raster, and a code-only checkout cannot establish real-data readiness. Missing
Sentinel, municipal boundaries, real ML grid and model must not fail software CI.
Synthetic tests still exercise preflight/import errors, evidence gates, QA and
publication rollback. Production validation is unchanged and remains a separate
operator task; no failure is suppressed to manufacture a readiness PASS.

The CI work also isolates tests that previously depended on a pre-existing `tmp`
directory, actual repository source availability, or a locally installed WorldPop
raster. The real processors and API behavior are unchanged.

## Local verification

From an environment with Python 3.14 and Node 24:

```sh
python -m pip install -r backend/requirements-shap.txt -r backend/requirements-optimizer.txt -r backend/requirements-test.txt
python -m pip check
python -m ruff check backend scripts tests
python -m pytest tests -q
cd frontend
npm ci
npm run lint
npm test
npm run build
cd ..
git diff --check
```

The workflow sets `MPLBACKEND=Agg` and limits numeric-library threads to one for
headless, bounded test execution. The PowerShell helper
[`test_full_system.ps1`](../scripts/test_full_system.ps1) remains available locally;
the Linux workflow uses portable commands directly.

Local verification used Python 3.14.7 and Node 24.19.0 on Windows. A clean
`npm ci`, Ruff, ESLint, Prettier check, 217 Python tests with 24 subtests,
39 frontend tests and the production build passed. The Python suite emitted
144 dependency deprecation warnings. The project-health command reported all
seven software checks PASS while the production source gate remained pending.
YAML syntax/dependencies and `git diff --check` were checked locally. These
results do not establish the status of a hosted GitHub Actions run; Linux and
unpinned transitive dependencies may differ. For a current local software and
source-status check on Windows, use [project health](project_health.md).
