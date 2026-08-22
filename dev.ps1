<#
dev.ps1 — start the Enterprise Architecture backend and frontend together.

Usage (from the repo root):
  .\dev.ps1

Opens two PowerShell windows:
- Backend : uvicorn src.main:app --reload --port 8000  (http://127.0.0.1:8000)
- Frontend: npm run dev                                 (Vite, http://localhost:6769)

Close either window (or Ctrl+C in it) to stop that service.

If script execution is blocked, run once in this session:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

$root = $PSScriptRoot

# Single-quote the paths so directories with spaces (e.g. "Py Apps") work.
# Use the venv's python directly so no activation / PATH setup is needed.
$backendCmd  = "Set-Location -LiteralPath '$root\backend'; .\venv\Scripts\python.exe -m uvicorn src.main:app --reload --port 8000"
$frontendCmd = "Set-Location -LiteralPath '$root\frontend'; npm run dev"

Write-Host "Starting backend (uvicorn) and frontend (vite) in separate windows..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList '-NoExit', '-Command', $backendCmd
Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontendCmd

Write-Host "Both services launched. Backend: http://127.0.0.1:8000  Frontend: http://localhost:6769" -ForegroundColor Green
