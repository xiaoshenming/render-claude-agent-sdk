param(
    [Parameter(Mandatory = $true)]
    [string]$ManimPython,
    [switch]$RequireApiKey
)

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$arguments = @(
    (Join-Path $PSScriptRoot 'scripts\handoff_doctor.py'),
    '--manim-python',
    $ManimPython
)
if ($RequireApiKey) {
    $arguments += '--require-api-key'
}
& $python @arguments
exit $LASTEXITCODE
