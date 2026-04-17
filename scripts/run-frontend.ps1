Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$frontendDir = Join-Path $repoRoot "frontend"
$envFile = Join-Path $frontendDir ".env.local"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Missing $envFile. Run scripts/run-api.ps1 first so the frontend knows which API URL to use."
}

$apiUrl = ""
foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -like "NEXT_PUBLIC_API_URL=*") {
        $apiUrl = $line.Substring("NEXT_PUBLIC_API_URL=".Length).Trim()
        break
    }
}

if (-not $apiUrl) {
    throw "NEXT_PUBLIC_API_URL was not found in $envFile. Run scripts/run-api.ps1 again."
}

Write-Host ""
Write-Host "DeepResearch Frontend"
Write-Host "  API URL: $apiUrl"
Write-Host "  Frontend: http://127.0.0.1:3000"
Write-Host ""

Push-Location $frontendDir
try {
    $env:NEXT_PUBLIC_API_URL = $apiUrl
    npm run dev
}
finally {
    Pop-Location
}
