import atexit
import os
import time
import threading
from PIL import Image, ImageDraw
import pystray
from core.config import APP_NAME, obtener_ruta_recurso
from core.pricing import notificar_windows


class TrayManager:
    """Gestor de bandeja del sistema de Windows y Centinela de Wishlist (SRP)."""
    def __init__(self, root_window, abrir_modal_cb):
        self.root = root_window
        self.abrir_modal_cb = abrir_modal_cb
        self.tray_icon = None
        self._running = False
        self._ultimo_chequeo_ts = time.time()
        atexit.register(self.limpiar_salida)

    def _crear_icono(self):
        try:
            return Image.open(obtener_ruta_recurso("icono.ico"))
        except Exception:
            img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((2, 2, 62, 62), fill=(20, 30, 48))
            draw.polygon([(20, 46), (32, 14), (44, 46), (32, 36)], fill=(0, 180, 255))
            return img

    def mostrar_ventana(self, icon=None, item=None):
        def _restaurar():
            era_max = getattr(self.root, "_era_maximizada", False) or (self.root.state() == "zoomed")
            self.root.deiconify()
            if era_max:
                self.root.state("zoomed")
            elif self.root.state() == "iconic":
                self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
        self.root.after(0, _restaurar)

    def salir_completo(self, icon=None, item=None):
        self.limpiar_salida()
        if icon:
            try:
                icon.stop()
            except Exception:
                pass
        try:
            if hasattr(self.root, "_gamepad") and self.root._gamepad:
                self.root._gamepad.stop()
        except Exception:
            pass
        try:
            self.root.ui_executor.shutdown(wait=False)
        except Exception:
            pass
        try:
            self.root.db.get_connection().close()
        except Exception:
            pass
        os._exit(0)

    def limpiar_salida(self):
        if self.tray_icon and self._running:
            self._running = False
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

    def ocultar_a_tray(self):
        self.root.withdraw()
        notificar_windows(f"{APP_NAME} minimizado", "Monitoreando rebajas y récords históricos en segundo plano.")

    def forzar_chequeo_watchdog(self, icon=None, item=None):
        """Dispara de inmediato una revisión silenciosa de la wishlist."""
        self._ultimo_chequeo_ts = time.time()
        if hasattr(self.root, "ejecutar_watchdog_silencioso"):
            self.root.after(0, self.root.ejecutar_watchdog_silencioso)

    def _loop_centinela_wishlist(self):
        """Hilo demonio que revisa la wishlist en segundo plano según el intervalo configurado."""
        while self._running:
            try:
                time.sleep(30)
                if not self._running:
                    break
                config = getattr(self.root, "config", None)
                if not config or not getattr(self.root, "winfo_exists", lambda: False)():
                    continue
                if not self.root.winfo_exists():
                    break

                activado = config.datos.get("watchdog_activado", True)
                if not activado:
                    continue

                intervalo_hs = float(config.datos.get("watchdog_intervalo_hs", 6))
                segundos_intervalo = max(1800, int(intervalo_hs * 3600))  # Mínimo 30 minutos

                ahora = time.time()
                if ahora - self._ultimo_chequeo_ts >= segundos_intervalo:
                    self._ultimo_chequeo_ts = ahora
                    if hasattr(self.root, "ejecutar_watchdog_silencioso"):
                        self.root.after(0, self.root.ejecutar_watchdog_silencioso)
            except Exception:
                pass

    def iniciar_tray(self):
        if self._running or self.tray_icon:
            return
        menu = pystray.Menu(
            pystray.MenuItem(f"Abrir {APP_NAME}", self.mostrar_ventana, default=True),
            pystray.MenuItem("⭐ Comprobar Mínimos de Wishlist Ahora", self.forzar_chequeo_watchdog),
            pystray.MenuItem("Ver Eventos y Rebajas", lambda icon, item: self.root.after(0, self.abrir_modal_cb)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self.salir_completo),
        )
        self.tray_icon = pystray.Icon("SteamScopeTray", self._crear_icono(), APP_NAME, menu)
        self._running = True
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        threading.Thread(target=self._loop_centinela_wishlist, daemon=True).start()
