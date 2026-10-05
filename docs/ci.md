# Software continuous integration

The `GreenPulse CI` workflow is defined in [ci.yml](../.github/workflows/ci.yml).
It runs on pushes to `main`, pull requests targeting `main`, and manual dispatch.
It requests only `contents: read`, uses official GitHub actions, persists no checkout
credentials, uses no repository secrets, and does not deploy, push or upload datasets.

## Jobs and runtime

| Job ID | GitHub check name | Purpose |
| --- | --- | --- |
| `repository-checks` | Repository checks | Working-tree whitespace plus the latest commit diff (full PR diff against the target parent for PR merge checkouts) |
| `python-tests` | Python tests | Source-audit fixtures followed by every remaining Python test |
| `frontend` | Frontend tests & build | Lockfile installation, frontend unit tests and Vite production compilation |

All jobs run on `ubuntu-24.04`. Software failures are blocking. There are no
non-blocking test steps. Concurrency cancels superseded runs on the same ref.
Python and frontend jobs finish with `git diff --check` and `git diff --exit-code HEAD`,
even after a failed step. These detect changes to tracked files without failing on
ignored caches, temporary fixtures or `frontend/dist`.

Python **3.14** matches the documented project interpreter. The unchanged pinned
requirements resolve to compatible CPython 3.14 Linux wheels in a pip dry run.
Node **24 LTS** satisfies Vite 8's declared `^20.19.0 || >=22.12.0` engine range.
See the [Node release schedule](https://nodejs.org/en/about/previous-releases).

A single pip invocation installs the SHAP chain, optimizer and test requirements.
The SHAP chain already includes XGBoost, ML, data and base requirements; pip resolves
the shared dependencies once. No project pins were changed. Setup-python caches
pip downloads using all `backend/requirements*.txt` files as the cache input.
The existing tracked `frontend/package-lock.json` supports `npm ci`; setup-node
caches npm downloads keyed by that lockfile. No new lockfile was generated.

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
python -m pytest tests -q
cd frontend
npm ci
npm test
npm run build
cd ..
git diff --check
```

The workflow sets `MPLBACKEND=Agg` and limits numeric-library threads to one for
headless, bounded test execution. The PowerShell helper
[`test_full_system.ps1`](../scripts/test_full_system.ps1) remains available locally;
the Linux workflow uses portable commands directly.

Local preparation used Python 3.14.7 and Node 24.19.0 on Windows. Dedicated source
audit tests passed (35 tests); the complete source-only suite passed (178 tests and
24 subtests, 144 dependency deprecation warnings). The snapshot contained LFS
pointers and no production WorldPop, Sentinel, ML grid or model. A clean `npm ci`,
17 frontend tests and the production build passed; tracked snapshot files were
unchanged. YAML syntax/structure and whitespace were checked locally.

This is not a recorded GitHub Actions success: the workflow has not been committed,
pushed or executed on GitHub during preparation. Linux runtime behavior still needs
its first hosted run. Dependency resolution is a compatibility check, not Linux test
execution; unpinned transitive Python dependencies may resolve differently later.
