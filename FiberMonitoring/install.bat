@echo off
setlocal
set "APP_PYTHON=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "APP_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
pushd "%~dp0"
"%APP_PYTHON%" -m pip install -r desktop\requirements.txt
if errorlevel 1 goto failed
pushd frontend
call npm ci
if errorlevel 1 goto failed_frontend
call npm run build:check
if errorlevel 1 goto failed_frontend
popd
popd
echo Installation complete. Run start.bat to launch the desktop application.
exit /b 0
:failed_frontend
popd
:failed
popd
echo Installation failed. See the error above. Python 3.11+ and Node.js 18+ are required.
pause
exit /b 1
