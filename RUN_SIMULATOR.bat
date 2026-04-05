@echo off
TITLE Star Citizen TTK Simulator Launcher
COLOR 0A

:: This forces the command prompt to look ONLY inside this specific folder
cd /d "%~dp0"

echo ===================================================
echo     Star Citizen TTK Simulator Initialization
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    COLOR 0C
    echo [ERROR] Python is not installed or not added to your PATH.
    pause
    exit
)

echo [OK] Python detected. Checking dependencies...
:: Tell Python directly to install the packages
python -m pip install streamlit pandas --quiet

echo [OK] Launching Local Web Server...
echo.

:: Tell Python directly to run the Streamlit module!
python -m streamlit run "%~dp0app.py"

pause