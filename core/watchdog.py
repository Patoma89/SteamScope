"""Centinela silencioso de Watchlist y récords ATL sin dependencias de interfaz gráfica."""
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from core.notifications import notificar_oferta_enriquecida


class WatchlistWatchdog:
    """Monitorea periódicamente la Watchlist en busca de récords ATL, metas y descuentos."""

    def __init__(
        self,
        db: Any,
        config: Any,
        api_client: Any,
        sfx: Any = None,
        on_alerts_updated: Optional[Callable[[], None]] = None,
        check_tick_seconds: float = 30.0,
    ) -> None:
        self.db = db
        self.config = config
        self.api_client = api_client
        self.sfx = sfx
        self._on_alerts_updated = on_alerts_updated
        self._check_tick_seconds = float(check_tick_seconds)
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._last_check_ts = time.time()

    def run_once(self) -> Dict[str, Any]:
        """Ejecuta una comprobación completa de la Watchlist y registra alertas ATL."""
        with self._run_lock:
            rows = self.db.get_all_watchlist() or []
            if not rows:
                return {"checked": 0, "atl_hits": [], "target_hits": [], "discount_hits": []}

            appids = [str(r[0]) for r in rows]
            precios_lote = self.api_client.obtener_precios_argentina_lote(appids) or {}
            pares_hist = {
                aid: (d["oferta"], d.get("descuento", 0), d.get("normal", d["oferta"]))
                for aid, d in precios_lote.items()
                if float(d.get("oferta", 0.0) or 0.0) > 0.0
            }
            res_atl = self.db.update_historical_min_batch(pares_hist) if pares_hist else {}

            umbral = int(self.config.datos.get("umbral_alerta_pct", 50) or 50)
            dolar = float(self.config.datos.get("dolar_referencia", 1000.0) or 1000.0)
            imp_raw = self.config.datos.get("impuestos_pct", 51)
            imp = float(imp_raw if imp_raw is not None else 51)

            atl_hits: List[Dict[str, Any]] = []
            target_hits: List[Dict[str, Any]] = []
            discount_hits: List[Dict[str, Any]] = []

            for appid, titulo, _precio_guardado, _fecha, _link, _tag, target_p in rows:
                aid = str(appid)
                p_data = precios_lote.get(aid)
                if not p_data:
                    continue

                p_fin = float(p_data.get("oferta", 0.0) or 0.0)
                desc_pct = int(p_data.get("descuento", 0) or 0)
                target_val = float(target_p or 0.0)
                es_atl = bool(res_atl.get(aid, False)) and p_fin > 0

                entry = {
                    "appid": aid,
                    "titulo": str(titulo or f"App {aid}"),
                    "precio_usd": p_fin,
                    "descuento": desc_pct,
                }

                if es_atl:
                    self.db.registrar_alerta_atl(aid, entry["titulo"], p_fin, desc_pct)
                    atl_hits.append(entry)

                if target_val > 0 and 0 < p_fin <= target_val:
                    target_hits.append({**entry, "target_price": target_val})

                if desc_pct >= umbral:
                    discount_hits.append(entry)

            if atl_hits or target_hits or discount_hits:
                dest = (atl_hits or target_hits or discount_hits)[0]
                p_ars = round(dest["precio_usd"] * dolar * (1.0 + imp / 100.0))
                try:
                    notificar_oferta_enriquecida(
                        titulo=dest["titulo"],
                        precio_usd=dest["precio_usd"],
                        descuento=dest["descuento"],
                        precio_ars=p_ars,
                        banner_url=f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{dest['appid']}/header.jpg",
                        appid=dest["appid"],
                        es_gratis=(dest["precio_usd"] == 0),
                    )
                except Exception:
                    pass

                if self.sfx is not None and self.config.datos.get("alerta_sonido_atl", True):
                    try:
                        self.sfx.play("atl")
                    except Exception:
                        pass

                if self._on_alerts_updated is not None:
                    try:
                        self._on_alerts_updated()
                    except Exception:
                        pass

            return {
                "checked": len(rows),
                "atl_hits": atl_hits,
                "target_hits": target_hits,
                "discount_hits": discount_hits,
            }

    def _safe_run_once(self) -> None:
        try:
            self.run_once()
        except Exception:
            pass

    def trigger_now(self) -> None:
        """Dispara de inmediato una comprobación en un hilo demonio."""
        self._last_check_ts = time.time()
        threading.Thread(target=self._safe_run_once, daemon=True).start()

    def start(self) -> None:
        """Inicia el bucle periódico de vigilancia en segundo plano."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._last_check_ts = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop_event.wait(self._check_tick_seconds):
            try:
                if not self.config.datos.get("watchdog_activado", True):
                    continue
                intervalo_hs = float(self.config.datos.get("watchdog_intervalo_hs", 6) or 6)
                segundos_intervalo = max(1800, int(intervalo_hs * 3600))
                ahora = time.time()
                if ahora - self._last_check_ts >= segundos_intervalo:
                    self._last_check_ts = ahora
                    self._safe_run_once()
            except Exception:
                pass

    def stop(self) -> None:
        """Detiene el bucle del centinela."""
        self._stop_event.set()
