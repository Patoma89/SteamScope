---
name: python-windows-packaging
description: >-
  Use this skill whenever building, compiling, packaging, or creating Windows installers for Python desktop applications. Covers PyInstaller onefile compilation, asset embedding, taskbar AppUserModelID, Inno Setup compiler integration, and release distribution.
---

# 📦 Python Windows Packaging Pro: PyInstaller & Inno Setup Releases

Esta skill describe el pipeline profesional para compilar aplicaciones de escritorio Python a ejecutables nativos (`.exe`) independientes y generar instaladores de grado comercial para Windows con **Inno Setup**.

---

## ⚙️ 1. Compilación con PyInstaller

### Comando Canónico de Compilación
```powershell
py -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "SteamScope" `
    --icon "icono.ico" `
    --add-data "icono.ico;." `
    --add-data "core;core" `
    --add-data "ui;ui" `
    --collect-all customtkinter `
    --hidden-import mplcursors `
    --hidden-import pystray._win32 `
    SteamScope.py
```

### Explicación de Flags Críticos:
- `--onefile`: Empaqueta el runtime de Python, librerías C y scripts en un solo binario en `dist/`.
- `--windowed`: Suprime la consola negra de comandos al ejecutar la aplicación.
- `--add-data "carpeta;carpeta"`: En Windows se usa punto y coma `;` como separador de origen y destino.
- `--collect-all customtkinter`: Extrae los archivos JSON de temas (`themes/`) y fuentes tipográficas de CustomTkinter.
- `--hidden-import`: Incluye módulos dinámicos que PyInstaller no detecta por análisis estático (ej. backends de Windows para `pystray` o `mplcursors`).

---

## 📌 2. Resolución Dinámica de Rutas en Tiempo de Ejecución

Cuando el ejecutable corre empaquetado por PyInstaller, los archivos se descomprimen en una carpeta temporal `sys._MEIPASS`.

### Patrón Helper Obligatorio
```python
import sys
import os

def obtener_ruta_recurso(nombre_archivo: str) -> str:
    """Resuelve la ruta absoluta de un recurso tanto en desarrollo como en ejecutable empaquetado."""
    if hasattr(sys, '_MEIPASS'):
        # Ruta en tiempo de ejecución del ejecutable onefile
        return os.path.join(sys._MEIPASS, nombre_archivo)
    # Ruta en entorno de desarrollo local
    return os.path.abspath(nombre_archivo)
```

---

## 🪟 3. Fijar Ícono en la Barra de Tareas de Windows (AppUserModelID)

Sin esto, Windows agrupa la app bajo el ícono genérico de Python en la barra de tareas:

```python
import ctypes

def registrar_app_en_windows(app_id: str):
    """Permite que Windows muestre el ícono propio en la barra de tareas y notificaciones."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
```

---

## 🛠️ 4. Generación del Instalador con Inno Setup (.iss)

Inno Setup crea instaladores livianos, limpios y compatibles con auto-actualizaciones silenciosas.

### Parámetros Clave en el Script `.iss`:
1. **Mutex para evitar instalación con la app abierta**:
   ```ini
   AppMutex=SteamScopeAppMutexInstance
   ```
2. **Archivos a incluir**:
   ```ini
   [Files]
   Source: "dist\SteamScope.exe"; DestDir: "{app}"; Flags: ignoreversion
   Source: "icono.ico"; DestDir: "{app}"; Flags: ignoreversion
   ```
3. **Accesos directos**:
   ```ini
   [Icons]
   Name: "{autoprograms}\SteamScope"; Filename: "{app}\SteamScope.exe"; IconFilename: "{app}\icono.ico"
   Name: "{autodesktop}\SteamScope"; Filename: "{app}\SteamScope.exe"; IconFilename: "{app}\icono.ico"; Tasks: desktopicon
   ```

### Compilación desde Línea de Comandos:
```cmd
"C:\Program Files\Inno Setup 7\ISCC.exe" "Newnew.iss"
```

---

## 🛡️ 5. Mitigación de Falsos Positivos en Antivirus
1. Evitar usar empaquetadores como UPX (`--noupx` en PyInstaller), ya que son frecuentemente catalogados como sospechosos por motores heurísticos.
2. Mantener la metadata del ejecutable completa (`company_name`, `file_description`, `legal_copyright`, `version`).
3. Almacenar datos de usuario y bases de datos en `%LOCALAPPDATA%` (`C:\Users\<Usuario>\AppData\Local\<AppName>`), nunca en `C:\Program Files` donde se requieren permisos de administrador.
