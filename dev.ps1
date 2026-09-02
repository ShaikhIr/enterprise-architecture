<#
    dev.ps1 — start (or stop) the Enterprise Architecture backend and frontend together.

    Usage (from the repo root):
        .\dev.ps1          # start both services
        .\dev.ps1 -Kill    # stop both services AND close their windows

    Start opens two PowerShell windows:
      - Backend : uvicorn src.main:app --reload --port 8000  (http://127.0.0.1:8000)
      - Frontend: npm run dev                                 (Vite, http://localhost:6769)

    Close either window (or Ctrl+C in it) to stop that service, or run
    `.\dev.ps1 -Kill` to stop both at once and close both windows.

    If script execution is blocked, run once in this session:
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

[CmdletBinding()]
param(
    # Stop both services and close their windows instead of starting them.
    [switch]$Kill
)

$root = $PSScriptRoot

# Window titles used to tag the two launcher terminals so -Kill can find and
# close the exact windows this script opened (not any other PowerShell window).
$backendTitle  = 'enterprise-architecture-dev-backend'
$frontendTitle = 'enterprise-architecture-dev-frontend'

function Stop-ProcessTree {
    <#
        Stop a process and all of its descendants. Killing the launcher
        PowerShell window this way also takes down uvicorn/Vite and their
        child processes (reload worker, esbuild, etc.) running inside it.
    #>
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }

    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host ("  Closing PID {0} ({1})" -f $proc.Id, $proc.ProcessName) -ForegroundColor DarkGray
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-DevWindow {
    <#
        Find the launcher PowerShell window by its unique title and close the
        whole tree, which stops the dev server running inside it and closes the
        terminal window itself.
    #>
    param([string]$Title, [string]$Label)

    # The window title is set via `$host.UI.RawUI.WindowTitle`; the process
    # command line still carries the title token we passed, so match on that.
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Title*" }

    if (-not $procs) {
        Write-Host ("{0}: no window found (title '{1}')." -f $Label, $Title) -ForegroundColor DarkYellow
        return
    }

    foreach ($p in $procs) {
        Write-Host ("{0}: closing window and stopping service..." -f $Label) -ForegroundColor Yellow
        Stop-ProcessTree -ProcessId $p.ProcessId
    }
}

if ($Kill) {
    Write-Host "Stopping services and closing their windows..." -ForegroundColor Cyan
    Stop-DevWindow -Title $backendTitle  -Label 'Backend'
    Stop-DevWindow -Title $frontendTitle -Label 'Frontend'
    Write-Host "Done. Both windows closed." -ForegroundColor Green
    return
}

# --- Start both services --------------------------------------------------

# Single-quote the paths so directories with spaces (e.g. "Py Apps") work.
# Use the venv's python directly so no activation / PATH setup is needed.
# The window title is set first so -Kill can later locate this exact window.
$backendCmd  = "`$host.UI.RawUI.WindowTitle = '$backendTitle'; Set-Location -LiteralPath '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --port 8000"
$frontendCmd = "`$host.UI.RawUI.WindowTitle = '$frontendTitle'; Set-Location -LiteralPath '$root\frontend'; npm run dev"

Write-Host "Starting backend (uvicorn) and frontend (vite) in separate windows..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList '-NoExit', '-Command', $backendCmd
Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontendCmd

Write-Host "Both services launched. Backend: http://127.0.0.1:8000  Frontend: http://localhost:6769" -ForegroundColor Green
Write-Host "To stop both and close their windows, run: .\dev.ps1 -Kill" -ForegroundColor Cyan
