"""Cliente ligero de Scryfall para resolver nombres/imágenes de cartas por ID de Arena."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .config import BASE_DIR, CARD_CACHE_PATH
from .i18n import tr

logger = logging.getLogger(__name__)

SCRYFALL_ARENA_URL = "https://api.scryfall.com/cards/arena/{arena_id}"
SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named?fuzzy={name}"
SCRYFALL_IMAGE_URL = "https://cards.scryfall.io/normal/front/{set}/{number}.jpg"
HTTP_HEADERS = {"User-Agent": "mtga-companion/1.0 (personal use)"}
_RATE_SLEEP = 0.1  # ser amable con la API pública

# Imagen placeholder para cartas no encontradas en Scryfall
PLACEHOLDER_IMAGE_PATH = str(BASE_DIR / "gui" / "assets" / "card_placeholder.png")

# Evita escrituras simultáneas de la caché desde varios hilos.
_CACHE_FILE_LOCK = threading.Lock()


def _is_placeholder_name(name: object) -> bool:
    """Reconoce el nombre de respaldo tanto en español como en inglés."""
    return str(name or "").startswith(("Carta #", "Card #"))


class ScryfallCancelled(Exception):
    """Se lanza cuando el trabajo de Scryfall se cancela al cerrar la app."""


class ScryfallClient:
    def __init__(
        self,
        cache_path: Path = CARD_CACHE_PATH,
        cancel_event: threading.Event | None = None,
    ):
        self.cache_path = cache_path
        self._cancel_event = cancel_event
        self._cache: dict[str, dict[str, Any]] = {}
        self._load_cache()

    def _check_cancelled(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise ScryfallCancelled()

    def _sleep_rate_limit(self) -> None:
        if self._cancel_event is not None:
            if self._cancel_event.wait(_RATE_SLEEP):
                raise ScryfallCancelled()
        else:
            time.sleep(_RATE_SLEEP)

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._cache = {}

        # Compatibilidad con cachés antiguas: inferir si la carta se encontró.
        for entry in self._cache.values():
            if isinstance(entry, dict):
                name = str(entry.get("name", ""))
                entry.setdefault("found", bool(name) and not _is_placeholder_name(name))

    def _save_cache(self) -> None:
        """Guarda la caché de forma atómica y fusionando lo que haya en disco.

        Varias instancias de ScryfallClient pueden escribir a la vez (por
        ejemplo, la pestaña Mazos y la pestaña Meta). Fusionar antes de
        escribir evita que la última instancia borre entradas de las demás.
        """
        with _CACHE_FILE_LOCK:
            merged: dict[str, dict[str, Any]] = {}
            if self.cache_path.exists():
                try:
                    with open(self.cache_path, "r", encoding="utf-8") as f:
                        disk = json.load(f)
                    if isinstance(disk, dict):
                        merged.update(disk)
                except (json.JSONDecodeError, OSError):
                    merged = {}

            merged.update(self._cache)
            self._cache = merged

            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.cache_path)

    def resolve(self, arena_id: str | int) -> dict[str, Any]:
        """Devuelve {"name","image","type_line"} para un cardId de Arena."""
        self._check_cancelled()
        key = str(arena_id)
        cached = self._cache.get(key)
        if (
            isinstance(cached, dict)
            and cached.get("found", True)
            and "name" in cached
        ):
            return cached

        entry: dict[str, Any] = {
            "name": tr("Carta #{id}", id=key),
            "image": PLACEHOLDER_IMAGE_PATH,
            "type_line": "",
            "arena_id": key,
            "rarity": "",
            "found": False,
        }
        try:
            self._check_cancelled()
            resp = requests.get(
                SCRYFALL_ARENA_URL.format(arena_id=key),
                headers=HTTP_HEADERS,
                timeout=10,
            )
            self._check_cancelled()
            if resp.status_code == 200:
                data = resp.json()
                entry = {
                    "name": data.get("name", tr("Carta #{id}", id=key)),
                    "image": self._extract_image(data) or PLACEHOLDER_IMAGE_PATH,
                    "type_line": data.get("type_line", ""),
                    "arena_id": str(data.get("arena_id") or key),
                    "rarity": data.get("rarity", ""),
                    "found": True,
                }
            else:
                # Si no se encuentra por ID de Arena, no tenemos el nombre para buscar
                # por nombre, así que usamos el placeholder
                entry["name"] = tr("Carta #{id}", id=key)
        except requests.RequestException as exc:
            logger.warning("Error consultando Scryfall para arena_id=%s: %s", key, exc)

        self._cache[key] = entry
        self._save_cache()
        self._sleep_rate_limit()
        return entry

    @staticmethod
    def _extract_image(card: dict[str, Any]) -> str | None:
        if card.get("image_uris"):
            return card["image_uris"].get("normal") or card["image_uris"].get("small")
        faces = card.get("card_faces") or []
        if faces and faces[0].get("image_uris"):
            return faces[0]["image_uris"].get("normal") or faces[0]["image_uris"].get("small")
        return None

    def resolve_by_name(self, name: str) -> dict[str, Any]:
        """Resuelve una carta por su nombre (inglés) contra Scryfall."""
        self._check_cancelled()
        cached = self._cache.get(name)
        if (
            isinstance(cached, dict)
            and cached.get("found", True)
            and "name" in cached
        ):
            return cached

        entry: dict[str, Any] = {
            "name": name,
            "image": PLACEHOLDER_IMAGE_PATH,
            "type_line": "",
            "arena_id": "",
            "rarity": "",
            "found": False,
        }
        try:
            self._check_cancelled()
            resp = requests.get(
                SCRYFALL_NAMED_URL.format(name=requests.utils.quote(name)),
                headers=HTTP_HEADERS,
                timeout=10,
            )
            self._check_cancelled()
            if resp.status_code == 200:
                data = resp.json()
                entry = {
                    "name": data.get("name", name),
                    "image": self._extract_image(data) or PLACEHOLDER_IMAGE_PATH,
                    "type_line": data.get("type_line", ""),
                    "arena_id": (
                        str(data["arena_id"]) if data.get("arena_id") else ""
                    ),
                    "rarity": data.get("rarity", ""),
                    "found": True,
                }
            else:
                entry["name"] = name
        except requests.RequestException as exc:
            logger.warning("Error consultando Scryfall para %r: %s", name, exc)

        if (
            not entry.get("found")
            and isinstance(cached, dict)
            and cached.get("found", True)
            and "name" in cached
        ):
            # Una actualización fallida no debe borrar la imagen/nombre que ya
            # teníamos. Se reintentará la rareza en la próxima consulta.
            return cached

        self._cache[name] = entry
        self._save_cache()
        self._sleep_rate_limit()
        return entry

    def resolve_deck(self, card_entries) -> list[dict[str, Any]]:
        """Resuelve una lista de CardEntry (o dicts {cardId, quantity}) a
        cartas con nombre, imagen y tipo, ordenadas por cantidad."""
        cards: list[dict[str, Any]] = []
        for e in card_entries:
            self._check_cancelled()
            cid = e.card_id if hasattr(e, "card_id") else e.get("cardId")
            qty = e.quantity if hasattr(e, "quantity") else e.get("quantity", 1)
            info = self.resolve(cid)
            cards.append({
                "card_id": str(cid),
                "arena_id": str(cid),
                "name": info["name"],
                "quantity": qty,
                "image": info["image"],
                "type_line": info.get("type_line", ""),
                "rarity": info.get("rarity", ""),
                "found": info.get("found", True),
            })
        cards.sort(key=lambda c: (-c["quantity"], c["name"]))
        return cards

    def resolve_deck_by_name(self, name_qty_list: list[dict]) -> list[dict[str, Any]]:
        """Resuelve una lista de cartas por nombre ([{'name','quantity'}, ...])
        a cartas con nombre, imagen y tipo. Usado para mazos meta."""
        cards: list[dict[str, Any]] = []
        for item in name_qty_list:
            self._check_cancelled()
            name = item.get("name")
            qty = int(item.get("quantity", 1) or 1)
            if not name:
                continue
            info = self.resolve_by_name(name)
            card = {
                "card_id": name,
                "arena_id": info.get("arena_id", ""),
                "name": info["name"],
                # Nombre tal como aparece en el decklist de origen. Arena
                # suele importar la cara frontal de las aventuras/split.
                "export_name": name,
                "quantity": qty,
                "image": info["image"],
                "type_line": info.get("type_line", ""),
                "rarity": info.get("rarity", ""),
                "found": info.get("found", True),
            }
            if item.get("zone"):
                card["zone"] = item["zone"]
            cards.append(card)
        cards.sort(key=lambda c: (-c["quantity"], c["name"]))
        return cards
