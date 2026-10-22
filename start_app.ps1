$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "가상환경을 찾을 수 없습니다: $PythonExe"
}

Set-Location -LiteralPath $ProjectDir
& $PythonExe -m streamlit run app.py --server.headless true --server.port 8501
