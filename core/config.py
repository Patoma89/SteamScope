import os
import sys
import json
import shutil
import threading
import winsound

# ================= CONSTANTES Y CONFIGURACIÓN =================
APP_VERSION = "2.0.1"
APP_NAME = "SteamScope"

UPDATE_JSON_URL = "https://raw.githubusercontent.com/Patoma89/SteamScope/main/version.json"
GITHUB_API_RELEASES = "https://api.github.com/repos/Patoma89/SteamScope/releases/latest"
FALLBACK_RELEASES_WEB = "https://github.com/Patoma89/SteamScope/releases"

PATCH_NOTES = [
    {
        "version": "v2.0.1",
        "fecha": "Noviembre 2026",
        "cambios": [
            "🩹 Corrección en Ficha Técnica: Solucionado el fallo que impedía guardar o editar notas personales privadas.",
            "📐 Diseño y Botonera Blindada: Barra inferior ensanchada para asegurar que el botón 'Compartir' no se corte y 'Cerrar' quede visible.",
            "🌐 Descuento dinámico en botón Web: Detección en vivo de ofertas evitando porcentajes estáticos incorrectos.",
            "🔄 Sincronización instantánea: Refresco automático e inmediato de la Watchlist al actualizar apuntes de juegos."
        ]
    },
    {
        "version": "v2.0.0",
        "fecha": "Noviembre 2026",
        "cambios": [
            "👑 LA GRAN ACTUALIZACIÓN 2.0: La mayor evolución en la historia de SteamScope con 4 nuevos pilares y decenas de mejoras.",
            "🌐 Radar Multi-Tienda (Epic Games & GOG): Nuevo monitor de juegos gratis semanales de Epic Games Store y catálogo sin DRM con reclamo directo.",
            "🃏 Gestor de Cromos & Billetera Steam: Valorizador inteligente de inventario para fondear compras vendiendo cartas acumuladas (-15% fee de mercado).",
            "🎮 Modo Consola & Steam Deck (XInput Gamepad): Navegación 100% nativa con joystick de Xbox, PlayStation o Deck en interfaz adaptativa 10ft.",
            "🔔 Notificaciones Enriquecidas de Windows 11: Alertas push con carátula en alta definición, precio en USD/ARS y acceso directo web.",
            "🎰 Ruleta Loot Box 'Spin-In-Place': Experiencia inmersiva de sorteo continuo sin cerrar la ventana, con animaciones fluidas a 60 FPS.",
            "🖼️ Visor Interactivo de Capturas HD: Pantalla completa (F11/doble clic), navegación por flechas (← / →), pre-carga en RAM y zoom dinámico.",
            "⏳ Insignias de Alerta Temprana: Avisos visuales de ofertas que finalizan en menos de 48 hs y juegos 100% gratuitos por tiempo limitado.",
            "🎁 Píldoras de 1 Clic: Acceso directo en barra de KPIs para aislar juegos '100% Gratis' y 'Récords ATL' instantáneamente.",
            "💰 Medidor de Ahorro en Changuito: Reporte en vivo del dinero total ahorrado en USD y ARS (% global OFF acumulado).",
            "💬 Compartir Ofertas con Amigos: Generación automática de fichas limpias con enlace a la web para compartir por WhatsApp, Telegram y Discord.",
            "🌐 Acceso Directo Steam Web (-21% Impuestos): Botón dedicado para abrir la tienda en el navegador y evitar percepciones impositivas.",
            "⚡ Command Palette Global (Ctrl+K): Buscador universal flotante para saltar a cualquier juego de inmediato.",
            "🔧 Auto-Actualizador Resiliente: Eliminado el error de DLL al reiniciar tras actualizar desde GitHub mediante sanitización de entorno PyInstaller.",
            "📊 Exportador a CSV / Excel: Descarga tu biblioteca o watchlist en planillas limpias compatibles con Excel (utf-8-sig)."
        ]
    },
    {
        "version": "v1.9.0",
        "fecha": "Noviembre 2026",
        "cambios": [
            "🏷️ Explorador de Categorías & Subgéneros de Steam: Nuevo filtrado jerárquico de 2 niveles. Elegí categorías principales y profundizá en Shooters (FPS, TPS, Looter, Táctico, Boomer), RPG (Souls-like, ARPG, CRPG), Estrategia, y más.",
            "⭐ Cazador de Mínimos Históricos (ATL Watchdog): Insignia dorada interactiva para ofertas que rompen el récord histórico de todos los tiempos y filtro de 1 clic para ver únicamente récords.",
            "🔔 Centinela Silencioso en Bandeja & Centro de Récords: Al minimizar SteamScope, el vigilante periódico comprueba tu Wishlist y guarda el historial completo de mínimos cazados (Ctrl+H).",
            "🎯 Medidor de Presupuesto en el Changuito (Budget Tracker): Fijá un tope de gasto en USD y visualizá en tiempo real tu consumo con barra de progreso y alerta de límite.",
            "⚡ Atajos de Teclado Power-User: Navegá a 60 FPS con Ctrl+F (Buscador), Esc (Limpiar), F5 (Refrescar), Ctrl+1/2/3 (Pestañas), Ctrl+D (Dashboard), Ctrl+H (Historial ATL) y Ctrl+B (Changuito).",
            "📋 Copiar Ficha de Oferta en 1 Clic: Botón rápido para copiar un resumen estilizado con emojis y precios (USD y ARS) listo para pegar en WhatsApp o Discord.",
            "🟢 Badge Steam Deck Ready: Detección automática en las tarjetas para juegos verificados y jugables en la portátil de Valve.",
            "🎨 Tipografía y Contraste Blindados: Corrección integral de legibilidad en todas las skins, eliminando textos negros sobre fondos oscuros.",
            "⚡ Motor de Búsqueda Ultra-Rápido (<0.5s): Integración directa con storesearch de Steam con resultados exactos y relevantes sin bloqueos ni retrasos."
        ]
    },
    {
        "version": "v1.8.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "🎨 Interfaz y Diálogos 100% Skin-Aware (Cero Popups Nativos): Reemplazo completo de cuadros grises de Windows por modales oscuros dinámicos adaptados a cada skin (Modo Drácula, Neón P89, Steam Deck OLED, etc.) con alto contraste.",
            "⚡ Biblioteca Instantánea (0ms con Caché SQLite + Paginación): Tu biblioteca de Steam ahora se guarda en SQLite local y se pagina de a 30 juegos, abriendo al instante sin tirones ni esperas.",
            "💰 Valuador de Cuenta & Costo por Hora: Calculá en 1 clic cuánto vale tu biblioteca de Steam en USD y ARS, cuánto dinero tenés sin estrenar (0 hs) y tu ratio $/hora jugada.",
            "📊 Nuevo Dashboard Visual de Estadísticas: Ventana interactiva con 4 gráficos en vivo (Distribución de Descuentos, Top Géneros, Estado de tu Backlog y Top Juegos Más Jugados).",
            "⚔️ Comparador Cara a Cara (Versus): Seleccioná dos juegos para compararlos lado a lado (Precio USD/ARS, Descuento, Mínimo Histórico, Metacritic, Peso en Disco y ProtonDB) con medalla al ganador.",
            "🔍 Filtro Instantáneo en Vivo y Ordenamiento de Biblioteca: Filtrá por texto en tiempo real tanto en Ofertas como en Mi Biblioteca sin re-escanear.",
            "🔑 Asistente y Sincronización Web de Steam API Key: Acceso directo y verificación de clave para importar bibliotecas de +600 juegos al instante."
        ]
    },
    {
        "version": "v1.7.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "🌎 Comparador Regional LATAM-USD vs EE.UU.: Detecta en la Ficha Técnica si el juego tiene Precio Regional cuidado en Argentina o si cobra lo mismo que en EE.UU.",
            "🎮 Nueva Pestaña 'Mi Biblioteca & Backlog': Analiza tus juegos comprados, cuántos nunca abriste (0 hs), tu top por horas y un botón '🎲 ¿A qué juego hoy?' para sortear tu backlog.",
            "🤝 Radar 'Co-op con Amigos': Cruzá tu biblioteca con el Steam ID de un amigo para ver juegos multijugador en común o descubrir ofertas Co-op para ambos.",
            "🎬 Galería Multimedia y Trailer en Ficha: Miniaturas de capturas HD interactivas (clic para ampliar) y acceso directo al Trailer Oficial de Steam.",
            "🃏 Detector de Cromos (Trading Cards) y Bundles: Etiqueta '🃏 Cromos' con filtro dedicado en el Mini-Dashboard y aviso de packs ahorrativos.",
            "💾 Backup Portátil (.zip) y Atajos Power-User: Exportá/importá tu base y ajustes en 1 clic desde Configuración y navegá con Ctrl+F, Ctrl+B, F5 y Flechas."
        ]
    },
    {
        "version": "v1.6.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "📊 Mini-Dashboard Interactivo (KPIs): Píldoras en vivo de Récords Históricos (ATL), Suscripciones y Promedio de Precios con filtro de 1 clic.",
            "🧮 Selector Global USD / ARS Tarjeta / ARS Cripto: Alterná en tiempo real el cálculo de todas las tarjetas entre Dólar Tarjeta y Dólar Cripto.",
            "🔼 Filtros Colapsables y UI Steam Deck: Botón para contraer el panel de filtros, tipografía unificada Segoe UI y tarjetas con precio original tachado.",
            "💀 Skeleton Loading Progresivo: Tarjetas animadas de carga durante el escaneo con estado de lotes en tiempo real.",
            "⚡ Watchlist & Wishlist 10x más rápidas: Importación y comprobación de rebajas por lotes paralelos (de 40s a ~1.5s) y Precio Objetivo (🎯) configurable."
        ]
    },
    {
        "version": "v1.5.2",
        "fecha": "Octubre 2026",
        "cambios": [
            "✨ Paginación Directa: Nuevo botón para saltar a cualquier página al instante.",
            "📊 Tooltips Históricos: El gráfico de historial ahora muestra precios interactivos al pasar el mouse.",
            "🎨 Soporte para Temas Custom: La app ahora lee custom_themes.json desde AppData.",
            "🪙 Fallback Dólar y FX: Si DolarAPI falla, se usa CriptoYa como respaldo. Nuevo sonido Ca-Ching al actualizar precio.",
            "🎲 Validación en Ruleta: Evita sumar al changuito juegos que ya tenés agregados."
        ]
    },
    {
        "version": "v1.5.1",
        "fecha": "Octubre 2026",
        "cambios": [
            "🛠️ Corrección Estructural UI: Eliminación definitiva de bloques duplicados y optimización del panel lateral en las tarjetas (vistas Normal y Compacta).",
            "💡 Estabilidad de Precios: Contenedor lateral de precios unificado y protegido contra deformaciones o saltos al redimensionar la ventana.",
        ]
    },
    {
        "version": "v1.5.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "✨ Rediseño y Limpieza UI: Barra de búsqueda inteligente unificada (búsqueda directa o filtros generales).",
            "🎃 Skin 'Halloween Terror': Nueva paleta temática naranja y violeta con contraste optimizado.",
            "🎲 Ruleta Loot Box: Animación dinámica con desaceleración progresiva y efectos de sonido reactivos.",
            "💡 Comparador Deluxe/Bundles: Detección inteligente de saltos de versión baratos en la Ficha Técnica.",
            "💾 Requisitos de Almacenamiento: Lectura y badge automático del peso en disco (GB).",
            "⏳ Radar de Fin de Oferta: Visualización del tiempo restante de rebaja.",
            "🛒 Mini Drawer en Changuito: Vista previa flotante al pasar el mouse sobre la barra inferior.",
        ]
    },
    {
        "version": "v1.4.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "⚡ Motor de Red Ultra-Rápido (HTTP Keep-Alive): Sesiones persistentes optimizadas que aceleran escaneos y peticiones hasta un 40%.",
            "🪙 Comparador Dólar Tarjeta vs. Cripto: Visualización en vivo en el Changuito y Ficha Técnica del ahorro exacto al pagar con criptomonedas.",
            "📸 Exportación de Presupuesto a PNG: Generá una placa visual con la lista y costo total de tu changuito lista para compartir en redes o Discord.",
            "📢 Integración Webhook de Discord: Publicá ofertas y fichas técnicas directamente en tu servidor de Discord con un solo clic.",
            "🎯 Precio Objetivo en Watchlist: Configurá un monto límite en tus juegos guardados para recibir alertas exactas cuando bajen de ese precio.",
            "🛡️ Estabilidad y Concurrencia: Base de datos SQLite migrada a modo WAL (sin bloqueos) y generador de reportes PDF 100% seguro en segundo plano."
        ]
    },
    {
        "version": "v1.3.1",
        "fecha": "Octubre 2026",
        "cambios": ["Bug fixes."]
    },
    {
        "version": "v1.3.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "📄 Exportación a PDF Ejecutivo con Gráficos: Nuevo generador de reportes PDF que incluye portada de métricas, gráficos de barras (Descuentos y Géneros) y listado completo de ofertas en USD y ARS.",
            "🔔 Alertas Nativas Interactivas (Clickables): Nuevo sistema de popups flotantes en el escritorio que al hacer clic traen SteamScope al frente y abren directamente la Ficha Técnica del juego rebajado.",
            "💾 Presets de Filtros y Búsquedas Recientes: Guardá tu configuración favorita de filtros con un clic y accedé instantáneamente a tus últimas búsquedas desde la barra de herramientas."
        ]
    },
    {
        "version": "v1.2.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "💎 Optimización Total de Memoria: El caché de imágenes ahora es inteligente, evitando el consumo excesivo de RAM en sesiones largas.",
            "🎨 Inmersión Estética (UI): Los gráficos de historial de precios y todas las ventanas modales ahora respetan los colores exactos de la skin elegida.",
            "⭐ Nombres en Wishlist Garantizados: Nuevo motor de sincronización que rescata el nombre oficial del juego aunque Steam lo oculte.",
            "⏳ Filtro de Juegos sin Precio: Los juegos en desarrollo o sin precio ($0.00) ahora se muestran correctamente como 'Próximamente' sin el botón de compra."
        ]
    },
    {
        "version": "v1.1.1",
        "fecha": "Octubre 2026",
        "cambios": [
            "⚡ Escaneo Ultra-Rápido: Optimización del motor de búsqueda para traer la cantidad exacta de ofertas (100, 200 o 500) sin bloqueos ni límites de la API de Steam.",
            "⭐ Sincronización de Wishlist Robusta: Corrección definitiva en la importación de nombres y filtrado inteligente de juegos próximos a salir (precio $0.00).",
            "🛠️ Estabilidad y Red: Eliminación de peticiones innecesarias para una velocidad de respuesta máxima y fluida en toda la interfaz."
        ]
    },
    {
        "version": "v1.1.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "🎨 Pack de Skins Temáticas: Sumamos 4 diseños completos ('Steam Deck OLED', 'Retro Synthwave', 'Terminal Pip-Boy' y 'Modo Drácula').",
            "🛒 Simulador de Carrito ('Changuito'): Armá tu presupuesto sumando juegos y visualizá el costo final en USD y ARS con impuestos en una barra flotante.",
            "🎵 Diseño Sonoro (UI SFX): Efectos de sonido de consola reactivos al navegar, sumar al carrito o detectar mínimos históricos (activable en Ajustes).",
            "🌡️ Termómetro de Compras: Consejero inteligente que cruza descuentos, récords históricos y cercanía de eventos de Steam.",
            "📸 Generador de Placas para Redes (Modo Creador): Exportá tarjetas promocionales en PNG (1080x1080) listas para subir a redes o Discord.",
            "🟢 Radar Anti-Suscripción: Etiquetas automáticas de advertencia cuando un juego forma parte de PC Game Pass, EA Play o Ubisoft+.",
            "🎲 Botón 'Sorpréndeme' (Ruleta): Sorteo inteligente de una oferta recomendada al azar entre tus resultados filtrados."
        ]
    },
    {
        "version": "v1.0.9",
        "fecha": "Octubre 2026",
        "cambios": [
            "✨ Rediseño Estético Launcher: Nueva vista de estantería en 4 columnas con Pósters Verticales redondeados y etiquetas de descuento estampadas en el arte.",
            "💎 Tarjetas Steam Store Moderna: Filas horizontales con bordes iluminados reactivos al mouse, miniaturas curvas y bloque de precio apilado.",
            "⚡ Renderizado Progresivo 60 FPS: Carga asíncrona en lotes que elimina cualquier tirón al cambiar de página o de vista."
        ]
    },
    {
        "version": "v1.0.8",
        "fecha": "Octubre 2026",
        "cambios": [
            "🖥️ Ficha Estilo Terminal: Rediseño completo de la Ficha Técnica con póster vertical, detección de DRM/Denuvo, Steam Deck, mínimo histórico global real y tabla punteada.",
            "💵 Dólar Cripto & Oficial: Selector rápido de cotización en Ajustes y Calculadora para alternar entre Dólar Tarjeta (+60%) y Dólar Cripto (0% imp).",
            "🔄 Auto-Actualizador Integrado: Botón 'Actualizar' en la barra inferior que descarga y actualiza la app automáticamente."
        ]
    },
    {
        "version": "v1.0.7",
        "fecha": "Octubre 2026",
        "cambios": [
            "💵 Dólar en Vivo: Botón en Ajustes y Calculadora para obtener la cotización actual automáticamente (DolarAPI).",
            "🃏 Ficha Técnica y Requisitos: Nueva opción con click derecho para ver sinopsis, requisitos de PC, cromos y logros sin salir de la app.",
            "🚫 Gestor de Blacklist: Nuevo panel en Ajustes para visualizar y restaurar juegos ignorados.",
            "🔍 Buscador y Resumen en Watchlist: Filtro por texto en tiempo real y cálculo del costo total (USD/ARS) de tu lista.",
            "🚀 Optimización de Motor: Pool de hilos controlado para imágenes/jugadores, limpieza de RAM en gráficos, filtro anti-duplicados diarios y soporte de alias (Vanity URL) para juegos propios."
        ]
    },
    {
        "version": "v1.0.6",
        "fecha": "Octubre 2026",
        "cambios": [
            "📱 Hub de Redes: Se agregó un nuevo botón en la barra inferior ('Mis Redes') con acceso directo a los canales oficiales de YouTube, Twitch y Discord de Patoma89.",
            "🔧 Optimización: Se eliminó la dependencia de imágenes locales para mejorar la portabilidad del script."
        ]
    },
    {
        "version": "v1.0.5",
        "fecha": "Octubre 2026",
        "cambios": [
            "🎨 Temas Dinámicos: Selector de skins. Incluye la opción 'Neón P89', que transforma toda la interfaz a un modo oscuro profundo con detalles cian, magenta y amarillo ciberpunk."
        ]
    },
    {
        "version": "v1.0.4",
        "fecha": "Octubre 2026",
        "cambios": [
            "🧹 Limpieza de Caché: Nuevo botón en Ajustes para liberar espacio en disco.",
            "🛡️ Protección Anti-Ban Steam: Escaneo inteligente de rebajas con pausas para evitar bloqueos (Rate Limit).",
            "👥 Filtros Cooperativos Avanzados: Búsqueda separada por PvP, Cooperativo Online y Cooperativo Local.",
            "🔑 Integración Steam API: Nuevo campo para ocultar automáticamente los juegos que ya tenés en tu biblioteca.",
            "📊 Reportes Excel Premium: Nueva hoja de 'Resumen' con métricas y costos totales generada con Pandas."
        ]
    },
    {
        "version": "v1.0.3",
        "fecha": "Octubre 2026",
        "cambios": [
            "📐 Reestructuración UI: Se eliminaron los márgenes muertos de las tarjetas.",
            "🛠️ Sistema de Grilla Real: Se reescribió el motor visual de la grilla."
        ]
    },
    {
        "version": "v1.0.2",
        "fecha": "Octubre 2026",
        "cambios": [
            "🎯 Búsqueda Personalizada: Nuevo campo para precio máximo deseado en USD.",
            "🛠️ Fix: Corrección en el botón de '100% Gratis'."
        ]
    },
    {
        "version": "v1.0.1",
        "fecha": "Octubre 2026",
        "cambios": [
            "📐 UI Ajustada: Reducción del tamaño general de las tarjetas.",
            "🖼️ Grilla Panorámica: La vista en grilla ahora utiliza 3 columnas."
        ]
    },
    {
        "version": "v1.0",
        "fecha": "Octubre 2026",
        "cambios": [
            "✨ Sistema de Vistas Dinámicas: Elegí entre vista 'Normal', 'Compacta' o 'Grilla'.",
            "🖼️ Posters Inteligentes: Descarga de portadas de la biblioteca de Steam.",
            "💾 Persistencia: Tu preferencia de vista se guarda automáticamente."
        ]
    },
    {
        "version": "v0.9",
        "fecha": "Octubre 2026",
        "cambios": [
            "✨ Visuales: Tarjetas reactivas al mouse con barra de estado de color según calidad de la oferta.",
            "🔔 Notificaciones: Avisos integrados in-app (Snackbars) modernos que no interrumpen el uso.",
            "📈 Gráficos: Rediseño visual del historial de precios estilo dashboard.",
            "🖱️ Interfaz: Nuevo menú contextual (Click Derecho) 100% personalizado."
        ]
    },
    {
        "version": "v0.8.1",
        "fecha": "Octubre 2026",
        "cambios": [
            "🎨 Interfaz: Los menúes contextuales (click derecho) ahora respetan el color del tema oscuro/claro.",
            "🎨 Interfaz: La ventana de ofertas ahora tiene un diseño oscuro acorde a la aplicación.",
            "🛠️ Sistema: Corrección definitiva del cierre en segundo plano desde la bandeja del sistema."
        ]
    },
    {
        "version": "v0.8",
        "fecha": "Octubre 2026",
        "cambios": [
            "⚙ QoL: La opción de minimizar a la bandeja o a la barra ahora se guarda en el panel de Ajustes."
        ]
    },
    {
        "version": "v0.7",
        "fecha": "Octubre 2026",
        "cambios": [
            "🎁 Buscador de Juegos Gratis: Nuevo botón dedicado para encontrar juegos con 100% de descuento.",
            "🏷️ Filtros de Watchlist: Ahora podés filtrar tus juegos guardados según tus etiquetas.",
            "⏳ Integración HowLongToBeat: Nuevo acceso rápido con click derecho para ver la duración.",
            "🌍 Comparativa Regional: Acceso rápido a SteamDB para comparar precios."
        ]
    },
    {
        "version": "v0.6",
        "fecha": "Octubre 2026",
        "cambios": [
            "🚀 Motor Multihilo: Escaneo de ofertas un 80% más rápido mediante peticiones concurrentes.",
            "🖼️ Caché en Disco: Las imágenes ahora se guardan localmente eliminando el consumo de internet y RAM.",
            "📈 Gráficos Históricos: Nuevo panel visual de historial de precios.",
            "🏷 Etiquetas Personalizadas: Clasificá tu Watchlist con tags propios."
        ]
    },
    {
        "version": "v0.5.1",
        "fecha": "Octubre 2026",
        "cambios": [
            "🛠️ Corrección de Error: Se arregló el crash al intentar importar Wishlists de perfiles privados."
        ]
    },
    {
        "version": "v0.5",
        "fecha": "Octubre 2026",
        "cambios": [
            "🖱️ Menú Contextual: Click derecho en cualquier juego para buscar gameplay en YouTube o ver SteamDB.",
            "🚫 Filtro de Ignorados (Blacklist): Ocultá para siempre juegos irrelevantes.",
            "👥 Radar de Jugadores Activos: Muestra la cantidad de gente jugando en este mismo instante.",
            "💾 Gestor de Backups: Importá y exportá tu base de datos local desde el menú de Ajustes."
        ]
    },
    {
        "version": "v0.4",
        "fecha": "Octubre 2026",
        "cambios": [
            "🔄 Sincronización Automática de Wishlist de Steam.",
            "⚙ Panel de Configuración Dinámico (Dólar, impuestos, ID).",
            "📉 Etiqueta visual de Mínimo Histórico y registro de precios."
        ]
    },
    {
        "version": "v0.3",
        "fecha": "Octubre 2026",
        "cambios": [
            "🌐 Funciones de Red: Integración de API para ofertas de Steam.",
            "💾 Base de Datos: Migración a SQLite.",
            "🖼️ Interfaz Gráfica: Implementación de CustomTkinter."
        ]
    },
    {
        "version": "v0.2",
        "fecha": "Octubre 2026",
        "cambios": [
            "🛠️ Estructura: Limpieza del código y separación en módulos más organizados."
        ]
    },
    {
        "version": "v0.1",
        "fecha": "Septiembre 2026",
        "cambios": [
            "🐣 Inicio del Proyecto: Creación del primer prototipo en consola.",
            "🔍 Búsqueda Básica: Funcionalidad inicial para buscar precios por consola usando Python."
        ]
    }
]

STEAM_CALENDAR = [
    {"name": "Steam Scream Fest (Halloween)", "start": "2026-10-26T17:00:00Z", "end": "2026-11-02T17:00:00Z", "type": "Themed"},
    {"name": "Steam Autumn Sale (Black Friday)", "start": "2026-11-26T17:00:00Z", "end": "2026-12-04T17:00:00Z", "type": "Major"},
    {"name": "Steam Winter Sale 2026", "start": "2026-12-17T17:00:00Z", "end": "2027-01-04T17:00:00Z", "type": "Major"},
    {"name": "Steam Spring Sale 2027", "start": "2027-03-18T17:00:00Z", "end": "2027-03-25T17:00:00Z", "type": "Major"}
]

SKIN_PALETTES = {
    "Oscuro": {
        "mode": "Dark", "win_bg": "#242424", "panel_bg": "#2b2b2b", "card_bg": "#181b20",
        "card_hover": "#22262e", "border": "#282c34", "accent": "#38bdf8", "accent_2": "#1f538d",
        "text": "#f8fafc", "subtext": "#cbd5e1", "price_bg": "#121418", "deal_badge": "#4c6b22", "deal_text": "#beee11"
    },
    "Claro": {
        "mode": "Light", "win_bg": "#ebebeb", "panel_bg": "#dbdbdb", "card_bg": "#ffffff",
        "card_hover": "#f1f5f9", "border": "#cbd5e1", "accent": "#1976d2", "accent_2": "#00695c",
        "text": "#0f172a", "subtext": "#334155", "price_bg": "#f1f5f9", "deal_badge": "#2e7d32", "deal_text": "#ffffff"
    },
    "Sistema": {
        "mode": "Dark", "win_bg": "#242424", "panel_bg": "#2b2b2b", "card_bg": "#181b20",
        "card_hover": "#22262e", "border": "#282c34", "accent": "#38bdf8", "accent_2": "#1f538d",
        "text": "#f8fafc", "subtext": "#cbd5e1", "price_bg": "#121418", "deal_badge": "#4c6b22", "deal_text": "#beee11"
    },
    "Neón P89": {
        "mode": "Dark", "win_bg": "#09090b", "panel_bg": "#121217", "card_bg": "#111318",
        "card_hover": "#1a1d26", "border": "#262936", "accent": "#00f0ff", "accent_2": "#ff003c",
        "text": "#ffffff", "subtext": "#cbd5e1", "price_bg": "#0b0c10", "deal_badge": "#a4d007", "deal_text": "#0b0c10"
    },
    "Steam Deck OLED": {
        "mode": "Dark", "win_bg": "#000000", "panel_bg": "#0a0c0f", "card_bg": "#0e1116",
        "card_hover": "#161b22", "border": "#1f242c", "accent": "#1a9fff", "accent_2": "#00e676",
        "text": "#ffffff", "subtext": "#cbd5e1", "price_bg": "#050608", "deal_badge": "#1a9fff", "deal_text": "#ffffff"
    },
    "Retro Synthwave": {
        "mode": "Dark", "win_bg": "#120322", "panel_bg": "#1c0636", "card_bg": "#240946",
        "card_hover": "#310d5e", "border": "#ff00ea", "accent": "#00f0ff", "accent_2": "#ff00ea",
        "text": "#fff0ff", "subtext": "#e8bfff", "price_bg": "#140328", "deal_badge": "#ff00ea", "deal_text": "#ffffff"
    },
    "Terminal Pip-Boy": {
        "mode": "Dark", "win_bg": "#050b05", "panel_bg": "#091409", "card_bg": "#0c1c0c",
        "card_hover": "#132a13", "border": "#39ff14", "accent": "#39ff14", "accent_2": "#22c55e",
        "text": "#39ff14", "subtext": "#86efac", "price_bg": "#040804", "deal_badge": "#39ff14", "deal_text": "#040804"
    },
    "Modo Drácula": {
        "mode": "Dark", "win_bg": "#191a21", "panel_bg": "#21222c", "card_bg": "#282a36",
        "card_hover": "#343746", "border": "#44475a", "accent": "#ff5555", "accent_2": "#bd93f9",
        "text": "#f8f8f2", "subtext": "#b3c2e6", "price_bg": "#1e1f29", "deal_badge": "#ff5555", "deal_text": "#ffffff"
    },
    "Halloween Terror": {
        "mode": "Dark", "win_bg": "#0c0a0e", "panel_bg": "#141118", "card_bg": "#1c1722",
        "card_hover": "#292133", "border": "#ff7518", "accent": "#ff7518", "accent_2": "#9d4edd",
        "text": "#fdf0d5", "subtext": "#d8cdc9", "price_bg": "#100d14", "deal_badge": "#ff7518", "deal_text": "#ffffff"
    }
}


def cargar_temas_personalizados():
    app_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SteamScope")
    theme_file = os.path.join(app_dir, "custom_themes.json")
    if os.path.exists(theme_file):
        try:
            with open(theme_file, 'r', encoding='utf-8') as f:
                customs = json.load(f)
                for nombre, colores in customs.items():
                    SKIN_PALETTES[nombre] = colores
        except Exception:
            pass


cargar_temas_personalizados()

MODALIDADES = {
    "Cualquiera": "",
    "Single-Player": "Single-player",
    "Multijugador PvP": "PvP",
    "Cooperativo Online": "Online Co-op",
    "Cooperativo Local": "Local Co-op"
}

CATEGORIAS_STEAM = {
    "Todas las Categorías": {
        "Todas las subcategorías": []
    },
    "🎯 Shooters": {
        "Todos los Shooters": ["shooter", "fps", "third-person shooter", "tactical shooter", "looter shooter", "boomer shooter", "hero shooter", "battle royale", "bullet hell", "top-down shooter", "arena shooter", "shoot 'em up"],
        "FPS (Primera Persona)": ["fps", "first-person shooter"],
        "TPS (Tercera Persona)": ["third-person shooter", "tps"],
        "Táctico / Militar": ["tactical", "military", "tactical shooter", "realistic"],
        "Looter Shooter": ["looter shooter", "loot"],
        "Extraction Shooter": ["extraction shooter", "pvpvve", "survival shooter"],
        "Boomer Shooter / Retro": ["boomer shooter", "retro fps", "old school", "classic fps"],
        "Hero Shooter / Arena": ["hero shooter", "arena shooter"],
        "Battle Royale": ["battle royale"],
        "Bullet Hell / Shmup": ["bullet hell", "shoot 'em up", "shmup", "danmaku"],
        "Top-Down Shooter": ["top-down shooter", "twin stick shooter"]
    },
    "⚔️ Rol / RPG": {
        "Todos los RPG": ["rpg", "arpg", "jrpg", "crpg", "souls-like", "action rpg", "role-playing"],
        "ARPG / Hack & Slash": ["action rpg", "arpg", "hack and slash", "hack & slash", "loot"],
        "Souls-like": ["souls-like", "soulslike", "difficult", "dark fantasy"],
        "CRPG / Rol Clásico": ["crpg", "classic rpg", "party-based", "isometric"],
        "JRPG": ["jrpg", "japanese rpg", "anime"],
        "Roguelite de Rol": ["rogue-lite", "roguelike", "dungeon crawler"],
        "MMORPG": ["mmorpg", "massively multiplayer"]
    },
    "🧠 Estrategia & Gestión": {
        "Toda la Estrategia": ["strategy", "rts", "turn-based strategy", "city builder", "management", "tower defense", "4x"],
        "Estrategia en Tiempo Real (RTS)": ["rts", "real-time strategy"],
        "Por Turnos / 4X": ["turn-based strategy", "4x", "turn-based tactics"],
        "City Builder / Gestión": ["city builder", "colony sim", "management", "base building"],
        "Automatización & Fábricas": ["automation", "resource management", "crafting"],
        "Tower Defense": ["tower defense"]
    },
    "🏃 Acción & Plataformas": {
        "Toda la Acción": ["action", "platformer", "metroidvania", "beat 'em up", "fighting", "stealth"],
        "Metroidvania": ["metroidvania"],
        "Plataformas 2D / 3D": ["platformer", "2d platformer", "3d platformer", "precision platformer"],
        "Beat 'em Up / Lucha": ["beat 'em up", "fighting", "brawler"],
        "Sigilo (Stealth)": ["stealth", "ninja", "assassin"]
    },
    "💀 Supervivencia & Terror": {
        "Todos": ["survival", "survival horror", "horror", "open world", "crafting"],
        "Supervivencia & Crafteo": ["survival", "crafting", "open world survival craft"],
        "Mundo Abierto (Open World)": ["open world", "exploration"],
        "Survival Horror": ["survival horror", "zombies"],
        "Terror Psicológico": ["psychological horror", "horror", "atmospheric"]
    },
    "🃏 Cartas, Puzles & Sim": {
        "Todos": ["card game", "deckbuilder", "puzzle", "farming sim", "racing", "simulation"],
        "Deckbuilder / Cartas": ["card battler", "deckbuilding", "card game", "roguelike deckbuilder"],
        "Puzles & Lógica": ["puzzle", "logic", "physics"],
        "Simulador de Granjas / Cozy": ["farming sim", "cozy", "relaxing", "life sim"],
        "Carreras / Conducción": ["racing", "driving", "automobile sim"]
    },
    "🎮 Plataforma & Features Steam": {
        "Todas las Características": ["co-op", "multiplayer", "singleplayer", "steam deck", "controller"],
        "Steam Deck Verificado": ["steam deck", "deck verified", "great on deck"],
        "Mando Total": ["full controller support", "controller"],
        "Cromos de Steam": ["trading cards"],
        "Cooperativo Local": ["local co-op", "shared/split screen", "split screen"],
        "Cooperativo Online": ["online co-op", "co-op"],
        "Steam Cloud": ["steam cloud"]
    }
}

GENEROS = {
    "Todos": "",
    "Acción": "Action",
    "Shooter / FPS": "Shooter",
    "Supervivencia": "Survival",
    "Rol / RPG": "RPG",
    "Estrategia": "Strategy",
    "Aventura": "Adventure",
    "Terror": "Horror",
    "Simulación": "Simulation"
}

RANGOS_DESCUENTO = {
    "Cualquier Descuento": (1, 100),
    "Hasta 25%": (1, 25),
    "Entre 25% y 50%": (25, 50),
    "Entre 50% y 75%": (50, 75),
    "Más de 75%": (75, 100),
    "100% (Gratis)": (100, 100)
}

RANGOS_PRECIO = {
    "Cualquier Precio": (0.0, 999.0),
    "Menos de $5 USD": (0.0, 5.0),
    "Entre $5 y $15 USD": (5.0, 15.0),
    "Entre $15 y $30 USD": (15.0, 30.0),
    "Más de $30 USD": (30.0, 999.0)
}

FILTROS_CALIDAD = {
    "Cualquier Calidad": 0,
    "> 70% (Positivas)": 70,
    "> 80% (Muy Positivas)": 80,
    "> 90% (Extremadamente Positivas)": 90
}

ITEMS_POR_PAGINA = 25


def obtener_ruta_appdata():
    app_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SteamScope")
    old_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SteamDealHunterPro")
    if os.path.exists(old_dir) and not os.path.exists(app_dir):
        try:
            shutil.move(old_dir, app_dir)
        except Exception:
            pass
    os.makedirs(app_dir, exist_ok=True)
    os.makedirs(os.path.join(app_dir, "cache"), exist_ok=True)
    return app_dir


def limpiar_cache_imagenes():
    """
    Elimina archivos temporales de miniaturas en cache/ para liberar espacio en disco.
    Retorna una tupla: (archivos_eliminados: int, mb_liberados: float).
    """
    app_dir = obtener_ruta_appdata()
    cache_dir = os.path.join(app_dir, "cache")
    if not os.path.exists(cache_dir):
        return 0, 0.0
    borrados = 0
    bytes_liberados = 0
    try:
        for fname in os.listdir(cache_dir):
            fpath = os.path.join(cache_dir, fname)
            try:
                if os.path.isfile(fpath):
                    sz = os.path.getsize(fpath)
                    os.remove(fpath)
                    borrados += 1
                    bytes_liberados += sz
            except Exception:
                pass
    except Exception:
        pass
    mb_liberados = round(bytes_liberados / (1024 * 1024), 2)
    return borrados, mb_liberados


def obtener_ruta_recurso(nombre_archivo):
    if hasattr(sys, '_MEIPASS'):
        ruta = os.path.join(sys._MEIPASS, nombre_archivo)
        if os.path.exists(ruta):
            return ruta
    # Busca en la carpeta raíz del proyecto (un nivel arriba de core/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta_local = os.path.join(base_dir, nombre_archivo)
    if os.path.exists(ruta_local):
        return ruta_local
    return nombre_archivo


class SoundManager:
    """Gestor de efectos sonoros desacoplado de la interfaz (SRP)."""
    def __init__(self, config_manager):
        self.config = config_manager

    def play(self, sfx_type="click"):
        if not self.config.datos.get("sfx_enabled", True):
            return
        threading.Thread(target=self._beep_thread, args=(sfx_type,), daemon=True).start()

    def _beep_thread(self, sfx_type):
        try:
            if sfx_type == "click":
                winsound.Beep(950, 22)
            elif sfx_type == "page":
                winsound.Beep(720, 18)
                winsound.Beep(1080, 25)
            elif sfx_type == "cart_add":
                winsound.Beep(880, 35)
                winsound.Beep(1320, 50)
            elif sfx_type == "cart_remove":
                winsound.Beep(600, 40)
            elif sfx_type == "coin":
                winsound.Beep(1200, 70)
                winsound.Beep(1600, 100)
            elif sfx_type in ("roulette", "roulette_tick"):
                winsound.Beep(1100, 15)
            elif sfx_type == "roulette_win":
                winsound.Beep(523, 60)
                winsound.Beep(659, 60)
                winsound.Beep(784, 80)
                winsound.Beep(1046, 140)
            elif sfx_type == "atl":
                winsound.Beep(1046, 45)
                winsound.Beep(1318, 45)
                winsound.Beep(1567, 70)
        except Exception:
            pass


class ConfigManager:
    """Repositorio de configuración persistente en JSON (SRP)."""
    def __init__(self, config_path=None):
        self.config_path = config_path or os.path.join(obtener_ruta_appdata(), "config.json")
        self.datos = self.cargar()

    def cargar(self):
        defaults = {
            "steam_id": "", "steam_api_key": "", "impuestos_pct": 60, "dolar_referencia": 1000.0,
            "dolar_cripto_ref": 1150.0, "umbral_alerta_pct": 50, "minimizar_a": "Preguntar",
            "vista_resultados": "Normal", "tema": "Oscuro", "sfx_enabled": True, "moneda": "USD",
            "update_url": UPDATE_JSON_URL, "busquedas_recientes": [], "filtro_favorito": {},
            "carrito_guardado": {}, "discord_webhook": "", "metodo_pago_defecto": "Tarjeta",
            "watchdog_activado": True, "watchdog_intervalo_hs": 6, "alerta_sonido_atl": True,
            "presupuesto_carrito_usd": 0.0
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        return defaults

    def guardar_basico(self, k, v):
        self.datos[k] = v
        self._persistir()

    def guardar(self, steam_id, steam_api_key, impuestos, dolar, umbral, minimizar_a, sfx_enabled, discord_webhook="",
                watchdog_activado=None, watchdog_intervalo_hs=None, alerta_sonido_atl=None):
        nuevos = {
            "steam_id": steam_id, "steam_api_key": steam_api_key, "impuestos_pct": impuestos,
            "dolar_referencia": dolar, "umbral_alerta_pct": umbral, "minimizar_a": minimizar_a,
            "sfx_enabled": sfx_enabled, "discord_webhook": discord_webhook
        }
        if watchdog_activado is not None:
            nuevos["watchdog_activado"] = bool(watchdog_activado)
        if watchdog_intervalo_hs is not None:
            nuevos["watchdog_intervalo_hs"] = int(watchdog_intervalo_hs)
        if alerta_sonido_atl is not None:
            nuevos["alerta_sonido_atl"] = bool(alerta_sonido_atl)
        self.datos.update(nuevos)
        self._persistir()

    def _persistir(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.datos, f, indent=4)
        except Exception:
            pass
