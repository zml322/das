@echo off
setlocal
set "APP_PYTHON=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "APP_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
set "FIBER_DEV=1"
echo Start the frontend first: cd frontend, then npm run dev.
echo Development URL: http://localhost:5173
pushd "%~dp0desktop"
"%APP_PYTHON%" main.py
set "app_exit=%errorlevel%"
popd
if not "%app_exit%"=="0" (
    echo Application failed with exit code %app_exit%. See the error above.
    pause
)
exit /b %app_exit%
