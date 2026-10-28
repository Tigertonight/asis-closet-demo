@echo off
setlocal
cd /d "%~dp0"
rem Only this PowerShell process; organizational Group Policy still takes precedence.
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0start-stamp.ps1"
if errorlevel 1 (
  echo The stamp window was not started. See the message above and README.md.
  pause
)
