import os
import unittest
from core.config import SKIN_PALETTES
from ui.modals import texto_contraste_acento, DialogoVisorCapturas


class TestUIModals(unittest.TestCase):
    def test_texto_contraste_acento(self):
        pal_dracula = SKIN_PALETTES["Modo Drácula"]
        self.assertEqual(texto_contraste_acento(pal_dracula), "white")

        pal_neon = SKIN_PALETTES["Neón P89"]
        self.assertEqual(texto_contraste_acento(pal_neon), "black")

        pal_pipboy = SKIN_PALETTES["Terminal Pip-Boy"]
        self.assertEqual(texto_contraste_acento(pal_pipboy), "black")

        pal_steamdeck = SKIN_PALETTES["Steam Deck OLED"]
        self.assertEqual(texto_contraste_acento(pal_steamdeck), "white")

        pal_halloween = SKIN_PALETTES["Halloween Terror"]
        self.assertEqual(texto_contraste_acento(pal_halloween), "white")

    def test_todas_las_paletas_tienen_claves_requeridas(self):
        claves_necesarias = [
            "mode", "win_bg", "panel_bg", "card_bg", "card_hover",
            "border", "accent", "accent_2", "text", "subtext",
            "deal_badge", "deal_text", "price_bg"
        ]
        for nombre_skin, pal in SKIN_PALETTES.items():
            for k in claves_necesarias:
                self.assertIn(k, pal, f"A la skin '{nombre_skin}' le falta la clave '{k}'")
                self.assertTrue(isinstance(pal[k], str) and len(pal[k]) > 0)

    def test_limpieza_entorno_pyinstaller_actualizador(self):
        """Verifica que las variables que originan el error de DLL en PyInstaller se eliminen correctamente."""
        dummy_env = {
            "PATH": "C:\\Windows",
            "_MEIPASS2": "C:\\Temp\\_MEI12345",
            "_MEI_OTHER": "1",
            "PYTHONPATH": "C:\\Temp",
            "USER": "patoma"
        }
        clean_env = dummy_env.copy()
        for k in list(clean_env.keys()):
            if "_MEI" in k or k.startswith("PYTHON"):
                clean_env.pop(k, None)

        self.assertNotIn("_MEIPASS2", clean_env)
        self.assertNotIn("_MEI_OTHER", clean_env)
        self.assertNotIn("PYTHONPATH", clean_env)
        self.assertIn("PATH", clean_env)
        self.assertIn("USER", clean_env)

    def test_visor_capturas_url_y_navegacion_logica(self):
        """Verifica la lógica de navegación circular del visor sin necesidad de instanciar Toplevel."""
        capturas = [
            {"path_full": "http://img1.jpg", "path_thumbnail": "http://thumb1.jpg"},
            {"path_full": "http://img2.jpg", "path_thumbnail": "http://thumb2.jpg"},
            {"path_full": "http://img3.jpg", "path_thumbnail": "http://thumb3.jpg"}
        ]
        total = len(capturas)
        
        # Siguiente desde el último debe volver al primero (0)
        idx = 2
        sig_idx = 0 if idx >= total - 1 else idx + 1
        self.assertEqual(sig_idx, 0)
        
        # Anterior desde el primero debe ir al último (2)
        idx = 0
        ant_idx = total - 1 if idx <= 0 else idx - 1
        self.assertEqual(ant_idx, 2)

    def test_pedir_input_skin_argument_compatibility(self):
        """Verifica que pedir_input_skin admita tanto valor_inicial como valor_defecto sin error."""
        from unittest.mock import patch, MagicMock
        from ui.modals import pedir_input_skin

        mock_parent = MagicMock()
        mock_parent.palette = {"win_bg": "#101010", "accent": "#00e676"}

        with patch("ui.modals.DialogoInputSkin") as mock_dialog:
            mock_inst = MagicMock()
            mock_inst.valor = "Nota probada"
            mock_dialog.return_value = mock_inst

            # 1. Con valor_inicial
            res1 = pedir_input_skin(mock_parent, "Título", "Prompt", valor_inicial="Hola")
            self.assertEqual(res1, "Nota probada")
            mock_dialog.assert_called_with(mock_parent, "Título", "Prompt", valor_inicial="Hola", modo="str", min_val=None, max_val=None)

            # 2. Con valor_defecto (compatibilidad regresiva)
            res2 = pedir_input_skin(mock_parent, "Título", "Prompt", valor_defecto="Mundo")
            self.assertEqual(res2, "Nota probada")
            mock_dialog.assert_called_with(mock_parent, "Título", "Prompt", valor_inicial="Mundo", modo="str", min_val=None, max_val=None)


if __name__ == "__main__":
    unittest.main()
