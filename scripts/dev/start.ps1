Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

Write-Host "Starting TridentWear at http://127.0.0.1:8000"
Write-Host "Press Ctrl+C to stop the server."
Write-Host ""

python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
