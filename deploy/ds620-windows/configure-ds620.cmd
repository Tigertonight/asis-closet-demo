@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -STA -File "%~dp0configure-ds620.ps1" -PrinterName "DS620"
if errorlevel 1 (
  echo Configuration did not complete. See the message above and README.md.
) else (
  echo Configuration completed. Close and reopen the browser before printing.
)
pause
