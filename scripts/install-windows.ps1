# One-time install of the bare-metal dependencies on Windows.
# Run from the REPO ROOT in PowerShell:
#     Set-ExecutionPolicy -Scope Process Bypass
#     .\scripts\install-windows.ps1
#
# What this script does:
#  1. Resolves a real Python 3.11 interpreter (prefers the `py` launcher,
#     falls back to `python` on PATH, refuses the Microsoft Store stub).
#  2. Verifies node / npm / psql are on PATH.
#  3. Creates a Python venv under backend\.venv and installs requirements.
#  4. Runs `npm ci` + `npm run build` for the frontend.
#  5. Seeds backend\.env from backend\.env.example on first run.
#
# It does NOT install PostgreSQL / Redis themselves — those are operator
# steps documented in docs/DEPLOYMENT.md.

$ErrorActionPreference = "Stop"
Set-Location -Path "$PSScriptRoot\.."

# -----------------------------------------------------------------------------
# Resolve a real Python interpreter.
#
# Priority:
#   1. $env:PYTHON_EXE — operator override (full path to python.exe).
#   2. py -3.11        — official Python Launcher for Windows; picks the right
#                        install even when the Microsoft Store stub is on PATH.
#   3. python          — last resort; rejected if it's the Store stub.
# -----------------------------------------------------------------------------
Write-Host "=== Resolving Python 3.11 ===" -ForegroundColor Cyan

function Test-RealPython($exe) {
    # The Microsoft Store stub returns exit 9009 with a specific message.
    # A real Python prints a version string and exits 0.
    try {
        $output = & $exe -c "import sys; print(sys.version_info[:2])" 2>&1
        if ($LASTEXITCODE -eq 0 -and $output -match "\(3, 1[1-9]\)") {
            return $true
        }
    } catch { }
    return $false
}

$pythonCmd = $null
$pythonArgs = @()

if ($env:PYTHON_EXE -and (Test-Path $env:PYTHON_EXE)) {
    if (Test-RealPython $env:PYTHON_EXE) {
        $pythonCmd = $env:PYTHON_EXE
        Write-Host "  using PYTHON_EXE = $env:PYTHON_EXE"
    } else {
        Write-Error "PYTHON_EXE points at $env:PYTHON_EXE but it's not a real Python 3.11+."
    }
}

if (-not $pythonCmd) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $test = & $py.Source -3.11 -c "import sys; print(sys.version_info[:2])" 2>&1
        if ($LASTEXITCODE -eq 0 -and $test -match "\(3, 1[1-9]\)") {
            $pythonCmd = $py.Source
            $pythonArgs = @("-3.11")
            Write-Host "  using py -3.11 → $(& $py.Source -3.11 -c "import sys; print(sys.executable)")"
        }
    }
}

if (-not $pythonCmd) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -like "*\WindowsApps\*") {
        Write-Error @"
The `python` on your PATH (`$($python.Source)`) is the Microsoft Store
stub, not a real Python install. Pick one of these to continue:

  Option A (recommended) — install the Python Launcher
    The standard installer from https://www.python.org/downloads/windows/
    ships `py.exe` and adds it to PATH. Once installed, rerun this script.

  Option B — point this script at your real Python
    `$env:PYTHON_EXE = 'C:\Users\Shamseer\AppData\Local\Programs\Python\Python311\python.exe'`
    `.\scripts\install-windows.ps1`

  Option C — disable the Store stub
    Settings → Apps → Advanced app settings → App execution aliases
    → toggle OFF the two `python.exe` / `python3.exe` entries.
    Open a NEW PowerShell window (PATH cache is per-session) and rerun.
"@
    }
    if ($python -and (Test-RealPython $python.Source)) {
        $pythonCmd = $python.Source
        Write-Host "  using python → $($python.Source)"
    }
}

if (-not $pythonCmd) {
    Write-Error "No Python 3.11+ found. See docs/DEPLOYMENT.md."
}

# -----------------------------------------------------------------------------
# Other prereqs — just check they're on PATH.
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Other prereqs ===" -ForegroundColor Cyan
foreach ($cmd in "node", "npm", "psql") {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $found) {
        Write-Error "$cmd not found in PATH. Install it (see docs/DEPLOYMENT.md) and re-run."
    }
    $path = if ($found.Path) { $found.Path } else { $found.Source }
    Write-Host "  $cmd : $path"
}

# -----------------------------------------------------------------------------
# Create / update the venv.
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Backend venv ===" -ForegroundColor Cyan
if (-not (Test-Path "backend\.venv\Scripts\python.exe")) {
    Write-Host "  creating backend\.venv …"
    & $pythonCmd @pythonArgs -m venv backend\.venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "backend\.venv\Scripts\python.exe")) {
        Write-Error "venv creation failed. Stub Python? Try `$env:PYTHON_EXE = 'C:\path\to\real\python.exe'`."
    }
} else {
    Write-Host "  backend\.venv already exists — reusing."
}

& backend\.venv\Scripts\python.exe -m pip install --upgrade pip
& backend\.venv\Scripts\pip.exe install -r backend\requirements.txt -r backend\requirements-dev.txt

# -----------------------------------------------------------------------------
# Frontend.
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Frontend build ===" -ForegroundColor Cyan
Push-Location frontend
npm ci
npm run build
Pop-Location

# -----------------------------------------------------------------------------
# Seed backend\.env on first run.
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "=== backend\.env ===" -ForegroundColor Cyan
if (-not (Test-Path "backend\.env")) {
    Copy-Item "backend\.env.example" "backend\.env"
    Write-Host "  copied backend\.env.example -> backend\.env"
    Write-Host "  EDIT backend\.env to set strong SECRET_KEY / JWT_SECRET_KEY / POSTGRES_PASSWORD before running scripts\start-all.ps1."
} else {
    Write-Host "  backend\.env already exists — left alone."
}

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Green
Write-Host "  1. Edit backend\.env (secrets, DB password)."
Write-Host "  2. Create the Postgres database + role (see docs/DEPLOYMENT.md)."
Write-Host "  3. Run: .\scripts\bootstrap-db.ps1   (one-time schema + seed)"
Write-Host "  4. Run: .\scripts\start-all.ps1     (every time)"
