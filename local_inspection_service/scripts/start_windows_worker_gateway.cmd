@echo off
setlocal

if not defined VANTALINE_WORKER_HOST set "VANTALINE_WORKER_HOST=100.103.240.14"
if not defined VANTALINE_WORKER_PORT set "VANTALINE_WORKER_PORT=8766"
if not defined VANTALINE_LOCAL_BASE_URL set "VANTALINE_LOCAL_BASE_URL=http://127.0.0.1:8765"
if not defined VANTALINE_LOCATEANYTHING_BASE_URL set "VANTALINE_LOCATEANYTHING_BASE_URL=http://127.0.0.1:8000"
if not defined VANTALINE_QWEN_BASE_URL set "VANTALINE_QWEN_BASE_URL=http://100.103.240.14:8080"
if not defined PYTHON_EXE set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
if not defined VANTALINE_WORKER_RESTART_DELAY_SECONDS set "VANTALINE_WORKER_RESTART_DELAY_SECONDS=5"

set "WORKER_SCRIPT=%~dp0windows_worker_gateway.py"
set "LOG_DIR=%~dp0..\data"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:supervise
powershell.exe -NoProfile -Command "try { $headers = @{}; if ($env:VANTALINE_WORKER_TOKEN) { $headers['Authorization'] = 'Bearer ' + $env:VANTALINE_WORKER_TOKEN }; $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Headers $headers 'http://%VANTALINE_WORKER_HOST%:%VANTALINE_WORKER_PORT%/health'; if ($r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if "%ERRORLEVEL%"=="0" (
  timeout /t %VANTALINE_WORKER_RESTART_DELAY_SECONDS% /nobreak >nul
  goto supervise
)

echo [%date% %time%] Starting Windows worker gateway on %VANTALINE_WORKER_HOST%:%VANTALINE_WORKER_PORT% >> "%LOG_DIR%\windows_worker_gateway_supervisor.log"
"%PYTHON_EXE%" "%WORKER_SCRIPT%" >> "%LOG_DIR%\windows_worker_gateway.out.log" 2>> "%LOG_DIR%\windows_worker_gateway.err.log"
echo [%date% %time%] Worker gateway exited with %ERRORLEVEL%; restarting after %VANTALINE_WORKER_RESTART_DELAY_SECONDS%s >> "%LOG_DIR%\windows_worker_gateway_supervisor.log"
timeout /t %VANTALINE_WORKER_RESTART_DELAY_SECONDS% /nobreak >nul
goto supervise
