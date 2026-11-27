import unittest
from unittest.mock import MagicMock, patch
from core.api_client import consultar_dolar_api, obtener_cotizaciones_dolar, resolver_steam_id, SteamAPIClient


class TestAPIClient(unittest.TestCase):
    def test_resolver_steam_id_direct(self):
        self.assertIsNone(resolver_steam_id("   "))
        self.assertEqual(resolver_steam_id("76561198000000000"), "76561198000000000")
        self.assertEqual(
            resolver_steam_id("https://steamcommunity.com/profiles/76561198000000000/"),
            "76561198000000000",
        )

    def test_obtener_precios_argentina_lote_mock(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "620": {
                "success": True,
                "data": {
                    "price_overview": {
                        "initial": 999,
                        "final": 199,
                        "discount_percent": 80,
                    }
                },
            }
        }
        mock_session.get.return_value = mock_resp

        client = SteamAPIClient(session=mock_session)
        precios = client.obtener_precios_argentina_lote(["620"])
        self.assertIn("620", precios)
        self.assertAlmostEqual(precios["620"]["normal"], 9.99)
        self.assertAlmostEqual(precios["620"]["oferta"], 1.99)
        self.assertEqual(precios["620"]["descuento"], 80)

    def test_obtener_datos_basicos_lote_mock(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "620": {
                "success": True,
                "data": {
                    "name": "Portal 2",
                    "type": "game",
                    "header_image": "https://example.com/portal2.jpg",
                },
            }
        }
        mock_session.get.return_value = mock_resp

        client = SteamAPIClient(session=mock_session)
        basicos = client.obtener_datos_basicos_lote(["620"])
        self.assertEqual(basicos["620"]["name"], "Portal 2")
        self.assertEqual(basicos["620"]["type"], "game")

    def test_obtener_cotizaciones_dolar_dolarapi_single_request(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"casa": "oficial", "venta": 1050.5},
            {"casa": "cripto", "venta": 1220.0},
            {"casa": "bolsa", "venta": 1195.0},
            {"casa": "tarjeta", "venta": 1680.8},
        ]
        mock_session.get.return_value = mock_resp

        fx = obtener_cotizaciones_dolar(session=mock_session)
        self.assertTrue(fx["ok"])
        self.assertAlmostEqual(fx["oficial"], 1050.5)
        self.assertAlmostEqual(fx["cripto"], 1220.0)
        self.assertAlmostEqual(fx["mep"], 1195.0)
        self.assertAlmostEqual(fx["tarjeta"], 1680.8)
        self.assertEqual(fx["source"], "DolarAPI")
        self.assertEqual(mock_session.get.call_count, 1)

    def test_obtener_cotizaciones_dolar_criptoya_dict_fallback(self):
        mock_session = MagicMock()
        resp_fail = MagicMock(status_code=503)
        resp_cy = MagicMock(status_code=200)
        resp_cy.json.return_value = {
            "oficial": {"price": 1095.5},
            "cripto": {"usdt": {"ask": 1210.0}},
            "mep": {"al30": {"ci": {"price": 1190.0}}},
        }
        mock_session.get.side_effect = [resp_fail, resp_cy]

        fx = obtener_cotizaciones_dolar(session=mock_session)
        self.assertTrue(fx["ok"])
        self.assertAlmostEqual(fx["oficial"], 1095.5)
        self.assertAlmostEqual(fx["cripto"], 1210.0)
        self.assertAlmostEqual(fx["mep"], 1190.0)
        self.assertEqual(fx["source"], "CriptoYa")

    def test_obtener_cotizaciones_dolar_bluelytics_fallback_and_sanity(self):
        mock_session = MagicMock()
        resp_bad = MagicMock(status_code=200)
        resp_bad.json.return_value = [
            {"casa": "oficial", "venta": -10},
            {"casa": "cripto", "venta": "invalido"},
        ]
        resp_cy_fail = MagicMock(status_code=500)
        resp_bl = MagicMock(status_code=200)
        resp_bl.json.return_value = {"oficial": {"value_sell": 1105.0}}
        mock_session.get.side_effect = [resp_bad, resp_cy_fail, resp_bl]

        fx = obtener_cotizaciones_dolar(session=mock_session)
        self.assertTrue(fx["ok"])
        self.assertAlmostEqual(fx["oficial"], 1105.0)
        self.assertIsNone(fx["cripto"])
        self.assertEqual(fx["source"], "Bluelytics")

    @patch("core.api_client.HTTP_SESSION.get")
    def test_consultar_dolar_api_criptoya_dict_oficial(self, mock_get):
        resp_fail = MagicMock(status_code=500)
        resp_cy = MagicMock(status_code=200)
        resp_cy.json.return_value = {"oficial": {"price": 1080.0}}
        mock_get.side_effect = [resp_fail, resp_cy]

        val = consultar_dolar_api("oficial")
        self.assertAlmostEqual(val, 1080.0)


if __name__ == "__main__":
    unittest.main()
