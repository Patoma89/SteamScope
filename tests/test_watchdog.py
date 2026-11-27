import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.config import ConfigManager
from core.database import DatabaseManager
from core.watchdog import WatchlistWatchdog
from web_bridge.tray_v3 import TrayV3Manager


class _TrackingSFX:
    def __init__(self):
        self.calls = []

    def play(self, sfx_type="click"):
        self.calls.append(sfx_type)


class TestWatchdogAndTrayV3(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_cache.db")
        self.cfg_path = os.path.join(self.tmp_dir.name, "test_config.json")
        self.db = DatabaseManager(db_path=self.db_path)
        self.cfg = ConfigManager(config_path=self.cfg_path)
        self.sfx = _TrackingSFX()
        self.api_client = MagicMock()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_run_once_with_empty_watchlist(self):
        wd = WatchlistWatchdog(db=self.db, config=self.cfg, api_client=self.api_client, sfx=self.sfx)
        res = wd.run_once()
        self.assertEqual(res, {"checked": 0, "atl_hits": [], "target_hits": [], "discount_hits": []})
        self.api_client.obtener_precios_argentina_lote.assert_not_called()

    @patch("core.watchdog.notificar_oferta_enriquecida")
    def test_run_once_detects_atl_and_target_hit(self, mock_notif):
        self.db.add_watchlist("1091500", "Cyberpunk 2077", 44.99, "https://store.steampowered.com/app/1091500")
        self.db.update_historical_min("1091500", 29.99, 33, 44.99)
        self.db.set_watchlist_target_price("1091500", 20.0)

        self.api_client.obtener_precios_argentina_lote.return_value = {
            "1091500": {"normal": 44.99, "oferta": 15.74, "descuento": 65}
        }
        updated_calls = []
        wd = WatchlistWatchdog(
            db=self.db,
            config=self.cfg,
            api_client=self.api_client,
            sfx=self.sfx,
            on_alerts_updated=lambda: updated_calls.append(True),
        )

        res = wd.run_once()
        self.assertEqual(res["checked"], 1)
        self.assertEqual(len(res["atl_hits"]), 1)
        self.assertEqual(len(res["target_hits"]), 1)
        self.assertEqual(len(res["discount_hits"]), 1)
        self.assertEqual(self.db.contar_alertas_atl(), 1)
        mock_notif.assert_called_once()
        self.assertEqual(self.sfx.calls, ["atl"])
        self.assertEqual(updated_calls, [True])

    def test_start_and_stop_lifecycle(self):
        wd = WatchlistWatchdog(
            db=self.db,
            config=self.cfg,
            api_client=self.api_client,
            sfx=self.sfx,
            check_tick_seconds=0.05,
        )
        wd.start()
        self.assertIsNotNone(wd._thread)
        self.assertTrue(wd._thread.is_alive())
        wd.stop()
        wd._thread.join(timeout=1.0)
        self.assertFalse(wd._thread.is_alive())

    def test_tray_v3_manager_init_and_safe_stop(self):
        tray = TrayV3Manager(
            on_show=lambda: None,
            on_check_now=lambda: None,
            on_quit=lambda: None,
            on_open_events=lambda: None,
        )
        self.assertFalse(tray.is_running)
        tray.stop()
        self.assertFalse(tray.is_running)


if __name__ == "__main__":
    unittest.main()
