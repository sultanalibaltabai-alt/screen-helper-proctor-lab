@echo off
setlocal
cd /d "%~dp0"
if not exist "ScreenHelper.exe" goto incomplete
if not exist "_internal\python313.dll" goto incomplete
if not exist "config.local.json" goto configure
if exist "api-check.json" del /q "api-check.json"
echo Testing the configured API with a generated 2+2 question.
echo One image; primary and optional reserve may each retry once. Charges may apply.
echo No desktop capture. The report identifies the model that answered.
start "" /wait "%~dp0ScreenHelper.exe" --api-check
if not exist "api-check.json" goto fail
type api-check.json
echo.
echo Expected: answer B, ok true.
pause
exit /b 0
:configure
echo Run Setup.cmd first.
pause
exit /b 1
:incomplete
echo Extract ALL files from the ZIP before running ApiTest.cmd.
pause
exit /b 2
:fail
echo API check could not finish. Verify Setup.cmd settings.
pause
exit /b 1
