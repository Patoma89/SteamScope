"""
Mixin de Herramientas Avanzadas para SteamScopeWebAPI:
Radar Epic & GOG, Ruleta Loot Box, Dashboard Visual, Eventos Steam, FX en vivo,
Ajustes, Blacklist, Exportadores CSV / Backup .zip y Discord Webhook.
Python puro consumiendo exclusivamente core/ (sin Tkinter/CustomTkinter/pywebview).
"""
import os
import random
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.api_client import HTTP_SESSION, obtener_cotizaciones_dolar
from core.config import STEAM_CALENDAR, limpiar_cache_imagenes
from core.csv_utils import escribir_csv
from core.multi_store import obtener_promociones_epic, obtener_promociones_gog


class WebAPIToolsMixin:
    """Extensión de herramientas avanzadas, configuración y exportadores para SteamScopeWebAPI."""

    # ================= RADAR EPIC & GOG =================
    def get_free_games_radar(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Consulta juegos gratuitos activos y próximos de Epic Games Store + catálogo GOG."""
        items = obtener_promociones_epic(forzar_refresco=bool(force_refresh)) or []
        activos = [it for it in items if it.get("es_activo")]
        proximos = [it for it in items if it.get("es_proximo")]
        gog_data = obtener_promociones_gog(forzar_refresco=bool(force_refresh)) or {}
        gog_gratis = list(gog_data.get("gratis") or [])
        gog_ofertas = list(gog_data.get("ofertas") or [])
        self.sfx.play("click")
        return {
            "ok": True,
            "activos": activos,
            "proximos": proximos,
            "gog_gratis": gog_gratis,
            "gog_ofertas": gog_ofertas,
            "total": len(items) + len(gog_gratis) + len(gog_ofertas),
            "gog_links": [
                {"label": "🎁 Juegos Gratis en GOG (DRM-Free)", "url": "https://www.gog.com/en/games?priceRange=0,0&discounted=true"},
                {"label": "🔥 Ofertas Destacadas GOG", "url": "https://www.gog.com/en/games?discounted=true"},
            ],
        }

    # ================= RULETA LOOT BOX 60 FPS =================
    def spin_roulette(self, mode: str = "deals", exclude_appid: str = "", count: int = 1) -> Dict[str, Any]:
        """Sortea 1, 3 o 5 juegos de ofertas o del backlog evitando repetir el actual."""
        ex_id = str(exclude_appid or "")
        modo = "backlog" if mode == "backlog" else "deals"
        try:
            n = max(1, min(5, int(count or 1)))
        except (TypeError, ValueError):
            n = 1

        if modo == "backlog":
            lib = self.db.get_library_cached() or []
            if not lib:
                return {"ok": False, "error": "Tu biblioteca cacheada está vacía."}
            cands = [g for g in lib if str(g.get("appid")) != ex_id] or lib
            unplayed = [g for g in cands if float(g.get("horas", 0.0) or 0.0) < 0.5]
            if len(unplayed) >= n:
                pool = unplayed
            elif unplayed:
                unplayed_ids = {str(g.get("appid")) for g in unplayed}
                pool = unplayed + [g for g in cands if str(g.get("appid")) not in unplayed_ids]
            else:
                pool = cands

            picked = random.sample(pool, min(n, len(pool)))
            covers = self.db.get_cover_urls_batch([g.get("appid") for g in picked]) or {}
            items = []
            for g in picked:
                aid = str(g.get("appid", ""))
                row = dict(g)
                cached_cover = covers.get(aid, "")
                row["cover_url"] = cached_cover
                row["header_url"] = cached_cover or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
                row["thumb_url"] = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_231x87.jpg"
                row["link"] = f"https://store.steampowered.com/app/{aid}"
                items.append(row)

            pool_titles = [str(g.get("titulo", "")) for g in random.sample(pool, min(12, len(pool)))]
            if items[0].get("titulo") not in pool_titles:
                pool_titles.append(str(items[0].get("titulo")))
            self.sfx.play("roulette_win")
            return {
                "ok": True,
                "mode": "backlog",
                "item": items[0],
                "items": items,
                "pool_titles": pool_titles,
            }

        # Modo Ofertas
        cart_ids = set((self.config.datos.get("carrito_guardado", {}) or {}).keys())
        blacklist = set(self.db.get_blacklist() or [])
        pool_deals = [
            d for d in (self._deals_data or [])
            if str(d.get("appid")) != ex_id and str(d.get("appid")) not in cart_ids
        ]

        if len(pool_deals) < max(5, n):
            try:
                resp = HTTP_SESSION.get(
                    "https://www.cheapshark.com/api/1.0/deals",
                    params={
                        "storeID": "1",
                        "onSale": "1",
                        "pageSize": "30",
                        "pageNumber": str(random.randint(0, 18)),
                    },
                    timeout=6,
                )
                if resp.status_code == 200 and resp.json():
                    raw = [
                        d for d in resp.json()
                        if d.get("steamAppID")
                        and str(d.get("steamAppID")) not in blacklist
                        and str(d.get("steamAppID")) not in cart_ids
                    ]
                    ids_lote = [str(d.get("steamAppID")) for d in raw]
                    precios_ar = self.api_client.obtener_precios_argentina_lote(ids_lote) if ids_lote else {}
                    for d in raw:
                        aid = str(d.get("steamAppID"))
                        if aid in precios_ar:
                            norm = precios_ar[aid]["normal"]
                            sale = precios_ar[aid]["oferta"]
                            desc = precios_ar[aid]["descuento"]
                        else:
                            norm = float(d.get("normalPrice", 0) or 0)
                            sale = float(d.get("salePrice", 0) or 0)
                            desc = round(((norm - sale) / norm) * 100) if norm > sale else 0
                        pool_deals.append(
                            self._build_deal_item(
                                appid=aid,
                                titulo=d.get("title", f"App {aid}"),
                                thumb_url=d.get("thumb", ""),
                                sale_price=sale,
                                normal_price=norm,
                                discount_pct=desc,
                                rating=d.get("steamRatingPercent", "N/A"),
                                es_atl=False,
                            )
                        )
            except Exception:
                pass

        cands = [d for d in pool_deals if str(d.get("appid")) != ex_id] or pool_deals
        if not cands:
            return {"ok": False, "error": "No hay ofertas disponibles para sortear."}

        picked = random.sample(cands, min(n, len(cands)))
        sample = random.sample(cands, min(12, len(cands)))
        pool_titles = [str(d.get("titulo", "")) for d in sample]
        if picked[0].get("titulo") not in pool_titles:
            pool_titles.append(str(picked[0].get("titulo")))
        self.sfx.play("roulette_win")

        return {
            "ok": True,
            "mode": "deals",
            "item": picked[0],
            "items": picked,
            "pool_titles": pool_titles,
        }

    # ================= DASHBOARD VISUAL (4 GRÁFICOS) =================
    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Calcula los 4 datasets estadísticos para el Dashboard GPU."""
        deals = list(self._deals_data or [])
        b_lt25 = b_25_49 = b_50_74 = b_75_99 = b_100 = 0
        genre_counter: Counter = Counter()

        for d in deals:
            desc = int(d.get("descuento", 0) or 0)
            if desc >= 100:
                b_100 += 1
            elif desc >= 75:
                b_75_99 += 1
            elif desc >= 50:
                b_50_74 += 1
            elif desc >= 25:
                b_25_49 += 1
            elif desc > 0:
                b_lt25 += 1

            raw_gen = str(d.get("genero") or "Steam")
            for part in [x.strip() for x in raw_gen.split(",") if x.strip()][:2]:
                genre_counter[part] += 1

        discount_buckets = [
            {"label": "< 25%", "count": b_lt25},
            {"label": "25–49%", "count": b_25_49},
            {"label": "50–74%", "count": b_50_74},
            {"label": "75–99%", "count": b_75_99},
            {"label": "100% Gratis", "count": b_100},
        ]

        top_genres = [
            {"label": g, "count": c}
            for g, c in genre_counter.most_common(6)
        ]

        m = self.db.obtener_metricas_backlog() or {}
        total_lib = int(m.get("total", 0) or 0)
        sin_jugar = int(m.get("sin_jugar", 0) or 0)
        apenas = int(m.get("apenas_probados", 0) or 0)
        viciados = int(m.get("viciados", 0) or 0)
        en_curso = max(0, total_lib - sin_jugar - apenas - viciados)

        backlog_breakdown = [
            {"label": "Sin estrenar (<0.1h)", "count": sin_jugar},
            {"label": "Apenas probados (0.1–2h)", "count": apenas},
            {"label": "En curso (2–20h)", "count": en_curso},
            {"label": "Viciados (20h+)", "count": viciados},
        ]

        lib_rows = self.db.get_library_cached() or []
        lib_sorted = sorted(lib_rows, key=lambda x: float(x.get("horas", 0.0) or 0.0), reverse=True)
        top_played = [
            {
                "appid": str(g.get("appid", "")),
                "titulo": str(g.get("titulo", "")),
                "horas": round(float(g.get("horas", 0.0) or 0.0), 1),
            }
            for g in lib_sorted[:8]
            if float(g.get("horas", 0.0) or 0.0) > 0
        ]

        total_val = 0.0
        for g in lib_rows:
            pr = float(g.get("price_usd", -1.0) if g.get("price_usd") is not None else -1.0)
            if pr >= 0:
                total_val += pr
        horas_totales = float(m.get("horas_totales", 0.0) or 0.0)
        unplayed_val = float(m.get("dinero_sin_estrenar_usd", 0.0) or 0.0)
        cost_per_hour = round(total_val / horas_totales, 2) if horas_totales > 0 and total_val > 0 else 0.0
        discounts = [int(d.get("descuento", 0) or 0) for d in deals if int(d.get("descuento", 0) or 0) > 0]
        avg_discount = round(sum(discounts) / len(discounts), 1) if discounts else 0.0

        return {
            "ok": True,
            "deals_total": len(deals),
            "library_total": total_lib,
            "discount_buckets": discount_buckets,
            "top_genres": top_genres,
            "backlog_breakdown": backlog_breakdown,
            "top_played": top_played,
            "summary": {
                "total_value_usd": round(total_val, 2),
                "unplayed_value_usd": round(unplayed_val, 2),
                "cost_per_hour_usd": cost_per_hour,
                "avg_discount_pct": avg_discount,
                "horas_totales": round(horas_totales, 1),
            },
        }

    # ================= EVENTOS STEAM & FX EN VIVO =================
    def get_steam_events(self) -> Dict[str, Any]:
        """Devuelve el calendario oficial de Steam Sales con countdown en días."""
        now = datetime.now(timezone.utc)
        events = []
        for ev in STEAM_CALENDAR:
            start_dt = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(ev["end"].replace("Z", "+00:00"))
            if start_dt <= now <= end_dt:
                status = "active"
                days_left = max(0, (end_dt - now).days)
            elif now < start_dt:
                status = "upcoming"
                days_left = max(1, (start_dt - now).days)
            else:
                status = "past"
                days_left = 0

            events.append({
                "name": ev["name"],
                "type": ev.get("type", "Major"),
                "start_display": start_dt.strftime("%d/%m/%Y"),
                "end_display": end_dt.strftime("%d/%m/%Y"),
                "status": status,
                "days_left": days_left,
            })

        return {"ok": True, "events": events, "fx": self._get_fx_values()}

    def refresh_live_fx(self, force: bool = True, max_age_seconds: int = 1800) -> Dict[str, Any]:
        """Actualiza dólar oficial, cripto y MEP con caché TTL para evitar esperas redundantes."""
        if not force:
            fx_updated_ts = float(self.config.datos.get("fx_updated_ts", 0.0) or 0.0)
            if fx_updated_ts > 0 and (time.time() - fx_updated_ts) < max_age_seconds:
                fx = self._get_fx_values()
                return {
                    "ok": True,
                    "cached": True,
                    **fx,
                    "command_center": self.get_command_center_data(),
                }

        res = obtener_cotizaciones_dolar() or {}
        if not res.get("ok"):
            return {"ok": False, "error": "No se pudo consultar la cotización en vivo."}

        if res.get("oficial"):
            self.config.guardar_basico("dolar_referencia", round(float(res["oficial"]), 2))
        if res.get("cripto"):
            self.config.guardar_basico("dolar_cripto_ref", round(float(res["cripto"]), 2))
        if res.get("mep"):
            self.config.guardar_basico("dolar_mep_ref", round(float(res["mep"]), 2))

        self.config.guardar_basico("fx_updated_at", str(res.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.config.guardar_basico("fx_updated_ts", time.time())
        if res.get("source"):
            self.config.guardar_basico("fx_source", str(res["source"]))

        if force:
            self.sfx.play("coin")
        fx = self._get_fx_values()
        return {
            "ok": True,
            "cached": False,
            **fx,
            "command_center": self.get_command_center_data(),
        }

    # ================= AJUSTES, BLACKLIST Y MANTENIMIENTO =================
    def get_settings(self) -> Dict[str, Any]:
        """Devuelve la configuración actual editable del usuario."""
        d = self.config.datos
        return {
            "ok": True,
            "settings": {
                "steam_id": str(d.get("steam_id", "") or ""),
                "steam_api_key": str(d.get("steam_api_key", "") or ""),
                "dolar_referencia": float(d.get("dolar_referencia", 1000.0) or 1000.0),
                "dolar_cripto_ref": float(d.get("dolar_cripto_ref", 1150.0) or 1150.0),
                "impuestos_pct": float(d.get("impuestos_pct", 51) if d.get("impuestos_pct") is not None else 51),
                "umbral_alerta_pct": int(d.get("umbral_alerta_pct", 50) or 50),
                "minimizar_a": str(d.get("minimizar_a", "Preguntar") or "Preguntar"),
                "sfx_enabled": bool(d.get("sfx_enabled", True)),
                "discord_webhook": str(d.get("discord_webhook", "") or ""),
                "watchdog_activado": bool(d.get("watchdog_activado", True)),
                "watchdog_intervalo_hs": int(d.get("watchdog_intervalo_hs", 6) or 6),
                "alerta_sonido_atl": bool(d.get("alerta_sonido_atl", True)),
                "fx_source": str(d.get("fx_source", "Manual") or "Manual"),
                "fx_updated_at": str(d.get("fx_updated_at", "") or ""),
            },
        }

    def save_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Valida y persiste la configuración completa en config.json."""
        p = dict(payload or {})
        try:
            dolar = max(1.0, float(p.get("dolar_referencia", 1000.0)))
            cripto = max(1.0, float(p.get("dolar_cripto_ref", 1150.0)))
            imp = max(0.0, min(300.0, float(p.get("impuestos_pct", 51))))
            umbral = max(1, min(100, int(p.get("umbral_alerta_pct", 50))))
            intervalo = max(1, min(72, int(p.get("watchdog_intervalo_hs", 6))))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Valores numéricos inválidos en configuración."}

        minimizar = str(p.get("minimizar_a", "Preguntar"))
        if minimizar not in ("Preguntar", "Barra", "Bandeja"):
            minimizar = "Preguntar"

        prev_dolar = float(self.config.datos.get("dolar_referencia", 1000.0) or 1000.0)
        prev_cripto = float(self.config.datos.get("dolar_cripto_ref", 1150.0) or 1150.0)

        self.config.guardar(
            steam_id=str(p.get("steam_id", "") or "").strip(),
            steam_api_key=str(p.get("steam_api_key", "") or "").strip(),
            impuestos=imp,
            dolar=dolar,
            umbral=umbral,
            minimizar_a=minimizar,
            sfx_enabled=bool(p.get("sfx_enabled", True)),
            discord_webhook=str(p.get("discord_webhook", "") or "").strip(),
            watchdog_activado=bool(p.get("watchdog_activado", True)),
            watchdog_intervalo_hs=intervalo,
            alerta_sonido_atl=bool(p.get("alerta_sonido_atl", True)),
        )
        self.config.guardar_basico("dolar_cripto_ref", cripto)
        if abs(dolar - prev_dolar) > 1e-6 or abs(cripto - prev_cripto) > 1e-6:
            self.config.guardar_basico("fx_source", "Manual")
            self.config.guardar_basico("fx_updated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
            self.config.guardar_basico("fx_updated_ts", time.time())
        self.sfx.play("coin")
        return {
            "ok": True,
            "settings": self.get_settings()["settings"],
            "command_center": self.get_command_center_data(),
        }

    def get_blacklist(self) -> Dict[str, Any]:
        """Devuelve la lista detallada de juegos ignorados."""
        rows = self.db.get_blacklist_details() or []
        return {
            "ok": True,
            "items": [{"appid": str(r[0]), "titulo": str(r[1])} for r in rows],
        }

    def remove_from_blacklist(self, appid: str) -> Dict[str, Any]:
        """Restaura un juego desde la blacklist."""
        aid = str(appid or "").strip()
        if not aid:
            return {"ok": False, "error": "AppID inválido."}
        self.db.remove_blacklist(aid)
        self.sfx.play("click")
        return {"ok": True, "items": self.get_blacklist()["items"]}

    def clear_blacklist(self) -> Dict[str, Any]:
        """Vacía por completo la blacklist."""
        self.db.clear_blacklist()
        self.sfx.play("click")
        return {"ok": True, "items": []}

    def optimize_database(self) -> Dict[str, Any]:
        """Compacta SQLite ejecutando VACUUM y PRAGMA optimize."""
        ok = bool(self.db.optimizar_base_datos())
        self.sfx.play("coin" if ok else "click")
        return {"ok": ok}

    def clear_image_cache(self) -> Dict[str, Any]:
        """Elimina archivos temporales en AppData/cache liberando espacio en disco."""
        borrados, mb_liberados = limpiar_cache_imagenes()
        self.sfx.play("click")
        return {"ok": True, "deleted": borrados, "freed_mb": mb_liberados}

    # ================= EXPORTADORES, BACKUP Y DISCORD =================
    def export_csv(self, scope: str = "watchlist", dest_path: Optional[str] = None) -> Dict[str, Any]:
        """Exporta watchlist, library o deals a CSV UTF-8-SIG compatible con Excel."""
        sc = str(scope or "watchlist").lower()
        default_name = f"SteamScope_{sc}.csv"
        target = dest_path
        if not target and self._on_save_dialog is not None:
            target = self._on_save_dialog(default_name, "csv")
        if not target:
            return {"ok": False, "cancelled": True, "error": "Exportación cancelada."}

        if sc == "library":
            rows = self.db.get_library_cached() or []
            headers = ["AppID", "Título", "Horas Jugadas", "Precio Ref (USD)"]
            data_rows = [[g["appid"], g["titulo"], g["horas"], g["price_usd"]] for g in rows]
        elif sc == "deals":
            rows = list(self._deals_data or [])
            headers = ["AppID", "Título", "Precio Oferta (USD)", "Precio Normal (USD)", "Descuento (%)", "ATL", "Enlace"]
            data_rows = [
                [d["appid"], d["titulo"], d["precio_oferta_usd"], d["precio_normal_usd"], d["descuento"], "Sí" if d.get("es_atl") else "No", d["link"]]
                for d in rows
            ]
        else:
            rows = self.db.get_all_watchlist() or []
            headers = ["AppID", "Título", "Precio Guardado (USD)", "Fecha", "Etiqueta", "Precio Objetivo (USD)", "Enlace"]
            data_rows = [[r[0], r[1], r[2], r[3], r[5] or "", r[6] or 0.0, r[4]] for r in rows]

        try:
            escribir_csv(target, headers, data_rows)
            self.sfx.play("coin")
            return {"ok": True, "path": target, "rows": len(data_rows)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_backup_zip(self, dest_path: Optional[str] = None) -> Dict[str, Any]:
        """Genera un archivo .zip portátil con config.json y la base SQLite."""
        target = dest_path
        if not target and self._on_save_dialog is not None:
            target = self._on_save_dialog("SteamScope_Backup.zip", "zip")
        if not target:
            return {"ok": False, "cancelled": True, "error": "Respaldo cancelado."}

        try:
            archived = []
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                if self.config.config_path and os.path.isfile(self.config.config_path):
                    zf.write(self.config.config_path, arcname=os.path.basename(self.config.config_path))
                    archived.append(os.path.basename(self.config.config_path))
                if self.db.db_path and os.path.isfile(self.db.db_path):
                    try:
                        with self.db.session() as conn:
                            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    except Exception:
                        pass
                    zf.write(self.db.db_path, arcname=os.path.basename(self.db.db_path))
                    archived.append(os.path.basename(self.db.db_path))
            self.sfx.play("coin")
            return {"ok": True, "path": target, "files": archived}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def send_discord_webhook(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Publica una ficha de oferta mediante el Discord Webhook configurado."""
        webhook_url = str(self.config.datos.get("discord_webhook", "") or "").strip()
        if not webhook_url:
            return {"ok": False, "error": "Configurá tu Discord Webhook URL en Ajustes primero."}

        fx = self._get_fx_values()
        p_usd = float(item.get("precio_oferta_usd", 0.0) or 0.0)
        p_ars = round(p_usd * fx["dolar_referencia"] * (1.0 + fx["impuestos_pct"] / 100.0))
        titulo = str(item.get("titulo", "Oferta Steam"))
        aid = str(item.get("appid", ""))
        desc = int(item.get("descuento", 0) or 0)

        rating_raw = item.get("rating", "N/A")
        rating_str = str(rating_raw if rating_raw is not None else "N/A").strip() or "N/A"
        rating_display = f"{rating_str}%" if rating_str.isdigit() else rating_str

        payload = {
            "embeds": [{
                "title": f"🔥 {titulo} (-{desc}% OFF)",
                "url": item.get("link") or f"https://store.steampowered.com/app/{aid}",
                "color": 3719160,
                "fields": [
                    {"name": "💵 USD", "value": f"${p_usd:.2f}", "inline": True},
                    {"name": "💳 ARS Tarjeta", "value": f"${p_ars:,.0f}", "inline": True},
                    {"name": "⭐ Reseñas", "value": rating_display, "inline": True},
                ],
                "footer": {"text": "SteamScope 3.0 NEXT • by Patoma89"},
            }]
        }
        try:
            r = HTTP_SESSION.post(webhook_url, json=payload, timeout=6)
            if r.status_code in (200, 204):
                self.sfx.play("coin")
                return {"ok": True}
            return {"ok": False, "error": f"Discord devolvió HTTP {r.status_code}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
