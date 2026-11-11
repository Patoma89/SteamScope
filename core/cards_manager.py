"""
Módulo de Gestión y Valorización de Cromos de Steam para SteamScope 2.0 (SRP / Core Puro).
Analiza el inventario público de Steam del usuario, detecta cromos coleccionables
y calcula el saldo neto de billetera recuperable tras comisiones de mercado (15%).
"""

import time
from core.api_client import HTTP_SESSION

# Valve limita estrictamente el parámetro count a un máximo de 2000. Valores superiores causan HTTP 400.
COMMUNITY_INVENTORY_URL = "https://steamcommunity.com/inventory/{steamid}/753/6?l=spanish&count=2000"
COMMUNITY_BADGES_URL = "https://steamcommunity.com/profiles/{steamid}/badges/"
COMMUNITY_MARKET_URL = "https://steamcommunity.com/market/"

COMISION_STEAM_PCT = 0.15  # 15% de comisión del Mercado de la Comunidad de Steam
PRECIO_PROMEDIO_CROMO_USD = 0.06  # Estimación conservadora de mercado estándar

# Caché en memoria para evitar bloqueos por límite de peticiones (Rate Limit 429)
_CACHE_INVENTARIO = {}


def _asegurar_cookies_comunidad(session):
    """
    Obtiene cookies de sesión de Steam Community (sessionid, steamCountry)
    si aún no están presentes. Valve requiere una cookie de sesión válida
    para no activar el firewall de rate limit (HTTP 429).
    """
    if "sessionid" not in session.cookies:
        try:
            session.get("https://steamcommunity.com", timeout=6)
        except Exception:
            pass


def _es_cromo_coleccionable(desc: dict) -> bool:
    """Determina si un ítem de inventario es un cromo coleccionable vendible."""
    if not bool(desc.get("marketable", 0)):
        return False

    tipo = (desc.get("type") or "").lower()
    tags = desc.get("tags") or []

    if "cromo" in tipo or "trading card" in tipo or "carta" in tipo:
        return True

    for t in tags:
        cat = t.get("category", "")
        iname = (t.get("internal_name") or "").lower()
        lname = (t.get("localized_tag_name") or "").lower()
        if cat == "cardborder":
            return True
        if cat == "item_class" and ("cromo" in lname or "card" in iname):
            return True

    return False


def _extraer_info_juego(desc: dict):
    """Extrae el nombre del juego y el appid asociado a partir de los metadatos del cromo."""
    tags = desc.get("tags") or []
    game_name = "Juego Desconocido"
    appid = desc.get("market_fee_app") or desc.get("appid") or 0

    for t in tags:
        if t.get("category") == "Game":
            game_name = t.get("localized_tag_name") or t.get("name") or game_name
            internal = t.get("internal_name") or ""
            if internal.startswith("app_"):
                try:
                    appid = int(internal.replace("app_", ""))
                except Exception:
                    pass
            break

    return game_name, appid


def analizar_inventario_cromos(
    steamid_64: str,
    dolar_ref: float = 1000.0,
    forzar_refresco: bool = False,
    cache_ttl: int = 300
) -> dict:
    """
    Consulta el inventario de Steam del usuario y calcula el valor neto de sus cromos.
    Retorna un diccionario estructurado con métricas de billetera neta y desglose por juego.
    """
    global _CACHE_INVENTARIO

    sid_str = str(steamid_64).strip() if steamid_64 else ""
    if not sid_str or len(sid_str) < 16:
        return {
            "exito": False,
            "error": "Steam ID inválido o no configurado. Ingresá tu Steam ID de 17 dígitos en Ajustes.",
            "total_cromos": 0,
            "total_juegos": 0,
            "valor_bruto_usd": 0.0,
            "valor_neto_usd": 0.0,
            "valor_neto_ars": 0,
            "juegos": []
        }

    ahora = time.time()
    if not forzar_refresco and sid_str in _CACHE_INVENTARIO:
        cache_entry = _CACHE_INVENTARIO[sid_str]
        if (ahora - cache_entry["timestamp"]) < cache_ttl:
            return cache_entry["datos"]

    url = COMMUNITY_INVENTORY_URL.format(steamid=sid_str)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://steamcommunity.com/profiles/{sid_str}/inventory/",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
    }

    try:
        # Asegurar cookies de sesión previas
        _asegurar_cookies_comunidad(HTTP_SESSION)

        r = HTTP_SESSION.get(url, headers=headers, timeout=12)

        if r.status_code == 403:
            return {
                "exito": False,
                "error": "El inventario de este perfil es Privado. Cambialo a 'Público' en los ajustes de privacidad de Steam para valorizar tus cromos.",
                "total_cromos": 0,
                "total_juegos": 0,
                "valor_bruto_usd": 0.0,
                "valor_neto_usd": 0.0,
                "valor_neto_ars": 0,
                "juegos": []
            }

        if r.status_code == 429:
            return {
                "exito": False,
                "error": "Steam Community aplicó un límite temporal de peticiones (Rate Limit). Esperá unos segundos antes de reintentar.",
                "total_cromos": 0,
                "total_juegos": 0,
                "valor_bruto_usd": 0.0,
                "valor_neto_usd": 0.0,
                "valor_neto_ars": 0,
                "juegos": []
            }

        if r.status_code != 200:
            return {
                "exito": False,
                "error": f"Steam Community devolvió error HTTP {r.status_code}.",
                "total_cromos": 0,
                "total_juegos": 0,
                "valor_bruto_usd": 0.0,
                "valor_neto_usd": 0.0,
                "valor_neto_ars": 0,
                "juegos": []
            }

        data = r.json()
        descriptions = data.get("descriptions", [])
        assets = data.get("assets", [])

        if not descriptions:
            res_vacio = {
                "exito": True,
                "error": None,
                "total_cromos": 0,
                "total_juegos": 0,
                "valor_bruto_usd": 0.0,
                "valor_neto_usd": 0.0,
                "valor_neto_ars": 0,
                "url_insignias": COMMUNITY_BADGES_URL.format(steamid=sid_str),
                "url_mercado": COMMUNITY_MARKET_URL,
                "juegos": []
            }
            _CACHE_INVENTARIO[sid_str] = {"timestamp": ahora, "datos": res_vacio}
            return res_vacio

        # 1. Mapear descripciones por clave (classid, instanceid)
        desc_map = {}
        for desc in descriptions:
            key = (str(desc.get("classid")), str(desc.get("instanceid", "0")))
            desc_map[key] = desc

        cromos_por_juego = {}
        total_cromos = 0

        # 2. Contabilizar instancias reales mediante assets (incluyendo duplicados)
        if assets:
            for ast in assets:
                key = (str(ast.get("classid")), str(ast.get("instanceid", "0")))
                desc = desc_map.get(key)
                if not desc or not _es_cromo_coleccionable(desc):
                    continue

                game_name, appid = _extraer_info_juego(desc)
                if game_name not in cromos_por_juego:
                    cromos_por_juego[game_name] = {
                        "game_name": game_name,
                        "appid": appid,
                        "cantidad": 0,
                        "icon_url": desc.get("icon_url", "")
                    }
                cromos_por_juego[game_name]["cantidad"] += 1
                total_cromos += 1
        else:
            # Fallback en caso de que la respuesta no liste assets individuales
            for desc in descriptions:
                if not _es_cromo_coleccionable(desc):
                    continue

                game_name, appid = _extraer_info_juego(desc)
                if game_name not in cromos_por_juego:
                    cromos_por_juego[game_name] = {
                        "game_name": game_name,
                        "appid": appid,
                        "cantidad": 0,
                        "icon_url": desc.get("icon_url", "")
                    }
                cromos_por_juego[game_name]["cantidad"] += 1
                total_cromos += 1

        valor_bruto_usd = round(total_cromos * PRECIO_PROMEDIO_CROMO_USD, 2)
        # Saldo que efectivamente ingresa a la cartera de Steam tras la comisión del 15%
        valor_neto_usd = round(valor_bruto_usd * (1.0 - COMISION_STEAM_PCT), 2)
        valor_neto_ars = round(valor_neto_usd * float(dolar_ref))

        lista_juegos = list(cromos_por_juego.values())
        lista_juegos.sort(key=lambda x: x["cantidad"], reverse=True)

        resultado = {
            "exito": True,
            "error": None,
            "total_cromos": total_cromos,
            "total_juegos": len(lista_juegos),
            "valor_bruto_usd": valor_bruto_usd,
            "valor_neto_usd": valor_neto_usd,
            "valor_neto_ars": valor_neto_ars,
            "url_insignias": COMMUNITY_BADGES_URL.format(steamid=sid_str),
            "url_mercado": COMMUNITY_MARKET_URL,
            "juegos": lista_juegos
        }

        _CACHE_INVENTARIO[sid_str] = {"timestamp": ahora, "datos": resultado}
        return resultado

    except Exception as e:
        return {
            "exito": False,
            "error": f"Error al analizar cromos: {str(e)}",
            "total_cromos": 0,
            "total_juegos": 0,
            "valor_bruto_usd": 0.0,
            "valor_neto_usd": 0.0,
            "valor_neto_ars": 0,
            "juegos": []
        }
