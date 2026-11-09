@echo off
setlocal
cd /d "%~dp0"
:menu
echo.
echo STUDY TOOLS 1.2.0 / SCREEN HELPER 8.4 - Windows x64
echo 1. Configure OpenAI API
echo 2. Open Screen Helper panel
echo 3. Start Proctor Lab Windows
echo 4. Read instructions
echo 5. Configure Gemini API (Google key)
echo 6. Use shared cloud service (no provider key on this PC)
echo 0. Exit
set "toolChoice="
set /p "toolChoice=Choose: "
if "%toolChoice%"=="1" call "%~dp0ScreenHelper\Setup-OpenAI.cmd"
if "%toolChoice%"=="2" call "%~dp0ScreenHelper\Control.cmd"
if "%toolChoice%"=="3" call "%~dp0ProctorLabAgent\Start.cmd"
if "%toolChoice%"=="4" start "" notepad.exe "%~dp0README_RU.md"
if "%toolChoice%"=="5" call "%~dp0ScreenHelper\Setup-Gemini.cmd"
if "%toolChoice%"=="6" call "%~dp0ScreenHelper\Setup-Cloud.cmd"
if "%toolChoice%"=="0" exit /b
goto menu
