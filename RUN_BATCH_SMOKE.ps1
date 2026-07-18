param(
    [Parameter(Mandatory = $true)]
    [string]$ManimPython,
    [string]$Output = (Join-Path $PSScriptRoot 'runs\batch-smoke')
)

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python (Join-Path $PSScriptRoot 'scripts\run_handoff_batch.py') `
    --manim-python $ManimPython `
    --output $Output `
    --slot slot-001 `
    --workers 1
exit $LASTEXITCODE
