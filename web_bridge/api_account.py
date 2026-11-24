"""
Mixin de Watchlist, Récords ATL, Biblioteca & Co-op y Gestor de Cromos para SteamScopeWebAPI.
Python puro consumiendo exclusivamente core/ (sin Tkinter/CustomTkinter/pywebview).
"""
import math
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.api_client import HTTP_SESSION, resolver_steam_id
from core.cards_manager import (
    COMMUNITY_BADGES_URL,
    COMMUNITY_MARKET_URL,
    analizar_inventario_cromos,
)
from core.filters import normalizar_texto


class WebAPIAccountMixin:
    """Extensión de Watchlist, ATL, Biblioteca Co-op y Cromos para SteamScopeWebAPI."""

    # ================= WATCHLIST =================
    def get_watchlist(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Devuelve la Watchlist local enriquecida con notas, etiquetas, metas y estado de rebajas."""
        p = dict(params or {})
        search = normalizar_texto(str(p.get("search", "") or ""))
        tag_filter = str(p.get("tag", "") or "")

        rows = self.db.get_all_watchlist() or []
        notes_map = self.db.get_all_game_notes() or {}
        live_map = getattr(self, "_watchlist_live_status", {})
        cart_ids = set((self.config.datos.get("carrito_guardado", {}) or {}).keys())

        tags_set = set()
        items_out: List[Dict[str, Any]] = []

        for row in rows:
            aid = str(row[0])
            titulo = str(row[1] or f"App {aid}")
            precio_guardado = float(row[2] or 0.0)
            fecha = str(row[3] or "")
            link = str(row[4] or f"https://store.steampowered.com/app/{aid}")
            tag = str(row[5] or "").strip()
            target_price = float(row[6] or 0.0)
            if tag:
                tags_set.add(tag)

            if tag_filter and tag_filter != "Todas las etiquetas" and tag != tag_filter:
                continue
            if search and search not in normalizar_texto(f"{titulo} {tag} {aid}"):
                continue

            live = live_map.get(aid, {})
            precio_actual = float(live.get("precio_usd", precio_guardado) or 0.0)
            normal_usd = float(live.get("normal_usd", precio_actual) or precio_actual)
            descuento = int(live.get("descuento", 0) or 0)
            es_atl = bool(live.get("es_atl", False))
            cumple_target = bool(target_price > 0 and 0 < precio_actual <= target_price)

            items_out.append({
                "appid": aid,
                "titulo": titulo,
                "precio_oferta_usd": round(precio_actual, 2),
                "precio_normal_usd": round(normal_usd, 2),
                "descuento": descuento,
                "es_atl": es_atl,
                "cumple_target": cumple_target,
                "bajo_precio": bool(live.get("bajo_precio", False) or descuento > 0 or cumple_target),
                "fecha": fecha,
                "link": link,
                "tag": tag,
                "target_price": round(target_price, 2),
                "note": notes_map.get(aid, ""),
                "in_cart": aid in cart_ids,
                "thumb_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_sm_120.jpg",
                "header_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg",
            })

        total_usd = round(sum(it["precio_oferta_usd"] for it in items_out), 2)
        return {
            "ok": True,
            "items": items_out,
            "tags": sorted(tags_set),
            "total": len(items_out),
            "total_usd": total_usd,
            "steam_id": str(self.config.datos.get("steam_id", "") or ""),
        }

    def set_watchlist_tag(self, appid: str, tag_text: str) -> Dict[str, Any]:
        """Asigna o limpia la etiqueta personalizada de un juego en Watchlist."""
        aid = str(appid or "").strip()
        if not aid:
            return {"ok": False, "error": "AppID inválido."}
        clean_tag = str(tag_text or "").strip()
        self.db.set_watchlist_tag(aid, clean_tag)
        self.sfx.play("click")
        return {"ok": True, "appid": aid, "tag": clean_tag}

    def set_watchlist_target_price(self, appid: str, target_price: float) -> Dict[str, Any]:
        """Fija o desactiva (0) el precio objetivo en USD para un juego de Watchlist."""
        aid = str(appid or "").strip()
        if not aid:
            return {"ok": False, "error": "AppID inválido."}
        try:
            val = max(0.0, min(9999.0, float(target_price)))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Precio objetivo inválido."}
        self.db.set_watchlist_target_price(aid, round(val, 2))
        self.sfx.play("coin")
        return {
            "ok": True,
            "appid": aid,
            "target_price": round(val, 2),
            "command_center": self.get_command_center_data(),
        }

    def sync_steam_wishlist(self, steam_id_input: Optional[str] = None) -> Dict[str, Any]:
        """Importa la Wishlist pública de Steam resolviendo nombres y precios en lote."""
        raw_id = str(steam_id_input if steam_id_input is not None else self.config.datos.get("steam_id", "")).strip()
        steam_id = resolver_steam_id(raw_id)
        if not steam_id:
            return {"ok": False, "error": "Steam ID inválido. Configuralo en Ajustes o ingresalo aquí."}

        appids_wishlist: List[str] = []
        nombres_wishlist: Dict[str, str] = {}

        # 1. Endpoint wishlistdata (trae nombres oficiales por página)
        for p in range(10):
            url_pag = (
                f"https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/?p={p}"
                if (steam_id.isdigit() and len(steam_id) == 17)
                else f"https://store.steampowered.com/wishlist/id/{steam_id}/wishlistdata/?p={p}"
            )
            try:
                r_p = HTTP_SESSION.get(url_pag, timeout=8)
                if r_p.status_code != 200:
                    break
                d_p = r_p.json()
                if not isinstance(d_p, dict) or not d_p:
                    break
                for aid, inf in d_p.items():
                    aid_str = str(aid)
                    if aid_str not in appids_wishlist:
                        appids_wishlist.append(aid_str)
                    if isinstance(inf, dict) and inf.get("name"):
                        nombres_wishlist[aid_str] = str(inf["name"]).strip()
                if len(d_p) < 35:
                    break
            except Exception:
                break

        # 2. Respaldo / complemento oficial IWishlistService
        try:
            url_api = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={steam_id}"
            r_api = HTTP_SESSION.get(url_api, timeout=8)
            if r_api.status_code == 200:
                for it in (r_api.json() or {}).get("response", {}).get("items", []):
                    aid_str = str(it.get("appid", ""))
                    if aid_str and aid_str not in appids_wishlist:
                        appids_wishlist.append(aid_str)
        except Exception:
            pass

        if not appids_wishlist:
            return {"ok": False, "error": "No se encontraron juegos en la Wishlist (verificá que el perfil sea público)."}

        ids_sin_nombre = [aid for aid in appids_wishlist if not nombres_wishlist.get(aid)][:40]
        if ids_sin_nombre:
            datos_res = self.api_client.obtener_datos_basicos_lote(ids_sin_nombre) or {}
            for aid, inf in datos_res.items():
                if isinstance(inf, dict) and inf.get("name"):
                    nombres_wishlist[str(aid)] = str(inf["name"])

        precios_ar = self.api_client.obtener_precios_argentina_lote(appids_wishlist) or {}
        tuplas_lote = []
        pares_hist = {}
        fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

        for aid in appids_wishlist:
            p_info = precios_ar.get(aid, {})
            precio = float(p_info.get("oferta", 0.0) or 0.0)
            norm = float(p_info.get("normal", precio) or precio)
            desc = int(p_info.get("descuento", 0) or 0)
            if precio > 0:
                pares_hist[aid] = (precio, desc, norm)
            nombre = nombres_wishlist.get(aid) or f"Juego Steam {aid}"
            tuplas_lote.append((aid, nombre, precio, f"https://store.steampowered.com/app/{aid}", fecha_hoy))

        if pares_hist:
            self.db.update_historical_min_batch(pares_hist)
        self.db.add_watchlist_batch(tuplas_lote)
        self.sfx.play("coin")

        return {
            "ok": True,
            "imported_count": len(tuplas_lote),
            "total": len(self.db.get_all_watchlist() or []),
            "command_center": self.get_command_center_data(),
        }

    def check_watchlist_drops(self) -> Dict[str, Any]:
        """Comprueba precios actuales en lote para toda la Watchlist y registra récords ATL."""
        rows = self.db.get_all_watchlist() or []
        if not rows:
            return {"ok": False, "error": "Tu Watchlist está vacía."}

        all_ids = [str(r[0]) for r in rows]
        precios_lote = self.api_client.obtener_precios_argentina_lote(all_ids) or {}
        pares_hist = {
            aid: (d["oferta"], d.get("descuento", 0), d.get("normal", d["oferta"]))
            for aid, d in precios_lote.items()
            if float(d.get("oferta", 0.0) or 0.0) > 0.0
        }
        res_atl = self.db.update_historical_min_batch(pares_hist) if pares_hist else {}

        if not hasattr(self, "_watchlist_live_status"):
            self._watchlist_live_status = {}

        drops = []
        target_hits = []
        atl_hits = []

        for appid, titulo, precio_guardado, _fecha, _link, _tag, target_p in rows:
            aid = str(appid)
            p_info = precios_lote.get(aid)
            p_actual = float(p_info["oferta"]) if p_info else float(precio_guardado or 0.0)
            p_norm = float(p_info.get("normal", p_actual)) if p_info else float(precio_guardado or 0.0)
            desc = int(p_info.get("descuento", 0)) if p_info else 0
            es_min = bool(res_atl.get(aid, False))

            if es_min and p_actual > 0:
                self.db.registrar_alerta_atl(aid, titulo, p_actual, desc)
                atl_hits.append({"appid": aid, "titulo": titulo, "precio_usd": p_actual, "descuento": desc})

            target_val = float(target_p or 0.0)
            cumple_target = bool(target_val > 0 and 0 < p_actual <= target_val)
            bajo_precio = bool((0 < p_actual < float(precio_guardado or 0.0)) or desc > 0 or cumple_target)

            if cumple_target:
                target_hits.append({"appid": aid, "titulo": titulo, "precio_usd": p_actual, "target_price": target_val})
            if bajo_precio:
                drops.append({"appid": aid, "titulo": titulo, "precio_usd": p_actual, "descuento": desc})

            self._watchlist_live_status[aid] = {
                "precio_usd": p_actual,
                "normal_usd": p_norm,
                "descuento": desc,
                "es_atl": es_min,
                "cumple_target": cumple_target,
                "bajo_precio": bajo_precio,
            }

        if drops or atl_hits:
            self.sfx.play("atl")
        else:
            self.sfx.play("click")

        return {
            "ok": True,
            "checked": len(rows),
            "drops": drops,
            "target_hits": target_hits,
            "atl_hits": atl_hits,
            "command_center": self.get_command_center_data(),
        }

    # ================= RÉCORDS ATL =================
    def get_atl_history(self, limite: int = 100) -> Dict[str, Any]:
        """Devuelve el historial de mínimos históricos capturados."""
        items = self.db.obtener_alertas_atl(limite=int(limite or 100)) or []
        return {"ok": True, "count": len(items), "items": items}

    def clear_atl_history(self) -> Dict[str, Any]:
        """Limpia por completo el historial de alertas ATL."""
        self.db.limpiar_alertas_atl()
        self.sfx.play("click")
        return {"ok": True, "command_center": self.get_command_center_data()}

    # ================= BIBLIOTECA & RADAR CO-OP =================
    def get_library(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Lee la biblioteca cacheada en SQLite en 0ms, filtra, ordena y pagina."""
        p = dict(params or {})
        search = normalizar_texto(str(p.get("search", "") or ""))
        filter_mode = str(p.get("filter_mode", "all") or "all")
        sort_by = str(p.get("sort_by", "horas_desc") or "horas_desc")
        per_page = max(1, min(100, int(p.get("per_page", 30) or 30)))

        raw_lib = self.db.get_library_cached() or []
        metrics = self.db.obtener_metricas_backlog() or {}
        friend_ids = getattr(self, "_friend_appids", set())
        friend_id = getattr(self, "_friend_id", "")

        # Valuación global sobre toda la biblioteca cacheada
        total_val = 0.0
        unplayed_val = 0.0
        priced_count = 0
        for g in raw_lib:
            pr = float(g.get("price_usd", -1.0) if g.get("price_usd") is not None else -1.0)
            if pr >= 0:
                priced_count += 1
                total_val += pr
                if float(g.get("horas", 0.0) or 0.0) < 0.1:
                    unplayed_val += pr

        horas_tot = float(metrics.get("horas_totales", 0.0) or 0.0)
        cost_per_hour = round(total_val / horas_tot, 2) if horas_tot > 0 and total_val > 0 else 0.0

        common_count = sum(1 for g in raw_lib if str(g.get("appid")) in friend_ids) if friend_ids else 0

        # Filtrado
        filtrados = []
        for g in raw_lib:
            aid = str(g.get("appid", ""))
            horas = float(g.get("horas", 0.0) or 0.0)
            if filter_mode == "unplayed" and horas >= 0.1:
                continue
            elif filter_mode == "played" and horas < 0.1:
                continue
            elif filter_mode == "coop" and (not friend_ids or aid not in friend_ids):
                continue

            if search and search not in normalizar_texto(f"{g.get('titulo', '')} {aid}"):
                continue

            item = dict(g)
            item["in_common_coop"] = bool(friend_ids and aid in friend_ids)
            filtrados.append(item)

        if sort_by == "horas_asc":
            filtrados.sort(key=lambda x: float(x.get("horas", 0.0) or 0.0))
        elif sort_by == "titulo_asc":
            filtrados.sort(key=lambda x: str(x.get("titulo", "")).lower())
        elif sort_by == "precio_desc":
            filtrados.sort(key=lambda x: float(x.get("price_usd", -1.0) or -1.0), reverse=True)
        else:
            filtrados.sort(key=lambda x: float(x.get("horas", 0.0) or 0.0), reverse=True)

        total_filtered = len(filtrados)
        total_pages = max(1, math.ceil(total_filtered / per_page))
        page = max(1, min(total_pages, int(p.get("page", 1) or 1)))
        start = (page - 1) * per_page

        return {
            "ok": True,
            "items": filtrados[start:start + per_page],
            "total_filtered": total_filtered,
            "page": page,
            "total_pages": total_pages,
            "metrics": metrics,
            "valuation": {
                "total_value_usd": round(total_val, 2),
                "unplayed_value_usd": round(unplayed_val, 2),
                "priced_count": priced_count,
                "cost_per_hour_usd": cost_per_hour,
            },
            "friend_id": friend_id,
            "friend_common_count": common_count,
            "steam_id": str(self.config.datos.get("steam_id", "") or ""),
        }

    def sync_steam_library(
        self,
        steam_id_input: Optional[str] = None,
        api_key_input: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Descarga la biblioteca de Steam y la persiste en SQLite."""
        sid_raw = str(steam_id_input if steam_id_input is not None else self.config.datos.get("steam_id", "")).strip()
        api_key = str(api_key_input if api_key_input is not None else self.config.datos.get("steam_api_key", "")).strip()
        if not sid_raw:
            return {"ok": False, "error": "Ingresá tu Steam ID o configurá uno en Ajustes."}

        resolved_id, juegos = self.api_client.obtener_biblioteca_detalle(sid_raw, api_key)
        if not juegos:
            return {
                "ok": False,
                "error": "No se pudieron obtener juegos (perfil privado o falta Steam API Key para bibliotecas grandes).",
            }

        self.db.save_library_batch(juegos)
        self.sfx.play("coin")
        return {
            "ok": True,
            "count": len(juegos),
            "steam_id": str(resolved_id or sid_raw),
            "command_center": self.get_command_center_data(),
        }

    def valuate_library(self, max_games: int = 120) -> Dict[str, Any]:
        """Consulta precios actuales en Steam para valuar juegos de la biblioteca sin precio."""
        raw_lib = self.db.get_library_cached() or []
        if not raw_lib:
            return {"ok": False, "error": "Primero sincronizá tu biblioteca de Steam."}

        pending_ids = [
            str(g["appid"])
            for g in raw_lib
            if float(g.get("price_usd", -1.0) if g.get("price_usd") is not None else -1.0) < 0
        ][:int(max_games or 120)]

        if not pending_ids:
            return {"ok": True, "updated_count": 0, "command_center": self.get_command_center_data()}

        precios_ar = self.api_client.obtener_precios_argentina_lote(pending_ids) or {}
        mapa_precios = {}
        for aid in pending_ids:
            info = precios_ar.get(aid)
            if info:
                mapa_precios[aid] = float(info.get("normal") or info.get("oferta") or 0.0)
            else:
                mapa_precios[aid] = 0.0

        self.db.update_library_prices_batch(mapa_precios)
        self.sfx.play("coin")
        return {
            "ok": True,
            "updated_count": len(mapa_precios),
            "command_center": self.get_command_center_data(),
        }

    def cross_friend_library(self, friend_steam_id: str) -> Dict[str, Any]:
        """Cruza la biblioteca local con la de un amigo para detectar juegos Co-op en común."""
        raw_friend = str(friend_steam_id or "").strip()
        if not raw_friend:
            return {"ok": False, "error": "Ingresá el Steam ID o URL del amigo."}

        api_key = str(self.config.datos.get("steam_api_key", "") or "").strip()
        resolved_id, friend_games = self.api_client.obtener_biblioteca_detalle(raw_friend, api_key)
        if not friend_games:
            return {"ok": False, "error": "No se pudo leer la biblioteca del amigo (verificá que sea pública)."}

        self._friend_appids = {str(g.get("appid")) for g in friend_games if g.get("appid")}
        self._friend_id = str(resolved_id or raw_friend)

        my_ids = {str(g.get("appid")) for g in (self.db.get_library_cached() or []) if g.get("appid")}
        common_count = len(my_ids & self._friend_appids)
        self.sfx.play("coin")

        return {
            "ok": True,
            "friend_id": self._friend_id,
            "friend_total": len(self._friend_appids),
            "common_count": common_count,
        }

    def clear_friend_cross(self) -> Dict[str, Any]:
        """Limpia el filtro de biblioteca compartida con amigo."""
        self._friend_appids = set()
        self._friend_id = ""
        return {"ok": True}

    def pick_random_backlog(self) -> Dict[str, Any]:
        """Sortea al azar un juego del backlog priorizando los que tienen < 0.5 horas jugadas."""
        raw_lib = self.db.get_library_cached() or []
        if not raw_lib:
            return {"ok": False, "error": "Tu biblioteca cacheada está vacía."}
        unplayed = [g for g in raw_lib if float(g.get("horas", 0.0) or 0.0) < 0.5]
        pool = unplayed if unplayed else raw_lib
        chosen = random.choice(pool)
        self.sfx.play("roulette_win")
        return {"ok": True, "game": chosen, "from_unplayed": bool(unplayed)}

    # ================= GESTOR DE CROMOS & BILLETERA =================
    def analyze_trading_cards(
        self,
        steam_id_input: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Analiza el inventario de cromos de Steam y estima el saldo neto recuperable (-15% fee)."""
        raw_id = str(steam_id_input if steam_id_input is not None else self.config.datos.get("steam_id", "")).strip()
        sid = resolver_steam_id(raw_id) if raw_id else ""
        fx = self._get_fx_values()
        res = analizar_inventario_cromos(
            sid,
            dolar_ref=fx["dolar_referencia"],
            forzar_refresco=bool(force_refresh),
        )
        ok = bool(res.get("exito"))
        if ok:
            self.sfx.play("coin")
        return {
            "ok": ok,
            "steam_id": sid,
            "market_url": COMMUNITY_MARKET_URL,
            "badges_url": COMMUNITY_BADGES_URL.format(steamid=sid) if sid else COMMUNITY_MARKET_URL,
            **res,
        }
