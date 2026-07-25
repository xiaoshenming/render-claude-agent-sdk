param(
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string]$ManimPython,
    [Parameter(Mandatory = $true)][string]$RuntimePythonPath,
    [int]$Concurrency = 2,
    [int]$CaseTimeout = 900
)

$ErrorActionPreference = "Stop"
$PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AgentRoot = Join-Path $PackageRoot "agent"
$AgentPython = Join-Path $AgentRoot ".venv\Scripts\python.exe"
$Inputs = Join-Path $PackageRoot "reproduction_inputs\MathPi_17"
if (-not $env:QUALITY_MODEL) {
    throw "QUALITY_MODEL is not set"
}

Push-Location $AgentRoot
try {
    & $AgentPython scripts\run_unified_quality_batch.py `
        --package $Inputs `
        --output $Output `
        --repo $AgentRoot `
        --model $env:QUALITY_MODEL `
        --manim-python (Resolve-Path -LiteralPath $ManimPython).Path `
        --runtime-python-path (Resolve-Path -LiteralPath $RuntimePythonPath).Path `
        --concurrency $Concurrency `
        --case-timeout $CaseTimeout `
        --max-turns 16 `
        --max-tool-calls 18
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

