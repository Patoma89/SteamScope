# ⚡ SteamScope — Directrices de Desarrollo Pro en Python

Este repositorio sigue directrices de ingeniería de software de nivel Senior para aplicaciones de escritorio en Python.

---

## 🏛️ Arquitectura del Proyecto (Separación Estricta de Capas)

- **`core/` (Lógica de Negocio Pura)**:
  - Nunca importar CustomTkinter ni Tkinter dentro de `core/` (excepción legacy: `exporters.py` solo para la UI v2; para CSV puro usar `csv_utils.py`).
  - Debe ser 100% testeable mediante tests unitarios en `tests/`.
  - Módulos: `config.py`, `database.py`, `api_client.py`, `pricing.py`, `filters.py`, `multi_store.py`, `cards_manager.py`, `gamepad.py`, `notifications.py`, `watchdog.py`, `csv_utils.py`, `exporters.py`.
- **`web_bridge/` + `web_ui/` (SteamScope 3.0 NEXT — Principal)**:
  - `web_bridge/` expone la API JSON pura para `pywebview` (`api.py`, mixins `api_*.py`, `asset_server.py`, `tray_v3.py`) sin importar Tkinter, CustomTkinter ni `ui/`.
  - `web_ui/` implementa la interfaz GPU-Acelerada Edge WebView2 (`index.html`, `styles.css`, `app.js`, `views_*.js`).
- **`SteamScope_v3.py` (Punto de Entrada Principal v3 & `SteamScope_v3.spec`)**.
- **`ui/` + `SteamScope.py` + `SteamScope.spec` (Capa Legacy v2 CustomTkinter)**:
  - Componentes visuales, diálogos y modales (`modals.py`, `charts.py`, `tray.py`).
  - Todo diálogo o ventana secundaria debe respetar la paleta dinámica activa (`parent.palette`).

---

## 🎨 Convenciones de Interfaz Gráfica (CustomTkinter)

1. **Hilo Principal sin Bloqueos**:
   - Todo trabajo de red (`requests`) o cálculo pesado se ejecuta en un thread demonio (`threading.Thread(target=..., daemon=True)`).
   - El retorno a la UI se hace **exclusivamente** mediante `self.after(0, ...)`.
   - Proteger siempre callbacks con `if not self.winfo_exists(): return`.
2. **Cero Popups Nativos**:
   - Queda prohibido el uso de `tkinter.messagebox` y `tkinter.simpledialog`.
   - Utilizar siempre `mostrar_alerta_skin()`, `preguntar_si_no_skin()` y `pedir_input_skin()` de `ui`.
3. **Contraste de Acento**:
   - Para texto sobre botones con color `accent`, usar `texto_contraste_acento(pal)` para garantizar legibilidad.
4. **Renderizado en Lotes (Batch Rendering)**:
   - Para listas con muchos elementos en `CTkScrollableFrame`, usar redibujado diferido en bloques para mantener 60 FPS al hacer scroll.

---

## 🧪 Pruebas Unitarias y Calidad

- Ejecutar la suite completa:
  ```powershell
  py -m unittest discover -s tests -v
  ```
- Verificación de compilación estricta antes de cada entrega:
  ```powershell
  py -m py_compile SteamScope.py SteamScope_v3.py core\*.py web_bridge\*.py ui\*.py tests\*.py
  ```

---

## 🧰 Skills Especializadas Disponibles

El proyecto cuenta con skills avanzadas en `.agents/skills/`:
- `project-planner`: Rol de Lead Product Manager y Planificador Estratégico, brainstorming, análisis de impacto y planes de acción por hitos.
- `software-architect`: Rol de Arquitecto de Software Senior, fases `/grill-me`, `/plan`, diseño de esquemas y optimización.
- `solid-principles-auditor`: Rol de Auditor de Código SOLID (SRP, OCP, LSP, ISP, DIP) con diagnóstico y refactorización.
- `python-gui-customtkinter`: Técnicas avanzadas de CustomTkinter, theming y modales.
- `python-pro-architecture`: SOLID aplicado, SQLite en modo WAL, networking resiliente y JSON atómico.
- `python-testing-qa`: Mocking con `unittest.mock`, aislamiento de BD y testing rápido.
- `python-windows-packaging`: PyInstaller, AppUserModelID e instalador Inno Setup.
