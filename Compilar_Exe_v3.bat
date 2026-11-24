@echo off
title Compilador SteamScope 3.0 NEXT EXE - by Patoma89
cd /d "%~dp0"
echo ========================================================
echo   EMPAQUETANDO STEAMSCOPE 3.0 NEXT EN EJECUTABLE (.EXE)
echo ========================================================
echo.

if exist "C:\Users\INFORMES1\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
    set "PY_CMD=C:\Users\INFORMES1\AppData\Local\Python\pythoncore-3.14-64\python.exe"
) else if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PY_CMD=py
    ) else (
        set PY_CMD=python
    )
)

echo [1/3] Verificando PyInstaller y pywebview...
"%PY_CMD%" -m pip install --upgrade pyinstaller pywebview --quiet

echo [2/3] Compilando dist\SteamScope.exe desde SteamScope_v3.spec...
"%PY_CMD%" -m PyInstaller --noconfirm --clean SteamScope_v3.spec

echo.
if exist "dist\SteamScope.exe" (
    echo [3/3] Generando Instalador Setup con Inno Setup...
    if exist "C:\Program Files\Inno Setup 7\ISCC.exe" (
        "C:\Program Files\Inno Setup 7\ISCC.exe" "SteamScope_v3_Setup.iss"
    ) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "SteamScope_v3_Setup.iss"
    ) else (
        echo [AVISO] No se encontro Inno Setup ISCC.exe; dist\SteamScope.exe generado igualmente.
    )
    echo ========================================================
    echo   EXITO!
    echo   - Instalador Setup: Output\SteamScope_v3.0.0_Setup.exe
    echo   - Ejecutable base:  dist\SteamScope.exe
    echo ========================================================
    if exist "Output" explorer Output
) else (
    echo [!] Hubo un problema al compilar. Revisa los mensajes de arriba.
)
pause
