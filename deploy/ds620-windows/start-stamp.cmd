@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -STA -File "%~dp0start-stamp.ps1"
if errorlevel 1 (
  echo The stamp window was not started. See the message above and README.md.
  pause
)
