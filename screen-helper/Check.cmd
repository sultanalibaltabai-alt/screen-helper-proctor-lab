@echo off
setlocal
cd /d "%~dp0"
if not exist "ScreenHelper.exe" goto incomplete
if not exist "_internal\python313.dll" goto incomplete
if exist "self-check.json" del /q "self-check.json"
echo Close any running Screen Helper with Ctrl+Alt+Q before checking.
start "" /wait "%~dp0ScreenHelper.exe" --self-check
if not exist "self-check.json" goto fail
type self-check.json
echo.
echo This checks the program only. It does not test OES or call the API.
pause
exit /b 0
:incomplete
echo Extract ALL files from the ZIP before running Check.cmd.
pause
exit /b 2
:fail
echo The check did not finish successfully.
pause
exit /b 1
