"""Modelos de datos del companion."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CardEntry:
    card_id: str
    quantity: int


@dataclass
class DetectedDeck:
    name: str
    fmt: str | None = None
    cards: list[CardEntry] = field(default_factory=list)
    source_module: str | None = None  # CurrentModule (CreateMatch, Complete, ...)


@dataclass
class MatchResult:
    deck: DetectedDeck | None
    result: str  # 'win' | 'loss' | 'unknown'
    opponent: str
    timestamp: str
    match_id: str | None = None
