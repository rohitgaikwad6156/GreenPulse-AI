[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontend = Join-Path $projectRoot "frontend"
$helper = Join-Path $PSScriptRoot "project_health.py"

# Match CI's bounded numeric test execution without changing project files.
$env:MPLBACKEND = "Agg"
$env:PYTHONUTF8 = "1"
$env:OMP_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:NUMBA_NUM_THREADS = "1"

$pythonOk = Test-Path -LiteralPath $python -PathType Leaf
$frontendOk = Test-Path -LiteralPath $frontend -PathType Container
$dependenciesOk = $frontendOk -and (Test-Path -LiteralPath (Join-Path $frontend "node_modules\.bin\vite.cmd") -PathType Leaf)
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
$git = Get-Command git.exe -ErrorAction SilentlyContinue
$environment = [ordered]@{
    "Virtualenv Python" = $(if ($pythonOk) { "AVAILABLE" } else { "MISSING: .venv Python" })
    "npm" = $(if ($npm) { "AVAILABLE" } else { "MISSING: npm.cmd" })
    "Frontend directory" = $(if ($frontendOk) { "AVAILABLE" } else { "MISSING: frontend directory" })
    "Frontend dependencies" = $(if ($dependenciesOk) { "AVAILABLE" } else { "MISSING: frontend/node_modules" })
    "Git" = $(if ($git) { "AVAILABLE" } else { "MISSING: git.exe" })
}

function Invoke-HealthCheck {
    param([string]$Executable, [string[]]$Arguments, [string]$Directory)
    Push-Location $Directory
    try {
        # Native stderr is diagnostic output; the process exit code decides PASS.
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $output = @(& $Executable @Arguments 2>&1 | ForEach-Object { $_.ToString() })
            $code = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $previousPreference }
    }
    finally { Pop-Location }
    if ($code -eq 0) {
        $line = $output | Where-Object { $_ -match "passed|built in|pass [0-9]+" } | Select-Object -Last 1
        return @{ status = "PASS"; detail = $(if ($line) { $line.Trim() } else { "Completed successfully" }) }
    }
    return @{ status = "FAIL"; detail = "Exit code $code; rerun this check for its full log";
              output = @($output | Select-Object -Last 35);
              omitted = [Math]::Max(0, $output.Count - 35) }
}

function Invoke-RepositoryDiffCheck {
    param([string]$GitExecutable, [string]$Directory)
    $arguments = @(
        @("diff", "--check"),
        @("diff", "--cached", "--check")
    )
    Push-Location $Directory
    try {
        & $GitExecutable rev-parse --verify "HEAD^" *> $null
        $hasParent = $LASTEXITCODE -eq 0
    }
    finally { Pop-Location }
    if ($hasParent) { $arguments += ,@("diff", "--check", "HEAD^", "HEAD") }
    else { $arguments += ,@("show", "--format=", "--check", "HEAD") }
    foreach ($argsForCheck in $arguments) {
        $result = Invoke-HealthCheck $GitExecutable $argsForCheck $Directory
        if ($result.status -ne "PASS") { return $result }
    }
    return @{ status = "PASS"; detail = "Working tree, staged diff and latest commit checked" }
}

$results = [ordered]@{}
$results.python_tests = if ($pythonOk) {
    Invoke-HealthCheck $python @("-m", "pytest", "tests", "-q") $projectRoot
} else { @{ status = "NOT RUN"; detail = ".venv Python missing" } }
$results.frontend_tests = if ($npm -and $frontendOk -and $dependenciesOk) {
    Invoke-HealthCheck $npm.Source @("test") $frontend
} else { @{ status = "NOT RUN"; detail = "npm, frontend directory or dependencies missing" } }
$results.frontend_build = if ($npm -and $frontendOk -and $dependenciesOk) {
    Invoke-HealthCheck $npm.Source @("run", "build") $frontend
} else { @{ status = "NOT RUN"; detail = "npm, frontend directory or dependencies missing" } }
$results.repository_diff = if ($git) {
    Invoke-RepositoryDiffCheck $git.Source $projectRoot
} else { @{ status = "NOT RUN"; detail = "Git missing" } }

$checks = [ordered]@{}
foreach ($key in $results.Keys) { $checks[$key] = $results[$key].status }
$softwareReady = @($checks.Values | Where-Object { $_ -ne "PASS" }).Count -eq 0
$health = $null
$helperProblem = $null
if ($pythonOk -and (Test-Path -LiteralPath $helper -PathType Leaf)) {
    $checksJson = ConvertTo-Json -InputObject $checks -Compress
    $previousChecks = [Environment]::GetEnvironmentVariable("GREENPULSE_HEALTH_CHECKS_JSON", "Process")
    $env:GREENPULSE_HEALTH_CHECKS_JSON = $checksJson
    try { $helperOutput = & $python -B $helper }
    finally {
        [Environment]::SetEnvironmentVariable("GREENPULSE_HEALTH_CHECKS_JSON", $previousChecks, "Process")
    }
    if ($LASTEXITCODE -eq 0) {
        try { $health = $helperOutput | ConvertFrom-Json }
        catch { $helperProblem = "Health evidence output was invalid JSON" }
    } else { $helperProblem = "Readiness helper failed" }
} else { $helperProblem = "Readiness helper or .venv Python missing" }
if (-not $health) { $softwareReady = $false }

Write-Output "GreenPulse AI Project Health"
Write-Output "============================"
Write-Output ""
Write-Output "ENVIRONMENT"
foreach ($key in $environment.Keys) { Write-Output ("{0,-29} {1}" -f $key, $environment[$key]) }
Write-Output ""
Write-Output "SOFTWARE"
foreach ($item in @(
    @{key="python_tests"; label="Backend / Python tests"},
    @{key="frontend_tests"; label="Frontend unit tests"},
    @{key="frontend_build"; label="Frontend production build"},
    @{key="repository_diff"; label="Repository diff check"}
)) {
    $result = $results[$item.key]
    Write-Output ("{0,-29} {1}" -f $item.label, $result.status)
    if ($result.status -ne "PASS") {
        Write-Output ("  Reason: {0}" -f $result.detail)
        if ($result.omitted -gt 0) { Write-Output ("  Earlier diagnostic lines omitted: {0}" -f $result.omitted) }
        if ($result.output) { $result.output | ForEach-Object { Write-Output ("  {0}" -f $_) } }
    }
}
Write-Output ""
Write-Output "DATA EVIDENCE"
if ($health) {
    foreach ($item in @(
        @{key="landsat_source_audit"; label="Landsat source audit"},
        @{key="landsat_processing_audit"; label="Landsat processing audit"},
        @{key="landsat_extreme_diagnostics"; label="Landsat extreme diagnostics"},
        @{key="sentinel_manual_intake"; label="Sentinel manual intake"},
        @{key="pmc_boundary"; label="PMC boundary"},
        @{key="pcmc_boundary"; label="PCMC boundary"},
        @{key="worldcover"; label="ESA WorldCover"},
        @{key="osm_roads"; label="OSM roads"},
        @{key="worldpop"; label="WorldPop (later stage)"},
        @{key="ward_gis"; label="Ward GIS (reporting only)"}
    )) { Write-Output ("{0,-29} {1}" -f $item.label, $health.data_evidence.($item.key)) }
} else { Write-Output "Source evidence              UNAVAILABLE" }
Write-Output ""
Write-Output "PRODUCTION"
if ($health) {
    $production = $health.production
    $gate = if ($null -eq $production.required_sources_total) { "UNKNOWN" } else { "{0} / {1} READY" -f $production.required_sources_ready, $production.required_sources_total }
    Write-Output ("{0,-29} {1}" -f "Required sources", $gate)
    Write-Output ("{0,-29} {1}" -f "Real ML grid", $production.ml_grid)
    Write-Output ("{0,-29} {1}" -f "XGBoost model", $production.xgboost_model)
} else {
    Write-Output "Required sources             UNKNOWN"
    Write-Output "Real ML grid                 UNAVAILABLE"
    Write-Output "XGBoost model                UNAVAILABLE"
}
Write-Output ""
Write-Output "SUMMARY"
Write-Output ("{0,-29} {1}" -f "Overall software", $(if ($softwareReady) { "READY" } else { "NOT READY" }))
Write-Output ("{0,-29} {1}" -f "Overall production", $(if ($health) { $health.overall.production } else { "PRODUCTION READINESS UNKNOWN" }))
Write-Output ""
Write-Output "NEXT BLOCKERS"
if ($health -and $null -ne $health.production.required_sources_total) {
    if ($health.production.blockers.Count -eq 0) { Write-Output "None at the source gate; run production preflight before processing." }
    else {
        $number = 1
        foreach ($blocker in $health.production.blockers) {
            Write-Output ("{0}. {1}" -f $number, $blocker.name)
            $number++
        }
    }
} else { Write-Output "Unable to determine blockers from repository evidence." }
if ($helperProblem) { Write-Output ("Health check: {0}" -f $helperProblem) }

# Pending climate data is an expected state. Only software/environment failures
# and an unusable health implementation affect this process exit code.
if ($softwareReady) { exit 0 }
exit 1
