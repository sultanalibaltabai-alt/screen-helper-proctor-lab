@echo off
setlocal
cd /d "%~dp0"
if exist "ScreenHelper.exe" goto portable
if not exist "helper.py" goto incomplete
if not exist "requirements.txt" goto incomplete
python -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" helper.py --configure
if errorlevel 1 goto fail
echo Ready. Run Start.cmd.
pause
exit /b 0
:portable
if not exist "_internal\python313.dll" goto incomplete
start "" /wait "%~dp0ScreenHelper.exe" --configure
exit /b 0
:incomplete
echo The archive has not been fully extracted.
echo Close this window. Right-click the ZIP and choose Extract All.
echo Open the extracted folder, then run Setup.cmd again.
echo Do not run CMD files directly from inside a ZIP archive.
pause
exit /b 2
:fail
echo Setup failed. Install Python 3.11 or newer with Add Python to PATH.
pause
exit /b 1
