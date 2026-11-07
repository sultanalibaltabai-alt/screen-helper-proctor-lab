@echo off
setlocal
cd /d "%~dp0"
if not exist "ScreenHelper.exe" goto incomplete
if not exist "_internal\python313.dll" goto incomplete
if not exist "config.local.json" goto configure
if exist "multi-check.json" del /q "multi-check.json"
echo Testing 1, 2, and 3 questions. Retries and reserve may add requests/charges.
echo Only sample pictures are sent. The desktop is NOT captured.
start "" /wait "%~dp0ScreenHelper.exe" --multi-check
if not exist "multi-check.json" goto fail
type multi-check.json
echo.
echo Expected: all_ok true. This is not an OES compatibility test.
pause
exit /b 0
:configure
echo Run Setup.cmd first.
pause
exit /b 1
:incomplete
echo Extract ALL files from the ZIP before running MultiTest.cmd.
pause
exit /b 2
:fail
echo The check could not finish. Verify Setup.cmd settings.
pause
exit /b 1
