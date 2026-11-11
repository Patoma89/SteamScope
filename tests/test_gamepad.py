"""
Pruebas Unitarias para el Módulo de Gamepad Nativo (XInput) de SteamScope 2.0.
"""

import unittest
from unittest.mock import MagicMock
from core.gamepad import GamepadManager


class TestGamepadManager(unittest.TestCase):
    def test_gamepad_manager_initialization(self):
        cb_called = {"a": False, "conn": False}
        callbacks = {
            "on_button_a": lambda: cb_called.update({"a": True}),
            "on_connection_change": lambda c: cb_called.update({"conn": True})
        }
        gm = GamepadManager(callbacks=callbacks)
        self.assertFalse(gm.is_connected)
        
        # Probar disparo manual seguro de callback
        gm._trigger("on_button_a")
        self.assertTrue(cb_called["a"])

        # Probar trigger inexistente no arroja excepción
        gm._trigger("on_boton_inexistente")

    def test_gamepad_manager_lifecycle(self):
        gm = GamepadManager()
        # Mock de DLL para simular ausencia o presencia
        gm._xinput_dll = None
        gm.start()
        self.assertFalse(gm._running)

        gm.stop()
        self.assertFalse(gm._running)


if __name__ == "__main__":
    unittest.main()
