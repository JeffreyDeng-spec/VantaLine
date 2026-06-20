@echo off
setlocal

if not defined VANTALINE_LOCAL_HOST set "VANTALINE_LOCAL_HOST=127.0.0.1"
if not defined VANTALINE_LOCAL_PORT set "VANTALINE_LOCAL_PORT=8765"
if not defined VANTALINE_BACKEND_RESTART_DELAY_SECONDS set "VANTALINE_BACKEND_RESTART_DELAY_SECONDS=5"
if not defined PYTHON_EXE set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "LOG_DIR=%SCRIPT_DIR%..\data"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:supervise
powershell.exe -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://%VANTALINE_LOCAL_HOST%:%VANTALINE_LOCAL_PORT%/api/auth/status'; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if "%ERRORLEVEL%"=="0" (
  timeout /t %VANTALINE_BACKEND_RESTART_DELAY_SECONDS% /nobreak >nul
  goto supervise
)

echo [%date% %time%] Starting local VantaLine backend on %VANTALINE_LOCAL_HOST%:%VANTALINE_LOCAL_PORT% >> "%LOG_DIR%\windows_vantaline_backend_supervisor.log"
pushd "%REPO_ROOT%"
"%PYTHON_EXE%" -m uvicorn local_inspection_service.server:app --host "%VANTALINE_LOCAL_HOST%" --port "%VANTALINE_LOCAL_PORT%" --proxy-headers >> "%LOG_DIR%\windows_vantaline_backend.out.log" 2>> "%LOG_DIR%\windows_vantaline_backend.err.log"
set "BACKEND_EXIT=%ERRORLEVEL%"
popd
echo [%date% %time%] Local VantaLine backend exited with %BACKEND_EXIT%; restarting after %VANTALINE_BACKEND_RESTART_DELAY_SECONDS%s >> "%LOG_DIR%\windows_vantaline_backend_supervisor.log"
timeout /t %VANTALINE_BACKEND_RESTART_DELAY_SECONDS% /nobreak >nul
goto supervise
