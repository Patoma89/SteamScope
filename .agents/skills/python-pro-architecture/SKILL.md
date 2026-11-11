---
name: python-pro-architecture
description: >-
  Use this skill whenever designing, structuring, or refactoring Python codebases following senior Clean Architecture, SOLID principles, resilient networking, SQLite performance patterns, and concurrency best practices.
---

# 🏛️ Python Pro Architecture: Clean Code & Robust Desktop Backend

Esta skill define los estándares de arquitectura y buenas prácticas de ingeniería de software para proyectos en Python de alta exigencia, asegurando código desacoplado, modular y altamente mantenible.

---

## 🧱 1. Separación de Responsabilidades (SRP & Capas)

El código debe dividirse estrictamente en dos dominios independientes:

```text
proyecto/
├── core/                  # Reglas de negocio puras (Backend agnóstico de UI)
│   ├── config.py          # Constantes, paletas y persistencia de configuración
│   ├── database.py        # Acceso a datos SQLite, caché local, transacciones
│   ├── api_client.py      # Clientes HTTP, deserialización y llamadas externas
│   ├── pricing.py         # Cálculos de negocio, lógica financiera, ordenamiento
│   └── exporters.py       # Generación de reportes (PDF, Excel, PNG, Webhooks)
├── ui/                    # Capa de presentación (Widgets, Ventanas y Eventos)
│   ├── modals.py          # Diálogos y ventanas secundarias
│   ├── charts.py          # Visualizaciones y gráficos embebidos
│   └── tray.py            # Integración con la bandeja de Windows
└── AppPrincipal.py        # Punto de entrada y orquestador
```

### Reglas de Dependencia:
1. `core/` **nunca** debe importar desde `ui/` ni conocer nada sobre CustomTkinter o Tkinter (salvo callbacks inyectados o adaptadores).
2. Los modelos de datos y diccionarios deben ser planos y serializables.
3. Si `core/` necesita emitir una notificación o pedir confirmación, recibe una función callback (Dependency Inversion).

---

## 🗄️ 2. Persistencia en SQLite de Alto Rendimiento

### Modo WAL y Conexión Segura
Para evitar bloqueos `database is locked` entre hilos de lectura y escritura:

```python
import sqlite3

def inicializar_conexion(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("PRAGMA journal_mode = WAL;")        # Concurrencia lectura/escritura
        conn.execute("PRAGMA synchronous = NORMAL;")       # Velocidad óptima sin riesgo
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA cache_size = -8000;")        # 8 MB de caché en RAM
    return conn
```

### Inserciones en Lote Atómicas (Batching)
Nunca ejecutar sentencias `execute()` en un bucle individual para listas de datos. Usar transacciones explícitas con `executemany`:

```python
def guardar_lote_juegos(conn: sqlite3.Connection, juegos: list[dict]):
    sql = """
    INSERT INTO biblioteca (appid, titulo, horas, precio_usd, actualizado_en)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(appid) DO UPDATE SET
        horas = excluded.horas,
        precio_usd = COALESCE(excluded.precio_usd, biblioteca.precio_usd),
        actualizado_en = excluded.actualizado_en;
    """
    filas = [
        (j["appid"], j["titulo"], j.get("horas", 0.0), j.get("precio_usd"), j["fecha"])
        for j in juegos
    ]
    with conn:  # Inicia transacción implícita; hace commit o rollback automático
        conn.executemany(sql, filas)
```

---

## 🌐 3. Cliente HTTP Resiliente (Networking de Producción)

### Reutilización de Conexiones y Reintentos Automáticos
Instanciar una sesión global con adaptadores de reintento para mitigar caídas de red o `503 Service Unavailable`:

```python
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

def crear_sesion_http() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "SteamScope/1.8.0 (Windows NT 10.0; Win64; x64) DesktopClient",
        "Accept": "application/json"
    })
    return session
```

### Reglas de Networking:
- **SIEMPRE especificar `timeout`** en cada llamada (ej. `timeout=4.0` o `timeout=(3.0, 10.0)` para conectar/leer).
- Usar bloques `try/except requests.RequestException` para encapsular errores y no propagar excepciones crudas a la UI.

---

## 💾 4. Escritura Atómica de Archivos de Configuración (Evitar Corrupción)

Para evitar que un corte de energía o cierre repentino corrompa `config.json`:

```python
import json
import os
import tempfile

def guardar_json_atomico(ruta_destino: str, datos: dict):
    directorio = os.path.dirname(ruta_destino)
    os.makedirs(directorio, exist_ok=True)
    
    # Escribir primero en un archivo temporal en el mismo directorio
    fd, temp_path = tempfile.mkstemp(dir=directorio, prefix="cfg_tmp_", text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
        
    # Reemplazo atómico garantizado por el sistema operativo
    os.replace(temp_path, ruta_destino)
```

---

## 🛡️ 5. Tipado y Firmas Claras (PEP 484 & PEP 585)

Usar anotaciones de tipo nativas (`list`, `dict`, `tuple`, `str | None`) para mejorar la autocompletación y detectar errores antes del tiempo de ejecución:

```python
def calcular_termometro(
    descuento: int,
    es_minimo_historico: bool,
    precio_oferta: float
) -> tuple[str, str, int]:
    """Evalúa la conveniencia de compra de un título.
    
    Returns:
        tuple[veredicto, color_hex, puntaje_1_al_10]
    """
    if descuento >= 75 or es_minimo_historico:
        return ("🔥 COMPRA OBLIGADA", "#00e676", 10)
    elif descuento >= 50:
        return ("⭐ MUY BUENA OFERTA", "#38bdf8", 8)
    return ("⚖️ OFERTA REGULAR", "#ffab00", 5)
```
