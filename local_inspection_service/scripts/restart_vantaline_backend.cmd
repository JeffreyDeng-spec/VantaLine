@echo off
REM One-click restart of the local VantaLine training backend (port 8765).
REM The supervisor (start_windows_vantaline_backend.cmd) auto-relaunches uvicorn
REM with the latest server.py once the running process exits, so this just
REM terminates the current (stale) backend and confirms it comes back.
setlocal

REM --- Self-elevate: the backend runs elevated, so we need admin to stop it. ---
net session >nul 2>&1
if %errorLevel% neq 0 (
  echo Requesting administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo [%date% %time%] Stopping VantaLine backend on port 8765...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if ($c) { $c | ForEach-Object { Write-Host ('Stopping PID ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force } } else { Write-Host 'No backend currently listening on 8765 (supervisor will start it).' }"

echo Waiting for supervisor to relaunch the backend...
set /a tries=0
:wait
timeout /t 3 /nobreak >nul
set /a tries+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:8765/api/auth/status'; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if %errorLevel%==0 (
  echo [%date% %time%] Backend is back up and healthy on port 8765.
  goto done
)
if %tries% geq 12 (
  echo Backend did not come back automatically. Start it manually with:
  echo   scripts\start_windows_vantaline_backend.cmd
  goto done
)
goto wait

:done
echo Done. New training jobs will now run "yolo detect train" with yolo26s.pt.
pause
