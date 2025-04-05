@echo off
echo SQL Agent Launcher
echo ------------------
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in the PATH.
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if pip is available
pip --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo pip is not available.
    echo Please make sure pip is installed with your Python installation.
    pause
    exit /b 1
)

REM Check if requirements are installed
echo Checking dependencies...
pip install -r requirements.txt

REM Run the Python launch script
echo Starting SQL Agent...
python run.py

pause
