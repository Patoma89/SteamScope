"""Gestor de bandeja del sistema para SteamScope 3.0 NEXT sin dependencias de Tkinter/pywebview."""
import atexit
import threading
from typing import Any, Callable, Optional

from core.config import APP_NAME, obtener_ruta_recurso


class TrayV3Manager:
    """Administra el ícono de bandeja del sistema usando pystray de forma segura e idempotente."""

    def __init__(
        self,
        on_show: Callable[[], Any],
        on_check_now: Callable[[], Any],
        on_quit: Callable[[], Any],
        on_open_events: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._on_show = on_show
        self._on_check_now = on_check_now
        self._on_quit = on_quit
        self._on_open_events = on_open_events
        self._icon: Any = None
        self._running = False
        self._atexit_registered = False

    @property
    def is_running(self) -> bool:
        """Indica si el ícono de bandeja se encuentra activo."""
        return bool(self._running and self._icon is not None)

    def _crear_icono(self) -> Any:
        from PIL import Image, ImageDraw

        try:
            return Image.open(obtener_ruta_recurso("icono.ico"))
        except Exception:
            img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((2, 2, 62, 62), fill=(20, 30, 48))
            draw.polygon([(20, 46), (32, 14), (44, 46), (32, 36)], fill=(0, 180, 255))
            return img

    def _safe_call(self, fn: Optional[Callable[[], Any]]) -> None:
        if fn is None:
            return
        try:
            fn()
        except Exception:
            pass

    def start(self) -> bool:
        """Inicializa y muestra el ícono en la bandeja del sistema."""
        if self._running:
            return True
        try:
            import pystray
        except Exception:
            return False

        items = [
            pystray.MenuItem(f"Abrir {APP_NAME}", lambda icon, item: self._safe_call(self._on_show), default=True),
            pystray.MenuItem("⭐ Comprobar Mínimos de Wishlist Ahora", lambda icon, item: self._safe_call(self._on_check_now)),
        ]
        if self._on_open_events is not None:
            items.append(
                pystray.MenuItem("📅 Ver Eventos y Rebajas", lambda icon, item: self._safe_call(self._on_open_events))
            )
        items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", lambda icon, item: self._safe_call(self._on_quit)),
        ])

        try:
            self._icon = pystray.Icon("SteamScopeTrayV3", self._crear_icono(), APP_NAME, pystray.Menu(*items))
            self._running = True
            if not self._atexit_registered:
                atexit.register(self.stop)
                self._atexit_registered = True
            threading.Thread(target=self._icon.run, daemon=True).start()
            return True
        except Exception:
            self._running = False
            self._icon = None
            return False

    def stop(self) -> None:
        """Detiene el ícono de bandeja de forma segura e idempotente."""
        self._running = False
        icon = self._icon
        self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
