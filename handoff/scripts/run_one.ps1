param(
    [Parameter(Mandatory = $true)][string]$Candidate,
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string]$ManimPython,
    [string[]]$RuntimePythonPath = @(),
    [string]$AssetsDir,
    [string]$Problem,
    [int]$MaxTurns = 24,
    [int]$MaxToolCalls = 40
)

$ErrorActionPreference = "Stop"
$PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AgentRoot = Join-Path $PackageRoot "agent"
$AgentPython = Join-Path $AgentRoot ".venv\Scripts\python.exe"
if (-not $env:QUALITY_MODEL) {
    throw "QUALITY_MODEL is not set"
}

$Arguments = @(
    "-m", "manim_quality.operator",
    "--candidate", (Resolve-Path -LiteralPath $Candidate).Path,
    "--workspace", (Resolve-Path -LiteralPath $Workspace).Path,
    "--output", $Output,
    "--model", $env:QUALITY_MODEL,
    "--manim-python", (Resolve-Path -LiteralPath $ManimPython).Path,
    "--max-turns", $MaxTurns,
    "--max-tool-calls", $MaxToolCalls
)
foreach ($root in $RuntimePythonPath) {
    $Arguments += @("--runtime-python-path", (Resolve-Path -LiteralPath $root).Path)
}
if ($AssetsDir) {
    $Arguments += @("--assets-dir", (Resolve-Path -LiteralPath $AssetsDir).Path)
}
if ($Problem) {
    $Arguments += @("--problem", (Resolve-Path -LiteralPath $Problem).Path)
}

Push-Location $AgentRoot
try {
    & $AgentPython @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

