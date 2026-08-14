@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || goto :failure
title Paperplane

echo.
echo ========================================
echo   Paperplane setup and launcher
echo ========================================
echo.

if not exist "pyproject.toml" (
    echo ERROR: pyproject.toml was not found next to Paperplane.cmd.
    goto :failure
)
if not exist "uv.lock" (
    echo ERROR: uv.lock was not found next to Paperplane.cmd.
    goto :failure
)
if not exist "streamlit_app.py" (
    echo ERROR: streamlit_app.py was not found next to Paperplane.cmd.
    goto :failure
)

rem Refresh credentials from the current Windows user's environment registry.
rem This avoids stale values inherited from a long-running Explorer process.
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v OPENAI_API_KEY 2^>nul') do if /i "%%A"=="OPENAI_API_KEY" set "OPENAI_API_KEY=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v OPENAI_BASE_URL 2^>nul') do if /i "%%A"=="OPENAI_BASE_URL" set "OPENAI_BASE_URL=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v AGNES_API_KEY 2^>nul') do if /i "%%A"=="AGNES_API_KEY" set "AGNES_API_KEY=%%C"

call :find_uv
if not defined UV_EXE (
    echo [1/5] Installing uv...
    where winget.exe >nul 2>&1
    if not errorlevel 1 (
        winget install --id astral-sh.uv --exact --silent --accept-package-agreements --accept-source-agreements
    )
    call :find_uv
)

if not defined UV_EXE (
    echo Windows Package Manager could not install uv.
    echo Trying the official uv installer from https://astral.sh/uv/ ...
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    call :find_uv
)

if not defined UV_EXE (
    echo ERROR: uv could not be installed automatically.
    echo Check your internet connection, then run Paperplane.cmd again.
    goto :failure
)

echo [1/5] uv is ready.
echo [2/5] Installing Python 3.12.10 if needed...
"%UV_EXE%" python install 3.12.10
if errorlevel 1 goto :setup_failure

echo [3/5] Creating the environment and installing locked dependencies...
"%UV_EXE%" sync --locked --python 3.12.10
if errorlevel 1 goto :setup_failure

echo [4/5] Downloading local document-layout models if needed...
"%UV_EXE%" run --locked --python 3.12.10 docling-tools models download layout tableformer --quiet
if errorlevel 1 goto :setup_failure

echo [5/5] Starting Paperplane...
echo Open http://127.0.0.1:8551 in your browser.
echo Close this window or press Ctrl+C to stop the app.
echo.
if not defined OPENAI_API_KEY (
    if not defined AGNES_API_KEY (
        echo Note: Neither OPENAI_API_KEY nor AGNES_API_KEY is set in this terminal.
        echo Scans and images require the key for the selected model.
    )
    echo.
)

"%UV_EXE%" run --locked --python 3.12.10 streamlit run streamlit_app.py --server.port=8551
set "PAPERPLANE_EXIT=%ERRORLEVEL%"
if not "%PAPERPLANE_EXIT%"=="0" (
    echo.
    echo Paperplane stopped with exit code %PAPERPLANE_EXIT%.
    pause
)
exit /b %PAPERPLANE_EXIT%

:find_uv
set "UV_EXE="
for /f "delims=" %%I in ('where uv.exe 2^>nul') do if not defined UV_EXE set "UV_EXE=%%I"
if not defined UV_EXE if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.cargo\bin\uv.exe"
if not defined UV_EXE if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
exit /b 0

:setup_failure
echo.
echo ERROR: Paperplane setup failed.
echo Review the message above, check your internet connection, and try again.
goto :failure

:failure
echo.
pause
exit /b 1
