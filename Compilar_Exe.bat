@echo off
title Compilador SteamScope EXE - by Patoma89
echo ========================================================
echo   EMPAQUETANDO STEAMSCOPE v2.0.1 EN EJECUTABLE (.EXE)
echo ========================================================
echo.

if exist "C:\Users\INFORMES1\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
    set "PY_CMD=C:\Users\INFORMES1\AppData\Local\Python\pythoncore-3.14-64\python.exe"
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PY_CMD=py
    ) else (
        set PY_CMD=python
    )
)

echo [1/3] Verificando PyInstaller y dependencias...
"%PY_CMD%" -m pip install --upgrade pyinstaller mplcursors --quiet

echo [2/3] Compilando ejecutable base dist\SteamScope.exe...
if exist icono.ico (
    "%PY_CMD%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "SteamScope" --icon "icono.ico" --add-data "icono.ico;." --add-data "core;core" --add-data "ui;ui" --collect-all customtkinter --hidden-import mplcursors --hidden-import pystray._win32 SteamScope.py
) else (
    "%PY_CMD%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "SteamScope" --add-data "core;core" --add-data "ui;ui" --collect-all customtkinter --hidden-import mplcursors --hidden-import pystray._win32 SteamScope.py
)

echo.
if exist "dist\SteamScope.exe" (
    echo [3/3] Generando Instalador Setup con Inno Setup...
    if exist "C:\Program Files\Inno Setup 7\ISCC.exe" (
        "C:\Program Files\Inno Setup 7\ISCC.exe" "Newnew.iss"
    ) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "Newnew.iss"
    )
    echo ========================================================
    echo   EXITO!
    echo   - Instalador Auto-Update: Output\SteamScope_v2.0.1_Setup.exe
    echo   - Ejecutable base:        dist\SteamScope.exe
    echo ========================================================
    explorer Output
) else (
    echo [!] Hubo un problema al compilar. Revisa los mensajes de arriba.
)
pause
