"""
Pruebas Unitarias para el Gestor y Valorizador de Cromos de SteamScope 2.0.
"""

import unittest
from unittest.mock import patch, MagicMock
from core.cards_manager import analizar_inventario_cromos, COMISION_STEAM_PCT, PRECIO_PROMEDIO_CROMO_USD, _CACHE_INVENTARIO


class TestCardsManager(unittest.TestCase):
    def setUp(self):
        _CACHE_INVENTARIO.clear()
    @patch("core.cards_manager.HTTP_SESSION.get")
    def test_analizar_inventario_cromos_calculos(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "descriptions": [
                {
                    "classid": "cls_101",
                    "instanceid": "0",
                    "name": "Cromo Portal 2",
                    "type": "Cromo coleccionable",
                    "marketable": 1,
                    "market_hash_name": "620-Portal Card",
                    "icon_url": "portal.jpg",
                    "tags": [{"category": "Game", "localized_tag_name": "Portal 2"}]
                },
                {
                    "classid": "cls_102",
                    "instanceid": "0",
                    "name": "Cromo Terraria",
                    "type": "Cromo coleccionable reflectante",
                    "marketable": 1,
                    "market_hash_name": "105600-Terraria Card",
                    "icon_url": "terraria.jpg",
                    "tags": [{"category": "Game", "localized_tag_name": "Terraria"}]
                },
                {
                    "classid": "cls_103",
                    "instanceid": "0",
                    "name": "Emoticono Feliz",
                    "type": "Emoticono",
                    "marketable": 1,
                    "market_hash_name": "620-Smile",
                    "icon_url": "smile.jpg",
                    "tags": [{"category": "Game", "localized_tag_name": "Portal 2"}]
                }
            ]
        }
        mock_get.return_value = mock_resp

        res = analizar_inventario_cromos("76561198000000000", dolar_ref=1200.0)
        self.assertTrue(res["exito"])
        self.assertEqual(res["total_cromos"], 2)  # Solo los 2 cromos, ignora el emoticono
        self.assertEqual(res["total_juegos"], 2)
        
        # Verificar deducción exacta de la comisión de Steam (15%)
        esperado_bruto = round(2 * PRECIO_PROMEDIO_CROMO_USD, 2)
        esperado_neto = round(esperado_bruto * (1.0 - COMISION_STEAM_PCT), 2)
        self.assertEqual(res["valor_bruto_usd"], esperado_bruto)
        self.assertEqual(res["valor_neto_usd"], esperado_neto)
        self.assertEqual(res["valor_neto_ars"], round(esperado_neto * 1200.0))

        nombres_juegos = [j["game_name"] for j in res["juegos"]]
        self.assertIn("Portal 2", nombres_juegos)
        self.assertIn("Terraria", nombres_juegos)

    @patch("core.cards_manager.HTTP_SESSION.get")
    def test_analizar_inventario_perfil_privado(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        res = analizar_inventario_cromos("76561198000000000")
        self.assertFalse(res["exito"])
        self.assertIn("privado", res["error"].lower())

    def test_analizar_inventario_steamid_invalido(self):
        res = analizar_inventario_cromos("")
        self.assertFalse(res["exito"])
        self.assertIn("inválido", res["error"])


if __name__ == "__main__":
    unittest.main()
