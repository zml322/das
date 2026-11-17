@echo off
setlocal
set "APP_PYTHON=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "APP_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%~dp0frontend\dist\index.html" (
    echo Frontend build missing. Run install.bat first.
    pause
    exit /b 1
)
set "FIBER_DEV=0"
pushd "%~dp0desktop"
"%APP_PYTHON%" main.py
set "app_exit=%errorlevel%"
popd
if not "%app_exit%"=="0" (
    echo Application failed with exit code %app_exit%. See the error above.
    pause
)
exit /b %app_exit%
