"""
Mixin de Ofertas, Búsqueda, Filtros, Changuito y Acciones de Catálogo para SteamScopeWebAPI.
Python puro consumiendo exclusivamente core/ (sin Tkinter/CustomTkinter/pywebview).
"""
import math
from typing import Any, Dict, List, Optional

from core.api_client import HTTP_SESSION
from core.config import (
    CATEGORIAS_STEAM,
    FILTROS_CALIDAD,
    ITEMS_POR_PAGINA,
    MODALIDADES,
    RANGOS_DESCUENTO,
    RANGOS_PRECIO,
)
from core.filters import filtrar_ofertas_en_memoria, normalizar_texto
from core.pricing import (
    SORT_STRATEGIES,
    detectar_suscripcion,
    es_steam_deck_verificado,
    evaluar_termometro_compra,
    formatear_oferta_para_compartir,
    ordenar_ofertas,
)

VALID_VIEWS = ("Compacta", "Normal", "Grilla")


class WebAPIDealsMixin:
    """Extensión de ofertas, búsqueda, filtros y changuito para SteamScopeWebAPI."""

    def _build_deal_item(
        self,
        appid: str,
        titulo: str,
        thumb_url: str,
        sale_price: float,
        normal_price: float,
        discount_pct: int,
        rating: Any,
        es_atl: bool,
    ) -> Dict[str, Any]:
        meta = self.db.get_game_meta(appid)
        if meta:
            mod_txt = str(meta[0] or "Single-Player")
            gen_display = str(meta[4] or meta[1] or "Steam")
            g_low = gen_display.lower()
            tiene_cromos = ("trading cards" in g_low) or ("cromos" in g_low) or ("cards" in g_low)
            es_deck = es_steam_deck_verificado(gen_display)
        else:
            es_dlc = any(
                kw in (titulo or "").lower()
                for kw in ("soundtrack", "dlc", "season pass", "pack", "expansion", "expansión", "paquete", "upgrade")
            )
            mod_txt = "Expansión / DLC" if es_dlc else "Single-Player"
            gen_display = "Contenido Adicional" if es_dlc else "Steam"
            tiene_cromos = False
            es_deck = False

        sub = detectar_suscripcion(titulo)
        term = evaluar_termometro_compra(discount_pct, es_atl, sale_price)

        return {
            "appid": appid,
            "titulo": titulo or f"App {appid}",
            "thumb_url": thumb_url or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_sm_120.jpg",
            "header_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
            "precio_oferta_usd": round(float(sale_price), 2),
            "precio_normal_usd": round(float(normal_price), 2),
            "descuento": int(discount_pct),
            "rating": str(rating if rating is not None else "N/A"),
            "modalidad": mod_txt,
            "genero": gen_display,
            "es_atl": bool(es_atl),
            "es_bug": bool((normal_price >= 19.99 and sale_price <= 2.00) or discount_pct >= 93),
            "tiene_cromos": tiene_cromos,
            "es_deck": es_deck,
            "suscripcion": {"label": sub[0], "color": sub[1]} if sub else None,
            "termometro": {"label": term[0], "color": term[1], "desc": term[2]},
            "link": f"https://store.steampowered.com/app/{appid}",
        }

    def _registrar_busqueda_reciente(self, query: str) -> List[str]:
        rec = list(self.config.datos.get("busquedas_recientes", []) or [])
        if query in rec:
            rec.remove(query)
        rec.insert(0, query)
        rec = rec[:5]
        self.config.guardar_basico("busquedas_recientes", rec)
        return rec

    def get_deals_metadata(self) -> Dict[str, Any]:
        """Devuelve catálogos de filtros, ordenamientos, vistas y presets guardados."""
        return {
            "descuentos": list(RANGOS_DESCUENTO.keys()),
            "precios": list(RANGOS_PRECIO.keys()),
            "calidades": list(FILTROS_CALIDAD.keys()),
            "modalidades": list(MODALIDADES.keys()),
            "categorias": {cat: list(subs.keys()) for cat, subs in CATEGORIAS_STEAM.items()},
            "ordenes": list(SORT_STRATEGIES.keys()),
            "limites": [50, 100, 200, 300],
            "vista": str(self.config.datos.get("vista_resultados", "Normal")),
            "recientes": list(self.config.datos.get("busquedas_recientes", []) or []),
            "preset": dict(self.config.datos.get("filtro_favorito", {}) or {}),
            "items_per_page": ITEMS_POR_PAGINA,
        }

    def search_or_scan_deals(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ejecuta búsqueda directa en Steam storesearch o escaneo de rebajas en CheapShark + AR."""
        p = dict(params or {})
        query = str(p.get("query", "") or "").strip()
        limite = int(p.get("limite", 100) or 100)
        limite = max(25, min(300, limite))
        blacklist = set(self.db.get_blacklist() or [])
        library_rows = self.db.get_library_cached() or []
        juegos_propios = {str(j.get("appid")) for j in library_rows if j.get("appid")}

        procesados: List[Dict[str, Any]] = []
        hubo_atl = False
        recientes = list(self.config.datos.get("busquedas_recientes", []) or [])

        if query:
            mode = "search"
            recientes = self._registrar_busqueda_reciente(query)
            items_raw: List[Dict[str, Any]] = []
            vistos = set()
            try:
                resp = HTTP_SESSION.get(
                    "https://store.steampowered.com/api/storesearch",
                    params={"term": query, "l": "spanish", "cc": "ar"},
                    timeout=6,
                )
                if resp.status_code == 200:
                    for it in (resp.json() or {}).get("items", []):
                        aid = str(it.get("id") or "")
                        if aid and aid not in vistos and aid not in blacklist:
                            vistos.add(aid)
                            items_raw.append(it)
            except Exception as exc:
                return {"ok": False, "error": f"Error al buscar en Steam: {exc}", "mode": mode}

            appids = [str(it.get("id")) for it in items_raw if it.get("id")]
            mapa_precios_ar = self.api_client.obtener_precios_argentina_lote(appids) if appids else {}
            pares_hist = {}
            for aid in appids:
                if aid in mapa_precios_ar and mapa_precios_ar[aid]["oferta"] > 0:
                    pares_hist[aid] = (
                        mapa_precios_ar[aid]["oferta"],
                        mapa_precios_ar[aid]["descuento"],
                        mapa_precios_ar[aid]["normal"],
                    )
            res_atl = self.db.update_historical_min_batch(pares_hist) if pares_hist else {}

            for it in items_raw:
                aid = str(it.get("id"))
                if aid in mapa_precios_ar:
                    norm = mapa_precios_ar[aid]["normal"]
                    sale = mapa_precios_ar[aid]["oferta"]
                    desc = mapa_precios_ar[aid]["descuento"]
                else:
                    p_info = it.get("price") or {}
                    norm = (p_info.get("initial", 0) or 0) / 100.0
                    sale = (p_info.get("final", 0) or 0) / 100.0
                    desc = round(((norm - sale) / norm) * 100) if norm > sale else 0

                es_atl = bool(res_atl.get(aid, False))
                if es_atl:
                    hubo_atl = True
                procesados.append(
                    self._build_deal_item(
                        appid=aid,
                        titulo=it.get("name", query),
                        thumb_url=it.get("tiny_image", ""),
                        sale_price=sale,
                        normal_price=norm,
                        discount_pct=desc,
                        rating="N/A",
                        es_atl=es_atl,
                    )
                )
        else:
            mode = "scan"
            vistos = set()
            max_pages = min(8, max(2, math.ceil(limite / 45) + 1))
            for page_num in range(max_pages):
                if len(procesados) >= limite:
                    break
                try:
                    resp = HTTP_SESSION.get(
                        "https://www.cheapshark.com/api/1.0/deals",
                        params={
                            "storeID": "1",
                            "onSale": "1",
                            "pageSize": "60",
                            "pageNumber": str(page_num),
                            "sortBy": "Deal Rating",
                        },
                        timeout=10,
                    )
                    if resp.status_code != 200:
                        break
                    raw_deals = resp.json() or []
                    if not raw_deals:
                        break
                except Exception as exc:
                    if not procesados:
                        return {"ok": False, "error": f"Error al escanear ofertas: {exc}", "mode": mode}
                    break

                candidatos = []
                for d in raw_deals:
                    aid = str(d.get("steamAppID") or "")
                    if not aid or aid in vistos or aid in blacklist or aid in juegos_propios:
                        continue
                    vistos.add(aid)
                    candidatos.append(d)

                ids_lote = [str(c.get("steamAppID")) for c in candidatos]
                mapa_precios_ar = self.api_client.obtener_precios_argentina_lote(ids_lote) if ids_lote else {}
                pares_hist = {}
                lote_items = []

                for d in candidatos:
                    if len(procesados) + len(lote_items) >= limite:
                        break
                    aid = str(d.get("steamAppID"))
                    if aid in mapa_precios_ar:
                        norm = mapa_precios_ar[aid]["normal"]
                        sale = mapa_precios_ar[aid]["oferta"]
                        desc = mapa_precios_ar[aid]["descuento"]
                    else:
                        norm = float(d.get("normalPrice", 0) or 0)
                        sale = float(d.get("salePrice", 0) or 0)
                        desc = int(round(float(d.get("savings", 0) or 0)))

                    pares_hist[aid] = (sale, desc, norm)
                    lote_items.append((d, aid, norm, sale, desc))

                res_atl = self.db.update_historical_min_batch(pares_hist) if pares_hist else {}
                for d, aid, norm, sale, desc in lote_items:
                    es_atl = bool(res_atl.get(aid, False))
                    if es_atl:
                        hubo_atl = True
                    procesados.append(
                        self._build_deal_item(
                            appid=aid,
                            titulo=d.get("title", f"App {aid}"),
                            thumb_url=d.get("thumb", ""),
                            sale_price=sale,
                            normal_price=norm,
                            discount_pct=desc,
                            rating=d.get("steamRatingPercent", "0"),
                            es_atl=es_atl,
                        )
                    )

        self._deals_data = procesados
        if hubo_atl:
            self.sfx.play("atl")

        p["page"] = 1
        page_res = self.query_deals(p)
        page_res["mode"] = mode
        page_res["total_raw"] = len(self._deals_data)
        page_res["recientes"] = recientes
        return page_res

    def query_deals(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Filtra, ordena y pagina las ofertas cargadas en memoria en microsegundos."""
        p = dict(params or {})
        base = list(self._deals_data)

        desc_key = str(p.get("descuento", "Cualquier Descuento") or "Cualquier Descuento")
        min_desc, max_desc = RANGOS_DESCUENTO.get(desc_key, (1, 100))
        if p.get("include_full_price") or str(p.get("query", "")).strip():
            if desc_key == "Cualquier Descuento":
                min_desc = 0

        precio_max_raw = str(p.get("precio_max_usd", "") or "").strip().replace(",", ".")
        if precio_max_raw:
            try:
                p_min, p_max = 0.0, float(precio_max_raw)
            except ValueError:
                p_min, p_max = RANGOS_PRECIO.get(p.get("precio_rango", "Cualquier Precio"), (0.0, 999.0))
        else:
            p_min, p_max = RANGOS_PRECIO.get(p.get("precio_rango", "Cualquier Precio"), (0.0, 999.0))

        calidad_key = str(p.get("calidad", "Cualquier Calidad") or "Cualquier Calidad")
        min_rating = float(FILTROS_CALIDAD.get(calidad_key, 0))
        mod_key = str(p.get("modalidad", "Cualquiera") or "Cualquiera")
        req_modo = MODALIDADES.get(mod_key, "")
        cat_padre = str(p.get("cat_padre", "Todas las Categorías") or "Todas las Categorías")
        subcat = str(p.get("subcat", "Todas las subcategorías") or "Todas las subcategorías")
        texto_local = str(p.get("local_filter", "") or "")

        filtradas_base = filtrar_ofertas_en_memoria(
            base,
            texto_busqueda=texto_local,
            categoria_padre=cat_padre,
            subcategoria=subcat,
            min_desc=min_desc,
            max_desc=max_desc,
            p_min=p_min,
            p_max=p_max,
            min_rating=min_rating,
            modalidad=req_modo,
        )

        # KPIs calculados antes del filtro KPI activo
        atl_cnt = sum(1 for d in filtradas_base if d.get("es_atl"))
        free_cnt = sum(
            1 for d in filtradas_base
            if d.get("descuento") == 100 or (d.get("precio_oferta_usd", 1) == 0.0 and d.get("descuento", 0) > 0)
        )
        sub_cnt = sum(1 for d in filtradas_base if d.get("suscripcion") or detectar_suscripcion(d.get("titulo", "")))
        cards_cnt = sum(1 for d in filtradas_base if d.get("tiene_cromos"))
        coop_cnt = sum(
            1 for d in filtradas_base
            if "cooperativo" in (d.get("modalidad") or "").lower()
            or "multi" in (d.get("modalidad") or "").lower()
            or "co-op" in normalizar_texto(d.get("genero", ""))
        )
        precios_pos = [d["precio_oferta_usd"] for d in filtradas_base if d.get("precio_oferta_usd", 0) > 0]
        avg_usd = round(sum(precios_pos) / len(precios_pos), 2) if precios_pos else 0.0

        kpis = {
            "all": len(filtradas_base),
            "atl": atl_cnt,
            "free": free_cnt,
            "sub": sub_cnt,
            "cards": cards_cnt,
            "coop": coop_cnt,
            "avg_usd": avg_usd,
        }

        kpi_filter = str(p.get("kpi_filter", "all") or "all")
        if kpi_filter == "atl":
            filtradas = [d for d in filtradas_base if d.get("es_atl")]
        elif kpi_filter == "free":
            filtradas = [
                d for d in filtradas_base
                if d.get("descuento") == 100 or (d.get("precio_oferta_usd", 1) == 0.0 and d.get("descuento", 0) > 0)
            ]
        elif kpi_filter == "sub":
            filtradas = [d for d in filtradas_base if d.get("suscripcion") or detectar_suscripcion(d.get("titulo", ""))]
        elif kpi_filter == "cards":
            filtradas = [d for d in filtradas_base if d.get("tiene_cromos")]
        elif kpi_filter == "coop":
            filtradas = [
                d for d in filtradas_base
                if "cooperativo" in (d.get("modalidad") or "").lower()
                or "multi" in (d.get("modalidad") or "").lower()
                or "co-op" in normalizar_texto(d.get("genero", ""))
            ]
        else:
            filtradas = filtradas_base

        sort_by = str(p.get("sort_by", "Mayor Descuento") or "Mayor Descuento")
        ordenar_ofertas(filtradas, sort_by)

        total_filtered = len(filtradas)
        per_page = int(p.get("per_page", ITEMS_POR_PAGINA) or ITEMS_POR_PAGINA)
        per_page = max(1, min(100, per_page))
        total_pages = max(1, math.ceil(total_filtered / per_page))
        page = max(1, min(total_pages, int(p.get("page", 1) or 1)))
        start = (page - 1) * per_page
        slice_items = filtradas[start:start + per_page]

        wl_ids = self.db.get_watchlist_ids_set() or set()
        cart_ids = set((self.config.datos.get("carrito_guardado", {}) or {}).keys())
        covers = self.db.get_cover_urls_batch([it.get("appid") for it in slice_items]) or {}

        items_out = []
        for it in slice_items:
            aid = str(it.get("appid"))
            row = dict(it)
            row["in_watchlist"] = aid in wl_ids
            row["in_cart"] = aid in cart_ids
            row["cover_url"] = covers.get(aid, "")
            items_out.append(row)

        return {
            "ok": True,
            "items": items_out,
            "total_raw": len(self._deals_data),
            "total_filtered": total_filtered,
            "page": page,
            "total_pages": total_pages,
            "kpis": kpis,
        }

    def set_vista(self, vista: str) -> Dict[str, Any]:
        """Guarda el modo de visualización de tarjetas (Compacta / Normal / Grilla)."""
        if vista not in VALID_VIEWS:
            return {"ok": False, "error": f"Vista inválida: {vista}"}
        self.config.guardar_basico("vista_resultados", vista)
        self.sfx.play("click")
        return {"ok": True, "vista": vista}

    def save_filter_preset(self, preset: Dict[str, Any]) -> Dict[str, Any]:
        """Persiste la configuración favorita de filtros."""
        clean = dict(preset or {})
        self.config.guardar_basico("filtro_favorito", clean)
        self.sfx.play("cart_add")
        return {"ok": True, "preset": clean}

    def load_filter_preset(self) -> Dict[str, Any]:
        """Recupera el preset de filtros guardado."""
        preset = dict(self.config.datos.get("filtro_favorito", {}) or {})
        if not preset:
            return {"ok": False, "error": "No hay preset guardado todavía."}
        self.sfx.play("click")
        return {"ok": True, "preset": preset}

    def get_cart(self) -> Dict[str, Any]:
        """Devuelve el detalle del changuito con totales en USD, Tarjeta, Cripto y Budget Tracker."""
        fx = self._get_fx_values()
        dolar_base = fx["dolar_referencia"]
        dolar_cripto = fx["dolar_cripto_ref"]
        mult_tarjeta = 1.0 + (fx["impuestos_pct"] / 100.0)

        carrito = self.config.datos.get("carrito_guardado", {}) or {}
        items = list(carrito.values())
        tot_usd = sum(float(i.get("precio_oferta_usd", 0.0) or 0.0) for i in items)
        tot_reg = sum(float(i.get("precio_normal_usd", i.get("precio_oferta_usd", 0.0)) or 0.0) for i in items)
        ahorro_usd = max(0.0, tot_reg - tot_usd)
        ahorro_pct = int(round((ahorro_usd / tot_reg) * 100)) if tot_reg > 0 else 0

        budget_usd = float(self.config.datos.get("presupuesto_carrito_usd", 0.0) or 0.0)
        budget_pct = round((tot_usd / budget_usd) * 100.0, 1) if budget_usd > 0 else 0.0
        if budget_usd <= 0:
            budget_status = "none"
        elif tot_usd > budget_usd:
            budget_status = "over"
        elif budget_pct >= 85.0:
            budget_status = "warn"
        else:
            budget_status = "ok"

        return {
            "ok": True,
            "items": items,
            "summary": {
                "count": len(items),
                "total_usd": round(tot_usd, 2),
                "total_ars_tarjeta": round(tot_usd * dolar_base * mult_tarjeta),
                "total_ars_cripto": round(tot_usd * dolar_cripto),
                "ahorro_usd": round(ahorro_usd, 2),
                "ahorro_pct": ahorro_pct,
                "budget_usd": round(budget_usd, 2),
                "budget_pct": budget_pct,
                "budget_status": budget_status,
                "remaining_usd": round(budget_usd - tot_usd, 2) if budget_usd > 0 else 0.0,
            },
        }

    def toggle_cart_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Agrega o quita un juego del changuito persistente."""
        aid = str(item.get("appid") or "")
        if not aid:
            return {"ok": False, "error": "AppID inválido."}
        carrito = dict(self.config.datos.get("carrito_guardado", {}) or {})
        if aid in carrito:
            del carrito[aid]
            in_cart = False
            self.sfx.play("cart_remove")
        else:
            carrito[aid] = dict(item)
            in_cart = True
            self.sfx.play("cart_add")
        self.config.guardar_basico("carrito_guardado", carrito)
        return {
            "ok": True,
            "in_cart": in_cart,
            "cart": self.get_cart(),
            "command_center": self.get_command_center_data(),
        }

    def clear_cart(self) -> Dict[str, Any]:
        """Vacía por completo el changuito guardado."""
        self.config.guardar_basico("carrito_guardado", {})
        self.sfx.play("cart_remove")
        return {
            "ok": True,
            "cart": self.get_cart(),
            "command_center": self.get_command_center_data(),
        }

    def set_cart_budget(self, budget_usd: float) -> Dict[str, Any]:
        """Fija o desactiva (0) el tope de presupuesto en USD para el changuito."""
        try:
            val = max(0.0, min(9999.0, float(budget_usd)))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Presupuesto inválido."}
        self.config.guardar_basico("presupuesto_carrito_usd", round(val, 2))
        self.sfx.play("click")
        return {
            "ok": True,
            "budget_usd": round(val, 2),
            "cart": self.get_cart(),
            "command_center": self.get_command_center_data(),
        }

    def toggle_watchlist_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Agrega o quita un juego de la Watchlist en SQLite."""
        aid = str(item.get("appid") or "")
        if not aid:
            return {"ok": False, "error": "AppID inválido."}
        wl_ids = self.db.get_watchlist_ids_set() or set()
        if aid in wl_ids:
            self.db.remove_watchlist(aid)
            in_wl = False
            self.sfx.play("cart_remove")
        else:
            titulo = str(item.get("titulo") or f"App {aid}")
            precio = float(item.get("precio_oferta_usd", 0.0) or 0.0)
            link = str(item.get("link") or f"https://store.steampowered.com/app/{aid}")
            self.db.add_watchlist(aid, titulo, precio, link)
            in_wl = True
            self.sfx.play("coin")
        return {
            "ok": True,
            "in_watchlist": in_wl,
            "command_center": self.get_command_center_data(),
        }

    def add_to_blacklist(self, appid: str, titulo: str = "Juego Oculto") -> Dict[str, Any]:
        """Añade un juego a la blacklist en SQLite y lo remueve de las ofertas en memoria."""
        aid = str(appid or "")
        if not aid:
            return {"ok": False, "error": "AppID inválido."}
        self.db.add_blacklist(aid, titulo or "Juego Oculto")
        self._deals_data = [d for d in self._deals_data if str(d.get("appid")) != aid]
        self.sfx.play("click")
        return {"ok": True, "appid": aid}

    def get_share_text(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Genera la ficha de texto formateada para compartir en WhatsApp o Discord."""
        fx = self._get_fx_values()
        txt = formatear_oferta_para_compartir(
            item,
            dolar_ref=fx["dolar_referencia"],
            impuestos_pct=fx["impuestos_pct"],
        )
        return {"ok": True, "text": txt}
