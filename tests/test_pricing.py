import unittest
from datetime import datetime, timezone
from core.pricing import (
    limpiar_html,
    extraer_espacio_disco,
    calcular_tiempo_restante,
    _parse_version_tuple,
    detectar_suscripcion,
    evaluar_termometro_compra,
    ordenar_ofertas,
)


class TestPricing(unittest.TestCase):
    def test_limpiar_html(self):
        raw = "<p>Requisitos:<br><ul><li>8 GB RAM</li><li>GTX 1060 &amp; superior</li></ul></p>"
        clean = limpiar_html(raw)
        self.assertIn("• 8 GB RAM", clean)
        self.assertIn("• GTX 1060 & superior", clean)
        self.assertNotIn("<p>", clean)

    def test_extraer_espacio_disco(self):
        self.assertEqual(extraer_espacio_disco("Almacenamiento: 65 GB de espacio disponible"), "65 GB")
        self.assertEqual(extraer_espacio_disco("Storage: 512 MB available space"), "512 MB")
        self.assertEqual(extraer_espacio_disco("Sin datos de disco"), "N/D")

    def test_calcular_tiempo_restante(self):
        now = datetime.now(timezone.utc).timestamp()
        self.assertEqual(calcular_tiempo_restante(0), None)
        self.assertEqual(calcular_tiempo_restante(now - 100), "Termina pronto")
        self.assertIn("Termina en", calcular_tiempo_restante(now + 3600 * 5))
        self.assertIn("d", calcular_tiempo_restante(now + 3600 * 72))

    def test_parse_version_tuple(self):
        self.assertEqual(_parse_version_tuple("v1.7.0"), (1, 7, 0))
        self.assertTrue(_parse_version_tuple("v1.8.0") > _parse_version_tuple("1.7.2"))

    def test_detectar_suscripcion(self):
        res_gp = detectar_suscripcion("Halo Infinite", "Xbox Game Studios")
        self.assertIsNotNone(res_gp)
        self.assertEqual(res_gp[0], "PC GAME PASS")

        res_ea = detectar_suscripcion("Battlefield 2042", "Electronic Arts")
        self.assertIsNotNone(res_ea)
        self.assertEqual(res_ea[0], "EA PLAY + GAME PASS")

        res_ubi = detectar_suscripcion("Assassin's Creed Mirage", "Ubisoft")
        self.assertIsNotNone(res_ubi)
        self.assertEqual(res_ubi[0], "UBISOFT+")

        self.assertIsNone(detectar_suscripcion("Half-Life Alyx", "Valve"))

    def test_evaluar_termometro_compra(self):
        v_prox, _, _ = evaluar_termometro_compra(0, False, 0.0)
        self.assertIn("PRÓXIMAMENTE", v_prox)

        v_free, _, _ = evaluar_termometro_compra(100, True, 0.0)
        self.assertIn("GRATIS", v_free)

        v_atl, _, _ = evaluar_termometro_compra(60, True, 9.99)
        self.assertIn("COMPRÁ YA", v_atl)

        v_high, _, _ = evaluar_termometro_compra(80, False, 4.99)
        self.assertIn("EXCELENTE OFERTA", v_high)

    def test_ordenar_ofertas(self):
        items = [
            {"titulo": "Zelda", "descuento": 20, "precio_oferta_usd": 40.0, "rating": "85"},
            {"titulo": "Alan Wake", "descuento": 75, "precio_oferta_usd": 10.0, "rating": "92"},
            {"titulo": "Metro", "descuento": 50, "precio_oferta_usd": 5.0, "rating": "78"},
        ]
        ordenar_ofertas(items, "Mayor Descuento")
        self.assertEqual(items[0]["titulo"], "Alan Wake")

        ordenar_ofertas(items, "Precio: Menor a Mayor")
        self.assertEqual(items[0]["titulo"], "Metro")

        ordenar_ofertas(items, "Mejor Puntuación")
        self.assertEqual(items[0]["titulo"], "Alan Wake")

        ordenar_ofertas(items, "Alfabético")
        self.assertEqual(items[0]["titulo"], "Alan Wake")
        self.assertEqual(items[-1]["titulo"], "Zelda")

    def test_es_minimo_historico_real(self):
        from core.pricing import es_minimo_historico_real
        # Precio nuevo menor al anterior
        self.assertTrue(es_minimo_historico_real(9.99, 14.99))
        # Precio igual (con tolerancia)
        self.assertTrue(es_minimo_historico_real(9.99, 10.00))
        # Precio mayor
        self.assertFalse(es_minimo_historico_real(19.99, 9.99))
        # Sin mínimo previo
        self.assertTrue(es_minimo_historico_real(9.99, 0.0))
        # Precio cero o inválido
        self.assertFalse(es_minimo_historico_real(0.0, 10.0))

    def test_formatear_oferta_para_compartir(self):
        from core.pricing import formatear_oferta_para_compartir
        item = {
            "appid": "782330",
            "titulo": "DOOM Eternal",
            "precio_oferta_usd": 4.99,
            "descuento": 75,
            "rating": "91",
            "es_atl": True,
            "tiene_cromos": True,
        }
        res = formatear_oferta_para_compartir(item, dolar_ref=1000.0, impuestos_pct=60.0)
        self.assertIn("DOOM Eternal", res)
        self.assertIn("-75% OFF", res)
        self.assertIn("RÉCORD HISTÓRICO", res)
        self.assertIn("$4.99 USD", res)
        self.assertIn("7,984 ARS", res)
        self.assertIn("https://store.steampowered.com/app/782330", res)
        self.assertIn("Cromos", res)

    def test_es_steam_deck_verificado(self):
        from core.pricing import es_steam_deck_verificado
        self.assertTrue(es_steam_deck_verificado("Single-player, Deck Verified, Action"))
        self.assertTrue(es_steam_deck_verificado("Great on Deck, RPG"))
        self.assertTrue(es_steam_deck_verificado("Steam Deck Verificado"))
        self.assertFalse(es_steam_deck_verificado("Strategy, Multiplayer, Simulation"))
        self.assertFalse(es_steam_deck_verificado(""))


if __name__ == "__main__":
    unittest.main()
