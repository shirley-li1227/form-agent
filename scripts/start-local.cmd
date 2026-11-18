@echo off
rem Logon autostart: start agent(8000), gateway(3000), web preview(4173), cloudflared tunnel
rem Pure cmd implementation, no PowerShell dependency.
rem Log: %LOCALAPPDATA%\form-agent-boot.log
setlocal
set "ROOT=D:\MyProject\form-agent"
set "LOG=%LOCALAPPDATA%\form-agent-autostart.log"
cd /d "%ROOT%"
echo [%date% %time%] boot begin >> "%LOG%"

for %%P in (8000 3000 4173) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do (
    taskkill /F /PID %%A >> "%LOG%" 2>&1
  )
)
ping -n 4 127.0.0.1 >nul

start "form-agent-api" /min "%ROOT%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
set "AI_AGENT_BASE_URL=http://127.0.0.1:8000"
set "PORT=3000"
start "form-agent-gateway" /min /d "%ROOT%\form-gateway-nest" node dist\main.js
start "form-agent-web" /min /d "%ROOT%\form-web-react" node node_modules\vite\bin\vite.js preview --port 4173

if exist "%LOCALAPPDATA%\cloudflared\cloudflared.exe" (
  start "form-agent-tunnel" /min "%LOCALAPPDATA%\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:4173 --protocol http2
)

echo [%date% %time%] boot end >> "%LOG%"
endlocal
