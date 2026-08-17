$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$PythonCommand = $null
$PythonArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        & py -3 --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = "py"
            $PythonArgs = @("-3")
        }
    } catch {}
}

if (-not $PythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
    try {
        & python --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = "python"
        }
    } catch {}
}

if (-not $PythonCommand) {
    throw "A working Python was not found. Reopen PowerShell after installing Python 3.10 or newer (64-bit)."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $PythonCommand @PythonArgs -m venv .venv
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Failed to create .venv. Verify that Python is installed and available on PATH."
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
& .\.venv\Scripts\python.exe -m pip install --no-deps -e .

Write-Host ""
Write-Host "Python dependencies installed."
Write-Host "Make sure ffmpeg, ffprobe, and Deno are on PATH, then run .\run.ps1"
& .\.venv\Scripts\python.exe -c "from ytb_gui.diagnostics import run_diagnostics; [print(('OK  ' if x.available else 'MISS') + ' ' + x.name + ': ' + x.detail) for x in run_diagnostics()]"

