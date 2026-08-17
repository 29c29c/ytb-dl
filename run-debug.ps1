$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "尚未创建运行环境，请先执行 .\setup.ps1"
}

& .\.venv\Scripts\python.exe -m ytb_gui

