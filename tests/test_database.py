import os
import tempfile
import unittest
from core.database import DatabaseManager
from core.config import ConfigManager


class TestDatabaseAndConfig(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_cache.db")
        self.cfg_path = os.path.join(self.tmp_dir.name, "test_config.json")
        self.db = DatabaseManager(db_path=self.db_path)
        self.cfg = ConfigManager(config_path=self.cfg_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_blacklist_crud_and_cache(self):
        self.assertEqual(self.db.get_blacklist(), [])
        self.db.add_blacklist("1091500", "Cyberpunk 2077")
        self.assertIn("1091500", self.db.get_blacklist())
        details = self.db.get_blacklist_details()
        self.assertEqual(details, [("1091500", "Cyberpunk 2077")])

        self.db.remove_blacklist("1091500")
        self.assertNotIn("1091500", self.db.get_blacklist())

    def test_watchlist_crud_and_targets(self):
        self.db.add_watchlist("1245620", "Elden Ring", 47.99, "https://store.steampowered.com/app/1245620")
        self.assertIn("1245620", self.db.get_watchlist_ids_set())

        self.db.set_watchlist_tag("1245620", "Souls")
        self.db.set_watchlist_target_price("1245620", 29.99)
        self.db.update_watchlist_title("1245620", "ELDEN RING (Actualizado)")

        rows = self.db.get_all_watchlist()
        self.assertEqual(len(rows), 1)
        appid, titulo, precio, _, _, tag, target = rows[0]
        self.assertEqual(appid, "1245620")
        self.assertEqual(titulo, "ELDEN RING (Actualizado)")
        self.assertAlmostEqual(precio, 47.99)
        self.assertEqual(tag, "Souls")
        self.assertAlmostEqual(target, 29.99)

        # Batch update de títulos
        self.db.add_watchlist("1091500", "Juego Steam 1091500", 29.99, "https://store.steampowered.com/app/1091500")
        self.db.update_watchlist_titles_batch({"1245620": "Elden Ring Final", "1091500": "Cyberpunk 2077"})
        mapa = {r[0]: r[1] for r in self.db.get_all_watchlist()}
        self.assertEqual(mapa["1245620"], "Elden Ring Final")
        self.assertEqual(mapa["1091500"], "Cyberpunk 2077")

        self.db.remove_watchlist("1245620")
        self.db.remove_watchlist("1091500")
        self.assertEqual(len(self.db.get_all_watchlist()), 0)

    def test_historical_min_batch(self):
        # Primera inserción con 80% de descuento -> ATL verdadero
        res1 = self.db.update_historical_min_batch({"400": (1.99, 80, 9.99), "500": (19.99, 0, 19.99)})
        self.assertTrue(res1["400"])
        self.assertFalse(res1["500"])

        # Subida de precio -> no es ATL
        res2 = self.db.update_historical_min_batch({"400": (4.99, 50, 9.99)})
        self.assertFalse(res2["400"])

        # Nuevo récord más bajo -> es ATL
        res3 = self.db.update_historical_min_batch({"400": (0.99, 90, 9.99)})
        self.assertTrue(res3["400"])

        logs = self.db.get_price_log("400")
        self.assertEqual(len(logs), 1)
        self.assertAlmostEqual(logs[0][1], 0.99)

        # Batch query de mínimos históricos
        mins = self.db.get_historical_mins_batch(["400", "500", "999999"])
        self.assertAlmostEqual(mins["400"], 0.99)
        self.assertAlmostEqual(mins["500"], 19.99)
        self.assertNotIn("999999", mins)

    def test_game_metadata(self):
        self.assertIsNone(self.db.get_game_meta("730"))
        self.db.save_game_meta("730", "Multijugador PvP", "Shooter", 0, 1, "Shooter, PvP, Trading Cards")
        meta = self.db.get_game_meta("730")
        self.assertIsNotNone(meta)
        self.assertEqual(meta[0], "Multijugador PvP")

    def test_config_persistence(self):
        self.cfg.guardar_basico("dolar_referencia", 1250.5)
        cfg2 = ConfigManager(config_path=self.cfg_path)
        self.assertAlmostEqual(cfg2.datos["dolar_referencia"], 1250.5)

    def test_library_cache_and_valuation(self):
        juegos = [
            {"appid": "730", "titulo": "Counter-Strike 2", "horas": 120.5, "minutos": 7230, "thumb_url": "http://img/730.jpg"},
            {"appid": "1245620", "titulo": "Elden Ring", "horas": 0.0, "minutos": 0, "thumb_url": "http://img/1245620.jpg"},
        ]
        self.db.save_library_batch(juegos)
        cached = self.db.get_library_cached()
        self.assertEqual(len(cached), 2)
        self.assertEqual(cached[0]["appid"], "730")
        self.assertEqual(cached[0]["price_usd"], -1.0)

        self.db.update_library_prices_batch({"730": 0.0, "1245620": 47.99})
        cached2 = self.db.get_library_cached()
        mapa_p = {j["appid"]: j["price_usd"] for j in cached2}
        self.assertEqual(mapa_p["730"], 0.0)
        self.assertAlmostEqual(mapa_p["1245620"], 47.99)

        # Re-sincronizar biblioteca preserva los precios ya valuados
        juegos[0]["horas"] = 135.0
        self.db.save_library_batch(juegos)
        cached3 = self.db.get_library_cached()
        mapa_p3 = {j["appid"]: (j["horas"], j["price_usd"]) for j in cached3}
        self.assertAlmostEqual(mapa_p3["730"][0], 135.0)
        self.assertAlmostEqual(mapa_p3["1245620"][1], 47.99)

    def test_atl_alerts_history_crud(self):
        self.assertEqual(len(self.db.obtener_alertas_atl()), 0)
        self.db.registrar_alerta_atl("367520", "Hollow Knight", 4.99, 50)
        self.db.registrar_alerta_atl("1091500", "Cyberpunk 2077", 29.99, 50)
        alertas = self.db.obtener_alertas_atl()
        self.assertEqual(len(alertas), 2)
        # Último insertado primero
        self.assertEqual(alertas[0]["appid"], "1091500")
        self.assertEqual(alertas[0]["titulo"], "Cyberpunk 2077")
        self.assertAlmostEqual(alertas[0]["precio_usd"], 29.99)
        self.assertEqual(alertas[0]["desc_pct"], 50)
        self.assertIn("202", alertas[0]["fecha"])

        self.db.limpiar_alertas_atl()
        self.assertEqual(len(self.db.obtener_alertas_atl()), 0)
        self.assertEqual(self.db.contar_alertas_atl(), 0)

    def test_game_notes_and_persistence(self):
        self.assertEqual(self.db.get_game_note("570"), "")
        self.db.save_game_note("570", "Jugar con amigos el finde")
        self.assertEqual(self.db.get_game_note("570"), "Jugar con amigos el finde")

        # Probar get_all_game_notes
        self.db.save_game_note("1091500", "Esperar a descuento del 70%")
        all_notes = self.db.get_all_game_notes()
        self.assertEqual(all_notes["570"], "Jugar con amigos el finde")
        self.assertEqual(all_notes["1091500"], "Esperar a descuento del 70%")

        # Borrado de nota al pasar string vacío
        self.db.save_game_note("570", "   ")
        self.assertEqual(self.db.get_game_note("570"), "")

    def test_optimizar_base_datos(self):
        self.assertTrue(self.db.optimizar_base_datos())

    def test_backlog_metrics(self):
        juegos = [
            {"appid": "1", "titulo": "Juego 0hs", "horas": 0.0, "minutos": 0, "price_usd": 19.99},
            {"appid": "2", "titulo": "Juego 1h", "horas": 1.2, "minutos": 72, "price_usd": 9.99},
            {"appid": "3", "titulo": "Juego 25hs", "horas": 25.0, "minutos": 1500, "price_usd": 49.99},
        ]
        self.db.save_library_batch(juegos)
        self.db.update_library_prices_batch({"1": 19.99, "2": 9.99, "3": 49.99})

        metricas = self.db.obtener_metricas_backlog()
        self.assertEqual(metricas["total"], 3)
        self.assertEqual(metricas["sin_jugar"], 1)
        self.assertEqual(metricas["apenas_probados"], 1)
        self.assertEqual(metricas["viciados"], 1)
        self.assertAlmostEqual(metricas["horas_totales"], 26.2, places=1)
        self.assertAlmostEqual(metricas["dinero_sin_estrenar_usd"], 19.99)
        self.assertAlmostEqual(metricas["pct_sin_jugar"], 33.3, places=1)


if __name__ == "__main__":
    unittest.main()
