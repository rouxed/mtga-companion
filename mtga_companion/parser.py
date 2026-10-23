"""Parser del Player.log de MTG Arena.

Extrae:
  * mazos activos (CourseDeckSummary + CourseDeck) y
  * resultados de partida (matchGameRoomStateChangedEvent + MatchCompleted).

El formato del log no es un estándar documentado; estos son los marcadores más
estables usados por la comunidad (igual que el proyecto previo y Untapped.gg).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .models import CardEntry, MatchResult

DECK_SUBMIT_MARKER = '"CourseDeckSummary"'
MATCH_COMPLETE_MARKER = "matchGameRoomStateChangedEvent"
MATCH_COMPLETE_STATE = "MatchGameRoomStateType_MatchCompleted"


def _extract_json_blob(line: str, start_idx: int) -> dict[str, Any] | None:
    """Extrae el primer objeto JSON balanceado que empieza en start_idx."""
    depth = 0
    buf: list[str] = []
    started = False
    for ch in line[start_idx:]:
        if ch == "{":
            depth += 1
            started = True
        if started:
            buf.append(ch)
        if ch == "}":
            depth -= 1
            if started and depth == 0:
                break
    try:
        return json.loads("".join(buf))
    except json.JSONDecodeError:
        return None


def _find_course_dicts(obj: Any) -> list[dict[str, Any]]:
    """Busca recursivamente dicts que tengan CourseDeckSummary y CourseDeck."""
    found: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if "CourseDeckSummary" in obj and "CourseDeck" in obj:
            found.append(obj)
        for v in obj.values():
            found.extend(_find_course_dicts(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_course_dicts(item))
    return found


def _pick_active_course(courses: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefiere el curso con CurrentModule == 'CreateMatch' (mazo que se va a usar)."""
    for c in courses:
        if c.get("CurrentModule") == "CreateMatch":
            return c
    return courses[0] if courses else None


def normalize_deck_cards(raw: list[Any] | None) -> list[CardEntry]:
    """Convierte MainDeck ([{cardId, quantity}, ...]) en una lista de CardEntry."""
    entries: list[CardEntry] = []
    if not raw:
        return entries
    for item in raw:
        if isinstance(item, dict):
            cid = item.get("cardId") or item.get("id") or item.get("grpId")
            qty = int(item.get("quantity", 1) or 1)
        else:
            cid, qty = item, 1
        if cid is None:
            continue
        entries.append(CardEntry(card_id=str(cid), quantity=qty))
    return entries


def _same_player(name_a: str, name_b: str) -> bool:
    """Compara nombres de Arena aceptando que el log omita el ``#tag``."""
    a = (name_a or "").strip()
    b = (name_b or "").strip()
    if not a or not b:
        return False
    if a.casefold() == b.casefold():
        return True
    return a.split("#", 1)[0].casefold() == b.split("#", 1)[0].casefold()


def _epoch_ms_to_iso(value: Any) -> str:
    """Convierte el ``timestamp`` (epoch en ms) del log a ISO UTC.

    Arena escribe milisegundos, pero se toleran segundos por si cambia el
    formato. Devuelve cadena vacía si no hay timestamp válido.
    """
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return ""
        try:
            numeric = float(value)
        except ValueError:
            return ""
    elif isinstance(value, (int, float)):
        numeric = float(value)
    else:
        return ""
    if numeric <= 0:
        return ""
    seconds = numeric / 1000.0 if numeric > 10_000_000_000 else numeric
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def parse_match_result(data: dict[str, Any], player_name: str | None) -> MatchResult:
    """Dado el JSON de una línea matchGameRoomStateChangedEvent, calcula el
    resultado y el oponente relativo a player_name.

    Si no se conoce el nombre del jugador, el resultado queda como
    ``unknown`` y el oponente como ``desconocido``: es preferible no mostrar
    un dato que mostrarlo mal.
    """
    event = data.get("matchGameRoomStateChangedEvent", {})
    room = event.get("gameRoomInfo", {}) if isinstance(event, dict) else {}
    if not isinstance(room, dict):
        room = {}

    final = room.get("finalMatchResult") or {}
    if not isinstance(final, dict):
        final = {}

    game_config = room.get("gameRoomConfig") or {}
    if not isinstance(game_config, dict):
        game_config = {}

    players = game_config.get("reservedPlayers") or []
    if not isinstance(players, list):
        players = []

    configured_name = (player_name or "").strip()
    my_team_id = None
    other_names: list[str] = []

    for player in players:
        if not isinstance(player, dict):
            continue
        name = (player.get("playerName") or "").strip()
        if not name:
            continue
        if configured_name and _same_player(name, configured_name):
            my_team_id = player.get("teamId")
        else:
            other_names.append(name)

    # Solo podemos afirmar quién es el oponente si identificamos al jugador.
    if configured_name and my_team_id is not None and other_names:
        opponent = ", ".join(other_names)
    else:
        opponent = "desconocido"

    result = "unknown"
    if my_team_id is not None:
        result_list = final.get("resultList") or []
        if not isinstance(result_list, list):
            result_list = []
        match_result = None
        game_results = []
        for entry in result_list:
            if not isinstance(entry, dict):
                continue
            if entry.get("scope") == "MatchScope_Match":
                match_result = entry
                break
            if entry.get("scope") == "MatchScope_Game":
                game_results.append(entry)

        # En BO1 puede no venir el resultado de tipo Match; usamos el último
        # resultado de partida como aproximación.
        chosen = match_result or (game_results[-1] if game_results else None)
        if chosen is not None:
            result = "win" if chosen.get("winningTeamId") == my_team_id else "loss"

    timestamp = _epoch_ms_to_iso(data.get("timestamp"))
    match_id = game_config.get("matchId")
    if isinstance(match_id, (str, int)):
        match_id = str(match_id).strip() or None
    else:
        match_id = None

    return MatchResult(
        deck=None,
        result=result,
        opponent=opponent,
        timestamp=timestamp,
        match_id=match_id,
    )
