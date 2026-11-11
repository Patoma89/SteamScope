import unittest
from unittest.mock import MagicMock
from core.api_client import resolver_steam_id, SteamAPIClient


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


if __name__ == "__main__":
    unittest.main()
