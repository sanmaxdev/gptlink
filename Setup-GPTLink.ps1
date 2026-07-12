$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'Codex CLI is required but was not found.'
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & 'C:\Users\dream\AppData\Local\Programs\Python\Python311\python.exe' -m venv .venv
}

& '.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt

Write-Host ''
Write-Host 'GPTLink setup complete.' -ForegroundColor Green
Write-Host 'Run Launch-GPTLink.cmd to start the application.'

