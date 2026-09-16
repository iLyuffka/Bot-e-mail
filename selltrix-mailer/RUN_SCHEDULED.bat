@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "UV_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "!UV_EXE!" exit /b 1
if not exist "!PYTHON_EXE!" exit /b 1
"!UV_EXE!" run --python "!PYTHON_EXE!" --no-python-downloads "%~dp0scheduled.py" %*
