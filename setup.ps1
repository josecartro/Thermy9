$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path 'upstream/paperang-cli/pyproject.toml')) {
    git clone https://github.com/wyrtensi/paperang-cli.git upstream/paperang-cli
    if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
}
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required' }
}
& ./.venv/Scripts/python.exe -m pip install bleak==3.0.2
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
docker build -t thermy9-render:local -f docker/Dockerfile .
if ($LASTEXITCODE -ne 0) { throw 'Renderer build failed. Check Docker Desktop is running.' }
Write-Host 'Ready. Open Start Thermy9.cmd.'
