@echo off
setlocal
cd /d "%~dp0"
if exist "ScreenHelper.exe" goto portable
if not exist "helper.py" goto incomplete
if not exist ".venv\Scripts\pythonw.exe" goto missing
if not exist "config.local.json" goto missing
start "" ".venv\Scripts\pythonw.exe" "%~dp0helper.py"
exit /b 0
:portable
if not exist "_internal\python313.dll" goto incomplete
if not exist "config.local.json" goto missing
start "" "%~dp0ScreenHelper.exe"
exit /b 0
:missing
echo Run Setup.cmd first.
pause
exit /b 1
:incomplete
echo Extract ALL files from the ZIP before launching Start.cmd.
echo ScreenHelper.exe and the _internal folder must be beside Start.cmd.
pause
exit /b 2
