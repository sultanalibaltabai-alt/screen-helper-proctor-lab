@echo off
setlocal
cd /d "%~dp0"
if exist "ScreenHelper.exe" (
  start "" "%~dp0ScreenHelper.exe" --panel
  exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "%~dp0helper.py" --panel
  exit /b 0
)
echo Extract the portable archive or run Setup.cmd first.
pause
