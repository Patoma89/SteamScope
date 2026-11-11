"""
Módulo de Soporte Nativo para Gamepad / Mando (XInput) para SteamScope 2.0 (SRP / Core Puro).
Utiliza la API nativa XInput de Windows mediante ctypes (sin dependencias externas).
Soporta mandos de Xbox 360, Xbox One, Xbox Series X/S, Steam Deck y compatibles XInput.
"""

import time
import threading
import ctypes
from ctypes import wintypes

# Definición de estructuras de datos nativas de XInput
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", wintypes.SHORT),
        ("sThumbLY", wintypes.SHORT),
        ("sThumbRX", wintypes.SHORT),
        ("sThumbRY", wintypes.SHORT),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


# Constantes de botones según la especificación de Microsoft XInput
XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_A = 0x1000
XINPUT_GAMEPAD_B = 0x2000
XINPUT_GAMEPAD_X = 0x4000
XINPUT_GAMEPAD_Y = 0x8000

# Umbral de zona muerta para palancas analógicas
DEADZONE_STICK = 16000


class GamepadManager:
    """Gestiona la detección y lectura de eventos de mandos XInput en un hilo secundario."""
    def __init__(self, callbacks=None):
        self.callbacks = callbacks or {}
        self._running = False
        self._thread = None
        self._xinput_dll = None
        self._connected = False
        self._prev_buttons = 0
        self._last_stick_nav_time = 0.0

        self._cargar_dll()

    def _cargar_dll(self):
        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                dll = getattr(ctypes.windll, name, None)
                if dll and hasattr(dll, "XInputGetState"):
                    self._xinput_dll = dll
                    break
            except Exception:
                pass

    @property
    def is_available(self) -> bool:
        return self._xinput_dll is not None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def start(self):
        if not self.is_available or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _poll_loop(self):
        state = XINPUT_STATE()
        while self._running:
            try:
                # Comprobar mando en slot 0 (mando principal)
                res = self._xinput_dll.XInputGetState(0, ctypes.byref(state))
                now_connected = (res == 0)

                if now_connected != self._connected:
                    self._connected = now_connected
                    cb_conn = self.callbacks.get("on_connection_change")
                    if cb_conn:
                        cb_conn(self._connected)

                if now_connected:
                    buttons = state.Gamepad.wButtons
                    thumb_x = state.Gamepad.sThumbLX
                    thumb_y = state.Gamepad.sThumbLY

                    # Detección de flanco ascendente (nuevo botón presionado)
                    new_presses = buttons & ~self._prev_buttons

                    if new_presses & XINPUT_GAMEPAD_A:
                        self._trigger("on_button_a")
                    if new_presses & XINPUT_GAMEPAD_B:
                        self._trigger("on_button_b")
                    if new_presses & XINPUT_GAMEPAD_X:
                        self._trigger("on_button_x")
                    if new_presses & XINPUT_GAMEPAD_Y:
                        self._trigger("on_button_y")
                    if new_presses & XINPUT_GAMEPAD_LEFT_SHOULDER:
                        self._trigger("on_bumper_left")
                    if new_presses & XINPUT_GAMEPAD_RIGHT_SHOULDER:
                        self._trigger("on_bumper_right")
                    if new_presses & XINPUT_GAMEPAD_START:
                        self._trigger("on_start")
                    if new_presses & XINPUT_GAMEPAD_BACK:
                        self._trigger("on_back")
                    if new_presses & XINPUT_GAMEPAD_DPAD_LEFT:
                        self._trigger("on_dpad_left")
                    if new_presses & XINPUT_GAMEPAD_DPAD_RIGHT:
                        self._trigger("on_dpad_right")
                    if new_presses & XINPUT_GAMEPAD_DPAD_UP:
                        self._trigger("on_dpad_up")
                    if new_presses & XINPUT_GAMEPAD_DPAD_DOWN:
                        self._trigger("on_dpad_down")

                    # Navegación con stick analógico izquierdo con auto-repetición y zona muerta
                    t_now = time.time()
                    if t_now - self._last_stick_nav_time > 0.25:
                        if thumb_x > DEADZONE_STICK:
                            self._trigger("on_dpad_right")
                            self._last_stick_nav_time = t_now
                        elif thumb_x < -DEADZONE_STICK:
                            self._trigger("on_dpad_left")
                            self._last_stick_nav_time = t_now

                    self._prev_buttons = buttons
                else:
                    self._prev_buttons = 0

                time.sleep(0.035)  # Polling eficiente a ~28 Hz (consumo CPU despreciable)
            except Exception:
                time.sleep(0.5)

    def _trigger(self, event_name):
        cb = self.callbacks.get(event_name)
        if cb:
            try:
                cb()
            except Exception:
                pass
