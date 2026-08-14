@echo off
setlocal
cd /d "%~dp0"
title Paperplane

where pwsh.exe >nul 2>&1
if errorlevel 1 (
    echo PowerShell 7 ^(pwsh.exe^) is required to start Paperplane.
    echo Install it, then double-click this file again.
    pause
    exit /b 1
)

pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" -OpenBrowser
set "paperplane_exit=%ERRORLEVEL%"

if not "%paperplane_exit%"=="0" (
    echo.
    echo Paperplane stopped with exit code %paperplane_exit%.
    pause
)

exit /b %paperplane_exit%
