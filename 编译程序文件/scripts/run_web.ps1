# 一键启动 Web 前端（Windows PowerShell）
# 用法：在项目根目录运行：
#   powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "[1/2] 安装/更新 web 依赖..." -ForegroundColor Cyan
py -3 -m pip install -r web/requirements.txt

Write-Host "[2/2] 启动 Flask... (浏览器打开 http://127.0.0.1:5000 )" -ForegroundColor Cyan
py -3 web/app.py

