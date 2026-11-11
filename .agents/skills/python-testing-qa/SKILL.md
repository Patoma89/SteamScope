---
name: python-testing-qa
description: >-
  Use this skill whenever writing, running, or debugging unit tests, integration tests, mock fixtures, and quality assurance workflows in Python. Covers unittest, unittest.mock, HTTP mocking, database isolation, and pre-commit syntax compilation.
---

# 🧪 Python Testing & QA Pro: Pruebas Unitarias y Aseguramiento de Calidad

Esta skill proporciona las directivas para implementar suites de pruebas unitarias robustas, rápidas y determinísticas sin dependencias de red externa ni efectos colaterales sobre datos reales.

---

## 🚀 1. Ejecución de la Suite de Pruebas

Para correr todos los tests de forma unificada:

```powershell
# Ejecución estándar con detalle exhaustivo
py -m unittest discover -s tests -v

# Ejecución de un archivo de pruebas específico
py -m unittest tests.test_database -v

# Verificación de sintaxis de todo el proyecto (Pre-commit check)
py -m py_compile SteamScope.py core\*.py ui\*.py tests\*.py
```

---

## 🎭 2. Mocking de Conexiones HTTP y APIs Externas

Las pruebas unitarias **NUNCA** deben realizar llamadas HTTP reales a Internet (Steam, CheapShark, SteamSpy). Deben aislarse con `unittest.mock.patch`:

### Ejemplo de Mock para `requests` / `HTTP_SESSION`
```python
import unittest
from unittest.mock import patch, MagicMock
from core.api_client import SteamAPIClient

class TestSteamAPI(unittest.TestCase):
    def setUp(self):
        self.client = SteamAPIClient()

    @patch("core.api_client.HTTP_SESSION.get")
    def test_obtener_precios_argentina_lote(self, mock_get):
        # 1. Configurar respuesta falsa (Payload simulado)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "730": {
                "success": True,
                "data": {
                    "price_overview": {
                        "initial": 1499,
                        "final": 749,
                        "discount_percent": 50
                    }
                }
            }
        }
        mock_get.return_value = mock_response

        # 2. Ejecutar la función real
        resultado = self.client.obtener_precios_argentina_lote(["730"])

        # 3. Aserciones de negocio
        self.assertIn("730", resultado)
        self.assertEqual(resultado["730"]["oferta"], 7.49)
        self.assertEqual(resultado["730"]["descuento"], 50)
        self.assertEqual(resultado["730"]["normal"], 14.99)
```

---

## 🗃️ 3. Aislamiento de Base de Datos para Tests (BD Temporal)

Nunca correr tests sobre la base de datos de producción `steamscope.db`. Usar siempre un directorio temporal o una base en memoria:

```python
import os
import tempfile
import unittest
from core.database import DatabaseManager

class TestDatabaseIsolation(unittest.TestCase):
    def setUp(self):
        # Crear directorio temporal aislado
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self.temp_dir.name, "test_steamscope.db")
        
        # Instanciar el gestor apuntando a la ruta temporal
        self.db = DatabaseManager(db_path=self.test_db_path)

    def tearDown(self):
        # Cerrar conexión y limpiar archivos temporales
        self.db.get_connection().close()
        self.temp_dir.cleanup()

    def test_insercion_y_recuperacion_watchlist(self):
        self.db.add_watchlist("105600", "Terraria", 4.99, "https://store.steampowered.com/app/105600")
        items = self.db.get_all_watchlist()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], "105600")
        self.assertEqual(items[0][1], "Terraria")
        self.assertEqual(items[0][2], 4.99)
```

---

## 📐 4. Buenas Prácticas de Aserciones

- Usar métodos específicos de `TestCase` en lugar de `assert` genérico para reportes claros de fallos:
  - `self.assertEqual(a, b)`: Imprime el diff detallado cuando los valores difieren.
  - `self.assertAlmostEqual(a, b, places=2)`: Para cálculos financieros o con floats.
  - `self.assertIn(elem, contenedor)`: Para verificar existencia en listas o diccionarios.
  - `self.assertRaises(ValueError)` o `with self.assertRaises(Exception):`: Para verificar excepciones esperadas.
  - `self.assertIsNone(x)` / `self.assertIsNotNone(x)`.

---

## 📋 5. Checklist para Nuevos Módulos
1. Cada nueva función pura en `core/` debe tener su correspondiente test en `tests/test_<modulo>.py`.
2. Las pruebas deben ejecutarse en menos de 1 segundo en total.
3. El pre-commit compile check (`py -m py_compile`) debe reportar 0 errores de sintaxis o indentación.
