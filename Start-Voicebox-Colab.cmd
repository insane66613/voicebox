@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_voicebox_colab_runtime.ps1" %*
if errorlevel 1 (
  echo.
  echo Voicebox Colab runtime startup failed. Review the error above.
  pause
  exit /b 1
)
endlocal
