@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || goto :failure
title Paperplane
set "UV_LINK_MODE=copy"

echo.
echo ========================================
echo   Paperplane launcher
echo ========================================
echo.

rem A new launcher run replaces only an existing Paperplane Streamlit process.
powershell.exe -NoProfile -Command "$connection = Get-NetTCPConnection -LocalPort 8551 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if (-not $connection) { exit 0 }; $owner = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $connection.OwningProcess); if (($owner.CommandLine -like '*streamlit run workspace_app.py*') -or ($owner.CommandLine -like '*paperplane.streamlit_runner run workspace_app.py*')) { Stop-Process -Id $connection.OwningProcess -Force; Wait-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue; exit 10 }; exit 20"
set "PORT_RESULT=%ERRORLEVEL%"
if "%PORT_RESULT%"=="10" echo Stopped the previous Paperplane run.
if "%PORT_RESULT%"=="20" goto :port_in_use
if not "%PORT_RESULT%"=="0" if not "%PORT_RESULT%"=="10" goto :setup_failure

if not exist "pyproject.toml" (
    echo ERROR: pyproject.toml was not found next to Paperplane.cmd.
    goto :failure
)
if not exist "uv.lock" (
    echo ERROR: uv.lock was not found next to Paperplane.cmd.
    goto :failure
)
if not exist "workspace_app.py" (
    echo ERROR: workspace_app.py was not found next to Paperplane.cmd.
    goto :failure
)

rem Refresh credentials from the current Windows user's environment registry.
rem This avoids stale values inherited from a long-running Explorer process.
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v OPENAI_API_KEY 2^>nul') do if /i "%%A"=="OPENAI_API_KEY" set "OPENAI_API_KEY=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v OPENAI_BASE_URL 2^>nul') do if /i "%%A"=="OPENAI_BASE_URL" set "OPENAI_BASE_URL=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v XAI_API_KEY 2^>nul') do if /i "%%A"=="XAI_API_KEY" set "XAI_API_KEY=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v GOOGLE_API_KEY 2^>nul') do if /i "%%A"=="GOOGLE_API_KEY" set "GOOGLE_API_KEY=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v GEMINI_API_KEY 2^>nul') do if /i "%%A"=="GEMINI_API_KEY" set "GEMINI_API_KEY=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v ANTHROPIC_API_KEY 2^>nul') do if /i "%%A"=="ANTHROPIC_API_KEY" set "ANTHROPIC_API_KEY=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v AGNES_API_KEY 2^>nul') do if /i "%%A"=="AGNES_API_KEY" set "AGNES_API_KEY=%%C"
for /f "tokens=1,2,*" %%A in ('reg.exe query "HKCU\Environment" /v OLLAMA_BASE_URL 2^>nul') do if /i "%%A"=="OLLAMA_BASE_URL" set "OLLAMA_BASE_URL=%%C"

call :find_uv
if not defined UV_EXE (
    echo Installing uv because it is not available...
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

echo uv is ready.

call :find_soffice
if not defined SOFFICE_EXE (
    echo Installing LibreOffice because it is not available...
    where winget.exe >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Windows Package Manager is required to install LibreOffice automatically.
        goto :setup_failure
    )
    winget install --id TheDocumentFoundation.LibreOffice --exact --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 goto :setup_failure
    call :find_soffice
) else (
    echo LibreOffice is ready.
)
if not defined SOFFICE_EXE (
    echo ERROR: LibreOffice was installed but soffice.com could not be located.
    goto :setup_failure
)

set "TORCH_EXTRA=cpu"
where nvidia-smi.exe >nul 2>&1 && set "TORCH_EXTRA=cu130"
set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
set "VENV_DOCLING=%CD%\.venv\Scripts\docling-tools.exe"

echo Checking the locked Python environment...
"%UV_EXE%" sync --check --locked --python 3.12.10 --extra %TORCH_EXTRA% >nul 2>&1
if not errorlevel 1 goto :dependencies_ready
if /i "%TORCH_EXTRA%"=="cu130" (
    "%UV_EXE%" sync --check --locked --python 3.12.10 --extra cpu >nul 2>&1
    if not errorlevel 1 (
        set "TORCH_EXTRA=cpu"
        goto :dependencies_ready
    )
)

echo Python or locked dependencies are missing or out of date.
"%UV_EXE%" python find 3.12.10 >nul 2>&1
if errorlevel 1 (
    echo Installing Python 3.12.10...
    "%UV_EXE%" python install 3.12.10
    if errorlevel 1 goto :setup_failure
)

echo Synchronizing locked dependencies with the %TORCH_EXTRA% PyTorch backend...
"%UV_EXE%" sync --locked --python 3.12.10 --extra %TORCH_EXTRA% --link-mode copy
if errorlevel 1 if /i "%TORCH_EXTRA%"=="cu130" (
    echo CUDA dependency setup failed. Retrying with the CPU backend...
    set "TORCH_EXTRA=cpu"
    "%UV_EXE%" sync --locked --python 3.12.10 --extra cpu --link-mode copy
)
if errorlevel 1 goto :setup_failure

:dependencies_ready
if not exist "%VENV_PYTHON%" goto :setup_failure
if not exist "%VENV_DOCLING%" goto :setup_failure
"%VENV_PYTHON%" -c "import torch.backends; from docling.datamodel.base_models import DocumentStream; from transformers import AutoModelForObjectDetection" >nul 2>&1
if not errorlevel 1 goto :runtime_ready
echo The Torch or Docling installation is incomplete. Repairing it...
"%UV_EXE%" sync --locked --python 3.12.10 --extra %TORCH_EXTRA% --link-mode copy --reinstall-package torch --reinstall-package torchvision
if errorlevel 1 goto :setup_failure
"%VENV_PYTHON%" -c "import torch.backends; from docling.datamodel.base_models import DocumentStream; from transformers import AutoModelForObjectDetection" >nul 2>&1
if errorlevel 1 goto :setup_failure

:runtime_ready
echo Locked Python environment is ready.

set "MODEL_ROOT=%USERPROFILE%\.cache\docling\models"
if defined DOCLING_CACHE_DIR set "MODEL_ROOT=%DOCLING_CACHE_DIR%\models"
set "MODELS_READY=1"
if not exist "%MODEL_ROOT%\docling-project--docling-layout-heron\model.safetensors" set "MODELS_READY="
if not exist "%MODEL_ROOT%\docling-project--docling-models\model_artifacts\tableformer\accurate\tableformer_accurate.safetensors" set "MODELS_READY="
if not exist "%MODEL_ROOT%\docling-project--docling-models\model_artifacts\tableformer\accurate\tm_config.json" set "MODELS_READY="
if not exist "%MODEL_ROOT%\RapidOcr\PP-OCRv6_det_small.pth" set "MODELS_READY="
if not exist "%MODEL_ROOT%\RapidOcr\PP-OCRv6_rec_small.pth" set "MODELS_READY="
if not exist "%MODEL_ROOT%\RapidOcr\ch_ptocr_mobile_v2.0_cls_mobile.pth" set "MODELS_READY="
if not exist "%MODEL_ROOT%\RapidOcr\PP-OCRv6_det_small.onnx" set "MODELS_READY="
if not exist "%MODEL_ROOT%\RapidOcr\PP-OCRv6_rec_small.onnx" set "MODELS_READY="
if not exist "%MODEL_ROOT%\RapidOcr\ch_ppocr_mobile_v2.0_cls_mobile.onnx" set "MODELS_READY="
if not exist "%MODEL_ROOT%\RapidOcr\ppocrv6_dict.txt" set "MODELS_READY="
if defined MODELS_READY goto :models_ready

echo Downloading local layout, table, and OCR models because they are not available...
"%VENV_DOCLING%" models download layout tableformer rapidocr --quiet
if errorlevel 1 goto :setup_failure

:models_ready
echo Local document models are ready.
"%VENV_PYTHON%" -m paperplane.ollama_ocr --check >nul 2>&1
if not errorlevel 1 goto :ollama_layout_ready
echo Downloading PP-DocLayoutV3 for Ollama OCR region detection...
"%VENV_PYTHON%" -m paperplane.ollama_ocr --download
if errorlevel 1 goto :setup_failure

:ollama_layout_ready
echo Ollama OCR layout model is ready.
echo Clearing previous Streamlit cache...
"%VENV_PYTHON%" -m streamlit cache clear >nul
if errorlevel 1 goto :setup_failure
echo Starting Paperplane...
echo Open http://127.0.0.1:8551 in your browser.
echo Close this window or press Ctrl+C to stop the app.
echo.
if not defined OPENAI_API_KEY if not defined XAI_API_KEY if not defined GOOGLE_API_KEY if not defined GEMINI_API_KEY if not defined ANTHROPIC_API_KEY if not defined AGNES_API_KEY (
    echo Note: No supported model API key is set in this terminal.
    echo Cloud AI and cloud enhancement require the key for the selected model.
    echo Docling, PDF Inspector, and a running local Ollama can work without a cloud key.
    echo.
)

"%VENV_PYTHON%" -m paperplane.streamlit_runner run workspace_app.py --server.port=8551
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

:find_soffice
set "SOFFICE_EXE="
for /f "delims=" %%I in ('where soffice.com 2^>nul') do if not defined SOFFICE_EXE set "SOFFICE_EXE=%%I"
if not defined SOFFICE_EXE if exist "%ProgramFiles%\LibreOffice\program\soffice.com" set "SOFFICE_EXE=%ProgramFiles%\LibreOffice\program\soffice.com"
if not defined SOFFICE_EXE if exist "%ProgramFiles(x86)%\LibreOffice\program\soffice.com" set "SOFFICE_EXE=%ProgramFiles(x86)%\LibreOffice\program\soffice.com"
exit /b 0

:setup_failure
echo.
echo ERROR: Paperplane setup failed.
echo Review the message above, check your internet connection, and try again.
goto :failure

:port_in_use
echo.
echo ERROR: Port 8551 is used by another application.
echo Stop that application, then run Paperplane again.
goto :failure

:failure
echo.
pause
exit /b 1
