@echo off
setlocal
cd /d "%~dp0"
if exist "ScreenHelper.exe" (
  start "" /wait "%~dp0ScreenHelper.exe" --configure-gemini
  exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" /wait "%~dp0.venv\Scripts\pythonw.exe" "%~dp0helper.py" --configure-gemini
  exit /b
)
echo Extract the full Windows portable archive first.
pause
