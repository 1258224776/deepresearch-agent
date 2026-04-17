param(
    [string[]]$PytestArgs = @("tests/test_rag_client.py", "tests/test_api.py", "-q")
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pytest @PytestArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
