"""
Pruebas Unitarias para el Módulo de Radar Multi-Tienda (Epic Games Store) de SteamScope 2.0.
"""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from core.multi_store import (
    _CACHE_EPIC,
    _CACHE_GOG,
    obtener_promociones_epic,
    obtener_promociones_gog,
)


class TestMultiStore(unittest.TestCase):
    def setUp(self):
        _CACHE_EPIC["datos"] = []
        _CACHE_EPIC["timestamp"] = 0.0
        _CACHE_GOG["datos"] = {"gratis": [], "ofertas": []}
        _CACHE_GOG["timestamp"] = 0.0

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

    @patch("core.multi_store.HTTP_SESSION.get")
    def test_obtener_promociones_gog_parsing(self, mock_get):
        resp_free = MagicMock(status_code=200)
        resp_free.json.return_value = {
            "products": [
                {
                    "title": "Daggerfall Unity",
                    "coverHorizontal": "//images.gog-statics.com/df.png",
                    "storeLink": "/en/game/daggerfall",
                    "price": {
                        "final": "$0.00",
                        "base": "$0.00",
                        "discount": None,
                        "finalMoney": {"amount": "0.00", "currency": "USD"},
                        "baseMoney": {"amount": "0.00", "currency": "USD"},
                    },
                }
            ]
        }
        resp_deals = MagicMock(status_code=200)
        resp_deals.json.return_value = {
            "products": [
                {
                    "title": "Fallout 4 GOTY",
                    "coverHorizontal": "https://images.gog-statics.com/fo4.png",
                    "storeLink": "https://www.gog.com/en/game/fallout_4",
                    "price": {
                        "final": "$6.99",
                        "base": "$27.99",
                        "discount": "-75%",
                        "finalMoney": {"amount": "6.99", "currency": "USD"},
                        "baseMoney": {"amount": "27.99", "currency": "USD"},
                    },
                }
            ]
        }
        mock_get.side_effect = [resp_free, resp_deals]

        gog = obtener_promociones_gog(forzar_refresco=True)
        self.assertEqual(len(gog["gratis"]), 1)
        self.assertEqual(gog["gratis"][0]["titulo"], "Daggerfall Unity")
        self.assertEqual(gog["gratis"][0]["imagen_url"], "https://images.gog-statics.com/df.png")
        self.assertEqual(gog["gratis"][0]["url_tienda"], "https://www.gog.com/en/game/daggerfall")
        self.assertTrue(gog["gratis"][0]["es_gratis"])

        self.assertEqual(len(gog["ofertas"]), 1)
        self.assertEqual(gog["ofertas"][0]["titulo"], "Fallout 4 GOTY")
        self.assertAlmostEqual(gog["ofertas"][0]["precio_oferta_usd"], 6.99)
        self.assertEqual(gog["ofertas"][0]["descuento"], 75)

    @patch("core.multi_store.HTTP_SESSION.get")
    def test_obtener_promociones_gog_error_handling(self, mock_get):
        mock_get.side_effect = Exception("Fallo de red GOG")
        gog = obtener_promociones_gog(forzar_refresco=True)
        self.assertEqual(gog, {"gratis": [], "ofertas": []})


if __name__ == "__main__":
    unittest.main()
