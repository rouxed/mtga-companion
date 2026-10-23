"""Tests del estado de partida reconstruido desde mensajes GRE."""
from __future__ import annotations

import json

from mtga_companion.game_state import GameStateTracker
from mtga_companion.models import CardEntry, DetectedDeck


def _message(
    gs_type: str,
    game_state_id: int,
    *,
    zones=None,
    objects=None,
    turn_info=None,
    game_info=None,
    annotations=None,
    system_seat=1,
) -> dict:
    state = {
        "type": f"GameStateType_{gs_type}",
        "gameStateId": game_state_id,
    }
    if zones is not None:
        state["zones"] = zones
    if objects is not None:
        state["gameObjects"] = objects
    if turn_info is not None:
        state["turnInfo"] = turn_info
    if game_info is not None:
        state["gameInfo"] = game_info
    if annotations is not None:
        state["annotations"] = annotations
    return {
        "greToClientEvent": {
            "greToClientMessages": [
                {
                    "type": "GREMessageType_GameStateMessage",
                    "systemSeatIds": [system_seat],
                    "gameStateMessage": state,
                }
            ]
        }
    }


def _zone(zone_type: str, owner: int | None, ids: list[int]) -> dict:
    return {
        "type": f"ZoneType_{zone_type}",
        "ownerSeatId": owner,
        "objectInstanceIds": ids,
    }


def _card(instance_id: int, grp_id: int, owner: int = 1) -> dict:
    return {
        "instanceId": instance_id,
        "grpId": grp_id,
        "type": "GameObjectType_Card",
        "ownerSeatId": owner,
        "controllerSeatId": owner,
    }


def _land(
    instance_id: int,
    grp_id: int,
    *,
    owner: int = 1,
    tapped: bool = False,
) -> dict:
    card = _card(instance_id, grp_id, owner=owner)
    card["cardTypes"] = ["CardType_Land"]
    if tapped:
        card["isTapped"] = True
    return card


def _deck() -> DetectedDeck:
    return DetectedDeck(
        name="Mazo de prueba",
        fmt="Standard",
        cards=[
            CardEntry("101", 4),
            CardEntry("102", 4),
            CardEntry("103", 4),
        ],
    )


def test_full_plus_hand_diff_reconstructs_remaining_cards():
    tracker = GameStateTracker(_deck())

    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[
                _zone("Hand", 1, []),
                _zone("Library", 1, list(range(1, 13))),
                _zone("Hand", 2, []),
                _zone("Library", 2, list(range(21, 33))),
            ],
            turn_info={"activePlayer": 1},
        )
    )
    snapshot = tracker.process_event(
        _message(
            "Diff",
            2,
            zones=[
                _zone("Hand", 1, [1, 2]),
                _zone("Library", 1, list(range(3, 13))),
            ],
            objects=[
                _card(1, 101),
                _card(2, 101),
            ],
        )
    )

    assert snapshot is not None
    assert snapshot.in_game is True
    assert snapshot.library_count == 10
    assert snapshot.hand_count == 2
    assert snapshot.remaining_counts["101"] == 2
    assert snapshot.remaining_counts["102"] == 4
    assert snapshot.remaining_counts["103"] == 4
    assert sum(snapshot.remaining_counts.values()) == 10


def test_cards_in_battlefield_and_graveyard_are_subtracted():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[
                _zone("Hand", 1, [1]),
                _zone("Library", 1, list(range(2, 13))),
                _zone("Battlefield", 1, [13]),
                _zone("Graveyard", 1, [14]),
            ],
            objects=[
                _card(1, 101),
                _card(13, 102),
                _card(14, 103),
            ],
        )
    )

    snapshot = tracker.snapshot()

    assert snapshot.library_count == 11
    assert snapshot.remaining_counts["101"] == 3
    assert snapshot.remaining_counts["102"] == 3
    assert snapshot.remaining_counts["103"] == 3


def test_opponent_cards_do_not_affect_local_remaining_counts():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[
                _zone("Hand", 1, [1]),
                _zone("Library", 1, list(range(2, 10))),
                _zone("Hand", 2, [21]),
                _zone("Library", 2, list(range(22, 34))),
            ],
            objects=[
                _card(1, 101),
                _card(21, 101, owner=2),
            ],
        )
    )

    snapshot = tracker.snapshot()

    assert snapshot.hand_count == 1
    assert snapshot.library_count == 8
    assert snapshot.remaining_counts["101"] == 3


def test_new_full_state_discards_previous_game():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
            objects=[_card(1, 101)],
        )
    )
    assert tracker.snapshot().library_count == 12

    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(31, 43)))],
            objects=[],
        )
    )
    snapshot = tracker.snapshot()

    assert snapshot.library_count == 12
    assert sum(snapshot.remaining_counts.values()) == 12


def test_play_draw_is_inferred_from_first_turn_active_player():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
            turn_info={"turnNumber": 1, "activePlayer": 1},
            system_seat=1,
        )
    )
    assert tracker.snapshot().on_play is True

    tracker.reset()
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
            turn_info={"turnNumber": 1, "activePlayer": 2},
            system_seat=1,
        )
    )
    assert tracker.snapshot().on_play is False


def test_game_over_state_marks_snapshot_inactive():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
        )
    )

    snapshot = tracker.process_event(
        _message(
            "Diff",
            2,
            zones=[_zone("Library", 1, list(range(1, 13)))],
            turn_info={"turnNumber": 9, "activePlayer": 1},
            game_info={"stage": "GameStage_GameOver"},
        )
    )

    assert snapshot is not None
    assert snapshot.in_game is False


def test_new_full_after_game_over_reactivates_overlay():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
            game_info={"stage": "GameStage_GameOver"},
        )
    )
    assert tracker.snapshot().in_game is False

    snapshot = tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
            game_info={"stage": "GameStage_Playing"},
        )
    )

    assert snapshot is not None
    assert snapshot.in_game is True


def test_process_line_reads_a_json_line():
    tracker = GameStateTracker(_deck())
    line = json.dumps(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
        )
    )

    snapshot = tracker.process_line(line)

    assert snapshot is not None
    assert snapshot.library_count == 12


def test_reset_clears_the_active_game_but_keeps_the_deck():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[_zone("Library", 1, list(range(1, 13)))],
        )
    )

    tracker.reset()
    snapshot = tracker.snapshot()

    assert snapshot.in_game is False
    assert snapshot.library_count == 0
    assert snapshot.deck_name == "Mazo de prueba"


def test_land_counts_follow_battlefield_and_tap_annotations():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[
                _zone("Battlefield", None, [13, 14]),
                _zone("Hand", 1, [15]),
                _zone("Library", 1, list(range(2, 9))),
            ],
            objects=[
                _land(13, 201, tapped=True),
                _land(14, 202),
                _land(15, 203),
                _card(1, 101),
            ],
        )
    )

    snapshot = tracker.snapshot()
    assert snapshot.lands_in_play == 2
    assert snapshot.lands_untapped == 1
    assert snapshot.lands_in_hand == 1

    snapshot = tracker.process_event(
        _message(
            "Diff",
            2,
            annotations=[
                {
                    "type": ["AnnotationType_TappedUntappedPermanent"],
                    "affectedIds": [14],
                    "details": [{"key": "tapped", "valueInt32": [1]}],
                }
            ],
        )
    )
    assert snapshot is not None
    assert snapshot.lands_in_play == 2
    assert snapshot.lands_untapped == 0

    snapshot = tracker.process_event(
        _message(
            "Diff",
            3,
            annotations=[
                {
                    "type": ["AnnotationType_TappedUntappedPermanent"],
                    "affectedIds": [13],
                    "details": [{"key": "tapped", "valueInt32": [0]}],
                }
            ],
        )
    )
    assert snapshot is not None
    assert snapshot.lands_untapped == 1


def test_opponent_cards_are_tracked_only_from_public_or_revealed_zones():
    tracker = GameStateTracker(_deck())
    tracker.process_event(
        _message(
            "Full",
            1,
            zones=[
                _zone("Hand", 1, [1]),
                _zone("Library", 1, list(range(2, 12))),
                _zone("Hand", 2, [21]),
                _zone("Library", 2, list(range(31, 41))),
                _zone("Revealed", 2, [22]),
                _zone("Graveyard", 2, [23]),
                _zone("Stack", None, [24]),
                _zone("Battlefield", None, [25]),
            ],
            objects=[
                _card(1, 101),
                _card(21, 501, owner=2),
                _card(22, 502, owner=2),
                _card(23, 503, owner=2),
                _card(24, 504, owner=2),
                _card(25, 505, owner=2),
            ],
        )
    )

    snapshot = tracker.snapshot()
    assert snapshot.opponent_revealed == {"502": 1, "503": 1, "504": 1}
    assert set(snapshot.opponent_order) == {"502", "503", "504"}

    # Aunque la zona Revealed se vacíe, la carta ya revelada sigue conocida.
    snapshot = tracker.process_event(
        _message("Diff", 2, zones=[_zone("Revealed", 2, [])])
    )
    assert snapshot is not None
    assert snapshot.opponent_revealed == {"502": 1, "503": 1, "504": 1}

    tracker.process_event(
        _message(
            "Full",
            3,
            zones=[_zone("Library", 1, list(range(1, 13)))],
        )
    )
    assert tracker.snapshot().opponent_revealed == {}
