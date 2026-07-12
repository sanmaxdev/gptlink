@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo GPTLink is not installed yet. Running setup...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-GPTLink.ps1"
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" run.py

