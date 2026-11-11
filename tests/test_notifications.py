"""
Pruebas Unitarias para el Módulo de Notificaciones Enriquecidas de Windows 10/11 en SteamScope 2.0.
"""

import unittest
from unittest.mock import patch, MagicMock
from core.notifications import notificar_oferta_enriquecida, _hilo_notificar_toast


class TestNotifications(unittest.TestCase):
    @patch("core.notifications.threading.Thread")
    def test_notificar_oferta_enriquecida_spawns_daemon_thread(self, mock_thread_cls):
        mock_instance = MagicMock()
        mock_thread_cls.return_value = mock_instance

        notificar_oferta_enriquecida(
            titulo="Hollow Knight",
            precio_usd=7.49,
            descuento=50,
            precio_ars=12000.0,
            appid="367520"
        )

        mock_thread_cls.assert_called_once()
        _, kwargs = mock_thread_cls.call_args
        self.assertTrue(kwargs.get("daemon"))
        mock_instance.start.assert_called_once()

    @patch("core.notifications.subprocess.run")
    @patch("core.notifications.HTTP_SESSION.get")
    def test_hilo_notificar_toast_xml_execution(self, mock_http_get, mock_sp_run):
        mock_http_get.side_effect = Exception("No network in mock")
        mock_sp_run.return_value = MagicMock(returncode=0)

        # Ejecutar directamente la lógica interna sin crear thread real
        _hilo_notificar_toast(
            titulo="Celeste",
            precio_usd=1.99,
            descuento=75,
            precio_ars=3200.0,
            banner_url=None,
            appid="504230",
            es_gratis=False
        )

        mock_sp_run.assert_called_once()
        cmd = mock_sp_run.call_args[0][0]
        self.assertIn("powershell", cmd[0].lower())


if __name__ == "__main__":
    unittest.main()
