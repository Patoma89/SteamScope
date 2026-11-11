import re
import html
import xml.etree.ElementTree as ET
import concurrent.futures
from datetime import datetime
from io import BytesIO
import requests
from PIL import Image, ImageOps

HEADERS_BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update(HEADERS_BROWSER)
_adapter = requests.adapters.HTTPAdapter(pool_connections=25, pool_maxsize=25)
HTTP_SESSION.mount("https://", _adapter)
HTTP_SESSION.mount("http://", _adapter)


def resolver_steam_id(input_usuario):
    limpio = (input_usuario or "").strip().rstrip("/")
    if not limpio:
        return None
    if "steamcommunity.com" in limpio:
        partes = [p for p in limpio.split("/") if p]
        if "profiles" in partes:
            idx = partes.index("profiles")
            if idx + 1 < len(partes):
                return partes[idx + 1]
        if "id" in partes:
            idx = partes.index("id")
            if idx + 1 < len(partes):
                limpio = partes[idx + 1]
    if re.match(r"^\d{17}$", limpio):
        return limpio
    try:
        url_xml = f"https://steamcommunity.com/id/{limpio}/?xml=1"
        resp = HTTP_SESSION.get(url_xml, timeout=5)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            steam_id_elem = root.find("steamID64")
            if steam_id_elem is not None and steam_id_elem.text:
                return steam_id_elem.text
    except Exception:
        pass
    return limpio


def consultar_dolar_api(tipo="oficial"):
    try:
        r = HTTP_SESSION.get(f"https://dolarapi.com/v1/dolares/{tipo}", timeout=4)
        if r.status_code == 200:
            venta = r.json().get("venta")
            if venta:
                return float(venta)
    except Exception:
        pass

    try:
        r2 = HTTP_SESSION.get("https://criptoya.com/api/dolar", timeout=4)
        if r2.status_code == 200:
            data = r2.json()
            if tipo == "cripto":
                val = float(data.get("cripto", {}).get("usdt", {}).get("ask", 0))
                if val > 0:
                    return val
            if tipo == "oficial":
                val = float(data.get("oficial", 0))
                if val > 0:
                    return val
    except Exception:
        pass

    return None


class SteamAPIClient:
    """
    Cliente de red unificado bajo estrategia Zero-Waste (SRP / DIP):
    - Agrupa consultas a Steam Store en lotes (batching) para precios y metadatos básicos.
    - Paraleliza la descarga de la Ficha Técnica (5 endpoints simultáneos en < 700ms).
    """
    def __init__(self, session=None):
        self.session = session or HTTP_SESSION

    def obtener_precios_argentina_lote(self, lista_appids):
        """Consulta precios de hasta N juegos agrupándolos en bloques de 30 AppIDs en paralelo."""
        precios_ar = {}
        if not lista_appids:
            return precios_ar
        chunks = [lista_appids[i:i + 40] for i in range(0, len(lista_appids), 40)]

        def _fetch_chunk(chunk):
            try:
                ids_str = ",".join(str(x) for x in chunk)
                url = f"https://store.steampowered.com/api/appdetails?appids={ids_str}&cc=ar&filters=price_overview"
                r = self.session.get(url, timeout=6)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                pass
            return {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            for res in ex.map(_fetch_chunk, chunks):
                if isinstance(res, dict):
                    for aid, info in res.items():
                        if isinstance(info, dict) and info.get("success"):
                            data = info.get("data")
                            if isinstance(data, dict):
                                if "price_overview" in data:
                                    po = data["price_overview"]
                                    precios_ar[str(aid)] = {
                                        "normal": po.get("initial", 0) / 100.0,
                                        "oferta": po.get("final", 0) / 100.0,
                                        "descuento": po.get("discount_percent", 0)
                                    }
                                else:
                                    precios_ar[str(aid)] = {
                                        "normal": 0.0,
                                        "oferta": 0.0,
                                        "descuento": 0
                                    }
        return precios_ar

    def resolver_nombre_individual(self, appid):
        """Resuelve el nombre real de un AppID vía Steam appdetails o CheapShark fallback."""
        aid_str = str(appid)
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={aid_str}&l=spanish&filters=basic"
            r = self.session.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and data.get(aid_str, {}).get("success"):
                    nm = data[aid_str].get("data", {}).get("name")
                    if nm:
                        return nm.strip()
        except Exception:
            pass
        # Fallback CheapShark
        try:
            url_cs = f"https://www.cheapshark.com/api/1.0/games?steamAppID={aid_str}"
            r_cs = self.session.get(url_cs, timeout=4)
            if r_cs.status_code == 200:
                d_cs = r_cs.json()
                if isinstance(d_cs, list) and d_cs and d_cs[0].get("external"):
                    return d_cs[0]["external"].strip()
        except Exception:
            pass
        return None

    def obtener_datos_basicos_lote(self, lista_appids):
        """
        Obtiene nombre ('name') y tipo ('type': game/dlc) de una lista de AppIDs
        usando un pool concurrente de hilos con fallback resiliente.
        """
        basicos = {}
        if not lista_appids:
            return basicos

        def _fetch_uno(aid):
            aid_str = str(aid)
            # Primero intento Steam appdetails
            try:
                url = f"https://store.steampowered.com/api/appdetails?appids={aid_str}&l=spanish&filters=basic"
                r = self.session.get(url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, dict) and data.get(aid_str, {}).get("success"):
                        d_inner = data[aid_str].get("data", {})
                        if isinstance(d_inner, dict) and d_inner.get("name"):
                            return aid_str, {
                                "name": d_inner.get("name").strip(),
                                "type": d_inner.get("type", "game"),
                                "header_image": d_inner.get("header_image")
                            }
            except Exception:
                pass

            # Fallback CheapShark para garantizar el nombre oficial
            try:
                url_cs = f"https://www.cheapshark.com/api/1.0/games?steamAppID={aid_str}"
                r_cs = self.session.get(url_cs, timeout=4)
                if r_cs.status_code == 200:
                    d_cs = r_cs.json()
                    if isinstance(d_cs, list) and d_cs and d_cs[0].get("external"):
                        return aid_str, {
                            "name": d_cs[0]["external"].strip(),
                            "type": "game",
                            "header_image": None
                        }
            except Exception:
                pass

            return aid_str, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            resultados = ex.map(_fetch_uno, lista_appids)
            for aid_str, res in resultados:
                if res:
                    basicos[aid_str] = res
        return basicos

    def obtener_header_image(self, appid):
        """Rescata la URL oficial de header_image desde Steam API (con hash) cuando las URLs estáticas dan 404."""
        if not appid:
            return None
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
            r = self.session.get(url, timeout=3.5)
            if r.status_code == 200:
                info = r.json().get(str(appid), {})
                if isinstance(info, dict) and info.get("success"):
                    return info.get("data", {}).get("header_image")
        except Exception:
            pass
        return None

    def obtener_historial_global_cheapshark(self, appid, db_manager=None):
        """
        Consulta en CheapShark el récord histórico real de todos los tiempos (cheapestPrice / cheapestPriceEver)
        y el precio minorista normal (retailPrice) del juego en Steam.
        Prioriza el endpoint `/deals?storeID=1&steamAppID=` + `/deals?id=` (evita rate-limits 429 de `/games`),
        con fallback a `/games?steamAppID=`.
        Si se provee db_manager, registra ese récord real con su fecha exacta en SQLite.
        """
        if not appid:
            return None
        appid_str = str(appid)

        def _procesar_y_guardar(p_val, ts, retail_price):
            dt_obj = datetime.fromtimestamp(ts) if ts > 0 else datetime.now()
            fecha_iso = dt_obj.strftime("%Y-%m-%d")
            fecha_display = dt_obj.strftime("%d/%m/%Y")
            if db_manager and p_val > 0:
                db_manager.registrar_punto_historico_externo(appid_str, p_val, fecha_iso)
            return {
                "atl_price": p_val,
                "atl_date_iso": fecha_iso,
                "atl_date_display": fecha_display,
                "retail_price": retail_price
            }

        # 1. Vía principal sin bloqueo 429: /deals?storeID=1&steamAppID=... -> /deals?id=...
        try:
            r_deals = self.session.get(
                f"https://www.cheapshark.com/api/1.0/deals?storeID=1&steamAppID={appid_str}",
                timeout=4.5
            )
            if r_deals.status_code == 200 and r_deals.json():
                d0 = r_deals.json()[0]
                deal_id = d0.get("dealID")
                retail_p = float(d0.get("normalPrice") or 0.0)
                if deal_id:
                    r_dinfo = self.session.get(
                        f"https://www.cheapshark.com/api/1.0/deals?id={deal_id}",
                        timeout=4.5
                    )
                    if r_dinfo.status_code == 200:
                        d_json = r_dinfo.json()
                        g_info = d_json.get("gameInfo", {})
                        if g_info.get("retailPrice"):
                            retail_p = float(g_info["retailPrice"])
                        cheapest = d_json.get("cheapestPrice", {})
                        if cheapest.get("price"):
                            return _procesar_y_guardar(
                                float(cheapest["price"]),
                                int(cheapest.get("date", 0)),
                                retail_p
                            )
        except Exception:
            pass

        # 2. Fallback clásico: /games?steamAppID=...
        try:
            r_cs = self.session.get(f"https://www.cheapshark.com/api/1.0/games?steamAppID={appid_str}", timeout=4)
            if r_cs.status_code == 200 and r_cs.json():
                g_id = r_cs.json()[0].get("gameID")
                if g_id:
                    r_det = self.session.get(f"https://www.cheapshark.com/api/1.0/games?id={g_id}", timeout=4)
                    if r_det.status_code == 200:
                        det_json = r_det.json()
                        cheapest = det_json.get("cheapestPriceEver", {})
                        deals = det_json.get("deals", [])
                        retail_price = 0.0
                        for d in deals:
                            if str(d.get("storeID")) == "1" and d.get("retailPrice"):
                                retail_price = float(d["retailPrice"])
                                break
                        if not retail_price and deals and deals[0].get("retailPrice"):
                            retail_price = float(deals[0]["retailPrice"])

                        if cheapest.get("price"):
                            return _procesar_y_guardar(
                                float(cheapest["price"]),
                                int(cheapest.get("date", 0)),
                                retail_price
                            )
        except Exception:
            pass
        return None

    def obtener_biblioteca_detalle(self, steam_id_input, api_key=""):
        """
        Descarga la biblioteca de juegos de un usuario de Steam con nombre y horas jugadas.
        Usa la API oficial IPlayerService/GetOwnedGames si hay api_key, o el XML público como respaldo.
        Retorna (steam_id_resuelto, lista_dicts_juegos).
        """
        steam_id = resolver_steam_id(steam_id_input)
        if not steam_id:
            return None, []

        juegos = []
        if api_key:
            try:
                url = (
                    "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
                    f"?key={api_key}&steamid={steam_id}&include_appinfo=1&include_played_free_games=1&format=json"
                )
                r = self.session.get(url, timeout=8)
                if r.status_code == 200:
                    games_raw = r.json().get("response", {}).get("games", [])
                    for g in games_raw:
                        aid = str(g.get("appid", ""))
                        if not aid:
                            continue
                        mins = int(g.get("playtime_forever", 0))
                        juegos.append({
                            "appid": aid,
                            "titulo": g.get("name") or f"App {aid}",
                            "horas": round(mins / 60.0, 1),
                            "minutos": mins,
                            "thumb_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_sm_120.jpg"
                        })
            except Exception:
                pass

        if not juegos:
            try:
                url_xml = f"https://steamcommunity.com/profiles/{steam_id}/games?tab=all&xml=1"
                r_xml = self.session.get(url_xml, timeout=8)
                if r_xml.status_code == 200 and r_xml.text.lstrip().startswith("<?xml"):
                    root = ET.fromstring(r_xml.content)
                    for game_elem in root.findall(".//game"):
                        aid_el = game_elem.find("appID")
                        name_el = game_elem.find("name")
                        hrs_el = game_elem.find("hoursOnRecord")
                        if aid_el is not None and aid_el.text:
                            aid = aid_el.text.strip()
                            nombre = name_el.text.strip() if (name_el is not None and name_el.text) else f"App {aid}"
                            hrs_txt = hrs_el.text.strip().replace(",", "") if (hrs_el is not None and hrs_el.text) else "0"
                            try:
                                hrs_val = float(hrs_txt)
                            except Exception:
                                hrs_val = 0.0
                            juegos.append({
                                "appid": aid,
                                "titulo": nombre,
                                "horas": round(hrs_val, 1),
                                "minutos": int(hrs_val * 60),
                                "thumb_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_sm_120.jpg"
                            })
            except Exception:
                pass

        # 3. Respaldo final: Perfil público XML (<mostPlayedGames>) cuando Steam pide login/API Key para el listado completo
        if not juegos:
            try:
                url_prof = f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
                r_prof = self.session.get(url_prof, timeout=8)
                if r_prof.status_code == 200 and r_prof.text.lstrip().startswith("<?xml"):
                    root_p = ET.fromstring(r_prof.content)
                    for mg in root_p.findall(".//mostPlayedGame"):
                        link_el = mg.find("gameLink")
                        name_el = mg.find("gameName")
                        hrs_el = mg.find("hoursOnRecord")
                        if link_el is not None and link_el.text:
                            m_aid = re.search(r"/app/(\d+)", link_el.text)
                            if m_aid:
                                aid = m_aid.group(1)
                                nombre = name_el.text.strip() if (name_el is not None and name_el.text) else f"App {aid}"
                                hrs_txt = hrs_el.text.strip().replace(",", "") if (hrs_el is not None and hrs_el.text) else "0"
                                try:
                                    hrs_val = float(hrs_txt)
                                except Exception:
                                    hrs_val = 0.0
                                juegos.append({
                                    "appid": aid,
                                    "titulo": nombre,
                                    "horas": round(hrs_val, 1),
                                    "minutos": int(hrs_val * 60),
                                    "thumb_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_sm_120.jpg"
                                })
            except Exception:
                pass

        juegos.sort(key=lambda x: x["horas"], reverse=True)
        return steam_id, juegos

    def descargar_ficha_completa_paralelo(self, appid, db_manager=None):
        """
        Descarga simultáneamente los recursos de la Ficha Técnica usando un pool de hilos
        (incluyendo comparativa de Precio Regional LATAM-USD vs US y capturas de pantalla).
        Retorna (data, poster_pil, review_summary, historico_global, proton_tier).
        """
        appid = str(appid)

        def _fetch_steam_details():
            try:
                r = self.session.get(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=ar&l=spanish", timeout=6)
                if r.status_code == 200:
                    raw = r.json().get(appid, {})
                    if raw.get("success"):
                        return raw.get("data", {})
            except Exception:
                pass
            return None

        def _fetch_us_price():
            try:
                r_us = self.session.get(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&filters=price_overview", timeout=4)
                if r_us.status_code == 200:
                    raw_us = r_us.json().get(appid, {})
                    if isinstance(raw_us, dict) and raw_us.get("success"):
                        po_us = raw_us.get("data", {}).get("price_overview", {})
                        if po_us:
                            return {
                                "normal_us": po_us.get("initial", 0) / 100.0,
                                "final_us": po_us.get("final", 0) / 100.0
                            }
            except Exception:
                pass
            return None

        def _fetch_reviews():
            try:
                r_rev = self.session.get(f"https://store.steampowered.com/appreviews/{appid}?json=1&language=all&purchase_type=all", timeout=4)
                if r_rev.status_code == 200:
                    q_sum = r_rev.json().get("query_summary", {})
                    desc_rev = q_sum.get("review_score_desc", "")
                    tot_rev = q_sum.get("total_reviews", 0)
                    traducciones = {
                        "Overwhelmingly Positive": "extremadamente positivas",
                        "Very Positive": "muy positivas",
                        "Positive": "positivas",
                        "Mostly Positive": "mayormente positivas",
                        "Mixed": "variadas",
                        "Mostly Negative": "mayormente negativas",
                        "Negative": "negativas"
                    }
                    desc_es = traducciones.get(desc_rev, desc_rev.lower())
                    if tot_rev > 0:
                        return (desc_es, f"({tot_rev:,} reseñas)".replace(",", "."))
            except Exception:
                pass
            return None

        def _fetch_cheapshark_atl():
            res_atl = self.obtener_historial_global_cheapshark(appid, db_manager=db_manager)
            if res_atl:
                return (res_atl["atl_price"], res_atl["atl_date_display"])
            return None

        def _fetch_protondb():
            try:
                r_pdb = self.session.get(f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json", timeout=4)
                if r_pdb.status_code == 200:
                    tier = r_pdb.json().get("tier")
                    if tier:
                        return tier.capitalize()
            except Exception:
                pass
            return None

        def _fetch_poster():
            urls_poster = [
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg",
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
            ]
            for u in urls_poster:
                try:
                    rp = self.session.get(u, timeout=4)
                    if rp.status_code == 200 and len(rp.content) > 800:
                        img_raw = Image.open(BytesIO(rp.content))
                        img_raw.load()
                        return ImageOps.fit(img_raw, (200, 300), Image.Resampling.LANCZOS)
                except Exception:
                    continue
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            f_data = ex.submit(_fetch_steam_details)
            f_us = ex.submit(_fetch_us_price)
            f_rev = ex.submit(_fetch_reviews)
            f_atl = ex.submit(_fetch_cheapshark_atl)
            f_pdb = ex.submit(_fetch_protondb)
            f_pos = ex.submit(_fetch_poster)

            data = f_data.result()
            us_price_info = f_us.result()
            review_summary = f_rev.result()
            historico_global = f_atl.result()
            proton_tier = f_pdb.result()
            poster_pil = f_pos.result()

        if isinstance(data, dict) and us_price_info:
            data["_us_price_info"] = us_price_info

        if poster_pil is None and isinstance(data, dict) and data.get("header_image"):
            try:
                rp = self.session.get(data["header_image"], timeout=4)
                if rp.status_code == 200 and len(rp.content) > 800:
                    img_raw = Image.open(BytesIO(rp.content))
                    img_raw.load()
                    poster_pil = ImageOps.fit(img_raw, (200, 300), Image.Resampling.LANCZOS)
            except Exception:
                pass

        return data, poster_pil, review_summary, historico_global, proton_tier
