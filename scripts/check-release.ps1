param(
    [switch]$WithMemoryEval,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

Invoke-Step "Backend syntax check" {
    python -m py_compile api.py memory.py agent_loop.py agent_planner.py agent.py
}

Invoke-Step "API integration tests" {
    python -m pytest tests/test_api.py -q --basetemp tests/.tmp/pytest -p no:cacheprovider
}

if ($WithMemoryEval) {
    Invoke-Step "Memory evaluation" {
        python scripts/eval_memory.py
    }
}

if (-not $SkipFrontend) {
    Push-Location (Join-Path $root "frontend")
    try {
        Invoke-Step "Frontend lint" {
            npm.cmd run lint
        }
        Invoke-Step "Frontend build" {
            npm.cmd run build
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Release checks passed." -ForegroundColor Green
