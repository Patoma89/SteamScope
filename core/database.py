import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from core.config import obtener_ruta_appdata


class DatabaseManager:
    """
    Repositorio SQLite optimizado bajo estrategia Zero-Waste y SRP:
    - Modo WAL + Índices para búsquedas O(log N).
    - Context manager que garantiza el cierre real de descriptores (conn.close()).
    - Caché en memoria RAM para sets de IDs frecuentes (Watchlist / Blacklist),
      eliminando las 25 consultas a disco al renderizar páginas de tarjetas.
    - Operaciones en lote (batching) para actualizar mínimos históricos en una única transacción.
    """
    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.join(obtener_ruta_appdata(), "steam_cache.db")
        self._watchlist_ids_cache = None
        self._blacklist_ids_cache = None
        self.init_db()

    def get_connection(self):
        """Mantiene compatibilidad con cierres directos y devuelve una conexión configurada."""
        conn = sqlite3.connect(self.db_path, timeout=15)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

    @contextmanager
    def session(self):
        """Context manager seguro que hace commit automático y cierra la conexión al salir."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        with self.session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS game_metadata ("
                "appid TEXT PRIMARY KEY, modalidad TEXT, genero TEXT, is_sp INTEGER, is_mp INTEGER, genres_list TEXT)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS watchlist ("
                "appid TEXT PRIMARY KEY, titulo TEXT, precio_guardado REAL, fecha_guardado TEXT, "
                "link TEXT, custom_tag TEXT, target_price REAL DEFAULT 0.0)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS price_history ("
                "appid TEXT PRIMARY KEY, min_price_usd REAL, date_recorded TEXT)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS price_log ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, appid TEXT, price_usd REAL, date_recorded TEXT)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS blacklist (appid TEXT PRIMARY KEY, titulo TEXT)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS user_library ("
                "appid TEXT PRIMARY KEY, titulo TEXT, horas REAL DEFAULT 0.0, "
                "minutos INTEGER DEFAULT 0, thumb_url TEXT, price_usd REAL DEFAULT -1.0)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS atl_alerts_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, appid TEXT, titulo TEXT, "
                "precio_usd REAL, desc_pct INTEGER, fecha TEXT)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS game_notes ("
                "appid TEXT PRIMARY KEY, note TEXT, updated_at TEXT)"
            )
            # Índices para eliminar Full Table Scans en historial de precios y alertas
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_log_appid_date ON price_log(appid, date_recorded)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_atl_alerts_fecha ON atl_alerts_history(fecha DESC)"
            )
            for alter_sql in (
                "ALTER TABLE watchlist ADD COLUMN custom_tag TEXT",
                "ALTER TABLE watchlist ADD COLUMN target_price REAL DEFAULT 0.0",
                "ALTER TABLE watchlist ADD COLUMN personal_note TEXT DEFAULT ''",
                "ALTER TABLE blacklist ADD COLUMN titulo TEXT",
                "ALTER TABLE user_library ADD COLUMN price_usd REAL DEFAULT -1.0",
            ):
                try:
                    cursor.execute(alter_sql)
                except Exception:
                    pass

    def invalidate_caches(self):
        """Invalida los sets cacheados en RAM (útil tras importar un backup externo)."""
        self._watchlist_ids_cache = None
        self._blacklist_ids_cache = None

    # ================= BLACKLIST =================
    def add_blacklist(self, appid, titulo="Juego Oculto"):
        appid = str(appid)
        try:
            with self.session() as conn:
                conn.cursor().execute("INSERT OR REPLACE INTO blacklist (appid, titulo) VALUES (?, ?)", (appid, titulo))
            if self._blacklist_ids_cache is not None:
                self._blacklist_ids_cache.add(appid)
        except Exception:
            pass

    def remove_blacklist(self, appid):
        appid = str(appid)
        try:
            with self.session() as conn:
                conn.cursor().execute("DELETE FROM blacklist WHERE appid = ?", (appid,))
            if self._blacklist_ids_cache is not None:
                self._blacklist_ids_cache.discard(appid)
        except Exception:
            pass

    def clear_blacklist(self):
        try:
            with self.session() as conn:
                conn.cursor().execute("DELETE FROM blacklist")
            self._blacklist_ids_cache = set()
        except Exception:
            pass

    def get_blacklist(self):
        """Retorna lista de AppIDs ignorados usando caché en memoria RAM."""
        if self._blacklist_ids_cache is None:
            try:
                with self.session() as conn:
                    rows = conn.cursor().execute("SELECT appid FROM blacklist").fetchall()
                    self._blacklist_ids_cache = {str(row[0]) for row in rows}
            except Exception:
                return []
        return list(self._blacklist_ids_cache)

    def get_blacklist_details(self):
        try:
            with self.session() as conn:
                rows = conn.cursor().execute("SELECT appid, titulo FROM blacklist").fetchall()
                return [(str(row[0]), row[1] or f"AppID {row[0]}") for row in rows]
        except Exception:
            return []

    # ================= HISTORIAL DE PRECIOS =================
    def update_historical_min(self, appid, current_price_usd, discount_pct=0, normal_price_usd=0.0):
        if current_price_usd <= 0:
            return False
        res = self.update_historical_min_batch([(appid, current_price_usd, discount_pct, normal_price_usd)])
        return res.get(str(appid), False)

    def update_historical_min_batch(self, items_price_pairs):
        """
        Actualiza el registro histórico de múltiples juegos en UNA ÚNICA transacción SQLite.
        Acepta:
          - dict {appid: current_price_usd} o {appid: (current_price_usd, discount_pct, normal_price_usd)}
          - lista de tuplas [(appid, current_price_usd)] o [(appid, current_price_usd, discount_pct, normal_price_usd)]
        Retorna dict {appid_str: es_atl_bool}.
        """
        resultados = {}
        if not items_price_pairs:
            return resultados

        validos = []
        if isinstance(items_price_pairs, dict):
            for aid, val in items_price_pairs.items():
                if isinstance(val, (tuple, list)):
                    p = float(val[0]) if len(val) > 0 and val[0] else 0.0
                    d = int(val[1]) if len(val) > 1 and val[1] else 0
                    n = float(val[2]) if len(val) > 2 and val[2] else p
                else:
                    p = float(val) if val else 0.0
                    d = 0
                    n = p
                if p > 0:
                    validos.append((str(aid), p, d, n))
        else:
            for item in items_price_pairs:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    aid = str(item[0])
                    p = float(item[1]) if item[1] else 0.0
                    d = int(item[2]) if len(item) > 2 and item[2] else 0
                    n = float(item[3]) if len(item) > 3 and item[3] else p
                    if p > 0:
                        validos.append((aid, p, d, n))

        if not validos:
            return resultados

        fecha = datetime.now().strftime("%Y-%m-%d")
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                for appid, current_price_usd, discount_pct, normal_price_usd in validos:
                    existing_log = cursor.execute(
                        "SELECT id, price_usd FROM price_log WHERE appid = ? AND date_recorded = ?",
                        (appid, fecha)
                    ).fetchone()
                    if not existing_log:
                        cursor.execute(
                            "INSERT INTO price_log (appid, price_usd, date_recorded) VALUES (?, ?, ?)",
                            (appid, current_price_usd, fecha)
                        )
                    elif current_price_usd != existing_log[1]:
                        cursor.execute(
                            "UPDATE price_log SET price_usd = ? WHERE id = ?",
                            (current_price_usd, existing_log[0])
                        )

                    row = cursor.execute(
                        "SELECT min_price_usd FROM price_history WHERE appid = ?", (appid,)
                    ).fetchone()
                    if not row:
                        cursor.execute(
                            "INSERT INTO price_history (appid, min_price_usd, date_recorded) VALUES (?, ?, ?)",
                            (appid, current_price_usd, fecha)
                        )
                        # En la primera vez que vemos el juego localmente, solo marcamos ATL preliminar
                        # si tiene un descuento extremo (>= 75%), para no dar falsos positivos en precios normales
                        resultados[appid] = (discount_pct >= 75)
                    elif current_price_usd <= row[0]:
                        if current_price_usd < row[0]:
                            cursor.execute(
                                "UPDATE price_history SET min_price_usd = ?, date_recorded = ? WHERE appid = ?",
                                (current_price_usd, fecha, appid)
                            )
                        # Solo es Mínimo Histórico si tiene descuento real (> 0%) o bajó respecto al precio normal
                        es_oferta_real = (discount_pct > 0) or (normal_price_usd > current_price_usd) or (current_price_usd < row[0])
                        resultados[appid] = bool(es_oferta_real)
                    else:
                        resultados[appid] = False
        except Exception:
            pass
        return resultados

    def get_historical_mins_batch(self, lista_appids):
        """Retorna un dict {appid: min_price_usd} para una lista de AppIDs."""
        if not lista_appids:
            return {}
        res = {}
        try:
            with self.session() as conn:
                placeholders = ",".join("?" for _ in lista_appids)
                rows = conn.cursor().execute(
                    f"SELECT appid, min_price_usd FROM price_history WHERE appid IN ({placeholders})",
                    [str(a) for a in lista_appids]
                ).fetchall()
                for r in rows:
                    res[str(r[0])] = float(r[1])
        except Exception:
            pass
        return res

    def registrar_punto_historico_externo(self, appid, price_usd, fecha_iso):
        """
        Inyecta un punto histórico verificado (ej. récord histórico real de CheapShark o precio base)
        en price_log y actualiza price_history si ese récord fue menor al guardado localmente.
        """
        if not appid or not price_usd or float(price_usd) <= 0 or not fecha_iso:
            return
        appid_str = str(appid)
        p_val = float(price_usd)
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                ex = cursor.execute(
                    "SELECT id, price_usd FROM price_log WHERE appid = ? AND date_recorded = ?",
                    (appid_str, fecha_iso)
                ).fetchone()
                if not ex:
                    cursor.execute(
                        "INSERT INTO price_log (appid, price_usd, date_recorded) VALUES (?, ?, ?)",
                        (appid_str, p_val, fecha_iso)
                    )
                elif p_val < ex[1]:
                    cursor.execute(
                        "UPDATE price_log SET price_usd = ? WHERE id = ?",
                        (p_val, ex[0])
                    )

                row = cursor.execute(
                    "SELECT min_price_usd FROM price_history WHERE appid = ?", (appid_str,)
                ).fetchone()
                if not row:
                    cursor.execute(
                        "INSERT INTO price_history (appid, min_price_usd, date_recorded) VALUES (?, ?, ?)",
                        (appid_str, p_val, fecha_iso)
                    )
                elif p_val < row[0]:
                    cursor.execute(
                        "UPDATE price_history SET min_price_usd = ?, date_recorded = ? WHERE appid = ?",
                        (p_val, fecha_iso, appid_str)
                    )
        except Exception:
            pass

    def get_price_log(self, appid):
        try:
            with self.session() as conn:
                return conn.cursor().execute(
                    "SELECT appid, price_usd, date_recorded FROM price_log WHERE appid = ? ORDER BY date_recorded ASC, id ASC",
                    (str(appid),)
                ).fetchall()
        except Exception:
            return []

    # ================= WATCHLIST =================
    def set_watchlist_tag(self, appid, tag_text):
        try:
            with self.session() as conn:
                conn.cursor().execute("UPDATE watchlist SET custom_tag = ? WHERE appid = ?", (tag_text, str(appid)))
        except Exception:
            pass

    def set_watchlist_target_price(self, appid, target_price):
        """Permite configurar el Precio Objetivo (USD) para alertas personalizadas."""
        try:
            with self.session() as conn:
                conn.cursor().execute(
                    "UPDATE watchlist SET target_price = ? WHERE appid = ?",
                    (max(0.0, float(target_price)), str(appid))
                )
        except Exception:
            pass

    def add_watchlist(self, appid, titulo, precio, link):
        appid = str(appid)
        try:
            with self.session() as conn:
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                conn.cursor().execute("""
                    INSERT OR REPLACE INTO watchlist (appid, titulo, precio_guardado, fecha_guardado, link, custom_tag, target_price)
                    VALUES (
                        ?, ?, ?, ?, ?,
                        (SELECT custom_tag FROM watchlist WHERE appid=?),
                        COALESCE((SELECT target_price FROM watchlist WHERE appid=?), 0.0)
                    )
                """, (appid, titulo, precio, fecha, link, appid, appid))
            if self._watchlist_ids_cache is not None:
                self._watchlist_ids_cache.add(appid)
        except Exception:
            pass

    def add_watchlist_batch(self, lista_tuplas):
        """Optimización masiva para guardar cientos de juegos en una única transacción."""
        if not lista_tuplas:
            return
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                for appid, titulo, precio, link, fecha in lista_tuplas:
                    aid_str = str(appid)
                    cursor.execute("""
                        INSERT OR REPLACE INTO watchlist (appid, titulo, precio_guardado, fecha_guardado, link, custom_tag, target_price)
                        VALUES (
                            ?, ?, ?, ?, ?,
                            (SELECT custom_tag FROM watchlist WHERE appid=?),
                            COALESCE((SELECT target_price FROM watchlist WHERE appid=?), 0.0)
                        )
                    """, (aid_str, titulo, precio, fecha, link, aid_str, aid_str))
            self._watchlist_ids_cache = None
        except Exception:
            pass

    def update_watchlist_title(self, appid, nuevo_titulo):
        """Actualiza el título de un juego guardado en la watchlist."""
        if not appid or not nuevo_titulo:
            return
        try:
            with self.session() as conn:
                conn.cursor().execute("UPDATE watchlist SET titulo = ? WHERE appid = ?", (str(nuevo_titulo), str(appid)))
        except Exception:
            pass

    def update_watchlist_titles_batch(self, mapa_titulos):
        """Actualiza en lote los títulos de múltiples juegos en la watchlist en una única transacción."""
        if not mapa_titulos:
            return
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                for aid, tit in mapa_titulos.items():
                    if tit:
                        cursor.execute("UPDATE watchlist SET titulo = ? WHERE appid = ?", (str(tit), str(aid)))
        except Exception:
            pass

    def remove_watchlist(self, appid):
        appid = str(appid)
        try:
            with self.session() as conn:
                conn.cursor().execute("DELETE FROM watchlist WHERE appid = ?", (appid,))
            if self._watchlist_ids_cache is not None:
                self._watchlist_ids_cache.discard(appid)
        except Exception:
            pass

    def get_all_watchlist(self):
        try:
            with self.session() as conn:
                rows = conn.cursor().execute(
                    "SELECT appid, titulo, precio_guardado, fecha_guardado, link, custom_tag, COALESCE(target_price, 0.0) "
                    "FROM watchlist ORDER BY fecha_guardado DESC"
                ).fetchall()
                self._watchlist_ids_cache = {str(r[0]) for r in rows}
                return rows
        except Exception:
            return []

    def get_watchlist_ids_set(self):
        """Retorna el set de IDs en Watchlist desde RAM (0 consultas a disco al paginar tarjetas)."""
        if self._watchlist_ids_cache is None:
            try:
                with self.session() as conn:
                    rows = conn.cursor().execute("SELECT appid FROM watchlist").fetchall()
                    self._watchlist_ids_cache = {str(r[0]) for r in rows}
            except Exception:
                return set()
        return set(self._watchlist_ids_cache)

    # ================= METADATOS DE JUEGOS =================
    def get_game_meta(self, appid):
        try:
            with self.session() as conn:
                row = conn.cursor().execute(
                    "SELECT modalidad, genero, is_sp, is_mp, genres_list FROM game_metadata WHERE appid = ?",
                    (str(appid),)
                ).fetchone()
                if row and row[4] and row[4] not in ("General", "Varios", ""):
                    return row
        except Exception:
            pass
        return None

    def save_game_meta(self, appid, mod, gen, is_sp, is_mp, glist):
        try:
            with self.session() as conn:
                conn.cursor().execute(
                    "INSERT OR REPLACE INTO game_metadata (appid, modalidad, genero, is_sp, is_mp, genres_list) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(appid), mod, gen, is_sp, is_mp, glist)
                )
        except Exception:
            pass

    # ================= CACHÉ DE BIBLIOTECA PERSONAL =================
    def save_library_batch(self, lista_juegos):
        """Guarda o actualiza la biblioteca del usuario en SQLite preservando precios ya valuados."""
        if not lista_juegos:
            return
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                for j in lista_juegos:
                    aid = str(j.get("appid", ""))
                    if not aid:
                        continue
                    p_in = j.get("price_usd", -1.0)
                    cursor.execute("""
                        INSERT OR REPLACE INTO user_library (appid, titulo, horas, minutos, thumb_url, price_usd)
                        VALUES (
                            ?, ?, ?, ?, ?,
                            CASE WHEN ? >= 0 THEN ? ELSE COALESCE((SELECT price_usd FROM user_library WHERE appid=?), -1.0) END
                        )
                    """, (
                        aid,
                        j.get("titulo") or f"App {aid}",
                        float(j.get("horas", 0.0)),
                        int(j.get("minutos", 0)),
                        j.get("thumb_url") or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_sm_120.jpg",
                        float(p_in),
                        float(p_in),
                        aid,
                    ))
        except Exception:
            pass

    def update_library_prices_batch(self, mapa_precios):
        """Actualiza el precio actual/normal en USD de los juegos de la biblioteca en una sola transacción."""
        if not mapa_precios:
            return
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                for aid, price_val in mapa_precios.items():
                    cursor.execute(
                        "UPDATE user_library SET price_usd = ? WHERE appid = ?",
                        (float(price_val), str(aid))
                    )
        except Exception:
            pass

    def get_library_cached(self):
        """Recupera la biblioteca guardada localmente en 0ms."""
        try:
            with self.session() as conn:
                rows = conn.cursor().execute(
                    "SELECT appid, titulo, horas, minutos, thumb_url, COALESCE(price_usd, -1.0) "
                    "FROM user_library ORDER BY horas DESC, titulo ASC"
                ).fetchall()
                return [
                    {
                        "appid": str(r[0]),
                        "titulo": r[1],
                        "horas": float(r[2] or 0.0),
                        "minutos": int(r[3] or 0),
                        "thumb_url": r[4],
                        "price_usd": float(r[5] if r[5] is not None else -1.0),
                    }
                    for r in rows
                ]
        except Exception:
            return []

    # ================= HISTORIAL DE ALERTAS ATL =================
    def registrar_alerta_atl(self, appid, titulo, precio_usd, desc_pct):
        """Registra un nuevo récord histórico detectado por el centinela."""
        try:
            with self.session() as conn:
                conn.cursor().execute(
                    "INSERT INTO atl_alerts_history (appid, titulo, precio_usd, desc_pct, fecha) VALUES (?, ?, ?, ?, ?)",
                    (str(appid), str(titulo), float(precio_usd), int(desc_pct), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
        except Exception:
            pass

    def obtener_alertas_atl(self, limite=50):
        """Devuelve los últimos récords históricos capturados."""
        try:
            with self.session() as conn:
                rows = conn.cursor().execute(
                    "SELECT appid, titulo, precio_usd, desc_pct, fecha FROM atl_alerts_history ORDER BY id DESC LIMIT ?",
                    (limite,)
                ).fetchall()
                return [
                    {"appid": str(r[0]), "titulo": r[1], "precio_usd": float(r[2]), "desc_pct": int(r[3]), "fecha": r[4]}
                    for r in rows
                ]
        except Exception:
            return []

    def limpiar_alertas_atl(self):
        """Vacía el historial de alertas ATL registradas."""
        try:
            with self.session() as conn:
                conn.cursor().execute("DELETE FROM atl_alerts_history")
        except Exception:
            pass

    def contar_alertas_atl(self):
        """Devuelve la cantidad total de alertas de récords históricos capturadas."""
        try:
            with self.session() as conn:
                row = conn.cursor().execute("SELECT COUNT(*) FROM atl_alerts_history").fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    # ================= NOTAS PERSONALES =================
    def get_game_note(self, appid):
        """Recupera la nota personal de un juego (o cadena vacía si no existe)."""
        if not appid:
            return ""
        try:
            with self.session() as conn:
                row = conn.cursor().execute(
                    "SELECT note FROM game_notes WHERE appid = ?", (str(appid),)
                ).fetchone()
                return str(row[0]) if row and row[0] else ""
        except Exception:
            return ""

    def save_game_note(self, appid, note_text):
        """Guarda o actualiza la nota personal de cualquier juego."""
        if not appid:
            return
        appid_str = str(appid)
        note_clean = (note_text or "").strip()
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                if note_clean:
                    cursor.execute(
                        "INSERT OR REPLACE INTO game_notes (appid, note, updated_at) VALUES (?, ?, ?)",
                        (appid_str, note_clean, ahora)
                    )
                else:
                    cursor.execute("DELETE FROM game_notes WHERE appid = ?", (appid_str,))
                # Sincronizar también con watchlist si está guardado allí
                try:
                    cursor.execute("UPDATE watchlist SET personal_note = ? WHERE appid = ?", (note_clean, appid_str))
                except Exception:
                    pass
        except Exception:
            pass

    def get_all_game_notes(self):
        """Retorna un dict {appid: note} con todas las notas personales registradas."""
        try:
            with self.session() as conn:
                rows = conn.cursor().execute("SELECT appid, note FROM game_notes").fetchall()
                return {str(r[0]): str(r[1]) for r in rows if r[1]}
        except Exception:
            return {}

    # ================= MANTENIMIENTO & MÉTRICAS =================
    def optimizar_base_datos(self):
        """Ejecuta VACUUM y optimización sobre SQLite para compactar el archivo y reconstruir índices."""
        try:
            conn = self.get_connection()
            try:
                conn.execute("VACUUM;")
                conn.execute("PRAGMA optimize;")
                return True
            finally:
                conn.close()
        except Exception:
            return False

    def obtener_metricas_backlog(self):
        """Calcula métricas detalladas de la biblioteca y backlog en 0ms."""
        try:
            with self.session() as conn:
                cursor = conn.cursor()
                total = cursor.execute("SELECT COUNT(*) FROM user_library").fetchone()[0] or 0
                if total == 0:
                    return {
                        "total": 0, "sin_jugar": 0, "apenas_probados": 0, "viciados": 0,
                        "horas_totales": 0.0, "dinero_sin_estrenar_usd": 0.0, "pct_sin_jugar": 0.0
                    }
                sin_jugar = cursor.execute("SELECT COUNT(*) FROM user_library WHERE horas < 0.1").fetchone()[0] or 0
                apenas_probados = cursor.execute("SELECT COUNT(*) FROM user_library WHERE horas >= 0.1 AND horas < 2.0").fetchone()[0] or 0
                viciados = cursor.execute("SELECT COUNT(*) FROM user_library WHERE horas >= 20.0").fetchone()[0] or 0
                horas_totales = cursor.execute("SELECT COALESCE(SUM(horas), 0.0) FROM user_library").fetchone()[0] or 0.0
                dinero_sin_estrenar = cursor.execute(
                    "SELECT COALESCE(SUM(CASE WHEN price_usd > 0 THEN price_usd ELSE 0 END), 0.0) FROM user_library WHERE horas < 0.1"
                ).fetchone()[0] or 0.0
                pct_sin_jugar = round((sin_jugar / total) * 100.0, 1) if total > 0 else 0.0
                return {
                    "total": total,
                    "sin_jugar": sin_jugar,
                    "apenas_probados": apenas_probados,
                    "viciados": viciados,
                    "horas_totales": round(horas_totales, 1),
                    "dinero_sin_estrenar_usd": round(dinero_sin_estrenar, 2),
                    "pct_sin_jugar": pct_sin_jugar
                }
        except Exception:
            return {
                "total": 0, "sin_jugar": 0, "apenas_probados": 0, "viciados": 0,
                "horas_totales": 0.0, "dinero_sin_estrenar_usd": 0.0, "pct_sin_jugar": 0.0
            }
