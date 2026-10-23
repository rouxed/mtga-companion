"""Estado de la partida en curso a partir de los mensajes GRE del Player.log.

El log de Arena manda un ``GameStateType_Full`` al empezar cada partida y luego
diffs con las zonas y objetos que cambian.  Para el overlay no necesitamos
reconstruir todo el tablero: alcanza con saber qué cartas propias están fuera
de la biblioteca y cuántas quedan en ella.

La identidad de las cartas de la biblioteca no viene en el log (solo sus
``objectInstanceIds``); por eso calculamos probabilidades a partir de la lista
del mazo y de las cartas conocidas en mano/campo/cementerio/exilio/pila.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import DetectedDeck
from .parser import _extract_json_blob


@dataclass
class GameSnapshot:
    """Estado compacto y serializable que consume el motor de probabilidades."""

    in_game: bool = False
    local_seat: int | None = None
    turn: int | None = None
    active_player: int | None = None
    step: str = ""
    phase: str = ""
    deck_name: str | None = None
    deck_total: int = 0
    library_count: int = 0
    hand_count: int = 0
    deck_counts: dict[str, int] = field(default_factory=dict)
    remaining_counts: dict[str, int] = field(default_factory=dict)
    hand_counts: dict[str, int] = field(default_factory=dict)
    unresolved_used: int = 0
    on_play: bool | None = None
    lands_in_play: int = 0
    lands_untapped: int = 0
    lands_in_hand: int = 0
    opponent_revealed: dict[str, int] = field(default_factory=dict)
    opponent_order: list[str] = field(default_factory=list)


class GameStateTracker:
    """Acumula los mensajes de estado de una partida de Arena.

    No depende de Qt para poder testearse con mensajes JSON reales.
    """

    def __init__(self, deck: DetectedDeck | None = None):
        self._deck = deck
        self._deck_counts = self._counts_from_deck(deck)
        self._zones: dict[tuple[str, int | None], list[int]] = {}
        self._objects: dict[int, dict[str, Any]] = {}
        self._turn_info: dict[str, Any] = {}
        self._players: list[dict[str, Any]] = []
        self._local_seat: int | None = None
        self._last_game_state_id: int | None = None
        self._in_game = False
        self._game_over = False
        self._on_play: bool | None = None
        self._opponent_ids: set[int] = set()
        self._opponent_order: list[str] = []

    # ------------------------------------------------------------------
    # Mazo
    # ------------------------------------------------------------------
    @staticmethod
    def _counts_from_deck(deck: DetectedDeck | None) -> dict[str, int]:
        counts: dict[str, int] = {}
        if deck is None:
            return counts
        for card in deck.cards:
            cid = str(card.card_id)
            qty = max(0, int(card.quantity))
            if not cid or not qty:
                continue
            counts[cid] = counts.get(cid, 0) + qty
        return counts

    def set_deck(self, deck: DetectedDeck | None) -> None:
        """Actualiza la lista del mazo activo.

        Al cambiar de mazo no se borra el estado de la partida: el overlay
        puede recibir el ``CourseDeck`` unos instantes antes o después de los
        primeros mensajes de estado.
        """
        self._deck = deck
        self._deck_counts = self._counts_from_deck(deck)

    def reset(self) -> None:
        """Olvida la partida actual (fin de partida, reconexión o nuevo mazo)."""
        self._zones.clear()
        self._objects.clear()
        self._turn_info = {}
        self._players = []
        self._local_seat = None
        self._last_game_state_id = None
        self._in_game = False
        self._game_over = False
        self._on_play = None
        self._opponent_ids.clear()
        self._opponent_order.clear()

    # ------------------------------------------------------------------
    # Procesamiento del log
    # ------------------------------------------------------------------
    def process_line(self, line: str) -> GameSnapshot | None:
        """Procesa una línea del Player.log si contiene un estado de partida."""
        if '"gameStateMessage"' not in line:
            return None
        idx = line.find("{")
        if idx == -1:
            return None
        data = _extract_json_blob(line, idx)
        if not data:
            return None
        return self.process_event(data)

    def process_event(self, data: dict[str, Any]) -> GameSnapshot | None:
        """Procesa un evento GreToClient completo."""
        event = data.get("greToClientEvent")
        if not isinstance(event, dict):
            return None
        messages = event.get("greToClientMessages")
        if not isinstance(messages, list):
            return None

        processed = False
        for message in messages:
            if not isinstance(message, dict):
                continue
            state = message.get("gameStateMessage")
            if not isinstance(state, dict):
                continue

            seats = message.get("systemSeatIds")
            if isinstance(seats, list) and seats:
                try:
                    self._local_seat = int(seats[0])
                except (TypeError, ValueError):
                    pass

            self._apply_state(state)
            processed = True

        return self.snapshot() if processed else None

    def _apply_state(self, state: dict[str, Any]) -> None:
        state_type = str(state.get("type") or "")
        raw_id = state.get("gameStateId")

        try:
            game_state_id = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            game_state_id = None

        if state_type == "GameStateType_Full":
            # Un Full es el comienzo de una partida nueva. No tocamos el mazo:
            # CourseDeck se recibe por separado.
            self._zones.clear()
            self._objects.clear()
            self._turn_info = {}
            self._players = []
            self._last_game_state_id = game_state_id
            self._in_game = True
            self._game_over = False
            self._on_play = None
            self._opponent_ids.clear()
            self._opponent_order.clear()
        elif (
            game_state_id is not None
            and self._last_game_state_id is not None
            and game_state_id < self._last_game_state_id
        ):
            # Algunos reinicios/reconexiones mandan un diff con id menor antes
            # del Full. Es más seguro empezar de cero que mezclar partidas.
            self._zones.clear()
            self._objects.clear()
            self._turn_info = {}
            self._players = []
            self._in_game = True
            self._game_over = False
            self._on_play = None
            self._opponent_ids.clear()
            self._opponent_order.clear()

        if game_state_id is not None:
            self._last_game_state_id = game_state_id

        objects = state.get("gameObjects")
        if isinstance(objects, list):
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                instance_id = obj.get("instanceId")
                if instance_id is None:
                    continue
                try:
                    instance_id = int(instance_id)
                except (TypeError, ValueError):
                    continue
                previous = self._objects.get(instance_id, {})
                previous.update(obj)
                self._objects[instance_id] = previous

        zones = state.get("zones")
        if isinstance(zones, list):
            for zone in zones:
                if not isinstance(zone, dict):
                    continue
                zone_type = str(zone.get("type") or "")
                if not zone_type:
                    continue
                owner = zone.get("ownerSeatId")
                try:
                    owner = int(owner) if owner is not None else None
                except (TypeError, ValueError):
                    owner = None
                ids = zone.get("objectInstanceIds")
                if not isinstance(ids, list):
                    continue
                parsed_ids: list[int] = []
                for raw in ids:
                    try:
                        parsed_ids.append(int(raw))
                    except (TypeError, ValueError):
                        continue
                self._zones[(zone_type, owner)] = parsed_ids
            self._in_game = True

        annotations = state.get("annotations")
        if isinstance(annotations, list):
            self._apply_annotations(annotations)
        self._track_opponent_cards()

        turn_info = state.get("turnInfo")
        if isinstance(turn_info, dict) and turn_info:
            self._turn_info.update(turn_info)

        players = state.get("players")
        if isinstance(players, list) and players:
            self._players = players

        game_info = state.get("gameInfo")
        if isinstance(game_info, dict):
            stage = str(game_info.get("stage") or "")
            match_state = str(game_info.get("matchState") or "")
            if stage == "GameStage_GameOver" or match_state in {
                "MatchState_GameComplete",
                "MatchState_MatchComplete",
            }:
                # El log no siempre manda el matchGameRoomStateChangedEvent
                # completo al terminar; el propio gameInfo alcanza para dejar
                # de mostrar probabilidades de una partida que ya terminó.
                self._game_over = True

        turn = self._turn()
        active = self._active_player()
        if turn == 1 and active is not None and self._local_seat is not None:
            # Solo se fija la primera vez: en turnos siguientes activePlayer
            # alterna y no queremos perder el dato de play/draw.
            if self._on_play is None:
                self._on_play = active == self._local_seat

        if self._game_over:
            self._in_game = False
        elif turn is not None or self._hand_ids() or self._library_ids():
            self._in_game = True

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _annotation_detail_int(
        cls, annotation: dict[str, Any], key: str
    ) -> int | None:
        details = annotation.get("details")
        if not isinstance(details, list):
            return None
        for detail in details:
            if not isinstance(detail, dict) or detail.get("key") != key:
                continue
            values = detail.get("valueInt32")
            if isinstance(values, list) and values:
                return cls._as_int(values[0])
        return None

    def _apply_annotations(self, annotations: list[Any]) -> None:
        """Aplica cambios que el log expresa como anotaciones, no como objetos.

        Arena suele mandar ``isTapped: true`` al girar una tierra, pero al
        desgirarla manda una anotación con ``tapped: 0`` y no repite el objeto.
        Sin esto el contador de tierras quedaría congelado en "girada".
        """
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            kinds = annotation.get("type") or []
            if isinstance(kinds, str):
                kinds = [kinds]
            affected = annotation.get("affectedIds") or []
            if not isinstance(affected, list):
                affected = []
            if "AnnotationType_TappedUntappedPermanent" in kinds:
                tapped = self._annotation_detail_int(annotation, "tapped")
                if tapped is None:
                    continue
                for raw_id in affected:
                    instance_id = self._as_int(raw_id)
                    obj = self._objects.get(instance_id) if instance_id is not None else None
                    if isinstance(obj, dict):
                        obj["isTapped"] = bool(tapped)
            elif "AnnotationType_ObjectIdChanged" in kinds:
                old_id = self._annotation_detail_int(annotation, "orig_id")
                new_id = self._annotation_detail_int(annotation, "new_id")
                if old_id is None or new_id is None:
                    continue
                if old_id in self._opponent_ids:
                    self._opponent_ids.discard(old_id)
                    self._opponent_ids.add(new_id)

    @staticmethod
    def _owner_of(obj: dict[str, Any]) -> int | None:
        return GameStateTracker._as_int(obj.get("ownerSeatId"))

    def _opponent_seat(self) -> int:
        return 2 if self._local() != 2 else 1

    def _is_opponent_card(
        self, instance_id: int, *, allow_owner_none: bool = False
    ) -> bool:
        obj = self._objects.get(instance_id)
        if not isinstance(obj, dict):
            return False
        if obj.get("type") not in (None, "GameObjectType_Card"):
            return False
        if obj.get("isFaceDown") or obj.get("faceDown"):
            return False
        owner = self._owner_of(obj)
        if owner == self._opponent_seat():
            return True
        return allow_owner_none and owner is None

    def _track_opponent_cards(self) -> None:
        """Acumula cartas del oponente que el log muestra en zonas públicas.

        Nunca se leen mano ni biblioteca del oponente. Solo se guardan IDs que
        aparecen en ``ZoneType_Revealed`` (reveladas explícitamente), pila,
        cementerio, exilio o comando. Las cartas permanecen en la lista aunque
        después vuelvan a una zona oculta, porque ya fueron reveladas.
        """
        opponent = self._opponent_seat()
        tracked = {
            "ZoneType_Revealed",
            "ZoneType_Stack",
            "ZoneType_Graveyard",
            "ZoneType_Exile",
            "ZoneType_Command",
        }
        for (zone_type, owner), ids in self._zones.items():
            if zone_type not in tracked:
                continue
            if owner not in (None, opponent):
                continue
            allow_owner_none = zone_type == "ZoneType_Revealed"
            for instance_id in ids:
                obj = self._objects.get(instance_id)
                if not isinstance(obj, dict):
                    continue
                if obj.get("grpId") is None:
                    continue
                if not self._is_opponent_card(
                    instance_id, allow_owner_none=allow_owner_none
                ):
                    continue
                if instance_id in self._opponent_ids:
                    continue
                self._opponent_ids.add(instance_id)
                card_id = str(obj["grpId"])
                if card_id not in self._opponent_order:
                    self._opponent_order.append(card_id)

    def _opponent_counts(self) -> tuple[dict[str, int], list[str]]:
        counts: dict[str, int] = {}
        for instance_id in self._opponent_ids:
            obj = self._objects.get(instance_id)
            if not isinstance(obj, dict):
                continue
            grp_id = obj.get("grpId")
            if grp_id is None:
                continue
            card_id = str(grp_id)
            counts[card_id] = counts.get(card_id, 0) + 1
        order = [card_id for card_id in self._opponent_order if card_id in counts]
        return counts, order

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def _turn(self) -> int | None:
        raw = self._turn_info.get("turnNumber")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def _active_player(self) -> int | None:
        raw = self._turn_info.get("activePlayer")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def _local(self) -> int:
        return self._local_seat if self._local_seat is not None else 1

    def _zone_ids(self, zone_type: str, owner: int | None = None) -> list[int]:
        owner = self._local() if owner is None else owner
        return list(self._zones.get((zone_type, owner), []))

    def _hand_ids(self) -> list[int]:
        return self._zone_ids("ZoneType_Hand")

    def _library_ids(self) -> list[int]:
        return self._zone_ids("ZoneType_Library")

    def _battlefield_ids(self) -> list[int]:
        """El campo de batalla es una zona compartida sin ``ownerSeatId``."""
        ids: list[int] = []
        for (zone_type, owner), object_ids in self._zones.items():
            if zone_type != "ZoneType_Battlefield":
                continue
            if owner not in (None, self._local()):
                continue
            ids.extend(object_ids)
        return ids

    @staticmethod
    def _is_land_object(obj: dict[str, Any]) -> bool:
        card_types = obj.get("cardTypes")
        return isinstance(card_types, list) and "CardType_Land" in card_types

    def _land_counts(self) -> tuple[int, int, int]:
        """Devuelve (tierras en juego, sin girar, en mano)."""
        in_play = 0
        untapped = 0
        for instance_id in self._battlefield_ids():
            obj = self._objects.get(instance_id)
            if not isinstance(obj, dict):
                continue
            if not self._is_own_card(instance_id) or not self._is_land_object(obj):
                continue
            in_play += 1
            if not bool(obj.get("isTapped")):
                untapped += 1
        in_hand = 0
        for instance_id in self._hand_ids():
            obj = self._objects.get(instance_id)
            if isinstance(obj, dict) and self._is_land_object(obj):
                in_hand += 1
        return in_play, untapped, in_hand

    def _is_own_card(self, instance_id: int) -> bool:
        obj = self._objects.get(instance_id)
        if not isinstance(obj, dict):
            return False
        if obj.get("type") not in (None, "GameObjectType_Card"):
            return False
        owner = obj.get("ownerSeatId")
        try:
            owner = int(owner) if owner is not None else None
        except (TypeError, ValueError):
            owner = None
        return owner in (None, self._local())

    def _known_non_library_counts(self) -> tuple[dict[str, int], int]:
        """Cuenta cartas propias conocidas fuera de la biblioteca.

        Se excluyen tokens, sideboard y zonas que no representan cartas del
        mazo principal.  ``unresolved`` cuenta objetos propios de los que no
        tenemos ``grpId``; el overlay lo muestra como dato parcial.
        """
        counts: dict[str, int] = {}
        unresolved = 0
        counted_zones = {
            "ZoneType_Hand",
            "ZoneType_Battlefield",
            "ZoneType_Graveyard",
            "ZoneType_Exile",
            "ZoneType_Stack",
            "ZoneType_Command",
        }
        for (zone_type, owner), ids in self._zones.items():
            if owner not in (None, self._local()):
                continue
            if zone_type not in counted_zones:
                continue
            for instance_id in ids:
                obj = self._objects.get(instance_id)
                if not isinstance(obj, dict):
                    unresolved += 1
                    continue
                if not self._is_own_card(instance_id):
                    continue
                grp_id = obj.get("grpId")
                if grp_id is None:
                    unresolved += 1
                    continue
                cid = str(grp_id)
                counts[cid] = counts.get(cid, 0) + 1
        return counts, unresolved

    def snapshot(self) -> GameSnapshot:
        library = self._library_ids()
        hand = self._hand_ids()
        used, unresolved = self._known_non_library_counts()
        remaining: dict[str, int] = {}
        for cid, total in self._deck_counts.items():
            remaining[cid] = max(0, total - used.get(cid, 0))
        hand_counts: dict[str, int] = {}
        for instance_id in hand:
            obj = self._objects.get(instance_id)
            if not isinstance(obj, dict):
                continue
            grp_id = obj.get("grpId")
            if grp_id is None:
                continue
            cid = str(grp_id)
            hand_counts[cid] = hand_counts.get(cid, 0) + 1

        lands_in_play, lands_untapped, lands_in_hand = self._land_counts()
        opponent_revealed, opponent_order = self._opponent_counts()

        return GameSnapshot(
            in_game=self._in_game,
            local_seat=self._local_seat,
            turn=self._turn(),
            active_player=self._active_player(),
            step=str(self._turn_info.get("step") or ""),
            phase=str(self._turn_info.get("phase") or ""),
            deck_name=self._deck.name if self._deck else None,
            deck_total=sum(self._deck_counts.values()),
            library_count=len(library),
            hand_count=len(hand),
            deck_counts=dict(self._deck_counts),
            remaining_counts=remaining,
            hand_counts=hand_counts,
            unresolved_used=unresolved,
            on_play=self._on_play,
            lands_in_play=lands_in_play,
            lands_untapped=lands_untapped,
            lands_in_hand=lands_in_hand,
            opponent_revealed=opponent_revealed,
            opponent_order=opponent_order,
        )
