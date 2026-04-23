Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $repoRoot "frontend"
$envFile = Join-Path $frontendDir ".env.local"

# Port: use env var API_PORT or default 8000
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$apiUrl = "http://localhost:$apiPort"

Set-Content -LiteralPath $envFile -Value "NEXT_PUBLIC_API_URL=$apiUrl`r`n" -Encoding utf8

Write-Host ""
Write-Host "DeepResearch"
Write-Host "  API     : $apiUrl  (logs in separate window)"
Write-Host "  Frontend: http://localhost:3000"
Write-Host ""

# Open API in a new PowerShell window (keeps logs visible)
$apiCmd = "Set-Location '$repoRoot'; python -m uvicorn api:app --host 0.0.0.0 --port $apiPort --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd

# Wait for API health check
Write-Host "Waiting for API..." -NoNewline
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    Write-Host "." -NoNewline
    try {
        $r = Invoke-WebRequest -Uri "$apiUrl/health" -TimeoutSec 1 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
Write-Host ""

if (-not $ready) {
    Write-Host "ERROR: API did not start within 30 s. Check the API window for errors."
    exit 1
}

Write-Host "API ready — starting frontend..."
Write-Host ""

Set-Location $frontendDir
$env:NEXT_PUBLIC_API_URL = $apiUrl
npm run dev
