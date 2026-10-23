"""Obtención de mazos meta desde internet (MTGGoldfish) y resolución
de cartas vía Scryfall. Todo diseñado para correr en un hilo aparte sin
bloquear la GUI.

Estrategia:
  * El listado de mazos meta se trae de una sola petición a MTGGoldfish.
  * Las cartas de cada mazo se traen bajo demanda, solo cuando el usuario
    selecciona un mazo.
  * Se usa el decklist de muestra que MTGGoldfish incluye en la página del
    arquetipo (main deck + sideboard), no el "Card Breakdown" agregado.
  * La caché guarda un listado por formato y expira a las 6 horas.
  * Si internet falla se usa la caché existente o un fallback local.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import META_CACHE_PATH
from .scryfall import ScryfallClient

logger = logging.getLogger(__name__)
META_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

META_CACHE_VERSION = 2
META_CACHE_TTL = 6 * 60 * 60  # 6 horas
_HEADERS = {"User-Agent": "mtga-companion/1.0 (personal use)"}

# URLs del metagame de MTGGoldfish por formato (solo la página principal, sin #paper)
MTGGOLDFISH_URLS = {
    "Standard": "https://www.mtggoldfish.com/metagame/standard/full",
    "Historic": "https://www.mtggoldfish.com/metagame/historic/full",
    "Explorer": "https://www.mtggoldfish.com/metagame/explorer/full",
    "Alchemy": "https://www.mtggoldfish.com/metagame/alchemy/full",
}

# Nombres exactos (en minúsculas) que corresponden a elementos de la interfaz.
NON_CARD_EXACT = {
    "mtggoldfish", "mtg goldfish", "mtggoldfish logo", "mtggoldfish home",
    "logo", "search", "menu", "home", "profile", "cart", "wishlist",
    "premium", "cards", "decks", "articles", "tools", "header", "footer",
    "banner", "button", "icon", "email", "discord", "facebook", "instagram",
    "twitter", "tumblr", "youtube", "rss", "sign in", "sign up", "log in",
    "log out", "login", "logout", "shopping cart", "shopping cart icon",
    "generic card back", "card back", "heavy play",
}

# Palabras que, como palabra completa, indican UI o redes sociales.
# Se comparan por palabra y no por subcadena para no descartar cartas reales
# como "Sign in Blood", "Wishclaw Talisman", "Cartouche of Ambition" o
# "Iconoclast".
NON_CARD_WORDS = {
    "discord", "facebook", "instagram", "twitter", "tumblr", "youtube",
    "rss", "mtggoldfish", "logo", "button", "banner", "footer", "header",
    "menu", "wishlist", "premium", "login", "logout",
}


def _clean_text(value: Any) -> str:
    """Normaliza espacios (incluidos los no separables) de un texto HTML."""
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _is_non_card(name: str) -> bool:
    """Devuelve True solo si el nombre es claramente UI, no una carta.

    La validación definitiva la hace Scryfall al resolver el nombre; este
    filtro es solo para no enviar basura obvia a la API. No se descartan
    nombres por cantidad de palabras ni por empezar con "The"/"A"/"An",
    porque eso eliminaba cartas reales.
    """
    n = name.strip()
    if not n:
        return True

    lower = n.casefold()

    # 1. Coincidencia exacta con nombres conocidos de UI.
    if lower in NON_CARD_EXACT:
        return True

    # 2. Fallback de Scryfall cuando no resuelve: "Carta #12345" / "Card #12345".
    if lower.startswith(("carta #", "card #")):
        return True

    # 3. Caracteres que no aparecen en nombres de cartas de Arena.
    if any(ch in n for ch in "?*"):
        return True

    # 4. URLs y textos sin letras.
    if lower.startswith(("http://", "https://", "www.")):
        return True
    if not re.search(r"[^\W\d_]", n, flags=re.UNICODE):
        return True

    # 5. Palabras de UI/redes sociales como palabra completa.
    words = set(re.findall(r"[^\W\d_]+", lower, flags=re.UNICODE))
    return bool(words & NON_CARD_WORDS)


def _parse_meta_share(value: Any) -> tuple[str | None, int | None]:
    """Extrae el porcentaje y la cantidad de mazos de un texto de MTGGoldfish.

    Ejemplos reales:
      ``META%11.5%(148)`` -> ``("11.5%", 148)``
      ``9.7%`` -> ``("9.7%", None)``
      ``Top`` -> ``(None, None)``
    """
    text = _clean_text(value)
    if not text:
        return None, None

    percent_match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    count_match = re.search(r"\((\d[\d.,]*)\)", text)
    percent = None
    if percent_match:
        percent = percent_match.group(1).replace(",", ".") + "%"
    count = None
    if count_match:
        try:
            count = int(count_match.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            count = None
    return percent, count


def _parse_price(value: Any) -> str | None:
    """Normaliza un precio de MTGGoldfish (``$ 241`` -> ``$241``)."""
    text = _clean_text(value)
    if not text:
        return None
    text = re.sub(r"\$\s+", "$", text)
    return text


def parse_decklist(text: str) -> list[dict[str, Any]]:
    """Parsea un decklist de Arena/MTGGoldfish en main deck + sideboard.

    Acepta encabezados ``Deck``/``Sideboard``, cantidades ``4 Name`` o
    ``4x Name`` y nombres con espacios o caras dobles. Devuelve diccionarios
    con ``name``, ``quantity`` y ``zone`` (``main`` o ``sideboard``).
    """
    cards: list[dict[str, Any]] = []
    zone = "main"
    ignore_section = False

    for raw_line in (text or "").splitlines():
        line = _clean_text(raw_line)
        if not line:
            continue

        header = line.casefold().rstrip(":")
        if header in {"deck", "maindeck", "main deck", "main"}:
            zone = "main"
            ignore_section = False
            continue
        if header in {"sideboard", "side board"}:
            zone = "sideboard"
            ignore_section = False
            continue
        if header in {"maybeboard", "maybe board"}:
            ignore_section = True
            continue
        if header in {"commander", "companion"}:
            zone = "main"
            ignore_section = False
            continue
        if ignore_section or line.startswith(("//", "#")):
            continue

        match = re.match(r"^(\d+)\s*[xX]?\s+(.+)$", line)
        if not match:
            continue
        quantity = max(1, int(match.group(1)))
        name = match.group(2).strip()
        if not name or _is_non_card(name):
            continue
        cards.append({"name": name, "quantity": quantity, "zone": zone})

    return cards


# ---------------------------------------------------------------------- #
# Mazos meta predefinidos (fallback si internet falla o no hay cartas).
# Se resuelven contra Scryfall al mostrarlos.
# ---------------------------------------------------------------------- #
FALLBACK_DECKS: dict[str, list[dict[str, Any]]] = {
    "Standard": [
        {
            "name": "Mono Red Aggro",
            "format": "Standard",
            "meta_share": "Top",
            "price": "$50-80",
            "source": "Fallback local",
            "cards": [
                {"name": "Monastery Swiftspear", "quantity": 4, "zone": "main"},
                {"name": "Lightning Strike", "quantity": 4, "zone": "main"},
                {"name": "Fable of the Mirror-Breaker", "quantity": 4, "zone": "main"},
                {"name": "Voltage Spike", "quantity": 4, "zone": "main"},
                {"name": "Reckless Charge", "quantity": 4, "zone": "main"},
                {"name": "Mountain", "quantity": 24, "zone": "main"},
            ],
        },
        {
            "name": "Azorius Control",
            "format": "Standard",
            "meta_share": "Top",
            "price": "$150-200",
            "source": "Fallback local",
            "cards": [
                {"name": "The Wandering Emperor", "quantity": 3, "zone": "main"},
                {"name": "Sheoldred's Edict", "quantity": 4, "zone": "main"},
                {"name": "Get Lost", "quantity": 4, "zone": "main"},
                {"name": "No More Lies", "quantity": 4, "zone": "main"},
                {"name": "Island", "quantity": 12, "zone": "main"},
                {"name": "Plains", "quantity": 12, "zone": "main"},
            ],
        },
    ],
    "Historic": [
        {
            "name": "Izzet Phoenix",
            "format": "Historic",
            "meta_share": "Top",
            "price": "$100-150",
            "source": "Fallback local",
            "cards": [
                {"name": "Arclight Phoenix", "quantity": 4, "zone": "main"},
                {"name": "Faithless Looting", "quantity": 4, "zone": "main"},
                {"name": "Lightning Helix", "quantity": 4, "zone": "main"},
                {"name": "Mountain", "quantity": 12, "zone": "main"},
                {"name": "Island", "quantity": 12, "zone": "main"},
            ],
        },
    ],
    "Explorer": [],
    "Alchemy": [],
}


class MetaFetcher:
    """Lógica síncrona de obtención de mazos meta. Se invoca desde un hilo."""

    def __init__(self, cache_path: Path = META_CACHE_PATH):
        self.cache_path = Path(cache_path)
        self.scryfall = ScryfallClient()

    # ------------------------------------------------------------------ #
    # 1. Listado de mazos meta (una sola petición)
    # ------------------------------------------------------------------ #
    def fetch_mtggoldfish_meta(self, format_name: str = "Standard") -> list[dict[str, Any]]:
        """Scrapea los mazos meta de MTGGoldfish para un formato dado.

        Devuelve mazos con nombre, meta share, cantidad de mazos, precios,
        URL del arquetipo y las tres cartas destacadas. Las cartas completas
        se dejan vacías y se cargan bajo demanda con ``fetch_deck_cards``.
        """
        url = MTGGOLDFISH_URLS.get(format_name, MTGGOLDFISH_URLS["Standard"])

        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        decks: list[dict[str, Any]] = []
        for tile in soup.select(".archetype-tile"):
            title_link = (
                tile.select_one(".archetype-tile-title .deck-price-online a")
                or tile.select_one(".archetype-tile-title a")
            )
            if title_link is None:
                continue

            name = _clean_text(title_link.get_text(" ", strip=True))
            if not name:
                continue

            href = (title_link.get("href") or "").split("#", 1)[0].strip()
            archetype_url = (
                urljoin("https://www.mtggoldfish.com/", href) if href else None
            )

            share_el = tile.select_one(
                ".metagame-percentage .archetype-tile-statistic-value"
            )
            share_text = _clean_text(share_el.get_text(" ", strip=True)) if share_el else ""
            share, share_count = _parse_meta_share(share_text)

            paper_el = tile.select_one(
                ".archetype-tile-statistics-right "
                ".deck-price-paper .archetype-tile-statistic-value"
            )
            mtgo_el = tile.select_one(
                ".archetype-tile-statistics-right "
                ".deck-price-online .archetype-tile-statistic-value"
            )
            price_paper = _parse_price(
                paper_el.get_text(" ", strip=True) if paper_el else None
            )
            price_mtgo = _parse_price(
                mtgo_el.get_text(" ", strip=True) if mtgo_el else None
            )

            top_card_items = tile.select(".archetype-tile-description ul li")
            if not top_card_items:
                top_card_items = tile.select("ul li")
            top_cards = [
                _clean_text(li.get_text(" ", strip=True))
                for li in top_card_items
            ]
            top_cards = [name for name in top_cards if name and not _is_non_card(name)][:3]

            decks.append({
                "name": name,
                "format": format_name,
                "meta_share": share or (share_text or None),
                "meta_share_count": share_count,
                "price": price_paper or price_mtgo,
                "price_paper": price_paper,
                "price_mtgo": price_mtgo,
                "url": archetype_url,
                "source": "MTGGoldfish",
                "top_cards": top_cards,
                "cards": [],
            })

        return decks

    # ------------------------------------------------------------------ #
    # 2. Cartas de un mazo específico (bajo demanda)
    # ------------------------------------------------------------------ #
    def _resolve_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resuelve nombres contra Scryfall y descarta los que no existen.

        Si Scryfall no está disponible (todas las resoluciones fallan), se
        devuelven los candidatos sin filtrar para no dejar el mazo vacío.
        """
        resolved = self.scryfall.resolve_deck_by_name(candidates)
        found = [card for card in resolved if card.get("found", True)]
        return found or resolved

    @staticmethod
    def _parse_deck_input(soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Extrae el decklist de muestra oculto en la página del arquetipo."""
        field = soup.find("input", id="deck_input_deck")
        if field is None:
            field = soup.find("input", attrs={"name": "deck_input[deck]"})
        if field is None:
            return []
        return parse_decklist(field.get("value") or "")

    @staticmethod
    def _parse_card_breakdown(soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Fallback: usa la sección Card Breakdown si no hay decklist de muestra.

        Solo recorre las tarjetas dentro de ``.spoiler-card-container`` para
        no confundir logos, iconos ni elementos de la interfaz con cartas.
        """
        breakdown = soup.select_one(".deck-archetype-breakdown")
        if breakdown is None:
            return []

        cards: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for container in breakdown.select(".spoiler-card-container"):
            heading = container.find("h3")
            heading_text = _clean_text(heading.get_text(" ", strip=True)) if heading else ""
            zone = "sideboard" if "sideboard" in heading_text.casefold() else "main"

            for card_el in container.select(".spoiler-card"):
                img = card_el.find("img", alt=True)
                label = card_el.select_one(".price-card-invisible-label")
                alt = _clean_text(img.get("alt")) if img else ""
                fallback_name = _clean_text(label.get_text(" ", strip=True)) if label else ""
                name = re.split(r"\s*[\[<]", alt or fallback_name)[0].strip()
                if not name or (name, zone) in seen or _is_non_card(name):
                    continue

                text = _clean_text(card_el.get_text(" ", strip=True))
                qty_match = re.search(
                    r"(\d+(?:[.,]\d+)?)\s+in\s+\d+%\s+of\s+decks", text
                )
                if not qty_match:
                    continue
                quantity = max(1, round(float(qty_match.group(1).replace(",", "."))))
                cards.append({"name": name, "quantity": quantity, "zone": zone})
                seen.add((name, zone))

        return cards

    def fetch_deck_cards(self, archetype_url: str) -> list[dict[str, Any]]:
        """Extrae el decklist de muestra de un arquetipo y resuelve sus cartas.

        Prioriza el campo oculto ``deck_input[deck]`` (main deck + sideboard).
        Si no está disponible, cae al "Card Breakdown" popular. Devuelve
        cartas con ``name``, ``quantity``, ``zone``, imagen y ``type_line``.
        """
        resp = requests.get(archetype_url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        candidates = self._parse_deck_input(soup)
        if not candidates:
            candidates = self._parse_card_breakdown(soup)
        if not candidates:
            return []

        return self._resolve_candidates(candidates)

    # ------------------------------------------------------------------ #
    # 3. Caché por formato con TTL
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clean_deck(deck: dict[str, Any]) -> dict[str, Any]:
        """Normaliza datos de una carta/mazo leídos de caché o de la web."""
        clean = dict(deck)
        clean.setdefault("cards", [])
        clean.setdefault("source", "MTGGoldfish")

        share, count = _parse_meta_share(clean.get("meta_share"))
        if share:
            clean["meta_share"] = share
        elif clean.get("meta_share"):
            clean["meta_share"] = _clean_text(clean["meta_share"])
        if count is not None:
            clean["meta_share_count"] = count

        # Compatibilidad con cachés antiguas que solo guardaban "price".
        price = clean.get("price")
        if price and not clean.get("price_paper") and not clean.get("price_mtgo"):
            cleaned_price = _parse_price(price)
            if cleaned_price and "$" in cleaned_price:
                clean["price_paper"] = cleaned_price
            elif cleaned_price and "tix" in cleaned_price.casefold():
                clean["price_mtgo"] = cleaned_price
            clean["price"] = cleaned_price
        for key in ("price_paper", "price_mtgo"):
            if clean.get(key):
                clean[key] = _parse_price(clean[key])
        return clean

    @classmethod
    def _normalize_cache(cls, data: Any) -> dict[str, Any]:
        """Migra la caché antigua (un solo formato) al formato por formato."""
        empty = {"version": META_CACHE_VERSION, "formats": {}}
        if not isinstance(data, dict):
            return empty

        formats: dict[str, Any] = {}
        raw_formats = data.get("formats")
        if isinstance(raw_formats, dict):
            for fmt, entry in raw_formats.items():
                if not isinstance(entry, dict):
                    continue
                decks = entry.get("decks")
                if not isinstance(decks, list):
                    decks = []
                formats[str(fmt)] = {
                    "updated_at": entry.get("updated_at"),
                    "decks": [
                        cls._clean_deck(d) for d in decks if isinstance(d, dict)
                    ],
                    "source": entry.get("source") or "MTGGoldfish",
                }

        # Formato heredado: {updated_at, format, decks}
        legacy_format = data.get("format")
        legacy_decks = data.get("decks")
        if isinstance(legacy_format, str) and isinstance(legacy_decks, list):
            formats.setdefault(
                legacy_format,
                {
                    "updated_at": data.get("updated_at"),
                    "decks": [
                        cls._clean_deck(d)
                        for d in legacy_decks
                        if isinstance(d, dict)
                    ],
                    "source": "MTGGoldfish",
                },
            )

        return {"version": META_CACHE_VERSION, "formats": formats}

    def _read_cache(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {"version": META_CACHE_VERSION, "formats": {}}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("No se pudo leer la caché meta %s", self.cache_path)
            return {"version": META_CACHE_VERSION, "formats": {}}
        return self._normalize_cache(data)

    def _write_cache(self, cache: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.cache_path)

    def _save_cached_meta(self, format_name: str, decks: list[dict[str, Any]]) -> None:
        cache = self._read_cache()
        source = "MTGGoldfish"
        if decks:
            source = str(decks[0].get("source") or source)
        cache["version"] = META_CACHE_VERSION
        cache.setdefault("formats", {})[format_name] = {
            "updated_at": time.time(),
            "decks": decks,
            "source": source,
        }
        try:
            self._write_cache(cache)
        except OSError:
            logger.exception("No se pudo guardar la caché meta")

    @staticmethod
    def is_cache_stale(updated_at: Any, now: float | None = None) -> bool:
        """Devuelve True si la caché no tiene fecha o superó el TTL."""
        if updated_at is None:
            return True
        try:
            timestamp = float(updated_at)
        except (TypeError, ValueError):
            return True
        return (now if now is not None else time.time()) - timestamp > META_CACHE_TTL

    def load_cached_meta(self, format_name: str | None = None) -> dict[str, Any]:
        """Devuelve la caché del formato pedido (o la más reciente).

        El resultado conserva la forma histórica ``updated_at``/``format``/
        ``decks`` y agrega ``stale`` y ``ttl``.
        """
        cache = self._read_cache()
        formats = cache.get("formats", {})
        if not formats:
            return {
                "updated_at": None,
                "format": format_name,
                "decks": [],
                "stale": True,
                "ttl": META_CACHE_TTL,
            }

        if format_name is not None and format_name not in formats:
            return {
                "updated_at": None,
                "format": format_name,
                "decks": [],
                "stale": True,
                "ttl": META_CACHE_TTL,
            }

        selected = format_name
        if selected is None:
            def _updated(item: tuple[str, dict[str, Any]]) -> float:
                try:
                    return float(item[1].get("updated_at") or 0)
                except (TypeError, ValueError):
                    return 0.0

            selected, _ = max(formats.items(), key=_updated)

        entry = formats.get(selected, {})
        updated_at = entry.get("updated_at")
        return {
            "updated_at": updated_at,
            "format": selected,
            "decks": entry.get("decks", []),
            "source": entry.get("source"),
            "stale": self.is_cache_stale(updated_at),
            "ttl": META_CACHE_TTL,
        }

    # ------------------------------------------------------------------ #
    # 4. Entrada principal
    # ------------------------------------------------------------------ #
    def fetch_meta(
        self, format_name: str = "Standard", force: bool = False
    ) -> list[dict[str, Any]]:
        """Devuelve la lista de mazos meta (sin cartas resueltas aún).

        Si ``force`` es False y hay caché fresca del formato, no se hace
        ninguna petición de red. Si la red falla se usa la caché existente
        (aunque esté vencida) o el fallback local.
        """
        if not force:
            cached = self.load_cached_meta(format_name)
            if cached["decks"] and not cached["stale"]:
                logger.info(
                    "Usando caché meta fresca de %s (%d mazos)",
                    format_name,
                    len(cached["decks"]),
                )
                return cached["decks"]

        try:
            decks = self.fetch_mtggoldfish_meta(format_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error obteniendo mazos meta: %s", exc)
            decks = []

        if decks:
            self._save_cached_meta(format_name, decks)
            return decks

        cached = self.load_cached_meta(format_name)
        if cached["decks"]:
            logger.info(
                "Usando caché meta de %s por fallo de red (%d mazos)",
                format_name,
                len(cached["decks"]),
            )
            return cached["decks"]

        logger.info("Usando mazos meta predefinidos (fallback)")
        return [
            {**deck, "cards": []}
            for deck in FALLBACK_DECKS.get(format_name, [])
        ]
