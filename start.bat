@echo off
REM BloodSync Startup Script for Windows
REM Helps diagnose and run the application

echo.
echo ==========================================
echo BloodSync Application Launcher
echo ==========================================
echo.

REM Check Python
echo Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo X Python is not installed
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
echo + Python found: %PYVER%
echo.

REM Check dependencies
echo Checking dependencies...
python -c "import flask; import boto3" >nul 2>&1
if %errorlevel% neq 0 (
    echo X Missing dependencies. Installing...
    pip install flask boto3
    if %errorlevel% neq 0 (
        echo X Failed to install dependencies
        exit /b 1
    )
)
echo + Dependencies OK
echo.

REM Check AWS credentials
echo Checking AWS configuration...
aws sts get-caller-identity >nul 2>&1
if %errorlevel% neq 0 (
    echo X AWS credentials not configured
    echo Please run: aws configure
    exit /b 1
)
echo + AWS credentials OK
echo.

REM Run app
echo ==========================================
echo Starting BloodSync Application
echo ==========================================
echo.
echo The app will start on: http://0.0.0.0:5000
echo Health check: http://YOUR_IP:5000/health
echo Logs: See console and %TEMP%\bloodsync.log
echo.
echo Press Ctrl+C to stop
echo.

python AWS_app.py
