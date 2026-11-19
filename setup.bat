@echo off
title BMU Sketch-to-Art Kiosk Setup (Windows)
echo ======================================================
echo    BMU Founder's Day - Sketch-to-Art Kiosk Setup
echo                  Windows Installer
echo ======================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo         Please install Python 3.9+ from https://www.python.org/downloads/
    echo         (Make sure to check "Add Python to PATH" during installation)
    echo.
    pause
    exit /b 1
)

echo [1/3] Upgrading pip and installing Python requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo [2/3] Checking FFmpeg installation...
where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] FFmpeg is NOT detected in your Windows PATH.
    echo     FFmpeg is required to composite the commemorative video.
    echo.
    echo     To install FFmpeg on Windows, run this in PowerShell as Administrator:
    echo         winget install Gyan.FFmpeg
    echo     Or download from https://www.gyan.dev/ffmpeg/builds/ and add bin to PATH.
    echo.
) else (
    echo [+] FFmpeg is installed and ready!
)

echo.
echo [3/3] Creating outputs directory...
if not exist outputs mkdir outputs

echo.
echo ======================================================
echo   Setup Complete!
echo   Double-click run_bridge.bat to start the server.
echo ======================================================
echo.
pause
