param(
    [Parameter(Mandatory = $true)]
    [string]$ManimPython,
    [string[]]$RuntimePythonPath = @()
)

$ErrorActionPreference = "Stop"
$PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AgentRoot = Join-Path $PackageRoot "agent"
$AgentPython = Join-Path $AgentRoot ".venv\Scripts\python.exe"
$Verifier = Join-Path $PackageRoot "handoff\scripts\verify_package.py"

& python $Verifier --root $PackageRoot
if (-not (Test-Path -LiteralPath $AgentPython -PathType Leaf)) {
    throw "Agent venv missing. Run handoff\scripts\setup_agent.ps1 first."
}
& $AgentPython -c "import manim_quality, claude_agent_sdk; print('Agent imports: OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Agent imports failed"
}
$OverlapRoot = Join-Path $AgentRoot ".vendor\quality_repair"
if (-not (Test-Path -LiteralPath $OverlapRoot -PathType Container)) {
    throw "Active overlap runtime is not materialized. Run setup_agent.ps1."
}

$ResolvedManim = (Resolve-Path -LiteralPath $ManimPython).Path
& $ResolvedManim -c "import manim; print('Manim:', manim.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Manim import failed"
}
foreach ($root in $RuntimePythonPath) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "Runtime Python path missing: $root"
    }
}

foreach ($command in @("ffmpeg", "ffprobe")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is not available on PATH"
    }
}
if (-not $env:ANTHROPIC_BASE_URL) {
    throw "ANTHROPIC_BASE_URL is not set"
}
if (-not ($env:ANTHROPIC_AUTH_TOKEN -or $env:ANTHROPIC_API_KEY)) {
    throw "ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY is not set"
}
if (-not $env:QUALITY_MODEL) {
    throw "QUALITY_MODEL is not set"
}

$Cases = Get-ChildItem (Join-Path $PackageRoot "reproduction_inputs\MathPi_17\cases") `
    -Directory -ErrorAction Stop
if ($Cases.Count -ne 17) {
    throw "Expected 17 reproduction cases, found $($Cases.Count)"
}
Write-Host "Preflight passed. Model: $env:QUALITY_MODEL; cases: 17" `
    -ForegroundColor Green
