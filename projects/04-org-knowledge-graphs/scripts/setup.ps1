$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
        else { & python -m venv .venv }
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required to create the virtual environment.' }
    }
    & ./.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    & ./.venv/Scripts/python.exe -m pip install --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    Push-Location -LiteralPath frontend
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed. Node 20.19+ or 22.12+ is required.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    Write-Host 'Ready. Run ./scripts/start.ps1, then open http://127.0.0.1:8764.'
} finally { Pop-Location }
