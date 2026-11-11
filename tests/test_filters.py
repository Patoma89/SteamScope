import unittest
from core.filters import (
    normalizar_texto,
    obtener_subcategorias_para,
    coincide_categoria_steam,
    coincide_busqueda_texto,
    filtrar_ofertas_en_memoria,
)


class TestFilters(unittest.TestCase):
    def test_normalizar_texto(self):
        self.assertEqual(normalizar_texto("¡Pokémon: Let's Go!"), "pokemon lets go")
        self.assertEqual(normalizar_texto("Áéíóú Üñ"), "aeiou un")
        self.assertEqual(normalizar_texto("  DOOM: Eternal  "), "doom eternal")
        self.assertEqual(normalizar_texto(""), "")
        self.assertEqual(normalizar_texto(None), "")

    def test_obtener_subcategorias_para(self):
        subcats_shooters = obtener_subcategorias_para("🎯 Shooters")
        self.assertIn("Todos los Shooters", subcats_shooters)
        self.assertIn("FPS (Primera Persona)", subcats_shooters)
        self.assertIn("Looter Shooter", subcats_shooters)

        subcats_invalid = obtener_subcategorias_para("Inexistente")
        self.assertEqual(subcats_invalid, ["Todas las subcategorías"])

    def test_coincide_categoria_steam(self):
        # Coincidencia con categoría padre completa
        tags_doom = "Action, FPS, Gore, Demons, Shooter"
        self.assertTrue(coincide_categoria_steam(tags_doom, "🎯 Shooters", "Todos los Shooters"))
        self.assertTrue(coincide_categoria_steam(tags_doom, "🎯 Shooters", "FPS (Primera Persona)"))
        self.assertFalse(coincide_categoria_steam(tags_doom, "🎯 Shooters", "Looter Shooter"))

        # Souls-like
        tags_elden = "Action RPG, Souls-like, Dark Fantasy, Difficult"
        self.assertTrue(coincide_categoria_steam(tags_elden, "⚔️ Rol / RPG", "Souls-like"))
        self.assertFalse(coincide_categoria_steam(tags_elden, "🎯 Shooters", "FPS (Primera Persona)"))

        # Categoría Todas
        self.assertTrue(coincide_categoria_steam(tags_doom, "Todas las Categorías"))

    def test_coincide_busqueda_texto(self):
        titulo = "Hades II"
        tags = "Roguelike, Action, Indie, Dungeon Crawler"

        # Búsqueda por título
        self.assertTrue(coincide_busqueda_texto("hades", titulo, tags))
        # Búsqueda por tag
        self.assertTrue(coincide_busqueda_texto("roguelike", titulo, tags))
        # Búsqueda combinada multi-término
        self.assertTrue(coincide_busqueda_texto("hades rogue", titulo, tags))
        # Búsqueda con acentos
        self.assertTrue(coincide_busqueda_texto("hàdés", titulo, tags))
        # No coincide
        self.assertFalse(coincide_busqueda_texto("cyberpunk", titulo, tags))

    def test_filtrar_ofertas_en_memoria(self):
        ofertas = [
            {
                "appid": "1",
                "titulo": "DOOM Eternal",
                "genero": "Action, FPS, Shooter",
                "precio_oferta_usd": 9.99,
                "descuento": 75,
                "rating": "92",
                "modalidad": "Single-Player",
                "es_atl": True,
                "tiene_cromos": True,
            },
            {
                "appid": "2",
                "titulo": "Borderlands 3",
                "genero": "Action, Looter Shooter, FPS, Co-op",
                "precio_oferta_usd": 14.99,
                "descuento": 85,
                "rating": "84",
                "modalidad": "Cooperativo Online",
                "es_atl": False,
                "tiene_cromos": True,
            },
            {
                "appid": "3",
                "titulo": "Hollow Knight",
                "genero": "Metroidvania, 2D, Difficult, Indie",
                "precio_oferta_usd": 7.49,
                "descuento": 50,
                "rating": "97",
                "modalidad": "Single-Player",
                "es_atl": True,
                "tiene_cromos": False,
            },
            {
                "appid": "4",
                "titulo": "Cities: Skylines II",
                "genero": "City Builder, Simulation, Management",
                "precio_oferta_usd": 39.99,
                "descuento": 20,
                "rating": "55",
                "modalidad": "Single-Player",
                "es_atl": False,
                "tiene_cromos": False,
            },
        ]

        # 1. Filtro solo ATL (mínimo histórico)
        res_atl = filtrar_ofertas_en_memoria(ofertas, solo_atl=True)
        self.assertEqual(len(res_atl), 2)
        self.assertEqual({x["appid"] for x in res_atl}, {"1", "3"})

        # 2. Filtro por subcategoría específica (Looter Shooter)
        res_looter = filtrar_ofertas_en_memoria(
            ofertas,
            categoria_padre="🎯 Shooters",
            subcategoria="Looter Shooter"
        )
        self.assertEqual(len(res_looter), 1)
        self.assertEqual(res_looter[0]["titulo"], "Borderlands 3")

        # 3. Filtro por categoría padre completa (Shooters)
        res_shooters = filtrar_ofertas_en_memoria(
            ofertas,
            categoria_padre="🎯 Shooters",
            subcategoria="Todos los Shooters"
        )
        self.assertEqual(len(res_shooters), 2)

        # 4. Filtro por rango de precio (menos de $10 USD)
        res_precio = filtrar_ofertas_en_memoria(ofertas, p_max=10.0)
        self.assertEqual(len(res_precio), 2)
        self.assertEqual({x["appid"] for x in res_precio}, {"1", "3"})

        # 5. Filtro por descuento (más de 60%)
        res_desc = filtrar_ofertas_en_memoria(ofertas, min_desc=60)
        self.assertEqual(len(res_desc), 2)
        self.assertEqual({x["appid"] for x in res_desc}, {"1", "2"})

        # 6. Filtro por rating mínimo (> 90%)
        res_rating = filtrar_ofertas_en_memoria(ofertas, min_rating=90)
        self.assertEqual(len(res_rating), 2)
        self.assertEqual({x["appid"] for x in res_rating}, {"1", "3"})

        # 7. Filtro por texto en vivo
        res_texto = filtrar_ofertas_en_memoria(ofertas, texto_busqueda="knight")
        self.assertEqual(len(res_texto), 1)
        self.assertEqual(res_texto[0]["titulo"], "Hollow Knight")

        # 8. Búsqueda con 0% descuento (min_desc=0 para búsqueda manual)
        ofertas_con_cero = ofertas + [{
            "appid": "5",
            "titulo": "Portal",
            "genero": "Puzzle, Sci-Fi",
            "precio_oferta_usd": 5.69,
            "descuento": 0,
            "rating": "98",
            "modalidad": "Single-Player",
            "es_atl": False,
            "tiene_cromos": True,
        }]
        res_cero = filtrar_ofertas_en_memoria(ofertas_con_cero, min_desc=0)
        self.assertEqual(len(res_cero), 5)
        self.assertIn("5", {x["appid"] for x in res_cero})

    def test_supervivencia_terror_categoria(self):
        tags_re = "Survival Horror, Zombies, Action, Atmospheric"
        self.assertTrue(coincide_categoria_steam(tags_re, "💀 Supervivencia & Terror", "Survival Horror"))
        self.assertTrue(coincide_categoria_steam(tags_re, "💀 Supervivencia & Terror", "Todos"))

    def test_filtro_gratis_y_ahorro_calculo(self):
        items = [
            {"titulo": "Juego Pago", "precio_oferta_usd": 9.99, "precio_normal_usd": 19.99, "descuento": 50},
            {"titulo": "Juego Regalado", "precio_oferta_usd": 0.0, "precio_normal_usd": 14.99, "descuento": 100},
            {"titulo": "Free To Play", "precio_oferta_usd": 0.0, "precio_normal_usd": 0.0, "descuento": 0},
        ]
        # Filtrado de 100% gratis por tiempo limitado o regalo
        gratis = [d for d in items if d.get("descuento") == 100 or (d.get("precio_oferta_usd", 1) == 0.0 and d.get("descuento", 0) > 0)]
        self.assertEqual(len(gratis), 1)
        self.assertEqual(gratis[0]["titulo"], "Juego Regalado")

        # Cálculo de ahorro
        ahorro_usd = sum(max(0.0, itm.get("precio_normal_usd", 0) - itm.get("precio_oferta_usd", 0)) for itm in items)
        self.assertAlmostEqual(ahorro_usd, 24.99, places=2)


if __name__ == "__main__":
    unittest.main()
