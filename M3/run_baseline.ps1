param(
    [string]$InputCsv = (Join-Path $PSScriptRoot "failed_drive_histories.csv"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "baseline_output"),
    [int]$Bootstraps = 2000,
    [int]$Seed = 2026
)
$ErrorActionPreference = "Stop"
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Project interpreter not found: $Python" }
& $Python (Join-Path $PSScriptRoot "baseline.py") --input $InputCsv --output-dir $OutputDir --bootstraps $Bootstraps --seed $Seed
if ($LASTEXITCODE -ne 0) { throw "Baseline exited with code $LASTEXITCODE" }
