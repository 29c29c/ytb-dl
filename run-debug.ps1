$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "The virtual environment is missing. Run .\setup.ps1 first."
}

& .\.venv\Scripts\python.exe -m ytb_gui

