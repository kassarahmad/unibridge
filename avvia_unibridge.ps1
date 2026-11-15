# UniBridge - starts everything locally: Qdrant (Docker), LM Studio model, API and Streamlit demo.
# Usage (from this folder):  powershell -ExecutionPolicy Bypass -File .\avvia_unibridge.ps1
$ErrorActionPreference = "Continue"   # native tools (docker, lms) write progress on stderr
Set-Location $PSScriptRoot
$Model = "qwen3vl-8b-instruct"

Write-Host "[1/5] Docker and Qdrant..." -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running: starting it, wait..." -ForegroundColor Yellow
    Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    $t = 0
    do { Start-Sleep 3; $t += 3; docker info *> $null } while ($LASTEXITCODE -ne 0 -and $t -lt 120)
    if ($LASTEXITCODE -ne 0) { throw "Docker Desktop did not start within 2 minutes" }
}
$exists = docker ps -a --filter "name=^p14-qdrant$" --format "{{.Names}}"
if ($exists) { docker start p14-qdrant | Out-Null; Write-Host "Qdrant container started" } else { cmd /c "docker compose up -d" }

Write-Host "[2/5] LM Studio server and model $Model (GPU, 8k context)..." -ForegroundColor Cyan
lms server start --port 1234
$loaded = (lms ps) -join "`n"
if ($loaded -notmatch [regex]::Escape($Model)) {
    lms load $Model --gpu max -c 8192 --identifier $Model
} else { Write-Host "model already loaded" }

Write-Host "[3/5] API on port 8001 (new window)..." -ForegroundColor Cyan
# stop an API left running from before (it would keep the old .env settings)
Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; .venv\Scripts\python.exe -m uvicorn p14_search.unibridge_main:app --port 8001"
$t = 0; $ok = $false
do {
    Start-Sleep 2; $t += 2
    try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/docs -TimeoutSec 2 *> $null; $ok = $true } catch {}
} while (-not $ok -and $t -lt 90)
if (-not $ok) { throw "The API did not start: look at the API window for the error" }

Write-Host "[4/5] Check of the local LLM (IT / EN / AR)..." -ForegroundColor Cyan
.venv\Scripts\python.exe scripts\check_local_llm.py

Write-Host "[5/5] Streamlit demo (new window) -> http://localhost:8501" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; .venv\Scripts\streamlit.exe run frontend\unibridge_app.py"
Write-Host "Done. API docs: http://127.0.0.1:8001/docs   Demo: http://localhost:8501" -ForegroundColor Green
