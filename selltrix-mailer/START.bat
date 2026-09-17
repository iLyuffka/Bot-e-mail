@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  set "UV_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"
  if not exist "!UV_EXE!" (
    echo Install uv first: winget install --id astral-sh.uv -e
    echo Then reopen this file. Read README.txt for instructions.
    pause
    exit /b 1
  )
) else (
  set "UV_EXE=uv"
)
py -3 -c "import sys, tkinter; assert sys.version_info >= (3,11)" >nul 2>nul
if errorlevel 1 (
  set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  if not exist "!PYTHON_EXE!" (
    echo Install Python 3.11 or newer with Tcl/Tk and Python Launcher:
    echo https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
) else (
  for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%P"
)
"%UV_EXE%" run --python "%PYTHON_EXE%" --no-python-downloads "%~dp0app.py"
if errorlevel 1 pause
