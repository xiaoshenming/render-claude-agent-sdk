param(
    [Parameter(Mandatory = $true)]
    [string]$ManimPython,
    [string]$Output = (Join-Path $PSScriptRoot 'runs\existing-code-smoke')
)

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python (Join-Path $PSScriptRoot 'scripts\run_existing_code_e2e.py') `
    --code (Join-Path $PSScriptRoot 'handoff_data\existing_code_real\candidate.py') `
    --problem (Join-Path $PSScriptRoot 'handoff_data\existing_code_real\problem.txt') `
    --expected-solution (Join-Path $PSScriptRoot 'handoff_data\existing_code_real\expected_solution.txt') `
    --manim-python $ManimPython `
    --output $Output `
    --allow-vendor-clean-fallback
exit $LASTEXITCODE
