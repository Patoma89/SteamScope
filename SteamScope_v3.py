"""
====================================================================
SteamScope 3.0 NEXT — Interfaz GPU-Acelerada (Edge WebView2 + pywebview)
Coexiste en paralelo con SteamScope.py (v2.0.1) compartiendo el 100%
de core/ y la base SQLite sin riesgo de regresión.
====================================================================
"""
import logging
import os
import sys
import traceback
from typing import Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.config import APP_VERSION, obtener_ruta_appdata
from core.database import DatabaseManager
from core.gamepad import GamepadManager
from web_bridge import SteamScopeWebAPI, start_local_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SteamScope.WebUI")


def _resolve_web_ui_dir() -> str:
    if hasattr(sys, "_MEIPASS"):
        cand = os.path.join(sys._MEIPASS, "web_ui")
        if os.path.isdir(cand):
            return cand
    if getattr(sys, "frozen", False):
        cand_exe = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "web_ui")
        if os.path.isdir(cand_exe):
            return cand_exe
    return os.path.join(current_dir, "web_ui")


def _register_windows_appid() -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Patoma89.SteamScope.3.0.NEXT")
        except Exception:
            pass


def _run_app() -> int:
    try:
        import webview
    except ImportError:
        print(
            "\n[!] Falta la dependencia 'pywebview' para ejecutar SteamScope 3.0 NEXT.\n"
            "    Instalala ejecutando:\n"
            "    pip install pywebview\n"
        )
        return 1

    _register_windows_appid()
    db = DatabaseManager()

    web_ui_dir = _resolve_web_ui_dir()
    if not os.path.isdir(web_ui_dir):
        raise FileNotFoundError(f"No se encontró el directorio web_ui en: {web_ui_dir}")
    cache_dir = os.path.join(obtener_ruta_appdata(), "cache")
    httpd, url = start_local_server(web_ui_dir, cache_dir=cache_dir)

    window_holder: list[Optional[webview.Window]] = [None]

    def _set_topmost(enabled: bool) -> None:
        win = window_holder[0]
        if win is not None:
            win.on_top = bool(enabled)

    def _save_dialog(default_name: str, ext: str) -> Optional[str]:
        win = window_holder[0]
        if win is None:
            return None
        try:
            fd_enum = getattr(webview, "FileDialog", None)
            dialog_mode = fd_enum.SAVE if fd_enum is not None else getattr(webview, "SAVE_DIALOG", 30)
            file_types = (f"Archivo {ext.upper()} (*.{ext})",)
            res = win.create_file_dialog(dialog_mode, save_filename=default_name, file_types=file_types)
            if isinstance(res, (list, tuple)) and res:
                return str(res[0])
            if isinstance(res, str) and res:
                return res
        except Exception:
            pass
        return None

    api = SteamScopeWebAPI(db=db, on_toggle_topmost=_set_topmost, on_save_dialog=_save_dialog)

    window = webview.create_window(
        title=f"⚡ SteamScope 3.0 NEXT (v{APP_VERSION}) | by Patoma89",
        url=url,
        js_api=api,
        width=1440,
        height=900,
        min_size=(1160, 740),
        background_color="#090C12",
    )
    window_holder[0] = window

    def _emit_js(script: str) -> None:
        win = window_holder[0]
        if win is not None:
            try:
                win.evaluate_js(script)
            except Exception:
                pass

    gamepad = GamepadManager(callbacks={
        "on_bumper_left": lambda: _emit_js("window.SteamScopeGamepad && window.SteamScopeGamepad.onAction('tab_prev')"),
        "on_bumper_right": lambda: _emit_js("window.SteamScopeGamepad && window.SteamScopeGamepad.onAction('tab_next')"),
        "on_start": lambda: _emit_js("window.SteamScopeGamepad && window.SteamScopeGamepad.onAction('spotlight')"),
        "on_button_x": lambda: _emit_js("window.SteamScopeGamepad && window.SteamScopeGamepad.onAction('roulette')"),
        "on_button_y": lambda: _emit_js("window.SteamScopeGamepad && window.SteamScopeGamepad.onAction('radar')"),
        "on_connection_change": lambda conn: _emit_js(
            f"window.SteamScopeGamepad && window.SteamScopeGamepad.onConnection({'true' if conn else 'false'})"
        ),
    })
    gamepad.start()

    wv_cache_dir = os.path.join(cache_dir, "webview2_cache")
    os.makedirs(wv_cache_dir, exist_ok=True)
    try:
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=wv_cache_dir,
        )
    finally:
        gamepad.stop()
        httpd.shutdown()
    return 0


def main() -> int:
    try:
        return _run_app()
    except Exception:
        tb = traceback.format_exc()
        logger.exception("Error fatal al iniciar SteamScope 3.0 NEXT")
        try:
            log_dir = obtener_ruta_appdata()
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "crash_v3.log")
            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write(tb)
        except Exception:
            pass
        print(tb)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
