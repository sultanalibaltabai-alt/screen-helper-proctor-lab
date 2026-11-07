@echo off
setlocal
cd /d "%~dp0"
if not exist "ScreenHelper.exe" goto incomplete
if not exist "_internal\python313.dll" goto incomplete
if exist "network-check.json" del /q "network-check.json"
echo Checking the configured API provider. No key or screenshot is sent.
start "" /wait "%~dp0ScreenHelper.exe" --network-check
if not exist "network-check.json" goto fail
type network-check.json
echo.
echo HTTP 401 is expected without a key and confirms API connectivity.
echo Gemini may return HTTP 403 without a key; this also confirms an HTTP response.
echo Connection reset / DNS / timeout means a network connection problem.
pause
exit /b 0
:incomplete
echo Extract ALL files from the ZIP before running Network.cmd.
pause
exit /b 2
:fail
echo Network check could not finish.
pause
exit /b 1
