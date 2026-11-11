"""
Módulo de Integración Multi-Tienda para SteamScope 2.0 (SRP / Core Puro).
Gestiona la extracción y normalización de promociones y juegos gratuitos
de tiendas externas como Epic Games Store y GOG sin dependencias de UI.
"""

import time
from datetime import datetime, timezone
from core.api_client import HTTP_SESSION

EPIC_FREE_GAMES_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=es-ES&country=AR"
)

# Caché en memoria para evitar saturar las APIs
_CACHE_EPIC = {
    "timestamp": 0.0,
    "datos": []
}


def obtener_promociones_epic(forzar_refresco=False, cache_ttl=1800) -> list:
    """
    Obtiene la lista de juegos gratuitos actuales y próximos de Epic Games Store.
    Retorna una lista de diccionarios con metadatos normalizados.
    """
    global _CACHE_EPIC
    ahora = time.time()
    if not forzar_refresco and (ahora - _CACHE_EPIC["timestamp"]) < cache_ttl and _CACHE_EPIC["datos"]:
        return _CACHE_EPIC["datos"]

    try:
        r = HTTP_SESSION.get(EPIC_FREE_GAMES_URL, timeout=8)
        if r.status_code != 200:
            return _CACHE_EPIC["datos"]

        data = r.json()
        elementos = (
            data.get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
        )
        
        juegos_procesados = []
        now_dt = datetime.now(timezone.utc)

        for el in elementos:
            promotions = el.get("promotions") or {}
            promo_offers = promotions.get("promotionalOffers", [])
            upcoming_offers = promotions.get("upcomingPromotionalOffers", [])
            
            es_activo = False
            es_proximo = False
            fecha_fin_str = None
            fecha_inicio_str = None

            # 1. Comprobar ofertas activas (100% gratis hoy)
            if promo_offers:
                for po in promo_offers:
                    offers = po.get("promotionalOffers", [])
                    for o in offers:
                        discount = o.get("discountSetting", {})
                        if discount.get("discountPercentage", 100) == 0:
                            start_str = o.get("startDate", "")
                            end_str = o.get("endDate", "")
                            try:
                                s_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                                e_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                                if s_dt <= now_dt <= e_dt:
                                    es_activo = True
                                    fecha_fin_str = e_dt.strftime("%d/%m/%Y %H:%M")
                                    break
                            except Exception:
                                pass
                    if es_activo:
                        break

            # 2. Comprobar próximas promociones (semana que viene)
            if not es_activo and upcoming_offers:
                for uo in upcoming_offers:
                    offers = uo.get("promotionalOffers", [])
                    for o in offers:
                        discount = o.get("discountSetting", {})
                        if discount.get("discountPercentage", 100) == 0:
                            start_str = o.get("startDate", "")
                            end_str = o.get("endDate", "")
                            try:
                                s_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                                e_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                                if s_dt > now_dt:
                                    es_proximo = True
                                    fecha_inicio_str = s_dt.strftime("%d/%m/%Y %H:%M")
                                    fecha_fin_str = e_dt.strftime("%d/%m/%Y %H:%M")
                                    break
                            except Exception:
                                pass
                    if es_proximo:
                        break

            if not es_activo and not es_proximo:
                continue

            # Extraer mejor imagen de portada
            img_url = ""
            key_images = el.get("keyImages", [])
            for k in ("DieselStoreFrontWide", "OfferImageWide", "Thumbnail", "VaultClosed"):
                for ki in key_images:
                    if ki.get("type") == k and ki.get("url"):
                        img_url = ki.get("url")
                        break
                if img_url:
                    break
            if not img_url and key_images:
                img_url = key_images[0].get("url", "")

            # Construir URL directa de la tienda
            slug = el.get("productSlug") or el.get("urlSlug")
            if not slug and el.get("offerMappings"):
                slug = el["offerMappings"][0].get("pageSlug")
            store_url = f"https://store.epicgames.com/es-ES/p/{slug}" if slug else "https://store.epicgames.com/es-ES/free-games"

            # Precios de referencia
            price_info = el.get("price", {}).get("totalPrice", {})
            orig_price_cents = price_info.get("originalPrice", 0)
            orig_price_usd = orig_price_cents / 100.0 if orig_price_cents else 0.0

            juegos_procesados.append({
                "tienda": "Epic Games",
                "titulo": el.get("title", "Juego Gratuito"),
                "descripcion": el.get("description", "Sin descripción disponible."),
                "imagen_url": img_url,
                "url_tienda": store_url,
                "precio_original_usd": orig_price_usd,
                "es_activo": es_activo,
                "es_proximo": es_proximo,
                "fecha_inicio": fecha_inicio_str,
                "fecha_fin": fecha_fin_str,
                "estado_texto": "🔥 ¡DISPONIBLE AHORA (100% OFF)!" if es_activo else f"⏳ Próximamente (desde {fecha_inicio_str})"
            })

        # Ordenar: primero los activos, luego los próximos
        juegos_procesados.sort(key=lambda x: (not x["es_activo"], x["titulo"]))
        _CACHE_EPIC["timestamp"] = ahora
        _CACHE_EPIC["datos"] = juegos_procesados
        return juegos_procesados
    except Exception:
        return _CACHE_EPIC["datos"]
