"""Probabilidades de robo para el overlay.

El cálculo es hipergeométrico y no necesita conocer el orden de la biblioteca:
solo la cantidad de cartas restantes de cada categoría/carta y el tamaño actual
de la biblioteca.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import CARD_CACHE_PATH
from .game_state import GameSnapshot
from .i18n import tr

logger = logging.getLogger(__name__)

_CATEGORY_LABELS = {
    "lands": "Tierras",
    "creatures": "Criaturas",
    "spells": "Hechizos",
    "other": "Otras",
}


@dataclass(frozen=True)
class CategoryOdds:
    key: str
    label: str
    remaining: int
    next_probability: float
    in_three_probability: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "remaining": self.remaining,
            "next": round(self.next_probability, 4),
            "in_three": round(self.in_three_probability, 4),
        }


@dataclass(frozen=True)
class CardOdds:
    card_id: str
    name: str
    type_line: str
    remaining: int
    next_probability: float
    in_three_probability: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "type_line": self.type_line,
            "remaining": self.remaining,
            "next": round(self.next_probability, 4),
            "in_three": round(self.in_three_probability, 4),
        }


@dataclass(frozen=True)
class TrackerCard:
    card_id: str
    name: str
    type_line: str
    category: str
    remaining: int
    next_probability: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "type_line": self.type_line,
            "category": self.category,
            "remaining": self.remaining,
            "next": round(self.next_probability, 4),
        }


@dataclass(frozen=True)
class OpponentCard:
    card_id: str
    name: str
    type_line: str
    quantity: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "type_line": self.type_line,
            "quantity": self.quantity,
        }


@dataclass(frozen=True)
class DrawOdds:
    status: str = "Esperando partida"
    deck_name: str | None = None
    turn: int | None = None
    on_play: bool | None = None
    library_count: int = 0
    hand_count: int = 0
    deck_total: int = 0
    known_remaining: int = 0
    unresolved_used: int = 0
    lands_in_play: int = 0
    lands_untapped: int = 0
    lands_in_hand: int = 0
    lands_in_library: int = 0
    categories: tuple[CategoryOdds, ...] = field(default_factory=tuple)
    top_cards: tuple[CardOdds, ...] = field(default_factory=tuple)
    deck_cards: tuple[TrackerCard, ...] = field(default_factory=tuple)
    opponent_cards: tuple[OpponentCard, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "deck_name": self.deck_name,
            "turn": self.turn,
            "on_play": self.on_play,
            "library_count": self.library_count,
            "hand_count": self.hand_count,
            "deck_total": self.deck_total,
            "known_remaining": self.known_remaining,
            "unresolved_used": self.unresolved_used,
            "lands_in_play": self.lands_in_play,
            "lands_untapped": self.lands_untapped,
            "lands_in_hand": self.lands_in_hand,
            "lands_in_library": self.lands_in_library,
            "categories": [item.to_dict() for item in self.categories],
            "top_cards": [item.to_dict() for item in self.top_cards],
            "deck_cards": [item.to_dict() for item in self.deck_cards],
            "opponent_cards": [item.to_dict() for item in self.opponent_cards],
        }


def hypergeometric_at_least_one(population: int, successes: int, draws: int) -> float:
    """P(robar al menos una copia) en ``draws`` robos sin reemplazo."""
    if population <= 0 or successes <= 0 or draws <= 0:
        return 0.0
    successes = min(successes, population)
    draws = min(draws, population)
    if draws >= population - successes + 1:
        # Todos los fracasos caben en los robos: es seguro que sale una copia.
        return 1.0
    try:
        return 1.0 - math.comb(population - successes, draws) / math.comb(
            population, draws
        )
    except (ValueError, ZeroDivisionError):
        return 0.0


def _load_card_meta(cache_path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _category_for(type_line: str) -> str:
    line = (type_line or "").lower()
    if "land" in line:
        return "lands"
    if "creature" in line:
        return "creatures"
    if any(
        kind in line
        for kind in (
            "instant",
            "sorcery",
            "artifact",
            "enchantment",
            "planeswalker",
            "battle",
        )
    ):
        return "spells"
    return "other"


class DrawOddsEngine:
    """Convierte un ``GameSnapshot`` en datos listos para el overlay."""

    def __init__(
        self,
        card_meta: dict[str, dict[str, Any]] | None = None,
        cache_path: Path = CARD_CACHE_PATH,
    ):
        self._card_meta = card_meta if card_meta is not None else _load_card_meta(cache_path)

    def update_card_meta(self, cards: list[dict[str, Any]]) -> None:
        """Incorpora cartas resueltas por Scryfall sin bloquear la GUI."""
        for card in cards:
            card_id = card.get("card_id")
            if card_id is None:
                continue
            self._card_meta[str(card_id)] = {
                "name": card.get("name") or "",
                "type_line": card.get("type_line") or "",
                "found": card.get("found", True),
            }

    def has_card_meta(self, card_id: str | int) -> bool:
        return str(card_id) in self._card_meta

    @staticmethod
    def _card_label(card_id: str, meta: dict[str, Any]) -> tuple[str, str]:
        name = str(meta.get("name") or "").strip()
        type_line = str(meta.get("type_line") or "").strip()
        return (name or tr("Carta #{id}", id=card_id), type_line)

    def _opponent_cards(self, snapshot: GameSnapshot) -> tuple[OpponentCard, ...]:
        cards: list[OpponentCard] = []
        seen: set[str] = set()
        ordered = list(reversed(snapshot.opponent_order))
        ordered.extend(
            card_id
            for card_id in snapshot.opponent_revealed
            if card_id not in seen and card_id not in ordered
        )
        for card_id in ordered:
            quantity = snapshot.opponent_revealed.get(card_id, 0)
            if quantity <= 0 or card_id in seen:
                continue
            seen.add(card_id)
            meta = self._card_meta.get(card_id, {})
            name, type_line = self._card_label(card_id, meta)
            cards.append(
                OpponentCard(
                    card_id=card_id,
                    name=name,
                    type_line=type_line,
                    quantity=quantity,
                )
            )
        return tuple(cards)

    def compute(self, snapshot: GameSnapshot, draws: int = 3) -> DrawOdds:
        base = DrawOdds(
            status="Esperando partida",
            deck_name=snapshot.deck_name,
            turn=snapshot.turn,
            on_play=snapshot.on_play,
            library_count=snapshot.library_count,
            hand_count=snapshot.hand_count,
            deck_total=snapshot.deck_total,
            known_remaining=sum(snapshot.remaining_counts.values()),
            unresolved_used=snapshot.unresolved_used,
            lands_in_play=snapshot.lands_in_play,
            lands_untapped=snapshot.lands_untapped,
            lands_in_hand=snapshot.lands_in_hand,
            opponent_cards=self._opponent_cards(snapshot),
        )

        if not snapshot.in_game:
            return base
        if snapshot.deck_total <= 0:
            return DrawOdds(
                **{
                    **base.__dict__,
                    "status": "Esperando mazo",
                }
            )
        if snapshot.library_count <= 0:
            return DrawOdds(
                **{
                    **base.__dict__,
                    "status": "Sin cartas en biblioteca",
                }
            )

        population = max(1, snapshot.library_count)
        known_with_meta = sum(
            qty
            for card_id, qty in snapshot.remaining_counts.items()
            if str(card_id) in self._card_meta
        )
        if known_with_meta == 0:
            # Al abrir la app puede tardar unos segundos en resolver los IDs
            # del mazo vía Scryfall. Evitamos mostrar "Otras 100%" como si
            # fuera un dato real mientras tanto.
            return DrawOdds(
                **{
                    **base.__dict__,
                    "status": "Resolviendo cartas",
                }
            )

        category_totals = {key: 0 for key in _CATEGORY_LABELS}
        card_totals: dict[str, int] = {}

        for card_id, qty in snapshot.remaining_counts.items():
            if qty <= 0:
                continue
            meta = self._card_meta.get(str(card_id), {})
            type_line = str(meta.get("type_line") or "")
            category = _category_for(type_line)
            category_totals[category] += qty
            card_totals[str(card_id)] = card_totals.get(str(card_id), 0) + qty

        known = sum(category_totals.values())
        if known < population:
            category_totals["other"] += population - known

        categories: list[CategoryOdds] = []
        for key in ("lands", "creatures", "spells", "other"):
            count = category_totals.get(key, 0)
            categories.append(
                CategoryOdds(
                    key=key,
                    label=tr(_CATEGORY_LABELS[key]),
                    remaining=count,
                    next_probability=min(1.0, count / population),
                    in_three_probability=hypergeometric_at_least_one(
                        population, count, draws
                    ),
                )
            )

        category_order = {"lands": 0, "creatures": 1, "spells": 2, "other": 3}
        tracker_cards: list[TrackerCard] = []
        for card_id, qty in snapshot.remaining_counts.items():
            if qty <= 0:
                continue
            meta = self._card_meta.get(str(card_id), {})
            type_line = str(meta.get("type_line") or "")
            category = _category_for(type_line)
            name, type_line = self._card_label(str(card_id), meta)
            tracker_cards.append(
                TrackerCard(
                    card_id=str(card_id),
                    name=name,
                    type_line=type_line,
                    category=category,
                    remaining=qty,
                    next_probability=min(1.0, qty / population),
                )
            )
        tracker_cards.sort(
            key=lambda card: (
                category_order.get(card.category, 9),
                -card.remaining,
                card.name.casefold(),
            )
        )

        # Para "outs" preferimos cartas que no sean tierras. Si el mazo es
        # raro o todavía no hay metadatos, mostramos las de mayor cantidad.
        out_totals = {
            card_id: qty
            for card_id, qty in card_totals.items()
            if _category_for(
                str(self._card_meta.get(card_id, {}).get("type_line") or "")
            )
            != "lands"
        }
        if not out_totals:
            out_totals = card_totals

        top_cards: list[CardOdds] = []
        for card_id, qty in sorted(
            out_totals.items(),
            key=lambda item: (-item[1], self._card_label(item[0], self._card_meta.get(item[0], {}))[0].casefold()),
        ):
            meta = self._card_meta.get(card_id, {})
            name, type_line = self._card_label(card_id, meta)
            top_cards.append(
                CardOdds(
                    card_id=card_id,
                    name=name,
                    type_line=type_line,
                    remaining=qty,
                    next_probability=min(1.0, qty / population),
                    in_three_probability=hypergeometric_at_least_one(
                        population, qty, draws
                    ),
                )
            )
            if len(top_cards) >= 3:
                break

        return DrawOdds(
            status="En partida",
            deck_name=snapshot.deck_name,
            turn=snapshot.turn,
            on_play=snapshot.on_play,
            library_count=snapshot.library_count,
            hand_count=snapshot.hand_count,
            deck_total=snapshot.deck_total,
            known_remaining=known,
            unresolved_used=snapshot.unresolved_used,
            lands_in_play=snapshot.lands_in_play,
            lands_untapped=snapshot.lands_untapped,
            lands_in_hand=snapshot.lands_in_hand,
            lands_in_library=category_totals.get("lands", 0),
            categories=tuple(categories),
            top_cards=tuple(top_cards),
            deck_cards=tuple(tracker_cards),
            opponent_cards=self._opponent_cards(snapshot),
        )
