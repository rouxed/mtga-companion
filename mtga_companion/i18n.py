"""Localización en tiempo de ejecución para la interfaz (español/inglés).

Las cadenas fuente de la aplicación se mantienen en español para conservar el
comportamiento existente. :func:`tr` devuelve la traducción inglesa cuando el
idioma activo es ``en``. La ventana principal se reconstruye al cambiar de
idioma, de modo que los widgets y el proceso auxiliar del overlay se crean de
nuevo con el idioma elegido.
"""
from __future__ import annotations

from collections.abc import Mapping

DEFAULT_LANGUAGE = "es"
LANGUAGE_ENV_VAR = "MTGA_COMPANION_LANG"

# Los nombres se muestran siempre en su propio idioma para que sean fáciles de
# reconocer en el selector.
LANGUAGE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("es", "Español"),
    ("en", "English"),
)
_LANGUAGE_CODES = frozenset(code for code, _label in LANGUAGE_OPTIONS)

_language = DEFAULT_LANGUAGE

# Traducciones español -> inglés. Se usan las cadenas españolas como claves
# para no tener que mantener identificadores paralelos en cada widget.
_EN: Mapping[str, str] = {
    # ------------------------------------------------------------------
    # Ventana principal / navegación
    # ------------------------------------------------------------------
    "MTGA Companion — Arena Tracker": "MTGA Companion — Arena Tracker",
    "Resumen de rendimiento y partidas recientes": (
        "Performance overview and recent matches"
    ),
    "Todas tus partidas registradas": "All your recorded matches",
    "Tus mazos y las cartas que los componen": "Your decks and the cards in them",
    "Mazos populares del metajuego actual": "Popular decks from the current metagame",
    "Player.log, jugador, overlay y seguimiento en vivo": (
        "Player.log, player, overlay and live tracking"
    ),
    "Iniciando seguimiento del Player.log…": "Starting Player.log tracking…",
    "NAVEGACIÓN": "NAVIGATION",
    "SESIÓN": "SESSION",
    "Jugador": "Player",
    "● INICIANDO": "● STARTING",
    "● EN VIVO": "● LIVE",
    "● ESPERANDO": "● WAITING",
    "● ERROR": "● ERROR",
    "● DETENIDO": "● STOPPED",
    "EN VIVO": "LIVE",
    "ESPERANDO": "WAITING",
    "Estado del seguimiento de Arena": "Arena tracking status",
    "Mostrar u ocultar el deck tracker durante la partida": (
        "Show or hide the deck tracker during the match"
    ),
    "Overlay ON": "Overlay ON",
    "Seguimiento activo · Player.log": "Tracking active · Player.log",
    "Seguimiento detenido": "Tracking stopped",
    "El seguimiento está detenido": "Tracking is stopped",
    "Error del watcher": "Watcher error",
    "Aplicando idioma…": "Applying language…",
    "Configuración": "Settings",
    "Historial": "History",
    "Mazos": "Decks",
    "Dashboard": "Dashboard",
    "Meta": "Meta",
    "Overlay": "Overlay",
    "ID": "ID",
    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    "Sin partidas": "No matches",
    "Registro global": "Global record",
    "RENDIMIENTO GLOBAL": "GLOBAL PERFORMANCE",
    "Todo tu historial registrado en Arena": (
        "All your history recorded in Arena"
    ),
    "Partidas": "Matches",
    "Partidas registradas": "Recorded matches",
    "Victorias": "Wins",
    "Resultados ganados": "Won games",
    "Derrotas": "Losses",
    "Resultados perdidos": "Lost games",
    "Sin resultado": "No result",
    "No se pudo determinar": "Could not be determined",
    "Winrate por período": "Winrate by period",
    "Hoy, 7 y 30 días": "Today, 7 and 30 days",
    "Hoy": "Today",
    "Últimos 7 días": "Last 7 days",
    "Últimos 30 días": "Last 30 days",
    "Partidas recientes": "Recent matches",
    "Últimas 15 partidas": "Last 15 matches",
    "Actualizar": "Refresh",
    "FECHA": "DATE",
    "MAZO": "DECK",
    "FORMATO": "FORMAT",
    "RESULTADO": "RESULT",
    "OPONENTE": "OPPONENT",
    "CARTAS": "CARDS",
    "Victoria": "Win",
    "Derrota": "Loss",
    "Desconocido": "Unknown",
    "{count} partidas · {winrate} de winrate": (
        "{count} matches · {winrate} winrate"
    ),
    "{winrate} de winrate": "{winrate} winrate",
    "{wins}V · {losses}D": "{wins}W · {losses}L",
    # ------------------------------------------------------------------
    # Historial
    # ------------------------------------------------------------------
    "Buscar": "Search",
    "Mazo, oponente o formato…": "Deck, opponent or format…",
    "Limpiar": "Clear",
    "{count} de {total} partidas": "{count} of {total} matches",
    "{count} partidas": "{count} matches",
    "0 partidas": "0 matches",
    # ------------------------------------------------------------------
    # Mazos
    # ------------------------------------------------------------------
    "MAZOS REGISTRADOS": "REGISTERED DECKS",
    "Ordenados por última vez jugados": "Sorted by last played",
    "Actualizar lista": "Refresh list",
    "Seleccioná un mazo": "Select a deck",
    "Cargando cartas…": "Loading cards…",
    "Todavía no hay mazos": "No decks yet",
    "Jugá una partida con Arena abierto para registrar tu primer mazo.": (
        "Play a match with Arena running to record your first deck."
    ),
    "Formato desconocido": "Unknown format",
    "{format}  ·  {wins}V-{losses}D  ·  {wr}%": (
        "{format}  ·  {wins}W-{losses}L  ·  {wr}%"
    ),
    "{format}  ·  {wins}V-{losses}D  ·  {wr}% de winrate  ·  última vez {date}": (
        "{format}  ·  {wins}W-{losses}L  ·  {wr}% winrate  ·  last played {date}"
    ),
    "Error cargando cartas": "Error loading cards",
    # ------------------------------------------------------------------
    # Categorías de cartas
    # ------------------------------------------------------------------
    "Tierras": "Lands",
    "Criaturas": "Creatures",
    "Planeswalkers": "Planeswalkers",
    "Instantáneos": "Instants",
    "Conjuros": "Sorceries",
    "Artefactos": "Artifacts",
    "Encantamientos": "Enchantments",
    "Batallas": "Battles",
    "Otras": "Other",
    "Hechizos": "Spells",
    "carta": "card",
    "cartas": "cards",
    "Carta": "Card",
    "Carta desconocida": "Unknown card",
    "Carta #{id}": "Card #{id}",
    "Mazo sin nombre": "Unnamed deck",
    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------
    "Formato": "Format",
    "Buscar en internet": "Search online",
    "Estado de la caché de mazos meta": "Meta deck cache status",
    "MAZOS META POPULARES": "POPULAR META DECKS",
    "Compartidos en MTGGoldfish": "Shared on MTGGoldfish",
    "Seleccioná un mazo meta": "Select a meta deck",
    "LISTA PARA MTG ARENA": "MTG ARENA DECKLIST",
    "Copiá y pegala en el juego": "Copy and paste it into the game",
    "Copiar lista": "Copy list",
    "Caché: {count} mazos": "Cache: {count} decks",
    "vencida": "stale",
    "actualizada": "up to date",
    "Sin caché. Presioná «Buscar en internet».": (
        "No cache. Press “Search online”."
    ),
    "Sin caché de {format}. Buscando...": "No cache for {format}. Searching...",
    "Buscando mazos meta ({format})...": "Searching meta decks ({format})...",
    "Sin mazos disponibles para {format}": "No decks available for {format}",
    "Sin conexión: {count} mazos de respaldo": (
        "Offline: {count} fallback decks"
    ),
    "{count} mazos encontrados": "{count} decks found",
    "Error al buscar mazos meta": "Error searching meta decks",
    "Sin nombre": "Unnamed",
    "Meta share: {share}": "Meta share: {share}",
    "Tabletop: {price}": "Tabletop: {price}",
    "MTGO: {price}": "MTGO: {price}",
    "Fuente: {source}": "Source: {source}",
    "Mazo meta": "Meta deck",
    "{share} ({count} mazos)": "{share} ({count} decks)",
    "Precio aprox.: {price}": "Approx. price: {price}",
    "No se pudieron cargar las cartas del mazo.": (
        "Could not load the deck's cards."
    ),
    "No se pudieron cargar las cartas.": "Could not load cards.",
    "Banquillo · ": "Sideboard · ",
    "Vacío": "Empty",
    "No hay ninguna lista para copiar.": "There is no list to copy.",
    "Copiado": "Copied",
    "Lista de exportación copiada al portapapeles.\nPegala en MTG Arena para importar el mazo.": (
        "Export list copied to clipboard.\n"
        "Paste it into MTG Arena to import the deck."
    ),
    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    "Idioma": "Language",
    "Idioma de la interfaz. Se aplica al instante.": (
        "Interface language. Applies immediately."
    ),
    "Player.log de MTG Arena": "MTG Arena Player.log",
    "El companion lee el archivo Player.log de MTG Arena en tiempo real.\n"
    "La ruta se detecta automáticamente; si hay varias instalaciones, "
    "podés elegir una abajo.": (
        "The companion reads the MTG Arena Player.log file in real time.\n"
        "The path is detected automatically; if there are several "
        "installations, you can choose one below."
    ),
    "Ruta al Player.log...": "Path to Player.log...",
    "Examinar…": "Browse…",
    "Detectadas": "Detected",
    "Sin rutas detectadas": "No paths detected",
    "Buscar rutas": "Find paths",
    "Se buscan instalaciones de Steam, Lutris, Heroic/Epic, Bottles, "
    "Wine manual y particiones Windows.": (
        "Searches for Steam, Lutris, Heroic/Epic, Bottles, manual Wine "
        "and Windows partitions."
    ),
    "Tu nombre de jugador en Arena": "Your Arena player name",
    "Se usa para saber si sos vos quien ganó o perdió cada partida "
    "(formato \"Nombre#12345\"). Si lo dejás vacío, el resultado se marcará "
    "como desconocido.": (
        "Used to determine whether you won or lost each match "
        "(format \"Name#12345\"). If left empty, results are marked as unknown."
    ),
    "Nombre#12345": "Name#12345",
    "Seguimiento de partidas en vivo": "Live match tracking",
    "Iniciar seguimiento": "Start tracking",
    "Detener seguimiento": "Stop tracking",
    "Detenido": "Stopped",
    "Activo": "Active",
    "Activo · Player.log": "Active · Player.log",
    "Esperando Player.log": "Waiting for Player.log",
    "Overlay de partida": "Match overlay",
    "Deck tracker con probabilidades de robo, contador de tierras y "
    "cartas vistas del oponente. Usa únicamente tu mazo, tu mano y las "
    "zonas públicas o reveladas del log; nunca la mano ni la biblioteca "
    "oculta del oponente.": (
        "Deck tracker with draw odds, land count and opponent cards seen. "
        "Uses only your deck, your hand and public or revealed zones from "
        "the log; never the opponent's hidden hand or library."
    ),
    "Mostrar overlay durante la partida": "Show overlay during the match",
    "Click-through: no bloquear los clics del juego": (
        "Click-through: do not block game clicks"
    ),
    "Con click-through activo, el overlay no recibe clics. "
    "Podés desactivarlo para moverlo con el mouse.": (
        "With click-through enabled, the overlay does not receive clicks. "
        "You can disable it to move it with the mouse."
    ),
    "Posición": "Position",
    "Opacidad": "Opacity",
    "Opacidad del panel del overlay": "Overlay panel opacity",
    "Overlay desactivado": "Overlay disabled",
    "Overlay activo": "Overlay active",
    "Estado del proceso de overlay": "Overlay process status",
    "Player.log detectado automáticamente": "Player.log detected automatically",
    "No se detectó el Player.log todavía.": (
        "Player.log has not been detected yet."
    ),
    "Ruta configurada · Player.log": "Configured path · Player.log",
    "Ruta de Player.log seleccionada": "Player.log path selected",
    "(pendiente)": "(pending)",
    "Ruta configurada{state} · {path}": "Configured path{state} · {path}",
    "Modificado: {date}": "Modified: {date}",
    "sin fecha": "no date",
    "Variable MTGA_LOG_PATH": "MTGA_LOG_PATH variable",
    "Steam": "Steam",
    "Steam (Flatpak)": "Steam (Flatpak)",
    "Steam (juego no Steam)": "Steam (non-Steam game)",
    "Lutris": "Lutris",
    "Heroic / Epic": "Heroic / Epic",
    "Bottles": "Bottles",
    "Wine": "Wine",
    "Prefijo Wine": "Wine prefix",
    "Partición Windows": "Windows partition",
    "{count} ruta(s) detectada(s) · usando {source}": (
        "{count} path(s) detected · using {source}"
    ),
    "Rutas detectadas": "Detected paths",
    "Se encontraron {count} Player.log.\n\n"
    "Se usará la ruta más reciente; podés cambiarla en el selector.\n\n"
    "{detail}": (
        "Found {count} Player.log files.\n\n"
        "The most recent path will be used; you can change it in the selector.\n\n"
        "{detail}"
    ),
    "No encontrado": "Not found",
    "No se pudo detectar automáticamente el Player.log.\n"
    "Se buscaron Steam, Lutris, Heroic/Epic, Bottles, Wine "
    "y particiones Windows.\n\n"
    "Si tu instalación usa una ruta personalizada, seleccionala "
    "manualmente con 'Examinar…'.": (
        "The Player.log could not be detected automatically.\n"
        "Searched Steam, Lutris, Heroic/Epic, Bottles, Wine "
        "and Windows partitions.\n\n"
        "If your installation uses a custom path, select it manually "
        "with 'Browse…'."
    ),
    "… y {count} más": "… and {count} more",
    "Seleccionar Player.log": "Select Player.log",
    "Logs (*.log);;Todos (*)": "Logs (*.log);;All files (*)",
    "Overlay no disponible: no se detectó X11/XWayland (DISPLAY)": (
        "Overlay unavailable: no X11/XWayland detected (DISPLAY)"
    ),
    "No se pudo iniciar el overlay ({error})": (
        "Could not start the overlay ({error})"
    ),
    # ------------------------------------------------------------------
    # Posiciones del overlay
    # ------------------------------------------------------------------
    "Arriba derecha": "Top right",
    "Arriba izquierda": "Top left",
    "Centro izquierda": "Center left",
    "Centro derecha": "Center right",
    "Abajo derecha": "Bottom right",
    "Abajo izquierda": "Bottom left",
    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------
    "Esperando partida": "Waiting for match",
    "Abrí Arena y jugá una partida": "Open Arena and play a match",
    "MTGA COMPANION": "MTGA COMPANION",
    "DECK TRACKER": "DECK TRACKER",
    "Sin mazo activo": "No active deck",
    "TIERRAS": "LANDS",
    "PROBABILIDADES": "ODDS",
    "CATEGORÍA": "CATEGORY",
    "AHORA": "NOW",
    "3 ROBOS": "3 DRAWS",
    "MAZO RESTANTE": "REMAINING DECK",
    "CARTAS VISTAS DEL OPONENTE": "OPPONENT CARDS SEEN",
    "En partida": "In match",
    "Esperando mazo": "Waiting for deck",
    "Sin cartas en biblioteca": "No cards in library",
    "Resolviendo cartas": "Resolving cards",
    " · en play": " · on the play",
    " · en draw": " · on the draw",
    "{count} cartas · mano {hand}": "{count} cards · hand {hand}",
    "Turno {turn}{play} · {context}": "Turn {turn}{play} · {context}",
    "{count} en juego": "{count} in play",
    " ({count} sin girar)": " ({count} untapped)",
    " · {count} en mano": " · {count} in hand",
    " · {count} en biblioteca": " · {count} in library",
    "MAZO RESTANTE · {count}": "REMAINING DECK · {count}",
    "+{count} cartas más": "+{count} more cards",
    "Sin cartas restantes": "No cards remaining",
    "+{count} cartas vistas más": "+{count} more cards seen",
    "Sin cartas vistas": "No cards seen",
    "Robos naturales · sin scry, surveil ni tutores": (
        "Natural draws · no scry, surveil or tutors"
    ),
    " · {count} sin identificar": " · {count} unidentified",
    # ------------------------------------------------------------------
    # Widgets / estados del watcher
    # ------------------------------------------------------------------
    "{count} victoria": "{count} win",
    "{count} victorias": "{count} wins",
    "{count} derrota": "{count} loss",
    "{count} derrotas": "{count} losses",
    " · {count} sin resultado": " · {count} no result",
    "WINRATE GLOBAL": "GLOBAL WINRATE",
    "{total} partidas · {wins}V · {losses}D": (
        "{total} matches · {wins}W · {losses}L"
    ),
    "Esperando a que exista el Player.log...": (
        "Waiting for Player.log to exist..."
    ),
    "Observando: {path}": "Watching: {path}",
    "Archivo reemplazado, releyendo: {path}": (
        "File replaced, re-reading: {path}"
    ),
    "No se pudo leer el Player.log; reintentando...": (
        "Could not read Player.log; retrying..."
    ),
    "No se pudo guardar la partida: {error}": (
        "Could not save the match: {error}"
    ),
    "El overlay X11 no está disponible: no hay DISPLAY/XWayland.": (
        "The X11 overlay is not available: no DISPLAY/XWayland."
    ),
    "Fallback local": "Local fallback",
    "MTG Arena Player.log": "MTG Arena Player.log",
}


def normalize_language(value: object) -> str:
    """Devuelve un código de idioma válido, usando español por defecto."""
    code = str(value or "").strip().lower().split("_", 1)[0].split("-", 1)[0]
    return code if code in _LANGUAGE_CODES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _language


def set_language(value: object) -> str:
    """Cambia el idioma activo y devuelve el código normalizado."""
    global _language
    _language = normalize_language(value)
    return _language


def tr(text: str, **kwargs: object) -> str:
    """Traduce una cadena fuente y aplica placeholders de formato.

    En español se conserva la cadena original. Las claves desconocidas se
    devuelven sin cambios para que añadir un texto nuevo nunca rompa la UI.
    """
    template = _EN.get(text, text) if _language == "en" else text
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template


def runtime_message(message: object) -> str:
    """Traduce mensajes dinámicos emitidos por el watcher.

    El watcher mantiene sus mensajes internos en español para que la lógica de
    estado no dependa del idioma; esta función solo adapta lo que se muestra.
    """
    text = str(message or "")
    if text.startswith("Observando:"):
        return tr("Observando: {path}", path=text.split(":", 1)[1].strip())
    if text.startswith("Archivo reemplazado, releyendo:"):
        path = text.split(":", 1)[1].strip()
        return tr("Archivo reemplazado, releyendo: {path}", path=path)
    if text.startswith("No se pudo guardar la partida:"):
        error = text.split(":", 1)[1].strip()
        return tr("No se pudo guardar la partida: {error}", error=error)
    return tr(text)
