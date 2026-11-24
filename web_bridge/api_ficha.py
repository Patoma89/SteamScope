"""
Mixin de Ficha Técnica Pro, Notas Personales y Comparador Versus 1v1 para SteamScopeWebAPI.
Python puro consumiendo exclusivamente core/ (sin Tkinter/CustomTkinter/pywebview).
"""
import concurrent.futures
import urllib.parse
from typing import Any, Dict, List, Optional

from core.pricing import (
    detectar_suscripcion,
    es_minimo_historico_real,
    evaluar_termometro_compra,
    extraer_espacio_disco,
    limpiar_html,
)

PROTON_RANK = {
    "native": 6,
    "platinum": 5,
    "gold": 4,
    "silver": 3,
    "bronze": 2,
    "borked": 1,
}


class WebAPIFichaMixin:
    """Extensión de Ficha Técnica, notas privadas y comparador Versus para SteamScopeWebAPI."""

    def get_game_details(self, appid: str, item_ref: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Descarga en paralelo todos los datos de un juego y retorna payload JSON limpio."""
        aid = str(appid or "").strip()
        if not aid:
            return {"ok": False, "error": "AppID inválido."}

        ref = dict(item_ref or {})
        data, _poster_pil, review_summary, historico_global, proton_tier = (
            self.api_client.descargar_ficha_completa_paralelo(aid, db_manager=self.db)
        )

        if not isinstance(data, dict) and not ref:
            return {"ok": False, "error": f"No se pudieron obtener detalles para AppID {aid}."}

        d = data if isinstance(data, dict) else {}
        titulo = str(d.get("name") or ref.get("titulo") or f"App {aid}")
        header_image = str(
            d.get("header_image")
            or ref.get("header_url")
            or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
        )
        if isinstance(d, dict) and d.get("header_image"):
            self.db.save_cover_url(aid, str(d["header_image"]))
        poster_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/library_600x900.jpg"

        is_free = bool(d.get("is_free", False))
        po = d.get("price_overview")
        if isinstance(po, dict):
            normal_usd = round(float(po.get("initial", 0) or 0) / 100.0, 2)
            final_usd = round(float(po.get("final", 0) or 0) / 100.0, 2)
            discount_pct = int(po.get("discount_percent", 0) or 0)
        elif is_free:
            normal_usd = 0.0
            final_usd = 0.0
            discount_pct = 0
        else:
            normal_usd = round(float(ref.get("precio_normal_usd", 0.0) or 0.0), 2)
            final_usd = round(float(ref.get("precio_oferta_usd", 0.0) or 0.0), 2)
            discount_pct = int(ref.get("descuento", 0) or 0)

        # Comparativa regional LATAM-USD vs EE.UU.
        us_info = d.get("_us_price_info") if isinstance(d.get("_us_price_info"), dict) else {}
        us_usd = round(float(us_info.get("final_us") or us_info.get("normal_us") or 0.0), 2)
        ar_ref = final_usd if final_usd > 0 else normal_usd
        if us_usd > 0 and ar_ref > 0:
            diff_pct = round(((us_usd - ar_ref) / us_usd) * 100.0, 1)
            if diff_pct >= 5.0:
                reg_status = "better"
                reg_label = f"🇦🇷 Precio Regional cuidado (-{diff_pct:.0f}% vs EE.UU.)"
            elif diff_pct <= -3.0:
                reg_status = "higher"
                reg_label = f"⚠️ Más caro que en EE.UU. (+{abs(diff_pct):.0f}%)"
            else:
                reg_status = "same"
                reg_label = "🇺🇸 Mismo precio que en EE.UU. (Sin ajuste regional)"
        else:
            diff_pct = 0.0
            reg_status = "unknown"
            reg_label = "Comparativa regional no disponible"

        # Calidad, ProtonDB y Requisitos PC
        mc_raw = d.get("metacritic") if isinstance(d.get("metacritic"), dict) else {}
        mc_score = mc_raw.get("score")
        mc_url = str(mc_raw.get("url") or "")

        reviews_obj = (
            {"summary": str(review_summary[0]), "count_text": str(review_summary[1])}
            if review_summary
            else None
        )

        pc_req = d.get("pc_requirements") if isinstance(d.get("pc_requirements"), dict) else {}
        min_raw = str(pc_req.get("minimum") or "")
        rec_raw = str(pc_req.get("recommended") or "")
        disk_space = extraer_espacio_disco(min_raw or rec_raw)

        # Multimedia y Bundles
        screenshots = [
            {
                "id": s.get("id", idx),
                "thumb": str(s.get("path_thumbnail") or s.get("path_full") or ""),
                "full": str(s.get("path_full") or s.get("path_thumbnail") or ""),
            }
            for idx, s in enumerate((d.get("screenshots") or [])[:12])
            if isinstance(s, dict) and (s.get("path_full") or s.get("path_thumbnail"))
        ]

        packages: List[Dict[str, Any]] = []
        pkg_groups = d.get("package_groups") or []
        if pkg_groups and isinstance(pkg_groups[0], dict):
            for sub in (pkg_groups[0].get("subs") or [])[:6]:
                if not isinstance(sub, dict):
                    continue
                cents = float(sub.get("price_in_cents_with_discount", 0) or 0)
                packages.append({
                    "name": limpiar_html(str(sub.get("option_text") or "Edición")),
                    "price_usd": round(cents / 100.0, 2),
                    "discount_pct": int(sub.get("percent_savings", 0) or 0),
                })

        # Histórico ATL y precio log local
        if historico_global:
            atl_price = round(float(historico_global[0] or 0.0), 2)
            atl_date = str(historico_global[1] or "")
            is_atl_now = es_minimo_historico_real(final_usd, atl_price) if final_usd > 0 else False
        else:
            atl_price = 0.0
            atl_date = ""
            is_atl_now = bool(ref.get("es_atl", False))

        log_rows = self.db.get_price_log(aid) or []
        price_history = [
            {"fecha": str(r[2]), "precio_usd": round(float(r[1] or 0.0), 2)}
            for r in log_rows
        ]

        publishers = [str(p) for p in (d.get("publishers") or [])]
        developers = [str(dev) for dev in (d.get("developers") or [])]
        genres = [str(g.get("description")) for g in (d.get("genres") or []) if isinstance(g, dict) and g.get("description")]
        categories = [str(c.get("description")) for c in (d.get("categories") or []) if isinstance(c, dict) and c.get("description")]
        rel_info = d.get("release_date") if isinstance(d.get("release_date"), dict) else {}

        sub = detectar_suscripcion(titulo, ", ".join(publishers))
        term = evaluar_termometro_compra(discount_pct, is_atl_now, final_usd)

        wl_ids = self.db.get_watchlist_ids_set() or set()
        cart_ids = set((self.config.datos.get("carrito_guardado", {}) or {}).keys())
        q_yt = urllib.parse.quote_plus(f"{titulo} steam trailer")
        q_hltb = urllib.parse.quote_plus(titulo)

        return {
            "ok": True,
            "appid": aid,
            "titulo": titulo,
            "header_image": header_image,
            "poster_url": poster_url,
            "short_description": limpiar_html(str(d.get("short_description") or "")),
            "developers": developers,
            "publishers": publishers,
            "release_date": str(rel_info.get("date") or "N/D"),
            "genres": genres,
            "categories": categories,
            "normal_usd": normal_usd,
            "final_usd": final_usd,
            "discount_pct": discount_pct,
            "is_free": is_free,
            "regional": {
                "us_usd": us_usd,
                "ar_usd": ar_ref,
                "diff_pct": diff_pct,
                "status": reg_status,
                "label": reg_label,
            },
            "metacritic": {"score": mc_score, "url": mc_url},
            "reviews": reviews_obj,
            "protondb": str(proton_tier or "Sin datos"),
            "disk_space": disk_space,
            "pc_requirements": {
                "minimum": limpiar_html(min_raw) if min_raw else "No especificado.",
                "recommended": limpiar_html(rec_raw) if rec_raw else "No especificado.",
            },
            "screenshots": screenshots,
            "packages": packages,
            "atl": {
                "price_usd": atl_price,
                "date": atl_date,
                "is_atl_now": is_atl_now,
            },
            "price_history": price_history,
            "suscripcion": {"label": sub[0], "color": sub[1]} if sub else None,
            "termometro": {"label": term[0], "color": term[1], "desc": term[2]},
            "personal_note": self.db.get_game_note(aid),
            "in_watchlist": aid in wl_ids,
            "in_cart": aid in cart_ids,
            "links": {
                "steam_web": f"https://store.steampowered.com/app/{aid}",
                "steam_desktop": f"steam://store/{aid}",
                "steamdb": f"https://steamdb.info/app/{aid}/",
                "hltb": f"https://howlongtobeat.com/?q={q_hltb}",
                "youtube": f"https://www.youtube.com/results?search_query={q_yt}",
            },
        }

    def save_game_note(self, appid: str, note_text: str) -> Dict[str, Any]:
        """Guarda la nota personal privada del usuario y sincroniza con Watchlist."""
        aid = str(appid or "").strip()
        if not aid:
            return {"ok": False, "error": "AppID inválido."}
        self.db.save_game_note(aid, note_text)
        self.sfx.play("click")
        return {
            "ok": True,
            "appid": aid,
            "note": self.db.get_game_note(aid),
            "command_center": self.get_command_center_data(),
        }

    def compare_games_versus(self, appid_a: str, appid_b: str) -> Dict[str, Any]:
        """Compara dos juegos en paralelo evaluando 5 métricas clave."""
        a_id = str(appid_a or "").strip()
        b_id = str(appid_b or "").strip()
        if not a_id or not b_id:
            return {"ok": False, "error": "Debes indicar dos AppIDs válidos para comparar."}

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fa = ex.submit(self.get_game_details, a_id)
            fb = ex.submit(self.get_game_details, b_id)
            game_a = fa.result()
            game_b = fb.result()

        if not game_a.get("ok") or not game_b.get("ok"):
            return {
                "ok": False,
                "error": game_a.get("error") or game_b.get("error") or "No se pudo descargar alguno de los juegos.",
            }

        def _num_winner(va: Optional[float], vb: Optional[float], higher_better: bool = True) -> str:
            if va is None or vb is None:
                return "tie"
            if abs(va - vb) < 1e-6:
                return "tie"
            if higher_better:
                return "A" if va > vb else "B"
            return "A" if va < vb else "B"

        rows: List[Dict[str, Any]] = []

        # 1. Precio Actual USD (menor gana)
        pa, pb = float(game_a["final_usd"]), float(game_b["final_usd"])
        rows.append({
            "metric": "Precio Actual (USD)",
            "val_a": "GRATIS" if game_a["is_free"] else f"${pa:.2f} USD",
            "val_b": "GRATIS" if game_b["is_free"] else f"${pb:.2f} USD",
            "winner": _num_winner(pa, pb, higher_better=False),
        })

        # 2. Descuento % (mayor gana)
        da, db_pct = int(game_a["discount_pct"]), int(game_b["discount_pct"])
        rows.append({
            "metric": "Descuento",
            "val_a": f"-{da}%",
            "val_b": f"-{db_pct}%",
            "winner": _num_winner(float(da), float(db_pct), higher_better=True),
        })

        # 3. Mínimo Histórico ATL (menor gana cuando ambos > 0)
        atla = float(game_a["atl"]["price_usd"] or 0.0)
        atlb = float(game_b["atl"]["price_usd"] or 0.0)
        rows.append({
            "metric": "Mínimo Histórico (ATL)",
            "val_a": f"${atla:.2f} USD" if atla > 0 else "N/D",
            "val_b": f"${atlb:.2f} USD" if atlb > 0 else "N/D",
            "winner": _num_winner(atla if atla > 0 else None, atlb if atlb > 0 else None, higher_better=False),
        })

        # 4. Metacritic (mayor gana)
        mca = game_a["metacritic"]["score"]
        mcb = game_b["metacritic"]["score"]
        rows.append({
            "metric": "Metacritic",
            "val_a": str(mca) if mca is not None else "N/D",
            "val_b": str(mcb) if mcb is not None else "N/D",
            "winner": _num_winner(
                float(mca) if isinstance(mca, (int, float)) else None,
                float(mcb) if isinstance(mcb, (int, float)) else None,
                higher_better=True,
            ),
        })

        # 5. ProtonDB Tier
        p_a = str(game_a["protondb"] or "Sin datos")
        p_b = str(game_b["protondb"] or "Sin datos")
        ra = PROTON_RANK.get(p_a.lower())
        rb = PROTON_RANK.get(p_b.lower())
        rows.append({
            "metric": "ProtonDB (Deck / Linux)",
            "val_a": p_a,
            "val_b": p_b,
            "winner": _num_winner(float(ra) if ra else None, float(rb) if rb else None, higher_better=True),
        })

        score_a = sum(1 for r in rows if r["winner"] == "A")
        score_b = sum(1 for r in rows if r["winner"] == "B")
        winner = "A" if score_a > score_b else ("B" if score_b > score_a else "tie")
        self.sfx.play("coin")

        return {
            "ok": True,
            "game_a": game_a,
            "game_b": game_b,
            "rows": rows,
            "score_a": score_a,
            "score_b": score_b,
            "winner": winner,
        }
