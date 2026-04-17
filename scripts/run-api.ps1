Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$frontendDir = Join-Path $repoRoot "frontend"
$envFile = Join-Path $frontendDir ".env.local"

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

$port = Get-FreePort
$apiUrl = "http://127.0.0.1:$port"

Set-Content -LiteralPath $envFile -Value "NEXT_PUBLIC_API_URL=$apiUrl`r`n" -Encoding utf8

Write-Host ""
Write-Host "DeepResearch API"
Write-Host "  URL: $apiUrl"
Write-Host "  Frontend env: $envFile"
Write-Host ""

Push-Location $repoRoot
try {
    python -m uvicorn api:app --host 127.0.0.1 --port $port --reload
}
finally {
    Pop-Location
}
