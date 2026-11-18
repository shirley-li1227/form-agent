# 本机一键重载：重启后端 agent、按需重建前端、重启 preview 预览
# 用法：pwsh -File scripts\dev-reload.ps1
# 说明：本脚本只作用于本机开发环境；真正的容器部署请用 docker compose。

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$python = Join-Path $root '.venv\Scripts\python.exe'
$web = Join-Path $root 'form-web-react'
$distIndex = Join-Path $web 'dist\index.html'

# ---------- 1. 重启后端 ----------
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn app.main:app*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $root 'agent.out.log') `
    -RedirectStandardError (Join-Path $root 'agent.err.log')
Start-Sleep -Seconds 5

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 10
    Write-Output ("backend: " + ($health | ConvertTo-Json -Compress))
} catch {
    Write-Output ("backend FAILED: " + $_.Exception.Message)
    Write-Output (Get-Content -LiteralPath (Join-Path $root 'agent.err.log') -Tail 20)
    exit 1
}

# ---------- 2. 重启网关 ----------
$gw = Join-Path $root 'form-gateway-nest'
$gwDist = Join-Path $gw 'dist\main.js'

Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like '*dist\main.js*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$newestGwSrc = Get-ChildItem -LiteralPath (Join-Path $gw 'src') -Recurse -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ((-not (Test-Path -LiteralPath $gwDist)) -or
    ($newestGwSrc.LastWriteTime -gt (Get-Item -LiteralPath $gwDist).LastWriteTime)) {
    Write-Output 'gateway: rebuilding...'
    Push-Location -LiteralPath $gw
    npm run build 2>&1 | Select-Object -Last 3
    Pop-Location
}

$env:AI_AGENT_BASE_URL = 'http://127.0.0.1:8000'
$env:PORT = '3000'
Start-Process -FilePath (Get-Command node).Source `
    -ArgumentList 'dist\main.js' `
    -WorkingDirectory $gw -WindowStyle Hidden
Start-Sleep -Seconds 3

function Test-TcpPort([int]$port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect('127.0.0.1', $port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

$gatewayUp = $false
for ($i = 0; $i -lt 15; $i++) {
    if (Test-TcpPort 3000) { $gatewayUp = $true; break }
    Start-Sleep -Milliseconds 800
}

if ($gatewayUp) {
    Write-Output 'gateway: listening on 3000'
} else {
    Write-Output 'gateway FAILED: 3000 未监听，请查看 nest 启动日志'
}

# ---------- 3. 前端：仅在源码比产物新时重建 ----------
$newestSrc = Get-ChildItem -LiteralPath (Join-Path $web 'src') -Recurse -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$needBuild = (-not (Test-Path -LiteralPath $distIndex)) -or
             ($newestSrc.LastWriteTime -gt (Get-Item -LiteralPath $distIndex).LastWriteTime)

if ($needBuild) {
    Write-Output 'frontend: rebuilding...'
    Push-Location -LiteralPath $web
    npm run build 2>&1 | Select-Object -Last 4
    Pop-Location
} else {
    Write-Output 'frontend: dist is up to date, skip build'
}

# ---------- 3. 重启 preview（端口 4173） ----------
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like '*vite*preview*4173*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Start-Process -FilePath (Get-Command node).Source `
    -ArgumentList 'node_modules\vite\bin\vite.js', 'preview', '--port', '4173' `
    -WorkingDirectory $web -WindowStyle Hidden
Start-Sleep -Seconds 4

try {
    $page = Invoke-WebRequest -Uri 'http://127.0.0.1:4173/' -TimeoutSec 10
    Write-Output ("frontend: HTTP " + $page.StatusCode)
} catch {
    Write-Output ("frontend FAILED: " + $_.Exception.Message)
    exit 1
}

try {
    $rag = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/form/rag/status' -TimeoutSec 10
    Write-Output ("rag: " + ($rag | ConvertTo-Json -Compress))
} catch {
    Write-Output ("rag status FAILED: " + $_.Exception.Message)
}
