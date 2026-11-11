import os
import csv
import tempfile
import unittest
from core.exporters import escribir_csv
from core.config import limpiar_cache_imagenes


class TestExportersAndMaintenance(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_escribir_csv_with_accents_and_quotes(self):
        file_path = os.path.join(self.tmp_dir.name, "test_export.csv")
        cabeceras = ["AppID", "Título", "Precio USD", "Estado Backlog"]
        filas = [
            ["1091500", "Cyberpunk 2077: Phantom Liberty", "$29.99", "🏆 Viciado (+20 hs)"],
            ["1245620", "Elden Ring, \"Edición Deluxe\"", "$47.99", "💤 Sin estrenar (0 hs)"],
        ]
        escribir_csv(file_path, cabeceras, filas)
        self.assertTrue(os.path.exists(file_path))

        # Leer asegurando que decodifica utf-8-sig
        with open(file_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 3)
            self.assertEqual(reader[0], cabeceras)
            self.assertEqual(reader[1][1], "Cyberpunk 2077: Phantom Liberty")
            self.assertEqual(reader[2][1], "Elden Ring, \"Edición Deluxe\"")
            self.assertEqual(reader[2][3], "💤 Sin estrenar (0 hs)")

    def test_limpiar_cache_imagenes_runs_safely(self):
        borrados, mb = limpiar_cache_imagenes()
        self.assertIsInstance(borrados, int)
        self.assertIsInstance(mb, float)
        self.assertGreaterEqual(borrados, 0)
        self.assertGreaterEqual(mb, 0.0)


if __name__ == "__main__":
    unittest.main()
