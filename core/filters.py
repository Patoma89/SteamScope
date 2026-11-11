"""
Módulo de Filtrado y Búsqueda en Memoria para SteamScope (SRP / Clean Architecture).
Proporciona operaciones puras de alta velocidad (sin I/O ni llamadas bloqueantes)
para filtrado reactivo a 60 FPS sobre colecciones de juegos y ofertas.
"""

import unicodedata
import re
from core.config import CATEGORIAS_STEAM


def normalizar_texto(texto: str) -> str:
    """
    Normaliza un texto para búsqueda difusa: minúsculas, sin tildes ni caracteres especiales.
    Ejemplo: "¡Pokémon: Let's Go!" -> 'pokemon lets go'
    """
    if not texto:
        return ""
    # Quitar tildes y diacríticos
    nfkd = unicodedata.normalize('NFKD', str(texto))
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Quitar apóstrofes para que Assassin's -> assassins, Let's -> lets
    sin_apostrofes = sin_tildes.replace("'", "").replace("’", "").replace("`", "")
    # Minúsculas y reemplazar símbolos no alfanuméricos por espacios
    limpio = re.sub(r'[^a-zA-Z0-9\s]', ' ', sin_apostrofes.lower())
    return " ".join(limpio.split())


def obtener_subcategorias_para(categoria_padre: str) -> list:
    """
    Retorna la lista ordenada de subcategorías disponibles para una categoría padre.
    """
    if not categoria_padre or categoria_padre not in CATEGORIAS_STEAM:
        return ["Todas las subcategorías"]
    return list(CATEGORIAS_STEAM[categoria_padre].keys())


def coincide_categoria_steam(tags_texto: str, categoria_padre: str, subcategoria: str = "") -> bool:
    """
    Evalúa si la cadena de tags del juego coincide con la categoría o subcategoría seleccionada.
    tags_texto: string de tags separados por coma o espacios (provenientes de genres_list / SteamSpy).
    """
    if not categoria_padre or categoria_padre in ("Todas las Categorías", "Todas", ""):
        return True

    cat_dict = CATEGORIAS_STEAM.get(categoria_padre)
    if not cat_dict:
        return True

    tags_norm = normalizar_texto(tags_texto)

    # Si hay una subcategoría específica
    if subcategoria and subcategoria not in ("Todas las subcategorías", "Todas", ""):
        keywords = cat_dict.get(subcategoria, [])
        if not keywords:
            return True
        return any(normalizar_texto(kw) in tags_norm for kw in keywords)

    # Si es "Todas las subcategorías", recopila todos los keywords del género padre
    todos_keywords = set()
    for kw_list in cat_dict.values():
        for kw in kw_list:
            todos_keywords.add(kw)

    if not todos_keywords:
        return True

    return any(normalizar_texto(kw) in tags_norm for kw in todos_keywords)


def coincide_busqueda_texto(query: str, titulo: str, tags_texto: str = "") -> bool:
    """
    Evalúa si todos los términos del query aparecen en el título o en los tags del juego.
    """
    q_norm = normalizar_texto(query)
    if not q_norm:
        return True

    titulo_norm = normalizar_texto(titulo)
    tags_norm = normalizar_texto(tags_texto)
    contenido_total = f"{titulo_norm} {tags_norm}"

    terminos = q_norm.split()
    return all(termino in contenido_total for termino in terminos)


def filtrar_ofertas_en_memoria(
    ofertas: list,
    texto_busqueda: str = "",
    categoria_padre: str = "Todas las Categorías",
    subcategoria: str = "Todas las subcategorías",
    min_desc: int = 1,
    max_desc: int = 100,
    p_min: float = 0.0,
    p_max: float = 999.0,
    min_rating: float = 0.0,
    solo_atl: bool = False,
    solo_cromos: bool = False,
    modalidad: str = ""
) -> list:
    """
    Filtra una lista de ofertas en memoria en microsegundos sin llamadas de red ni bloqueos.
    Retorna una nueva lista con los elementos que superan todos los criterios activos.
    """
    if not ofertas:
        return []

    resultado = []
    q_activo = bool(texto_busqueda and texto_busqueda.strip())
    cat_activa = bool(categoria_padre and categoria_padre not in ("Todas las Categorías", "Todas", ""))
    mod_activa = bool(modalidad and modalidad.strip())

    for item in ofertas:
        # 1. Filtro de Récord Histórico (ATL)
        if solo_atl and not item.get("es_atl", False):
            continue

        # 2. Filtro de Cromos
        if solo_cromos and not item.get("tiene_cromos", False):
            continue

        # 3. Filtro de Descuento
        desc = int(item.get("descuento", 0) or 0)
        if desc < min_desc or desc > max_desc:
            continue

        # 4. Filtro de Precio
        precio = float(item.get("precio_oferta_usd", 0.0) or 0.0)
        if precio < p_min or precio > p_max:
            continue

        # 5. Filtro de Calidad / Reseñas
        if min_rating > 0:
            rating_raw = str(item.get("rating", "0")).replace("%", "").strip()
            try:
                r_val = float(rating_raw)
            except ValueError:
                r_val = 0.0
            if r_val < min_rating:
                continue

        # 6. Filtro de Modalidad (Single-player, Co-op, etc.)
        if mod_activa:
            mod_item = str(item.get("modalidad", "")).lower()
            if modalidad.lower() not in mod_item:
                continue

        # 7. Filtro de Búsqueda de Texto (Título y Tags)
        tags_item = str(item.get("genero", "") or "")
        if q_activo:
            titulo = str(item.get("titulo", "") or "")
            if not coincide_busqueda_texto(texto_busqueda, titulo, tags_item):
                continue

        # 8. Filtro de Categoría / Subcategoría de Steam
        if cat_activa:
            if not coincide_categoria_steam(tags_item, categoria_padre, subcategoria):
                continue

        resultado.append(item)

    return resultado
