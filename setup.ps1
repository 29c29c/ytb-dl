$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
    $PythonArgs = @("-3.11")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
    $PythonArgs = @()
} else {
    throw "未找到 Python。请先安装 Python 3.10 或更高版本（推荐 3.11 x64）。"
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $PythonCommand @PythonArgs -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
& .\.venv\Scripts\python.exe -m pip install --no-deps -e .

Write-Host ""
Write-Host "Python 依赖安装完成。"
Write-Host "请确认 ffmpeg、ffprobe 和 Deno 已加入 PATH，然后运行 .\run.ps1"
& .\.venv\Scripts\python.exe -c "from ytb_gui.diagnostics import run_diagnostics; [print(('OK  ' if x.available else 'MISS') + ' ' + x.name + ': ' + x.detail) for x in run_diagnostics()]"

