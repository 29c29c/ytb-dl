$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\pythonw.exe")) {
    throw "The virtual environment is missing. Run .\setup.ps1 first."
}

Start-Process -FilePath ".\.venv\Scripts\pythonw.exe" -ArgumentList "-m", "ytb_gui"

