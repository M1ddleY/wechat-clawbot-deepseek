# 一键创建虚拟环境并安装依赖
$ErrorActionPreference = "Stop"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未检测到 Python，请先安装 Python 3.10+。"
    exit 1
}
python -m venv .venv
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 创建虚拟环境失败。"; exit 1 }
.\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
.\.venv\Scripts\pip.exe install -r requirements.txt
Write-Host "`n[完成] 依赖已安装。运行 run.bat 启动机器人。"
