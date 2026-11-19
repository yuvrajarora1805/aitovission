@echo off
title BMU Sketch-to-Art Bridge Server
echo ======================================================
echo    Starting BMU Founder's Day Kiosk Bridge Server
echo ======================================================
echo.
python comfy_bridge.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with an error. Press any key to close.
    pause
)
