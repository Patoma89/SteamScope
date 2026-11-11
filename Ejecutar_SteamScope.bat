@echo off
title Iniciando SteamScope...
cd /d "%~dp0"
python SteamScope.py
if errorlevel 1 (
    echo.
    echo Hubo un error al iniciar SteamScope.
    pause
)
