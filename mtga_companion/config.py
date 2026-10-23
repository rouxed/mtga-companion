"""Configuración, rutas XDG y detección automática del Player.log de MTG Arena."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
APP_DIR_NAME = "mtga-companion"


def _xdg_home(env_var: str, default_relative: str) -> Path:
    """Devuelve el directorio base XDG, respetando la variable de entorno."""
    value = os.environ.get(env_var, "").strip()
    if value:
        return Path(value).expanduser()
    return Path.home() / default_relative


DATA_DIR = _xdg_home("XDG_DATA_HOME", ".local/share") / APP_DIR_NAME
CONFIG_DIR = _xdg_home("XDG_CONFIG_HOME", ".config") / APP_DIR_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "mtga_companion.db"
CARD_CACHE_PATH = DATA_DIR / "card_cache.json"
META_CACHE_PATH = DATA_DIR / "meta_cache.json"
CARD_IMAGES_DIR = DATA_DIR / "card_images"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
LOG_DIR = DATA_DIR / "logs"

# Datos de versiones anteriores que vivían dentro del paquete.
LEGACY_DATA_DIR = BASE_DIR / "data"

# ID de Steam de MTG Arena
STEAM_APP_ID = "2141910"

# Nombre de jugador por defecto (se sobrescribe con settings.json / variable de entorno)
DEFAULT_PLAYER_NAME = os.environ.get("MTGA_PLAYER_NAME", "")

# Marcadores del Player.log de MTG Arena (confirmados contra logs reales)
DECK_SUBMIT_MARKER = '"CourseDeckSummary"'
MATCH_COMPLETE_MARKER = "matchGameRoomStateChangedEvent"
MATCH_COMPLETE_STATE = "MatchGameRoomStateType_MatchCompleted"

_VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')


def _parse_library_folders(vdf_path: Path) -> list[Path]:
    """Extrae las rutas de biblioteca de un ``libraryfolders.vdf`` de Steam.

    No se usa una dependencia externa para parsear VDF: el archivo real solo
    necesita las claves ``"path"``.
    """
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [Path(raw.replace("\\\\", "\\")) for raw in _VDF_PATH_RE.findall(text)]


@dataclass(frozen=True)
class LogCandidate:
    """Un Player.log encontrado y el launcher/prefijo que lo contiene."""

    path: Path
    source: str
    prefix: Path | None = None
    mtime: float = 0.0
    size: int = 0

    @property
    def modified_label(self) -> str:
        if not self.mtime:
            return "sin fecha"
        try:
            return datetime.fromtimestamp(self.mtime).strftime("%d/%m/%Y %H:%M")
        except (OSError, OverflowError, ValueError):
            return "sin fecha"


# Glob interno de todos los prefijos Wine/Proton. No se asume "steamuser":
# cada instalación puede usar un usuario distinto (steamuser, root, etc.).
_PREFIX_LOG_GLOB = (
    "drive_c/users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log"
)
_WINDOWS_LOG_GLOBS = (
    "*/Users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    "*/*/Users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    "Users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
)

_SOURCE_PRIORITY = {
    "Variable MTGA_LOG_PATH": 200,
    "WINEPREFIX": 160,
    "Steam": 120,
    "Steam (Flatpak)": 119,
    "Steam (juego no Steam)": 115,
    "Lutris": 105,
    "Heroic / Epic": 100,
    "Bottles": 95,
    "Wine": 80,
    "Prefijo Wine": 70,
    "Partición Windows": 60,
}

_PREFIX_YAML_RE = re.compile(
    r"^\s*(?:prefix|wineprefix|wine_prefix|wine-prefix)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _steam_roots(home: Path | None = None) -> list[Path]:
    home = Path(home) if home else Path.home()
    return [
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "root",
    ]


def _steam_libraries(home: Path | None = None) -> list[Path]:
    """Bibliotecas Steam conocidas, incluyendo las de libraryfolders.vdf."""
    libraries: list[Path] = []
    for root in _steam_roots(home):
        libraries.append(root)
        libraries.extend(
            _parse_library_folders(root / "steamapps" / "libraryfolders.vdf")
        )
    return list(dict.fromkeys(libraries))


def _compat_log_path(library: Path) -> Path:
    """Ruta clásica de Steam con usuario ``steamuser`` (compatibilidad)."""
    return (
        library
        / "steamapps"
        / "compatdata"
        / STEAM_APP_ID
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "AppData"
        / "LocalLow"
        / "Wizards Of The Coast"
        / "MTGA"
        / "Player.log"
    )


def _logs_in_prefix(prefix: Path, source: str) -> list[LogCandidate]:
    """Busca el Player.log dentro de un prefijo Wine/Proton."""
    found: list[LogCandidate] = []
    try:
        paths = prefix.glob(_PREFIX_LOG_GLOB)
    except OSError:
        return found
    for path in paths:
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        found.append(
            LogCandidate(
                path=path,
                source=source,
                prefix=prefix,
                mtime=stat.st_mtime,
                size=stat.st_size,
            )
        )
    return found


def _steam_prefixes(home: Path | None = None) -> list[tuple[Path, str]]:
    """Prefijos de Steam, incluidos app IDs no estándar para juegos agregados."""
    prefixes: list[tuple[Path, str]] = []
    for library in _steam_libraries(home):
        is_flatpak = ".var/app/com.valvesoftware.Steam" in str(library)
        source = "Steam (Flatpak)" if is_flatpak else "Steam"
        compatdata = library / "steamapps" / "compatdata"
        app_prefix = compatdata / STEAM_APP_ID / "pfx"
        if app_prefix.is_dir():
            prefixes.append((app_prefix, source))
        if compatdata.is_dir():
            try:
                other_prefixes = compatdata.glob("*/pfx")
            except OSError:
                other_prefixes = []
            for prefix in other_prefixes:
                if prefix.parent.name == STEAM_APP_ID:
                    continue
                if prefix.is_dir():
                    prefixes.append((prefix, "Steam (juego no Steam)"))
    return list(dict.fromkeys(prefixes))


def _clean_config_path(raw: str) -> Path | None:
    value = raw.strip().strip("'\"")
    if not value:
        return None
    value = os.path.expandvars(os.path.expanduser(value))
    path = Path(value)
    return path if path.is_absolute() else None


def _xdg_base(env: dict[str, str], key: str, home: Path, default: str) -> Path:
    raw = env.get(key, "").strip()
    return Path(raw).expanduser() if raw else home / default


def _lutris_config_dirs(home: Path, env: dict[str, str]) -> list[Path]:
    xdg_config = _xdg_base(env, "XDG_CONFIG_HOME", home, ".config")
    xdg_data = _xdg_base(env, "XDG_DATA_HOME", home, ".local/share")
    return list(dict.fromkeys([
        xdg_config / "lutris" / "games",
        xdg_data / "lutris" / "games",
        home / ".config" / "lutris" / "games",
        home / ".local" / "share" / "lutris" / "games",
        home / ".var" / "app" / "net.lutris.Lutris" / "config" / "lutris" / "games",
        home / ".var" / "app" / "net.lutris.Lutris" / "data" / "lutris" / "games",
    ]))


def _lutris_prefixes(home: Path, env: dict[str, str]) -> list[Path]:
    prefixes: list[Path] = []
    for directory in _lutris_config_dirs(home, env):
        if not directory.is_dir():
            continue
        try:
            configs = list(directory.glob("*.yml")) + list(directory.glob("*.yaml"))
        except OSError:
            continue
        for config in configs:
            try:
                text = config.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in _PREFIX_YAML_RE.finditer(text):
                path = _clean_config_path(match.group(1))
                if path and path.is_dir():
                    prefixes.append(path)
    return list(dict.fromkeys(prefixes))


def _heroic_config_dirs(home: Path, env: dict[str, str]) -> list[Path]:
    xdg_config = _xdg_base(env, "XDG_CONFIG_HOME", home, ".config")
    return list(dict.fromkeys([
        xdg_config / "heroic" / "GamesConfig",
        xdg_config / "heroic" / "gamesconfig",
        home / ".config" / "heroic" / "GamesConfig",
        home / ".config" / "heroic" / "gamesconfig",
        home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic" / "GamesConfig",
        home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic" / "gamesconfig",
    ]))


def _json_prefix_values(value) -> list[str]:
    """Extrae valores de claves relacionadas con prefijos de un JSON de Heroic."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            if isinstance(item, str) and "prefix" in key_lower:
                found.append(item)
            else:
                found.extend(_json_prefix_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_json_prefix_values(item))
    return found


def _heroic_prefixes(home: Path, env: dict[str, str]) -> list[Path]:
    prefixes: list[Path] = []
    for directory in _heroic_config_dirs(home, env):
        if not directory.is_dir():
            continue
        try:
            configs = list(directory.glob("*.json"))
        except OSError:
            continue
        for config in configs:
            try:
                data = json.loads(config.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, ValueError):
                continue
            for raw in _json_prefix_values(data):
                path = _clean_config_path(raw)
                if path and path.is_dir():
                    prefixes.append(path)
    xdg_data = _xdg_base(env, "XDG_DATA_HOME", home, ".local/share")
    for root in (
        home / "Games" / "Heroic" / "Prefixes",
        home / ".local" / "share" / "heroic" / "Prefixes",
        xdg_data / "heroic" / "Prefixes",
    ):
        prefixes.extend(_iter_prefix_dirs(root, max_depth=2))
    return list(dict.fromkeys(prefixes))


def _bottles_prefixes(home: Path, env: dict[str, str]) -> list[Path]:
    xdg_data = _xdg_base(env, "XDG_DATA_HOME", home, ".local/share")
    roots = [
        xdg_data / "bottles" / "bottles",
        home / ".local" / "share" / "bottles" / "bottles",
        home / ".var" / "app" / "com.usebottles.bottles" / "data" / "bottles" / "bottles",
    ]
    prefixes: list[Path] = []
    for root in roots:
        prefixes.extend(_iter_prefix_dirs(root, max_depth=1))
    return list(dict.fromkeys(prefixes))


def _common_prefix_roots(home: Path, env: dict[str, str]) -> list[Path]:
    xdg_data = _xdg_base(env, "XDG_DATA_HOME", home, ".local/share")
    return [
        home / "Games",
        home / "games",
        home / "Juegos",
        home / "Lutris",
        home / "Wine",
        home / "GOG Games",
        home / "Epic Games",
        home / "Prefixes",
        home / "prefixes",
        home / "wineprefixes",
        home / ".local" / "share" / "wineprefixes",
        xdg_data / "wineprefixes",
        home / ".wine",
        home / ".PlayOnLinux" / "wineprefix",
        home / ".local" / "share" / "PlayOnLinux" / "wineprefix",
        home / ".cxoffice",
    ]


def _iter_prefix_dirs(root: Path, max_depth: int = 2) -> list[Path]:
    """Busca directorios que contengan ``drive_c`` sin recorrer todo el home."""
    found: list[Path] = []
    if not root.is_dir():
        return found

    def walk(directory: Path, depth: int) -> None:
        if (directory / "drive_c").is_dir():
            found.append(directory)
            return
        if depth >= max_depth:
            return
        try:
            children = list(directory.iterdir())
        except (OSError, RuntimeError):
            return
        for child in children:
            if child.is_dir():
                walk(child, depth + 1)

    walk(root, 0)
    return list(dict.fromkeys(found))


def _windows_logs(mount_roots: tuple[Path, ...]) -> list[Path]:
    logs: list[Path] = []
    for mount in mount_roots:
        if not mount.is_dir():
            continue
        for pattern in _WINDOWS_LOG_GLOBS:
            try:
                logs.extend(path for path in mount.glob(pattern) if path.is_file())
            except OSError:
                continue
    return list(dict.fromkeys(logs))


def _env_prefixes(env: dict[str, str]) -> list[tuple[Path, str]]:
    prefixes: list[tuple[Path, str]] = []
    for key in ("WINEPREFIX", "MTGA_WINE_PREFIX"):
        raw = env.get(key, "").strip()
        if not raw:
            continue
        path = Path(os.path.expanduser(os.path.expandvars(raw)))
        if path.is_dir():
            prefixes.append((path, "WINEPREFIX"))
    compat_data = env.get("STEAM_COMPAT_DATA_PATH", "").strip()
    if compat_data:
        path = Path(os.path.expanduser(os.path.expandvars(compat_data)))
        pfx = path / "pfx" if path.name != "pfx" else path
        if pfx.is_dir():
            prefixes.append((pfx, "Steam"))
    return prefixes


def discover_log_candidates(
    home: Path | None = None,
    mount_roots: tuple[Path, ...] | None = None,
    env: dict[str, str] | None = None,
) -> list[LogCandidate]:
    """Descubre todos los Player.log de instalaciones Wine/Proton.

    Combina rutas de Steam, Lutris, Heroic/Epic, Bottles, Wine manual,
    variables de entorno y particiones Windows montadas. Devuelve primero
    el log modificado más recientemente, que suele ser el de la instalación
    activa. Los duplicados se resuelven conservando la fuente más específica.
    """
    home = Path(home) if home else Path.home()
    env = dict(os.environ) if env is None else dict(env)
    mounts = (
        (Path("/run/media"), Path("/mnt"), Path("/media"))
        if mount_roots is None
        else tuple(mount_roots)
    )

    candidates: dict[Path, LogCandidate] = {}

    def register(candidate: LogCandidate) -> None:
        try:
            if not candidate.path.is_file():
                return
            key = candidate.path.resolve(strict=False)
            stat = candidate.path.stat()
        except (OSError, RuntimeError):
            return
        candidate = LogCandidate(
            path=candidate.path,
            source=candidate.source,
            prefix=candidate.prefix,
            mtime=stat.st_mtime,
            size=stat.st_size,
        )
        previous = candidates.get(key)
        if previous is None:
            candidates[key] = candidate
            return
        previous_priority = _SOURCE_PRIORITY.get(previous.source, 0)
        new_priority = _SOURCE_PRIORITY.get(candidate.source, 0)
        if new_priority > previous_priority or (
            new_priority == previous_priority and candidate.mtime > previous.mtime
        ):
            candidates[key] = candidate

    explicit_log = env.get("MTGA_LOG_PATH", "").strip()
    if explicit_log:
        register(
            LogCandidate(
                path=Path(os.path.expanduser(os.path.expandvars(explicit_log))),
                source="Variable MTGA_LOG_PATH",
            )
        )

    for prefix, source in _env_prefixes(env):
        for candidate in _logs_in_prefix(prefix, source):
            register(candidate)

    for prefix, source in _steam_prefixes(home):
        for candidate in _logs_in_prefix(prefix, source):
            register(candidate)

    for prefix in _lutris_prefixes(home, env):
        for candidate in _logs_in_prefix(prefix, "Lutris"):
            register(candidate)

    for prefix in _heroic_prefixes(home, env):
        for candidate in _logs_in_prefix(prefix, "Heroic / Epic"):
            register(candidate)

    for prefix in _bottles_prefixes(home, env):
        for candidate in _logs_in_prefix(prefix, "Bottles"):
            register(candidate)

    for root in _common_prefix_roots(home, env):
        for prefix in _iter_prefix_dirs(root, max_depth=2):
            for candidate in _logs_in_prefix(prefix, "Prefijo Wine"):
                register(candidate)

    for path in _windows_logs(mounts):
        register(LogCandidate(path=path, source="Partición Windows"))

    def sort_key(item: LogCandidate) -> tuple[int, float, int, str]:
        explicit = item.source in {"Variable MTGA_LOG_PATH", "WINEPREFIX"}
        return (
            1 if explicit else 0,
            item.mtime,
            _SOURCE_PRIORITY.get(item.source, 0),
            str(item.path),
        )

    return sorted(candidates.values(), key=sort_key, reverse=True)


def candidate_log_paths() -> list[Path]:
    """Rutas candidatas al Player.log, de la más reciente a la más antigua."""
    return [candidate.path for candidate in discover_log_candidates()]


def detect_log_path() -> Path | None:
    """Devuelve la mejor ruta detectada, o None."""
    for path in candidate_log_paths():
        if path.is_file():
            return path
    return None


def _copy_if_missing(source: Path, destination: Path) -> bool:
    """Copia un archivo de datos antiguo si el nuevo todavía no existe."""
    if not source.is_file():
        return False
    if destination.exists() and destination.stat().st_size > 0:
        return False

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.parent / (destination.name + ".tmp")
        shutil.copy2(source, tmp_path)
        os.replace(tmp_path, destination)
        logger.info("Migrado %s -> %s", source, destination)
        return True
    except OSError:
        logger.exception("No se pudo migrar %s a %s", source, destination)
        return False


def _migrate_images(source: Path, destination: Path) -> int:
    """Copia las imágenes de caché que falten, sin sobrescribir las nuevas."""
    if not source.is_dir():
        return 0

    copied = 0
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            if not item.is_file():
                continue
            target = destination / item.name
            if target.exists():
                continue
            try:
                shutil.copy2(item, target)
                copied += 1
            except OSError:
                logger.warning("No se pudo migrar la imagen %s", item)
    except OSError:
        logger.exception("No se pudo crear el directorio de imágenes %s", destination)

    if copied:
        logger.info("Migradas %s imágenes de caché a %s", copied, destination)
    return copied


def ensure_app_data(
    data_dir: Path | None = None,
    config_dir: Path | None = None,
    legacy_dir: Path | None = None,
) -> None:
    """Crea los directorios XDG y migra datos de la versión anterior.

    Es idempotente: nunca sobrescribe una base, caché o configuración nueva.
    Los datos antiguos se copian (no se borran), así que el usuario conserva
    una copia de seguridad en el directorio del paquete.
    """
    data_dir = data_dir or DATA_DIR
    config_dir = config_dir or CONFIG_DIR
    legacy_dir = legacy_dir or BASE_DIR
    legacy_data = legacy_dir / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    _copy_if_missing(legacy_data / "mtga_companion.db", data_dir / "mtga_companion.db")
    _copy_if_missing(legacy_dir / "card_cache.json", data_dir / "card_cache.json")
    _copy_if_missing(legacy_data / "meta_cache.json", data_dir / "meta_cache.json")
    _copy_if_missing(legacy_dir / "settings.json", config_dir / "settings.json")
    _migrate_images(legacy_data / "card_images", data_dir / "card_images")


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        logger.warning("No se pudo leer la configuración %s", SETTINGS_PATH)
        return {}


def save_settings(settings: dict) -> None:
    """Guarda la configuración de forma atómica."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = SETTINGS_PATH.parent / (SETTINGS_PATH.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SETTINGS_PATH)
    except OSError:
        logger.exception("No se pudo guardar la configuración %s", SETTINGS_PATH)
