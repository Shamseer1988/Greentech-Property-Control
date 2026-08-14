# Stop every process started by start-all.ps1.
# Closes the labelled PowerShell windows by title.
$ErrorActionPreference = "Continue"
foreach ($title in "greentech-backend", "greentech-worker", "greentech-beat", "greentech-frontend") {
    $procs = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowTitle -eq $title
    }
    if ($procs) {
        Write-Host "Stopping $title (PID $($procs.Id -join ', '))..."
        $procs | Stop-Process -Force
    }
}
# Belt-and-braces: kill any orphaned waitress / celery / next processes,
# but ONLY ones running out of this repo — other portals on the same box
# must survive.
$root = (Resolve-Path "$PSScriptRoot\..").Path
Get-Process waitress-serve, celery, node -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and ($_.Path -like "$root*")
} | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "Done."
