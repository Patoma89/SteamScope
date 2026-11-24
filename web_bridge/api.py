"""
Puente Backend JSON puro para SteamScope 3.0 NEXT (Edge WebView2 + pywebview).
Consume exclusivamente la capa core/ sin importar Tkinter, CustomTkinter ni pywebview.
"""
import webbrowser
from typing import Any, Callable, Dict, List, Optional

from core.api_client import HTTP_SESSION, SteamAPIClient
from core.config import (
    APP_NAME,
    APP_VERSION,
    FALLBACK_RELEASES_WEB,
    PATCH_NOTES,
    SKIN_PALETTES,
    UPDATE_JSON_URL,
    ConfigManager,
    SoundManager,
)
from core.database import DatabaseManager
from core.filters import normalizar_texto
from core.pricing import _parse_version_tuple
from web_bridge.api_account import WebAPIAccountMixin
from web_bridge.api_deals import WebAPIDealsMixin
from web_bridge.api_ficha import WebAPIFichaMixin
from web_bridge.api_tools import WebAPIToolsMixin

VALID_CURRENCIES = ("USD", "ARS (Tarjeta)", "ARS (Cripto)")

_QUICK_NAVIGATION_ITEMS = [
    {"id": "command_center", "title": "Centro de Mando", "subtitle": "Vista general, métricas y accesos rápidos", "tab": "command_center"},
    {"id": "deals", "title": "Ofertas y Búsqueda", "subtitle": "Explorar descuentos de Steam con precios ARS/USD", "tab": "deals"},
    {"id": "radar", "title": "Radar Epic & GOG", "subtitle": "Juegos 100% gratis semanales y promociones", "tab": "radar"},
    {"id": "atl", "title": "Récords ATL", "subtitle": "Historial de mínimos históricos detectados", "tab": "atl"},
    {"id": "watchlist", "title": "Mi Watchlist", "subtitle": "Seguimiento de precios objetivo y rebajas", "tab": "watchlist"},
    {"id": "library", "title": "Mi Biblioteca & Co-op", "subtitle": "Caché SQLite, valuador de cuenta y cruce Co-op", "tab": "library"},
    {"id": "cards", "title": "Gestor de Cromos", "subtitle": "Valorización de inventario y saldo financiable", "tab": "cards"},
    {"id": "dashboard", "title": "Dashboard Visual", "subtitle": "Gráficos de descuentos, géneros y backlog", "tab": "dashboard"},
    {"id": "versus", "title": "Comparador Versus", "subtitle": "Comparativa cara a cara entre dos juegos", "tab": "versus"},
    {"id": "roulette", "title": "Ruleta Loot Box", "subtitle": "Sorteo sorpresa de ofertas o backlog", "tab": "roulette"},
    {"id": "events", "title": "Eventos & Calc", "subtitle": "Calendario oficial de Steam Sales y calculadora ARS", "tab": "events"},
    {"id": "settings", "title": "Ajustes", "subtitle": "Steam ID, API Key, Dólar, Webhook y Backup", "tab": "settings"},
]


def _normalize_moneda(moneda_raw: Any) -> str:
    txt = str(moneda_raw or "USD")
    if "Cripto" in txt or "🪙" in txt:
        return "ARS (Cripto)"
    if "ARS" in txt or "Tarjeta" in txt or "💳" in txt:
        return "ARS (Tarjeta)"
    return "USD"


class SteamScopeWebAPI(WebAPIDealsMixin, WebAPIFichaMixin, WebAPIAccountMixin, WebAPIToolsMixin):
    """API JSON-serializable entre `core/` y la interfaz GPU `web_ui/`."""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        config: Optional[ConfigManager] = None,
        sfx: Optional[SoundManager] = None,
        api_client: Optional[SteamAPIClient] = None,
        on_toggle_topmost: Optional[Callable[[bool], None]] = None,
        on_open_url: Optional[Callable[[str], Any]] = None,
        on_save_dialog: Optional[Callable[[str, str], Optional[str]]] = None,
    ) -> None:
        self.db = db if db is not None else DatabaseManager()
        self.config = config if config is not None else ConfigManager()
        self.sfx = sfx if sfx is not None else SoundManager(self.config)
        self.api_client = api_client if api_client is not None else SteamAPIClient()
        self._on_toggle_topmost = on_toggle_topmost
        self._on_open_url = on_open_url
        self._on_save_dialog = on_save_dialog
        self._always_on_top = False
        self._deals_data: List[Dict[str, Any]] = []
        self._watchlist_live_status: Dict[str, Dict[str, Any]] = {}
        self._friend_appids: set = set()
        self._friend_id: str = ""

    def _get_fx_values(self) -> Dict[str, Any]:
        d = self.config.datos
        dolar_base = float(d.get("dolar_referencia", 1000.0) or 1000.0)
        dolar_cripto = float(d.get("dolar_cripto_ref", round(dolar_base * 1.15)) or round(dolar_base * 1.15))
        impuestos_pct = float(d.get("impuestos_pct", 60) if d.get("impuestos_pct") is not None else 60)
        moneda = _normalize_moneda(d.get("moneda", "USD"))
        return {
            "dolar_referencia": dolar_base,
            "dolar_cripto_ref": dolar_cripto,
            "impuestos_pct": impuestos_pct,
            "moneda": moneda,
        }

    def get_bootstrap(self) -> Dict[str, Any]:
        """Retorna la configuración inicial completa, skins y métricas del Centro de Mando."""
        d = self.config.datos
        skin_id = str(d.get("tema", "Oscuro"))
        if skin_id not in SKIN_PALETTES:
            skin_id = "Oscuro"

        fx = self._get_fx_values()
        skins_meta = [
            {
                "id": sid,
                "label": sid,
                "mode": pal.get("mode", "Dark"),
                "accent": pal.get("accent", "#38bdf8"),
                "accent_2": pal.get("accent_2", "#1f538d"),
                "bg": pal.get("win_bg", "#242424"),
            }
            for sid, pal in SKIN_PALETTES.items()
        ]

        return {
            "app_name": APP_NAME,
            "app_title": "SteamScope 3.0 NEXT",
            "version": APP_VERSION,
            "skin_id": skin_id,
            "skins": SKIN_PALETTES,
            "skins_meta": skins_meta,
            "moneda": fx["moneda"],
            "vista": str(d.get("vista_resultados", "Normal")),
            "sidebar_collapsed": bool(d.get("sidebar_collapsed", False)),
            "always_on_top": self._always_on_top,
            "dolar_referencia": fx["dolar_referencia"],
            "dolar_cripto_ref": fx["dolar_cripto_ref"],
            "impuestos_pct": fx["impuestos_pct"],
            "presupuesto_carrito_usd": float(d.get("presupuesto_carrito_usd", 0.0) or 0.0),
            "command_center": self.get_command_center_data(),
        }

    def get_command_center_data(self) -> Dict[str, Any]:
        """Construye el payload del Centro de Mando desde SQLite y configuración local."""
        fx = self._get_fx_values()
        dolar_base = fx["dolar_referencia"]
        dolar_cripto = fx["dolar_cripto_ref"]
        mult_tarjeta = 1.0 + (fx["impuestos_pct"] / 100.0)

        atl_count = int(self.db.contar_alertas_atl() or 0)
        raw_atl = self.db.obtener_alertas_atl(limite=8) or []
        recent_atl = [
            {
                "appid": str(a.get("appid", "")),
                "titulo": str(a.get("titulo", "")),
                "precio_usd": float(a.get("precio_usd", 0.0) or 0.0),
                "descuento": int(a.get("desc_pct", 0) or 0),
                "fecha": str(a.get("fecha", "")),
            }
            for a in raw_atl
        ]

        wl_rows = self.db.get_all_watchlist() or []
        target_cnt = sum(1 for r in wl_rows if float(r[6] or 0.0) > 0.0)
        watchlist_preview = [
            {
                "appid": str(r[0]),
                "titulo": str(r[1] or ""),
                "precio_usd": float(r[2] or 0.0),
                "fecha": str(r[3] or ""),
                "link": str(r[4] or f"https://store.steampowered.com/app/{r[0]}"),
                "tag": str(r[5] or ""),
                "target_price": float(r[6] or 0.0),
            }
            for r in wl_rows[:8]
        ]

        backlog_metrics = self.db.obtener_metricas_backlog() or {}
        library_rows = self.db.get_library_cached() or []
        library_sorted = sorted(library_rows, key=lambda x: float(x.get("horas", 0.0) or 0.0), reverse=True)
        top_games = [
            {
                "appid": str(g.get("appid", "")),
                "titulo": str(g.get("titulo", "")),
                "horas": round(float(g.get("horas", 0.0) or 0.0), 1),
                "price_usd": float(g.get("price_usd", -1.0) if g.get("price_usd") is not None else -1.0),
            }
            for g in library_sorted[:6]
        ]

        carrito = self.config.datos.get("carrito_guardado", {}) or {}
        items = list(carrito.values())
        tot_usd = sum(float(i.get("precio_oferta_usd", 0.0) or 0.0) for i in items)
        tot_reg = sum(float(i.get("precio_normal_usd", i.get("precio_oferta_usd", 0.0)) or 0.0) for i in items)
        ahorro_usd = max(0.0, tot_reg - tot_usd)
        budget_usd = float(self.config.datos.get("presupuesto_carrito_usd", 0.0) or 0.0)
        budget_pct = round((tot_usd / budget_usd) * 100.0, 1) if budget_usd > 0 else 0.0

        return {
            "atl": {
                "count": atl_count,
                "recent": recent_atl,
            },
            "watchlist": {
                "total": len(wl_rows),
                "with_target": target_cnt,
                "items": watchlist_preview,
            },
            "backlog": {
                "total": int(backlog_metrics.get("total", 0) or 0),
                "sin_jugar": int(backlog_metrics.get("sin_jugar", 0) or 0),
                "apenas_probados": int(backlog_metrics.get("apenas_probados", 0) or 0),
                "viciados": int(backlog_metrics.get("viciados", 0) or 0),
                "horas_totales": float(backlog_metrics.get("horas_totales", 0.0) or 0.0),
                "dinero_sin_estrenar_usd": float(backlog_metrics.get("dinero_sin_estrenar_usd", 0.0) or 0.0),
                "pct_sin_jugar": float(backlog_metrics.get("pct_sin_jugar", 0.0) or 0.0),
                "top_games": top_games,
            },
            "cart": {
                "count": len(items),
                "total_usd": round(tot_usd, 2),
                "total_ars_tarjeta": round(tot_usd * dolar_base * mult_tarjeta),
                "total_ars_cripto": round(tot_usd * dolar_cripto),
                "ahorro_usd": round(ahorro_usd, 2),
                "budget_usd": round(budget_usd, 2),
                "budget_pct": budget_pct,
            },
            "fx": fx,
        }

    def set_skin(self, skin_name: str) -> Dict[str, Any]:
        """Aplica y persiste una skin oficial o personalizada."""
        if skin_name not in SKIN_PALETTES:
            return {"ok": False, "error": f"Skin desconocida: {skin_name}"}
        self.config.guardar_basico("tema", skin_name)
        self.sfx.play("click")
        return {"ok": True, "skin_id": skin_name, "palette": SKIN_PALETTES[skin_name]}

    def set_moneda(self, moneda: str) -> Dict[str, Any]:
        """Cambia la moneda activa (USD / ARS Tarjeta / ARS Cripto) y recalcula métricas."""
        if moneda not in VALID_CURRENCIES:
            return {"ok": False, "error": f"Moneda inválida: {moneda}"}
        self.config.guardar_basico("moneda", moneda)
        self.sfx.play("click")
        return {"ok": True, "moneda": moneda, "command_center": self.get_command_center_data()}

    def set_sidebar_collapsed(self, collapsed: bool) -> Dict[str, Any]:
        """Guarda el estado colapsado de la barra lateral."""
        val = bool(collapsed)
        self.config.guardar_basico("sidebar_collapsed", val)
        return {"ok": True, "sidebar_collapsed": val}

    def toggle_always_on_top(self) -> Dict[str, Any]:
        """Alterna la fijación de la ventana sobre otras aplicaciones."""
        self._always_on_top = not self._always_on_top
        if self._on_toggle_topmost is not None:
            self._on_toggle_topmost(self._always_on_top)
        self.sfx.play("click")
        return {"ok": True, "always_on_top": self._always_on_top}

    def global_search(self, query: str) -> Dict[str, Any]:
        """Búsqueda offline instantánea (<5ms) para Spotlight Ctrl+K."""
        q_norm = normalizar_texto(query)
        if len(q_norm) < 2:
            return {"ok": True, "results": []}

        results: List[Dict[str, Any]] = []
        seen_keys = set()

        # 1. Secciones / Acciones rápidas
        for nav in _QUICK_NAVIGATION_ITEMS:
            haystack = normalizar_texto(f"{nav['title']} {nav['subtitle']}")
            if q_norm in haystack:
                results.append({
                    "kind": "Sección",
                    "id": nav["id"],
                    "title": nav["title"],
                    "subtitle": nav["subtitle"],
                    "tab": nav["tab"],
                    "badge": "IR",
                })

        # 2. Watchlist local
        for row in self.db.get_all_watchlist() or []:
            aid = str(row[0])
            titulo = str(row[1] or "")
            tag = str(row[5] or "")
            if q_norm in normalizar_texto(f"{titulo} {tag} {aid}"):
                key = ("wl", aid)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                precio = float(row[2] or 0.0)
                results.append({
                    "kind": "Watchlist",
                    "id": aid,
                    "title": titulo,
                    "subtitle": f"${precio:.2f} USD" + (f" · #{tag}" if tag else ""),
                    "tab": "watchlist",
                    "url": str(row[4] or f"https://store.steampowered.com/app/{aid}"),
                    "badge": f"#{aid}",
                })

        # 3. Biblioteca cacheada en SQLite
        for game in self.db.get_library_cached() or []:
            aid = str(game.get("appid", ""))
            titulo = str(game.get("titulo", ""))
            if q_norm in normalizar_texto(f"{titulo} {aid}"):
                key = ("lib", aid)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                horas = float(game.get("horas", 0.0) or 0.0)
                results.append({
                    "kind": "Biblioteca",
                    "id": aid,
                    "title": titulo,
                    "subtitle": f"{horas:.1f} hs jugadas",
                    "tab": "library",
                    "url": f"https://store.steampowered.com/app/{aid}",
                    "badge": f"{horas:.0f}h",
                })

        # 4. Historial de Récords ATL
        for alert in self.db.obtener_alertas_atl(limite=50) or []:
            aid = str(alert.get("appid", ""))
            titulo = str(alert.get("titulo", ""))
            if q_norm in normalizar_texto(f"{titulo} {aid}"):
                key = ("atl", aid)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                precio = float(alert.get("precio_usd", 0.0) or 0.0)
                desc = int(alert.get("desc_pct", 0) or 0)
                results.append({
                    "kind": "Récord ATL",
                    "id": aid,
                    "title": titulo,
                    "subtitle": f"Mínimo histórico: ${precio:.2f} USD (-{desc}%)",
                    "tab": "atl",
                    "url": f"https://store.steampowered.com/app/{aid}",
                    "badge": f"-{desc}%",
                })

        return {"ok": True, "results": results[:25]}

    def get_patch_notes(self) -> List[Dict[str, Any]]:
        """Devuelve el historial de versiones de SteamScope."""
        return PATCH_NOTES

    def check_updates(self) -> Dict[str, Any]:
        """Consulta GitHub version.json comparando con APP_VERSION sin lanzar excepciones."""
        update_url = str(self.config.datos.get("update_url") or UPDATE_JSON_URL)
        try:
            resp = HTTP_SESSION.get(update_url, timeout=5)
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "has_update": False,
                    "current_version": APP_VERSION,
                    "error": f"HTTP {resp.status_code}",
                    "fallback_url": FALLBACK_RELEASES_WEB,
                }
            data = resp.json() or {}
            latest_raw = str(data.get("version") or APP_VERSION)
            latest_clean = latest_raw.lstrip("vV")
            has_update = _parse_version_tuple(latest_clean) > _parse_version_tuple(APP_VERSION)
            return {
                "ok": True,
                "has_update": has_update,
                "current_version": APP_VERSION,
                "latest_version": latest_clean,
                "url": str(data.get("url") or FALLBACK_RELEASES_WEB),
                "notas": list(data.get("notas") or []),
                "fallback_url": FALLBACK_RELEASES_WEB,
            }
        except Exception as exc:
            return {
                "ok": False,
                "has_update": False,
                "current_version": APP_VERSION,
                "error": str(exc),
                "fallback_url": FALLBACK_RELEASES_WEB,
            }

    def open_external_url(self, url: str) -> Dict[str, Any]:
        """Abre un enlace externo validando esquema seguro."""
        cleaned = (url or "").strip()
        if not cleaned.startswith(("https://", "http://", "steam://")):
            return {"ok": False, "error": "Esquema de URL no permitido."}
        try:
            if self._on_open_url is not None:
                self._on_open_url(cleaned)
            else:
                webbrowser.open(cleaned)
            return {"ok": True, "url": cleaned}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
