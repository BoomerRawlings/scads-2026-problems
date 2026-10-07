param([int]$Port = 8764, [string]$Database = 'runs/workspace.sqlite3')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe') -or -not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
        throw 'Run ./scripts/setup.ps1 first.'
    }
    Write-Host "Organization Atlas: http://127.0.0.1:$Port (Ctrl+C to stop)"
    & ./.venv/Scripts/python.exe -m orggraph --db $Database serve --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Server stopped with an error.' }
} finally { Pop-Location }
