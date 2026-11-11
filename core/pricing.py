import re
import html
from datetime import datetime, timezone
from plyer import notification
from core.config import APP_NAME, STEAM_CALENDAR

# ================= CATÁLOGOS DECLARATIVOS DE SUSCRIPCIÓN (OCP) =================
GAMEPASS_KEYWORDS = [
    "halo", "gears", "forza", "sea of thieves", "grounded", "pentiment", "starfield",
    "hi-fi rush", "age of empires", "age of mythology", "flight simulator", "minecraft",
    "state of decay", "psychonauts", "hellblade", "ori and the", "fable", "doom",
    "wolfenstein", "dishonored", "prey", "fallout", "elder scrolls", "skyrim", "oblivion",
    "deathloop", "ghostwire", "evil within", "rage 2", "quake", "diablo", "call of duty",
    "overwatch", "crash bandicoot", "spyro", "starcraft", "persona 3", "lies of p",
    "palworld", "no man's sky", "among us", "hollow knight", "dead cells", "slay the spire",
    "valheim", "deep rock galactic", "payday 3", "remnant", "stalker 2", "s.t.a.l.k.e.r.",
    "frostpunk", "cities: skylines", "crusader kings", "stellaris", "hearts of iron",
    "total war", "football manager", "yakuza", "like a dragon", "monster hunter rise",
    "resident evil 2", "resident evil 3", "control", "atomic heart", "plague tale",
    "chained echoes", "vampire survivors", "broforce", "celeste"
]

EAPLAY_KEYWORDS = [
    "battlefield", "need for speed", "mass effect", "dragon age", "dead space",
    "star wars jedi", "star wars battlefront", "star wars squadrons", "titanfall",
    "apex legends", "it takes two", "a way out", "unravel", "mirror's edge", "sims 4",
    "simcity", "plants vs. zombies", "burnout", "crysis", "alice: madness", "fe",
    "sea of solitude", "lost in random", "wild hearts", "immortals of aveum", "f1 23",
    "f1 24", "ea sports fc", "fifa", "madden", "pga tour", "super mega baseball",
    "grid legends", "dirt 5"
]

UBISOFT_KEYWORDS = [
    "assassin's creed", "far cry", "watch dogs", "tom clancy", "rainbow six",
    "ghost recon", "the division", "splinter cell", "anno 1800", "anno ", "for honor",
    "the crew", "riders republic", "immortals fenyx", "prince of persia", "rayman",
    "south park: the", "trials rising", "skull and bones"
]

# Estructura abierta a extensión (Open/Closed Principle):
# Para agregar una nueva suscripción (ej. Humble Choice), basta con añadir un ítem a esta lista.
SUBSCRIPTION_CATALOGS = [
    {
        "label": "EA PLAY + GAME PASS",
        "color": "#ff4747",
        "publishers": ("electronic arts",),
        "keywords": EAPLAY_KEYWORDS,
    },
    {
        "label": "UBISOFT+",
        "color": "#0070ff",
        "publishers": ("ubisoft",),
        "keywords": UBISOFT_KEYWORDS,
    },
    {
        "label": "PC GAME PASS",
        "color": "#107c10",
        "publishers": ("xbox game studios", "bethesda"),
        "keywords": GAMEPASS_KEYWORDS,
    },
]

# Criterios de ordenamiento desacoplados (Open/Closed Principle)
SORT_STRATEGIES = {
    "Mayor Descuento": (lambda x: x.get("descuento", 0), True),
    "Menor Descuento": (lambda x: x.get("descuento", 0), False),
    "Precio: Menor a Mayor": (lambda x: x.get("precio_oferta_usd", 0.0), False),
    "Precio: Mayor a Menor": (lambda x: x.get("precio_oferta_usd", 0.0), True),
    "Mejor Puntuación": (
        lambda x: float(x.get("rating", 0)) if str(x.get("rating", "0")).replace(".", "", 1).isdigit() else 0.0,
        True,
    ),
    "Alfabético": (lambda x: (x.get("titulo") or "").lower(), False),
}


def notificar_windows(titulo, mensaje):
    try:
        notification.notify(title=titulo, message=mensaje, app_name=APP_NAME, timeout=6)
    except Exception as e:
        print(f"Error notificación: {e}")


def es_minimo_historico_real(precio_actual: float, min_historico_registrado: float, tolerancia: float = 0.02) -> bool:
    """
    Evalúa si el precio actual iguala o supera el récord histórico anterior.
    Tolerancia de 2 centavos para variaciones de redondeo cambiario.
    """
    if precio_actual <= 0:
        return False
    if min_historico_registrado is None or min_historico_registrado <= 0:
        return True
    return precio_actual <= (min_historico_registrado + tolerancia)


def notificar_minimo_historico(titulo: str, precio_usd: float, descuento: int = 0, appid=None):
    """
    Emite una alerta interactiva de Windows cuando un juego alcanza su Mínimo Histórico (ATL).
    """
    tit_notif = f"⭐ ¡MÍNIMO HISTÓRICO EN STEAMSCOPE!"
    desc_txt = f" (-{descuento}%)" if descuento > 0 else ""
    msg = f"¡{titulo} está en su precio más bajo registrado!\nPrecio récord: ${precio_usd:.2f} USD{desc_txt}."
    notificar_windows(tit_notif, msg)


def limpiar_html(texto_html):
    if not texto_html:
        return "No especificado."
    texto = re.sub(r'<br\s*/?>', '\n', texto_html, flags=re.IGNORECASE)
    texto = re.sub(r'<li\s*>', '  • ', texto, flags=re.IGNORECASE)
    texto = re.sub(r'</li>', '\n', texto, flags=re.IGNORECASE)
    texto = re.sub(r'<[^>]+>', '', texto)
    texto = html.unescape(texto)
    lineas = [line.strip() for line in texto.splitlines() if line.strip()]
    return "\n".join(lineas)


def extraer_espacio_disco(texto_requisitos):
    """Detecta 'XX GB' o 'XX MB' disponibles en la cadena de requisitos de PC."""
    if not texto_requisitos:
        return "N/D"
    match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB)\b', texto_requisitos, re.IGNORECASE)
    if match:
        valor, unidad = match.groups()
        return f"{valor} {unidad.upper()}"
    return "N/D"


def calcular_tiempo_restante(timestamp_fin):
    """Calcula horas o días restantes antes de que termine la rebaja."""
    if not timestamp_fin or timestamp_fin <= 0:
        return None
    try:
        now = datetime.now(timezone.utc).timestamp()
        diff = int(timestamp_fin - now)
        if diff <= 0:
            return "Termina pronto"
        horas = diff // 3600
        if horas < 24:
            return f"Termina en {horas}h"
        dias = horas // 24
        return f"Termina en {dias}d"
    except Exception:
        return None


def _parse_version_tuple(v_str):
    limpio = re.sub(r'[^0-9.]', '', str(v_str))
    partes = [int(x) for x in limpio.split('.') if x.isdigit()]
    return tuple(partes) if partes else (0, 0, 0)


def detectar_suscripcion(titulo, publisher=""):
    """Evalúa de forma declarativa si un título pertenece a algún catálogo de suscripción (OCP)."""
    t_low = (titulo or "").lower()
    p_low = (publisher or "").lower()

    def _coincidencia_exacta(lista_keywords, texto):
        for k in lista_keywords:
            if re.search(rf"\b{re.escape(k)}\b", texto):
                return True
        return False

    for cat in SUBSCRIPTION_CATALOGS:
        if any(pub in p_low for pub in cat["publishers"]) or _coincidencia_exacta(cat["keywords"], t_low):
            return (cat["label"], cat["color"])
    return None


def evaluar_termometro_compra(descuento, es_atl, precio_usd):
    if precio_usd == 0 and descuento < 100:
        return ("⏳ PRÓXIMAMENTE / SIN PRECIO", "#8b929a", "El juego aún no salió a la venta o no tiene precio en Steam.")
    now = datetime.now(timezone.utc)
    prox_evento = None
    dias_para_evento = 999
    for ev in STEAM_CALENDAR:
        start = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
        if start > now:
            d = (start - now).days
            if d < dias_para_evento:
                dias_para_evento = d
                prox_evento = ev["name"]
    if descuento == 100:
        return ("🔥 ¡GRATIS! RECLAMAR YA", "#00e676", "Promoción 100% OFF temporal.")
    if es_atl and descuento >= 50:
        return ("🟢 COMPRÁ YA (Récord)", "#00e676", "Está en su precio más bajo registrado y con gran descuento.")
    if descuento >= 75:
        return ("🟢 EXCELENTE OFERTA", "#00e676", f"Descuento agresivo del {descuento}%. Muy difícil que baje más.")
    if es_atl and descuento >= 20:
        return ("🟢 BUEN MOMENTO", "#4af626", "Es su mínimo histórico hasta la fecha.")
    if dias_para_evento <= 25 and descuento < 50:
        return (f"🟡 ESPERAR ({dias_para_evento}d)", "#ffab00", f"Faltan {dias_para_evento} días para {prox_evento}. Suele bajar más.")
    if 30 <= descuento < 75:
        return ("🟡 OFERTA ACEPTABLE", "#ffab00", "Buen descuento, aunque no es récord histórico.")
    return ("🔴 NO CONVIENE HOY", "#ff5252", "Precio base o descuento bajo. Guardalo en Watchlist.")


def ordenar_ofertas(deals_list, criterio_nombre):
    """Ordena una lista de ofertas utilizando el diccionario de estrategias SORT_STRATEGIES (OCP)."""
    strategy = SORT_STRATEGIES.get(criterio_nombre)
    if strategy:
        key_fn, reverse_flag = strategy
        deals_list.sort(key=key_fn, reverse=reverse_flag)
    return deals_list


def formatear_oferta_para_compartir(item, dolar_ref=1000.0, impuestos_pct=60.0) -> str:
    """Genera un bloque de texto formateado con emojis listo para compartir en WhatsApp o Discord."""
    titulo = item.get("titulo", "Juego")
    appid = item.get("appid", "")
    desc = int(item.get("descuento", 0))
    p_usd = float(item.get("precio_oferta_usd", 0.0))
    p_ars = round(p_usd * float(dolar_ref) * (1.0 + float(impuestos_pct) / 100.0))
    rating = item.get("rating", "N/A")
    es_atl = bool(item.get("es_atl", False))
    tiene_cromos = bool(item.get("tiene_cromos", False))

    atl_badge = " ⭐ ¡RÉCORD HISTÓRICO (ATL)!" if es_atl else ""
    desc_txt = f" (-{desc}% OFF)" if desc > 0 else ""
    cromos_txt = " | 🃏 Con Cromos" if tiene_cromos else ""

    return (
        f"🎮 *{titulo}*{desc_txt}{atl_badge}\n"
        f"💵 *${p_usd:.2f} USD* (~${p_ars:,.0f} ARS con tarjeta)\n"
        f"⭐ {rating}% Reseñas Positivas{cromos_txt}\n"
        f"🔗 https://store.steampowered.com/app/{appid}"
    )


def es_steam_deck_verificado(genres_list: str) -> bool:
    """Verifica si la lista de tags/géneros contiene indicación de Steam Deck verificado o jugable."""
    if not genres_list:
        return False
    g_low = genres_list.lower()
    return any(k in g_low for k in ["steam deck", "deck verified", "great on deck", "verificado"])
