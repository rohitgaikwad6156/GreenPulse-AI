$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontend = Join-Path $projectRoot "frontend"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python virtual environment missing. Create .venv in the GreenPulse-AI root first."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules") -PathType Container)) {
    throw "Frontend dependencies missing. Run npm install inside frontend first."
}

Push-Location $projectRoot
try {
    & $python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "Python test suite failed with exit code $LASTEXITCODE." }
    Push-Location $frontend
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed with exit code $LASTEXITCODE." }
    }
    finally { Pop-Location }
}
finally { Pop-Location }

Write-Host "GreenPulse automated checks passed: Python tests and frontend build."
