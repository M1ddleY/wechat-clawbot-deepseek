# 本项目使用嵌入版 Python（D:\codex\python313），无需系统安装 Python。
$py = "D:\codex\python313\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[错误] 未找到 $py，请先安装/解压嵌入版 Python 3.13 到该路径。"
    exit 1
}
& $py -m pip install --no-warn-script-location -r requirements.txt
Write-Host "`n[完成] 依赖已就绪。运行 run.bat 启动机器人。"
