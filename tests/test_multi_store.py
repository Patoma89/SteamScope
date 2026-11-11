"""
Pruebas Unitarias para el Módulo de Radar Multi-Tienda (Epic Games Store) de SteamScope 2.0.
"""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from core.multi_store import obtener_promociones_epic, _CACHE_EPIC


class TestMultiStore(unittest.TestCase):
    def setUp(self):
        _CACHE_EPIC["datos"] = []
        _CACHE_EPIC["timestamp"] = 0.0

    @patch("core.multi_store.HTTP_SESSION.get")
    def test_obtener_promociones_epic_parsing(self, mock_get):
        now = datetime.now(timezone.utc)
        start_active = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_active = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        start_upcoming = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_upcoming = (now + timedelta(days=12)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "Catalog": {
                    "searchStore": {
                        "elements": [
                            {
                                "id": "game-1",
                                "title": "Juego Gratis Actual",
                                "description": "Un juego increíble gratis ahora",
                                "productSlug": "juego-gratis-actual",
                                "keyImages": [
                                    {"type": "Thumbnail", "url": "https://epic.com/thumb.jpg"},
                                    {"type": "DieselStoreFrontWide", "url": "https://epic.com/banner.jpg"}
                                ],
                                "price": {
                                    "totalPrice": {
                                        "originalPrice": 1999,
                                        "discountPrice": 0
                                    }
                                },
                                "promotions": {
                                    "promotionalOffers": [
                                        {
                                            "promotionalOffers": [
                                                {
                                                    "startDate": start_active,
                                                    "endDate": end_active,
                                                    "discountSetting": {
                                                        "discountType": "PERCENTAGE",
                                                        "discountPercentage": 0
                                                    }
                                                }
                                            ]
                                        }
                                    ],
                                    "upcomingPromotionalOffers": []
                                }
                            },
                            {
                                "id": "game-2",
                                "title": "Juego Próxima Semana",
                                "description": "Próximamente disponible",
                                "productSlug": "juego-proxima-semana",
                                "keyImages": [
                                    {"type": "OfferImageWide", "url": "https://epic.com/up.jpg"}
                                ],
                                "price": {
                                    "totalPrice": {
                                        "originalPrice": 2999,
                                        "discountPrice": 2999
                                    }
                                },
                                "promotions": {
                                    "promotionalOffers": [],
                                    "upcomingPromotionalOffers": [
                                        {
                                            "promotionalOffers": [
                                                {
                                                    "startDate": start_upcoming,
                                                    "endDate": end_upcoming,
                                                    "discountSetting": {
                                                        "discountType": "PERCENTAGE",
                                                        "discountPercentage": 0
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }
        mock_get.return_value = mock_response

        res = obtener_promociones_epic(forzar_refresco=True)
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 2)

        # Buscar juego activo y próximo
        activo = next((j for j in res if j["es_activo"]), None)
        proximo = next((j for j in res if j["es_proximo"]), None)

        self.assertIsNotNone(activo)
        self.assertIsNotNone(proximo)

        self.assertEqual(activo["titulo"], "Juego Gratis Actual")
        self.assertEqual(activo["precio_original_usd"], 19.99)
        self.assertIn("epicgames.com", activo["url_tienda"])

        self.assertEqual(proximo["titulo"], "Juego Próxima Semana")
        self.assertEqual(proximo["precio_original_usd"], 29.99)

    @patch("core.multi_store.HTTP_SESSION.get")
    def test_obtener_promociones_epic_error_handling(self, mock_get):
        mock_get.side_effect = Exception("Fallo de conexión simulado")
        res = obtener_promociones_epic(forzar_refresco=True)
        self.assertEqual(res, [])


if __name__ == "__main__":
    unittest.main()
