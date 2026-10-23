"""Posiciones admitidas para el panel del overlay."""
from __future__ import annotations

DEFAULT_POSITION = "middle-left"

POSITION_ITEMS = (
    ("Arriba derecha", "top-right"),
    ("Arriba izquierda", "top-left"),
    ("Centro izquierda", "middle-left"),
    ("Centro derecha", "middle-right"),
    ("Abajo derecha", "bottom-right"),
    ("Abajo izquierda", "bottom-left"),
)

POSITION_KEYS = tuple(key for _label, key in POSITION_ITEMS)


def normalize_position(value: str | None) -> str:
    """Devuelve una posición válida, usando el centro izquierdo por defecto."""
    position = str(value or "")
    return position if position in POSITION_KEYS else DEFAULT_POSITION
