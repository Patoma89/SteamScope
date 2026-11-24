import ast
import http.client
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from core.config import APP_VERSION, PATCH_NOTES, SKIN_PALETTES, ConfigManager
from core.database import DatabaseManager
from web_bridge import SteamScopeWebAPI, resolve_web_asset_path, start_local_server


class _SilentSFX:
    def play(self, _sfx_type="click"):
        return None


class TestWebBridge(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_cache.db")
        self.cfg_path = os.path.join(self.tmp_dir.name, "test_config.json")
        self.db = DatabaseManager(db_path=self.db_path)
        self.cfg = ConfigManager(config_path=self.cfg_path)
        self.topmost_calls = []
        self.api = SteamScopeWebAPI(
            db=self.db,
            config=self.cfg,
            sfx=_SilentSFX(),
            on_toggle_topmost=lambda val: self.topmost_calls.append(val),
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_bootstrap_and_skins(self):
        boot = self.api.get_bootstrap()
        self.assertEqual(boot["app_title"], "SteamScope 3.0 NEXT")
        self.assertIn(boot["skin_id"], SKIN_PALETTES)
        self.assertEqual(len(boot["skins_meta"]), len(SKIN_PALETTES))
        self.assertIn("command_center", boot)
        self.assertIn("USD", ("USD", "ARS (Tarjeta)", "ARS (Cripto)"))

    def test_command_center_metrics_with_data(self):
        self.db.add_watchlist("1091500", "Cyberpunk 2077", 29.99, "https://store.steampowered.com/app/1091500")
        self.db.set_watchlist_target_price("1091500", 19.99)
        self.db.registrar_alerta_atl("1091500", "Cyberpunk 2077", 19.99, 67)
        self.db.save_library_batch([
            {"appid": "570", "titulo": "Dota 2", "horas": 120.5, "minutos": 7230, "price_usd": 0.0},
            {"appid": "1245620", "titulo": "Elden Ring", "horas": 0.0, "minutos": 0, "price_usd": 47.99},
        ])
        self.cfg.guardar_basico("presupuesto_carrito_usd", 40.0)
        self.cfg.guardar_basico("carrito_guardado", {
            "1091500": {"appid": "1091500", "titulo": "Cyberpunk 2077", "precio_oferta_usd": 20.0, "precio_normal_usd": 45.0}
        })

        cc = self.api.get_command_center_data()
        self.assertEqual(cc["atl"]["count"], 1)
        self.assertEqual(cc["watchlist"]["total"], 1)
        self.assertEqual(cc["watchlist"]["with_target"], 1)
        self.assertEqual(cc["backlog"]["total"], 2)
        self.assertEqual(cc["backlog"]["sin_jugar"], 1)
        self.assertEqual(cc["cart"]["count"], 1)
        self.assertAlmostEqual(cc["cart"]["total_usd"], 20.0)
        self.assertAlmostEqual(cc["cart"]["ahorro_usd"], 25.0)
        self.assertAlmostEqual(cc["cart"]["budget_pct"], 50.0)

    def test_set_skin_moneda_and_sidebar_persistence(self):
        res_skin = self.api.set_skin("Neón P89")
        self.assertTrue(res_skin["ok"])
        self.assertEqual(self.cfg.datos["tema"], "Neón P89")

        res_bad = self.api.set_skin("SkinInexistente")
        self.assertFalse(res_bad["ok"])

        res_mon = self.api.set_moneda("ARS (Cripto)")
        self.assertTrue(res_mon["ok"])
        self.assertEqual(self.cfg.datos["moneda"], "ARS (Cripto)")

        res_sb = self.api.set_sidebar_collapsed(True)
        self.assertTrue(res_sb["sidebar_collapsed"])
        self.assertTrue(self.cfg.datos["sidebar_collapsed"])

        t1 = self.api.toggle_always_on_top()
        self.assertTrue(t1["always_on_top"])
        self.assertEqual(self.topmost_calls, [True])

    def test_global_search_offline(self):
        self.db.add_watchlist("1245620", "Elden Ring", 47.99, "https://store.steampowered.com/app/1245620")
        self.db.set_watchlist_tag("1245620", "Souls")
        self.db.save_library_batch([{"appid": "413150", "titulo": "Stardew Valley", "horas": 45.0, "minutos": 2700, "price_usd": 14.99}])
        self.db.registrar_alerta_atl("1091500", "Cyberpunk 2077", 19.99, 67)

        short = self.api.global_search("a")
        self.assertEqual(short["results"], [])

        res_wl = self.api.global_search("elden")
        self.assertTrue(any(r["kind"] == "Watchlist" and r["id"] == "1245620" for r in res_wl["results"]))

        res_lib = self.api.global_search("stardew")
        self.assertTrue(any(r["kind"] == "Biblioteca" and r["id"] == "413150" for r in res_lib["results"]))

        res_sec = self.api.global_search("cromos")
        self.assertTrue(any(r["kind"] == "Sección" and r["tab"] == "cards" for r in res_sec["results"]))

    def test_resolve_web_asset_path_security(self):
        cache_dir = os.path.join(self.tmp_dir.name, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        valid_img = os.path.join(cache_dir, "1091500.jpg")
        with open(valid_img, "wb") as f:
            f.write(b"fakeimg")

        outside = os.path.join(self.tmp_dir.name, "secret.txt")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("secret")

        self.assertEqual(resolve_web_asset_path("1091500.jpg", cache_dir=cache_dir), os.path.realpath(valid_img))
        self.assertIsNone(resolve_web_asset_path("../secret.txt", cache_dir=cache_dir))
        self.assertIsNone(resolve_web_asset_path("..\\secret.txt", cache_dir=cache_dir))
        self.assertIsNone(resolve_web_asset_path("", cache_dir=cache_dir))

    def test_local_asset_server_serves_index_and_blocks_traversal(self):
        web_dir = os.path.join(self.tmp_dir.name, "web_ui")
        cache_dir = os.path.join(self.tmp_dir.name, "cache")
        os.makedirs(web_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

        with open(os.path.join(web_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write("<h1>SteamScope 3.0 NEXT</h1>")
        with open(os.path.join(cache_dir, "cover.jpg"), "wb") as f:
            f.write(b"JPGDATA")
        with open(os.path.join(self.tmp_dir.name, "secret.txt"), "w", encoding="utf-8") as f:
            f.write("TOPSECRET")

        httpd, url = start_local_server(web_dir, cache_dir=cache_dir)
        try:
            port = httpd.server_address[1]
            self.assertTrue(url.endswith("/index.html"))

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/")
            r1 = conn.getresponse()
            body1 = r1.read().decode("utf-8")
            self.assertEqual(r1.status, 200)
            self.assertIn("SteamScope 3.0 NEXT", body1)

            conn.request("GET", "/cache/cover.jpg")
            r2 = conn.getresponse()
            body2 = r2.read()
            self.assertEqual(r2.status, 200)
            self.assertEqual(body2, b"JPGDATA")

            conn.request("GET", "/../secret.txt")
            r3 = conn.getresponse()
            r3.read()
            self.assertEqual(r3.status, 403)

            conn.request("GET", "/cache/../secret.txt")
            r4 = conn.getresponse()
            r4.read()
            self.assertEqual(r4.status, 403)
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()

    @patch("web_bridge.api.HTTP_SESSION.get")
    def test_check_updates_mocked(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "version": "v99.0.0",
            "url": "https://github.com/Patoma89/SteamScope/releases/latest",
            "notas": ["Nueva UI GPU 3.0"],
        }
        mock_get.return_value = mock_resp

        res = self.api.check_updates()
        self.assertTrue(res["ok"])
        self.assertTrue(res["has_update"])
        self.assertEqual(res["latest_version"], "99.0.0")
        self.assertEqual(res["notas"], ["Nueva UI GPU 3.0"])

    def test_version_consistency_with_version_json_and_patch_notes(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version_json_path = os.path.join(root_dir, "version.json")
        with open(version_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(APP_VERSION, "3.0.0")
        self.assertEqual(data["version"].lstrip("vV"), APP_VERSION)
        self.assertEqual(PATCH_NOTES[0]["version"], f"v{APP_VERSION}")
        self.assertEqual(self.api.get_bootstrap()["version"], APP_VERSION)

    @patch("web_bridge.api.HTTP_SESSION.get")
    def test_check_updates_same_version_returns_no_update(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "version": f"v{APP_VERSION}",
            "url": "https://github.com/Patoma89/SteamScope/releases/latest",
            "notas": [],
        }
        mock_get.return_value = mock_resp

        res = self.api.check_updates()
        self.assertTrue(res["ok"])
        self.assertFalse(res["has_update"])
        self.assertEqual(res["current_version"], APP_VERSION)
        self.assertEqual(res["latest_version"], APP_VERSION)

    def test_web_bridge_has_no_ui_or_tkinter_dependency(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bridge_dir = os.path.join(root_dir, "web_bridge")
        forbidden_roots = {"tkinter", "customtkinter", "ui", "pandas", "matplotlib"}
        py_files = [
            "__init__.py",
            "api.py",
            "api_deals.py",
            "api_ficha.py",
            "api_account.py",
            "api_tools.py",
            "asset_server.py",
            "tray_v3.py",
        ]
        for fname in py_files:
            fpath = os.path.join(bridge_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Falta archivo esperado: {fpath}")
            with open(fpath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fpath)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        self.assertNotIn(top, forbidden_roots, f"{fname} importa {alias.name}")
                        self.assertNotEqual(alias.name, "core.exporters", f"{fname} importa core.exporters")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    self.assertNotIn(top, forbidden_roots, f"{fname} importa desde {node.module}")
                    self.assertNotEqual(node.module, "core.exporters", f"{fname} importa desde core.exporters")

    def test_deals_metadata_and_presets(self):
        meta = self.api.get_deals_metadata()
        self.assertIn("Todas las Categorías", meta["categorias"])
        self.assertIn("🎯 Shooters", meta["categorias"])
        self.assertIn("Mayor Descuento", meta["ordenes"])
        self.assertEqual(self.api.set_vista("Grilla")["vista"], "Grilla")
        self.assertFalse(self.api.set_vista("Invalida")["ok"])

        self.assertFalse(self.api.load_filter_preset()["ok"])
        self.api.save_filter_preset({"descuento": "Más de 75%", "cat_padre": "🎯 Shooters"})
        loaded = self.api.load_filter_preset()
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["preset"]["descuento"], "Más de 75%")

    @patch("web_bridge.api_deals.HTTP_SESSION.get")
    def test_search_deals_steam_storesearch_mocked(self, mock_get):
        self.db.add_blacklist("999", "Ignorado")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {"id": 1091500, "name": "Cyberpunk 2077", "tiny_image": "http://img/cp.jpg"},
                {"id": 999, "name": "Ignorado", "tiny_image": "http://img/x.jpg"},
            ]
        }
        mock_get.return_value = mock_resp

        with patch.object(
            self.api.api_client,
            "obtener_precios_argentina_lote",
            return_value={"1091500": {"normal": 44.99, "oferta": 15.74, "descuento": 65}},
        ):
            res = self.api.search_or_scan_deals({"query": "Cyberpunk"})

        self.assertTrue(res["ok"])
        self.assertEqual(res["mode"], "search")
        self.assertEqual(res["total_filtered"], 1)
        self.assertEqual(res["items"][0]["appid"], "1091500")
        self.assertEqual(res["items"][0]["descuento"], 65)
        self.assertIn("Cyberpunk", res["recientes"])

    @patch("web_bridge.api_deals.HTTP_SESSION.get")
    def test_scan_deals_cheapshark_and_query_filters_kpis(self, mock_get):
        self.db.save_game_meta("100", "Single-Player", "Action", 1, 0, "Action, Trading Cards, Steam Deck Verified")
        self.db.save_game_meta("200", "Cooperativo Online", "Shooter", 0, 1, "Shooter, FPS, Online Co-op")

        page0 = MagicMock()
        page0.status_code = 200
        page0.json.return_value = [
            {"steamAppID": "100", "title": "Hollow Knight", "normalPrice": "14.99", "salePrice": "7.49", "savings": "50", "steamRatingPercent": "97"},
            {"steamAppID": "200", "title": "Deep Rock Galactic", "normalPrice": "19.99", "salePrice": "5.99", "savings": "70", "steamRatingPercent": "96"},
            {"steamAppID": "300", "title": "Free Promo Game", "normalPrice": "9.99", "salePrice": "0.0", "savings": "100", "steamRatingPercent": "85"},
        ]
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = []
        mock_get.side_effect = [page0, page1]

        with patch.object(
            self.api.api_client,
            "obtener_precios_argentina_lote",
            return_value={
                "100": {"normal": 14.99, "oferta": 7.49, "descuento": 50},
                "200": {"normal": 19.99, "oferta": 5.99, "descuento": 70},
                "300": {"normal": 9.99, "oferta": 0.0, "descuento": 100},
            },
        ):
            res = self.api.search_or_scan_deals({"limite": 50})

        self.assertTrue(res["ok"])
        self.assertEqual(res["mode"], "scan")
        self.assertEqual(res["kpis"]["all"], 3)
        self.assertEqual(res["kpis"]["free"], 1)
        self.assertEqual(res["kpis"]["cards"], 1)
        self.assertEqual(res["kpis"]["coop"], 1)

        only_free = self.api.query_deals({"kpi_filter": "free"})
        self.assertEqual(only_free["total_filtered"], 1)
        self.assertEqual(only_free["items"][0]["appid"], "300")

        only_shooters = self.api.query_deals({"cat_padre": "🎯 Shooters", "subcat": "FPS (Primera Persona)"})
        self.assertEqual(only_shooters["total_filtered"], 1)
        self.assertEqual(only_shooters["items"][0]["appid"], "200")

    def test_cart_budget_and_watchlist_blacklist_actions(self):
        item = {
            "appid": "1245620",
            "titulo": "Elden Ring",
            "precio_oferta_usd": 30.0,
            "precio_normal_usd": 60.0,
            "descuento": 50,
            "link": "https://store.steampowered.com/app/1245620",
        }
        self.api._deals_data = [dict(item)]

        self.api.set_cart_budget(32.0)
        r_cart = self.api.toggle_cart_item(item)
        self.assertTrue(r_cart["in_cart"])
        self.assertEqual(r_cart["cart"]["summary"]["budget_status"], "warn")
        self.assertAlmostEqual(r_cart["cart"]["summary"]["ahorro_usd"], 30.0)

        r_wl = self.api.toggle_watchlist_item(item)
        self.assertTrue(r_wl["in_watchlist"])
        self.assertIn("1245620", self.db.get_watchlist_ids_set())

        r_bl = self.api.add_to_blacklist("1245620", "Elden Ring")
        self.assertTrue(r_bl["ok"])
        self.assertIn("1245620", self.db.get_blacklist())
        self.assertEqual(self.api._deals_data, [])

        cleared = self.api.clear_cart()
        self.assertEqual(cleared["cart"]["summary"]["count"], 0)

    def test_share_text_formatting(self):
        res = self.api.get_share_text({
            "appid": "570",
            "titulo": "Dota 2",
            "descuento": 50,
            "precio_oferta_usd": 10.0,
            "rating": "90",
            "es_atl": True,
            "tiene_cromos": True,
        })
        self.assertTrue(res["ok"])
        self.assertIn("Dota 2", res["text"])
        self.assertIn("RÉCORD HISTÓRICO", res["text"])
        self.assertIn("https://store.steampowered.com/app/570", res["text"])

    def test_get_game_details_and_regional_compare_mocked(self):
        self.db.registrar_punto_historico_externo("1091500", 29.99, "2026-01-10")
        self.db.registrar_punto_historico_externo("1091500", 15.74, "2026-06-15")
        self.db.save_game_note("1091500", "Esperar DLC")

        fake_data = {
            "name": "Cyberpunk 2077",
            "header_image": "https://img/header.jpg",
            "short_description": "<p>RPG futurista</p>",
            "developers": ["CD PROJEKT RED"],
            "publishers": ["CD PROJEKT RED"],
            "release_date": {"date": "10 DIC 2020"},
            "genres": [{"description": "RPG"}],
            "categories": [{"description": "Un jugador"}],
            "is_free": False,
            "price_overview": {"initial": 4499, "final": 1574, "discount_percent": 65},
            "_us_price_info": {"normal_us": 59.99, "final_us": 29.99},
            "metacritic": {"score": 86, "url": "https://metacritic.com/cp2077"},
            "pc_requirements": {"minimum": "Almacenamiento: 70 GB disponibles", "recommended": "SSD 70 GB"},
            "screenshots": [{"id": 1, "path_thumbnail": "https://img/t1.jpg", "path_full": "https://img/f1.jpg"}],
            "package_groups": [{"subs": [{"option_text": "Cyberpunk 2077 Ultimate", "price_in_cents_with_discount": 2999, "percent_savings": 50}]}],
        }
        fake_tuple = (fake_data, object(), ("muy positivas", "(500.000 reseñas)"), (15.74, "15/06/2026"), "Gold")

        with patch.object(self.api.api_client, "descargar_ficha_completa_paralelo", return_value=fake_tuple):
            res = self.api.get_game_details("1091500")

        # Verificar que es 100% JSON-serializable (sin PIL.Image)
        serialized = json.dumps(res)
        self.assertIn("Cyberpunk 2077", serialized)
        self.assertTrue(res["ok"])
        self.assertEqual(res["regional"]["status"], "better")
        self.assertEqual(res["disk_space"], "70 GB")
        self.assertTrue(res["atl"]["is_atl_now"])
        self.assertEqual(res["personal_note"], "Esperar DLC")
        self.assertEqual(len(res["screenshots"]), 1)
        self.assertEqual(len(res["packages"]), 1)
        self.assertGreaterEqual(len(res["price_history"]), 2)

    def test_save_game_note_persistence(self):
        self.db.add_watchlist("1245620", "Elden Ring", 47.99, "https://store.steampowered.com/app/1245620")
        res = self.api.save_game_note("1245620", "Comprar en oferta de invierno")
        self.assertTrue(res["ok"])
        self.assertEqual(res["note"], "Comprar en oferta de invierno")
        self.assertEqual(self.db.get_game_note("1245620"), "Comprar en oferta de invierno")

    def test_compare_games_versus_scoring(self):
        data_a = (
            {
                "name": "Juego Barato",
                "is_free": False,
                "price_overview": {"initial": 2000, "final": 500, "discount_percent": 75},
                "metacritic": {"score": 92},
                "pc_requirements": {},
            },
            None,
            ("muy positivas", "(10.000)"),
            (4.99, "01/01/2026"),
            "Platinum",
        )
        data_b = (
            {
                "name": "Juego Caro",
                "is_free": False,
                "price_overview": {"initial": 6000, "final": 3000, "discount_percent": 50},
                "metacritic": {"score": 78},
                "pc_requirements": {},
            },
            None,
            ("variadas", "(2.000)"),
            (25.00, "01/01/2026"),
            "Silver",
        )

        def _fake_fetch(aid, db_manager=None):
            return data_a if str(aid) == "10" else data_b

        with patch.object(self.api.api_client, "descargar_ficha_completa_paralelo", side_effect=_fake_fetch):
            res = self.api.compare_games_versus("10", "20")

        self.assertTrue(res["ok"])
        self.assertEqual(res["winner"], "A")
        self.assertEqual(res["score_a"], 5)
        self.assertEqual(res["score_b"], 0)
        self.assertEqual(len(res["rows"]), 5)

    def test_watchlist_tags_targets_and_check_drops_mocked(self):
        self.db.add_watchlist("1091500", "Cyberpunk 2077", 44.99, "https://store.steampowered.com/app/1091500")
        self.db.update_historical_min("1091500", 29.99, 33, 44.99)
        self.api.set_watchlist_tag("1091500", "RPG")
        self.api.set_watchlist_target_price("1091500", 20.0)

        wl = self.api.get_watchlist({"tag": "RPG"})
        self.assertEqual(wl["total"], 1)
        self.assertEqual(wl["items"][0]["tag"], "RPG")
        self.assertAlmostEqual(wl["items"][0]["target_price"], 20.0)

        with patch.object(
            self.api.api_client,
            "obtener_precios_argentina_lote",
            return_value={"1091500": {"normal": 44.99, "oferta": 15.74, "descuento": 65}},
        ):
            res = self.api.check_watchlist_drops()

        self.assertTrue(res["ok"])
        self.assertEqual(len(res["drops"]), 1)
        self.assertEqual(len(res["target_hits"]), 1)
        self.assertEqual(len(res["atl_hits"]), 1)

        wl_after = self.api.get_watchlist()
        self.assertTrue(wl_after["items"][0]["cumple_target"])
        self.assertEqual(wl_after["items"][0]["descuento"], 65)

    def test_atl_history_get_and_clear(self):
        self.db.registrar_alerta_atl("570", "Dota Plus", 4.99, 50)
        h1 = self.api.get_atl_history()
        self.assertTrue(h1["ok"])
        self.assertEqual(h1["count"], 1)

        cleared = self.api.clear_atl_history()
        self.assertTrue(cleared["ok"])
        h2 = self.api.get_atl_history()
        self.assertEqual(h2["count"], 0)

    def test_library_pagination_valuation_backlog_and_friend_cross(self):
        self.db.save_library_batch([
            {"appid": "10", "titulo": "Counter-Strike", "horas": 100.0, "minutos": 6000, "price_usd": 9.99},
            {"appid": "20", "titulo": "Hollow Knight", "horas": 0.0, "minutos": 0, "price_usd": -1.0},
            {"appid": "30", "titulo": "Deep Rock Galactic", "horas": 12.0, "minutos": 720, "price_usd": 14.99},
        ])

        with patch.object(
            self.api.api_client,
            "obtener_precios_argentina_lote",
            return_value={"20": {"normal": 14.99, "oferta": 7.49, "descuento": 50}},
        ):
            val_res = self.api.valuate_library()
        self.assertTrue(val_res["ok"])
        self.assertEqual(val_res["updated_count"], 1)

        with patch.object(
            self.api.api_client,
            "obtener_biblioteca_detalle",
            return_value=("76561198000000001", [{"appid": "30", "titulo": "Deep Rock Galactic", "horas": 5.0, "minutos": 300}]),
        ):
            cross = self.api.cross_friend_library("amigo")
        self.assertTrue(cross["ok"])
        self.assertEqual(cross["common_count"], 1)

        lib_coop = self.api.get_library({"filter_mode": "coop"})
        self.assertEqual(lib_coop["total_filtered"], 1)
        self.assertEqual(lib_coop["items"][0]["appid"], "30")
        self.assertAlmostEqual(lib_coop["valuation"]["total_value_usd"], 39.97)

        rnd = self.api.pick_random_backlog()
        self.assertTrue(rnd["ok"])
        self.assertEqual(rnd["game"]["appid"], "20")

        self.api.clear_friend_cross()
        self.assertEqual(self.api.get_library()["friend_id"], "")

    @patch("web_bridge.api_account.analizar_inventario_cromos")
    def test_analyze_trading_cards_mocked(self, mock_cards):
        mock_cards.return_value = {
            "exito": True,
            "error": None,
            "total_cromos": 10,
            "total_juegos": 1,
            "valor_bruto_usd": 0.60,
            "valor_neto_usd": 0.51,
            "valor_neto_ars": 510,
            "juegos": [{"game_name": "Cyberpunk 2077", "appid": 1091500, "cantidad": 10, "icon_url": ""}],
        }
        res = self.api.analyze_trading_cards("76561198000000000", force_refresh=True)
        self.assertTrue(res["ok"])
        self.assertEqual(res["total_cromos"], 10)
        self.assertAlmostEqual(res["valor_neto_usd"], 0.51)

    @patch("web_bridge.api_tools.obtener_cotizaciones_dolar")
    @patch("web_bridge.api_tools.obtener_promociones_gog")
    @patch("web_bridge.api_tools.obtener_promociones_epic")
    def test_radar_epic_events_and_live_fx_mocked(self, mock_epic, mock_gog, mock_fx):
        mock_epic.return_value = [
            {"tienda": "Epic Games", "titulo": "Control", "es_activo": True, "es_proximo": False},
            {"tienda": "Epic Games", "titulo": "Sifu", "es_activo": False, "es_proximo": True},
        ]
        mock_gog.return_value = {
            "gratis": [{"tienda": "GOG", "titulo": "Tyrian 2000", "es_gratis": True, "precio_oferta_usd": 0.0}],
            "ofertas": [{"tienda": "GOG", "titulo": "Witcher 3", "es_gratis": False, "precio_oferta_usd": 5.99, "descuento": 80}],
        }
        radar = self.api.get_free_games_radar(force_refresh=True)
        self.assertTrue(radar["ok"])
        self.assertEqual(len(radar["activos"]), 1)
        self.assertEqual(len(radar["proximos"]), 1)
        self.assertEqual(len(radar["gog_gratis"]), 1)
        self.assertEqual(len(radar["gog_ofertas"]), 1)

        ev = self.api.get_steam_events()
        self.assertTrue(ev["ok"])
        self.assertGreaterEqual(len(ev["events"]), 1)

        mock_fx.return_value = {
            "ok": True,
            "oficial": 1120.0,
            "cripto": 1280.0,
            "mep": 1250.0,
            "tarjeta": 1792.0,
            "source": "DolarAPI",
            "updated_at": "2026-11-24 10:55",
        }
        fx_res = self.api.refresh_live_fx()
        self.assertTrue(fx_res["ok"])
        self.assertFalse(fx_res["cached"])
        self.assertAlmostEqual(fx_res["dolar_referencia"], 1120.0)
        self.assertAlmostEqual(fx_res["dolar_cripto_ref"], 1280.0)
        self.assertAlmostEqual(fx_res["dolar_mep_ref"], 1250.0)
        self.assertEqual(fx_res["fx_source"], "DolarAPI")

    @patch("web_bridge.api_tools.obtener_cotizaciones_dolar")
    def test_refresh_live_fx_ttl_cache(self, mock_fx):
        mock_fx.return_value = {
            "ok": True,
            "oficial": 1130.0,
            "cripto": 1290.0,
            "mep": 1260.0,
            "tarjeta": 1808.0,
            "source": "DolarAPI",
            "updated_at": "2026-11-24 10:56",
        }
        first = self.api.refresh_live_fx(force=True)
        self.assertTrue(first["ok"])
        self.assertFalse(first["cached"])
        self.assertEqual(mock_fx.call_count, 1)

        second = self.api.refresh_live_fx(force=False, max_age_seconds=1800)
        self.assertTrue(second["ok"])
        self.assertTrue(second["cached"])
        self.assertAlmostEqual(second["dolar_referencia"], 1130.0)
        self.assertEqual(mock_fx.call_count, 1)

    def test_roulette_backlog_and_dashboard_stats(self):
        self.db.save_library_batch([
            {"appid": "10", "titulo": "Hades", "horas": 0.0, "minutos": 0, "price_usd": 24.99},
            {"appid": "20", "titulo": "Balatro", "horas": 35.0, "minutos": 2100, "price_usd": 14.99},
        ])
        self.api._deals_data = [
            {"appid": "100", "titulo": "Juego A", "descuento": 80, "genero": "Action, RPG", "precio_oferta_usd": 5.0},
            {"appid": "200", "titulo": "Juego B", "descuento": 100, "genero": "Indie", "precio_oferta_usd": 0.0},
        ]

        rl = self.api.spin_roulette(mode="backlog", exclude_appid="20")
        self.assertTrue(rl["ok"])
        self.assertEqual(rl["item"]["appid"], "10")
        self.assertEqual(len(rl["items"]), 1)
        self.assertIn("header_url", rl["items"][0])

        self.db.save_library_batch([
            {"appid": "10", "titulo": "Hades", "horas": 0.0, "minutos": 0, "price_usd": 24.99},
            {"appid": "20", "titulo": "Balatro", "horas": 35.0, "minutos": 2100, "price_usd": 14.99},
            {"appid": "30", "titulo": "Hollow Knight", "horas": 0.0, "minutos": 0, "price_usd": 14.99},
            {"appid": "40", "titulo": "Celeste", "horas": 0.0, "minutos": 0, "price_usd": 19.99},
        ])
        rl3 = self.api.spin_roulette(mode="backlog", exclude_appid="20", count=3)
        self.assertTrue(rl3["ok"])
        self.assertEqual(len(rl3["items"]), 3)
        self.assertEqual(rl3["item"], rl3["items"][0])
        self.assertIn("header_url", rl3["items"][0])

        stats = self.api.get_dashboard_stats()
        self.assertTrue(stats["ok"])
        self.assertEqual(stats["deals_total"], 2)
        self.assertEqual(stats["library_total"], 4)
        self.assertEqual(stats["top_played"][0]["appid"], "20")
        self.assertIn("summary", stats)
        self.assertAlmostEqual(stats["summary"]["total_value_usd"], 74.96)
        self.assertAlmostEqual(stats["summary"]["avg_discount_pct"], 90.0)

        cc = self.api.get_command_center_data()
        self.assertIn("next_event", cc)
        self.assertIsNotNone(cc["next_event"])

    def test_settings_blacklist_export_csv_and_backup_zip(self):
        saved = self.api.save_settings({
            "steam_id": "patoma89",
            "steam_api_key": "KEY123",
            "dolar_referencia": 1050.0,
            "dolar_cripto_ref": 1200.0,
            "impuestos_pct": 60.0,
            "umbral_alerta_pct": 70,
            "minimizar_a": "Bandeja",
            "sfx_enabled": False,
            "discord_webhook": "https://discord.com/api/webhooks/test",
            "watchdog_activado": True,
            "watchdog_intervalo_hs": 4,
            "alerta_sonido_atl": True,
        })
        self.assertTrue(saved["ok"])
        self.assertEqual(self.api.get_settings()["settings"]["steam_id"], "patoma89")

        self.db.add_blacklist("999", "Juego Oculto")
        self.assertEqual(len(self.api.get_blacklist()["items"]), 1)
        self.api.remove_from_blacklist("999")
        self.assertEqual(len(self.api.get_blacklist()["items"]), 0)

        self.db.add_watchlist("570", "Dota 2", 0.0, "https://store.steampowered.com/app/570")
        csv_path = os.path.join(self.tmp_dir.name, "wl_export.csv")
        csv_res = self.api.export_csv("watchlist", dest_path=csv_path)
        self.assertTrue(csv_res["ok"])
        self.assertTrue(os.path.isfile(csv_path))

        zip_path = os.path.join(self.tmp_dir.name, "backup.zip")
        zip_res = self.api.export_backup_zip(dest_path=zip_path)
        self.assertTrue(zip_res["ok"])
        self.assertTrue(os.path.isfile(zip_path))
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        self.assertIn("test_config.json", names)
        self.assertIn("test_cache.db", names)

    @patch("web_bridge.api.HTTP_SESSION.get")
    def test_check_updates_fallback_to_github_releases(self, mock_get):
        resp_fail = MagicMock()
        resp_fail.status_code = 503

        resp_gh = MagicMock()
        resp_gh.status_code = 200
        resp_gh.json.return_value = {
            "tag_name": "v99.1.0",
            "html_url": "https://github.com/Patoma89/SteamScope/releases/tag/v99.1.0",
            "body": "Mejora 1\n\nMejora 2",
            "assets": [
                {
                    "name": "SteamScope_v99.1.0_Setup.exe",
                    "browser_download_url": "https://example.com/SteamScope_v99.1.0_Setup.exe",
                }
            ],
        }
        mock_get.side_effect = [resp_fail, resp_gh]

        res = self.api.check_updates()
        self.assertTrue(res["ok"])
        self.assertTrue(res["has_update"])
        self.assertEqual(res["latest_version"], "99.1.0")
        self.assertEqual(res["url"], "https://example.com/SteamScope_v99.1.0_Setup.exe")
        self.assertEqual(res["notas"], ["Mejora 1", "Mejora 2"])
        self.assertEqual(mock_get.call_count, 2)

    @patch("web_bridge.api_tools.HTTP_SESSION.post")
    def test_send_discord_webhook_rating_formatting(self, mock_post):
        self.cfg.guardar_basico("discord_webhook", "https://discord.com/api/webhooks/test")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_post.return_value = mock_resp

        res_na = self.api.send_discord_webhook({
            "appid": "10",
            "titulo": "Juego Sin Rating",
            "precio_oferta_usd": 4.99,
            "descuento": 50,
            "rating": "N/A",
        })
        self.assertTrue(res_na["ok"])
        payload_na = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload_na["embeds"][0]["fields"][2]["value"], "N/A")

        res_num = self.api.send_discord_webhook({
            "appid": "20",
            "titulo": "Juego Top",
            "precio_oferta_usd": 9.99,
            "descuento": 75,
            "rating": "92",
        })
        self.assertTrue(res_num["ok"])
        payload_num = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload_num["embeds"][0]["fields"][2]["value"], "92%")

    def test_export_backup_zip_checkpoints_wal(self):
        self.db.add_watchlist("12345", "Test WAL Game", 9.99, "https://store.steampowered.com/app/12345")
        zip_path = os.path.join(self.tmp_dir.name, "wal_backup.zip")
        res = self.api.export_backup_zip(dest_path=zip_path)
        self.assertTrue(res["ok"])

        extract_dir = os.path.join(self.tmp_dir.name, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extract("test_cache.db", path=extract_dir)

        extracted_db = os.path.join(extract_dir, "test_cache.db")
        conn = sqlite3.connect(extracted_db)
        try:
            row = conn.execute("SELECT titulo FROM watchlist WHERE appid = ?", ("12345",)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Test WAL Game")

    @patch("web_bridge.api.HTTP_SESSION.get")
    def test_resolve_steam_cover_caches_and_hydrates_library(self, mock_get):
        tarkov_url = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/3932890/4dd12ea3/header.jpg"
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "3932890": {
                "success": True,
                "data": {"header_image": tarkov_url},
            }
        }
        mock_get.return_value = mock_resp

        self.db.save_library_batch([
            {"appid": "3932890", "titulo": "Escape from Tarkov", "horas": 12.0, "minutos": 720, "price_usd": 49.99},
        ])

        r1 = self.api.resolve_steam_cover("3932890")
        self.assertTrue(r1["ok"])
        self.assertFalse(r1["cached"])
        self.assertEqual(r1["url"], tarkov_url)
        self.assertEqual(mock_get.call_count, 1)

        r2 = self.api.resolve_steam_cover("3932890")
        self.assertTrue(r2["ok"])
        self.assertTrue(r2["cached"])
        self.assertEqual(r2["url"], tarkov_url)
        self.assertEqual(mock_get.call_count, 1)

        lib = self.api.get_library({"page": 1})
        self.assertEqual(lib["items"][0]["cover_url"], tarkov_url)


if __name__ == "__main__":
    unittest.main()
