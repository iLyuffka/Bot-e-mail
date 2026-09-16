@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Install uv first: winget install --id astral-sh.uv -e
  echo Then reopen this file. Read README.txt for instructions.
  pause
  exit /b 1
)
py -3 -c "import sys, tkinter; assert sys.version_info >= (3,11)" >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11 or newer with Tcl/Tk and Python Launcher:
  echo https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%P"
uv run --python "%PYTHON_EXE%" --no-python-downloads "%~dp0app.py"
if errorlevel 1 pause
