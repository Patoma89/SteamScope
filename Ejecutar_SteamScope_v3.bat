@echo off
title Iniciando SteamScope 3.0 NEXT (GPU WebView2)...
cd /d "%~dp0"

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" SteamScope_v3.py
    goto :check_err
)

where py >nul 2>nul
if %errorlevel%==0 (
    py SteamScope_v3.py
    goto :check_err
)

python SteamScope_v3.py

:check_err
if errorlevel 1 (
    echo.
    echo [!] Hubo un error al iniciar SteamScope 3.0 NEXT.
    echo     Si falta pywebview, instala con: pip install pywebview
    pause
)
