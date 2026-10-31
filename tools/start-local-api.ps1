$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$tunnelScript = Join-Path $PSScriptRoot 'gigachat_tunnel.py'
foreach ($tunnelPort in @(8766, 8767)) {
    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $tunnelPort -State Listen -ErrorAction SilentlyContinue
    if (-not $listener) {
        Start-Process -FilePath $pythonPath -ArgumentList @('-u', $tunnelScript, '--port', $tunnelPort) -WorkingDirectory $projectRoot -WindowStyle Hidden
    }
}
Push-Location $projectRoot
try {
    # Recreate this one service so changes in backend/.env take effect too.
    docker compose up -d --no-deps --force-recreate api
    if ($LASTEXITCODE -ne 0) { throw 'API startup failed.' }
} finally {
    Pop-Location
}
