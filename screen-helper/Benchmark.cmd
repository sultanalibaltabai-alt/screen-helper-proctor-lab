@echo off
cd /d "%~dp0"
echo Tests 3 sample images per configured provider. API usage is billed normally.
echo OpenAI is skipped when openai.local.json is not configured. No desktop capture.
start "" /wait "%~dp0ScreenHelper.exe" --benchmark
if exist "benchmark.json" type benchmark.json
pause
