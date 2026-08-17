$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\pythonw.exe")) {
    throw "尚未创建运行环境，请先执行 .\setup.ps1"
}

Start-Process -FilePath ".\.venv\Scripts\pythonw.exe" -ArgumentList "-m", "ytb_gui"

