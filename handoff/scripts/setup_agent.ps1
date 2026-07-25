param(
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
$PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AgentRoot = Join-Path $PackageRoot "agent"
$VenvPython = Join-Path $AgentRoot ".venv\Scripts\python.exe"

function Assert-LastCommand([string]$Label) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $AgentRoot -PathType Container)) {
    throw "Agent source directory not found: $AgentRoot"
}

function Find-Python311 {
    if ($PythonExecutable) {
        return (Resolve-Path -LiteralPath $PythonExecutable).Path
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return $candidate.Trim()
        }
    }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $candidate = & uv python find 3.11 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return $candidate.Trim()
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidate = & python -c `
            "import sys; print(sys.executable if sys.version_info[:2] == (3, 11) else '')"
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return $candidate.Trim()
        }
    }
    throw "Python 3.11 not found. Install it or pass -PythonExecutable."
}

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    $BootstrapPython = Find-Python311
    & $BootstrapPython -m venv (Join-Path $AgentRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Python 3.11 virtual environment."
    }
}

& $VenvPython -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version"
Assert-LastCommand "Python version check"
& $VenvPython -m pip install --upgrade pip
Assert-LastCommand "pip upgrade"
& $VenvPython -m pip install -e "$AgentRoot[dev]"
Assert-LastCommand "Agent dependency installation"

Push-Location $AgentRoot
try {
    $OverlapRoot = Join-Path $AgentRoot ".vendor\quality_repair"
    if (-not (Test-Path -LiteralPath $OverlapRoot -PathType Container)) {
        & $VenvPython scripts\materialize_quality_repair.py
        Assert-LastCommand "Active overlap runtime materialization"
    }
    & $VenvPython -c `
        "from pathlib import Path; from manim_quality.layout.vendor_runtime import MaterializedQualityRepair; MaterializedQualityRepair(Path(r'$OverlapRoot')); print('Active overlap runtime: OK')"
    Assert-LastCommand "Active overlap runtime verification"
    & $VenvPython -m pytest `
        tests\unit\test_vendor_materialization.py `
        tests\unit\agents `
        tests\unit\operator `
        tests\integration\test_overlap_adapter.py `
        tests\integration\test_overlap_safety.py -q
    Assert-LastCommand "Focused Agent and overlap tests"
    & $VenvPython -m ruff check .
    Assert-LastCommand "Ruff"
    & $VenvPython scripts\check_engineering_standards.py
    Assert-LastCommand "Engineering standards"
}
finally {
    Pop-Location
}

Write-Host "Agent environment is ready: $VenvPython" -ForegroundColor Green
