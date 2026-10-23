"""Tests del motor de probabilidades hipergeométricas del overlay."""
from __future__ import annotations

from mtga_companion.draw_odds import DrawOddsEngine, hypergeometric_at_least_one
from mtga_companion.game_state import GameSnapshot


def _snapshot(**overrides) -> GameSnapshot:
    values = {
        "in_game": True,
        "deck_name": "Mazo de prueba",
        "turn": 4,
        "deck_total": 10,
        "library_count": 10,
        "hand_count": 0,
        "remaining_counts": {"1": 4, "2": 4, "3": 2},
    }
    values.update(overrides)
    return GameSnapshot(**values)


def test_hypergeometric_probability_of_at_least_one_copy():
    # 4 copias en 10 cartas, robando 3: 1 - C(6,3)/C(10,3).
    assert abs(hypergeometric_at_least_one(10, 4, 3) - (1 - 20 / 120)) < 1e-9


def test_hypergeometric_returns_zero_without_successes_or_draws():
    assert hypergeometric_at_least_one(10, 0, 3) == 0.0
    assert hypergeometric_at_least_one(10, 4, 0) == 0.0
    assert hypergeometric_at_least_one(0, 4, 3) == 0.0


def test_engine_groups_cards_and_calculates_next_and_three_draw_odds():
    engine = DrawOddsEngine(
        card_meta={
            "1": {"name": "Bosque", "type_line": "Basic Land — Forest"},
            "2": {"name": "Goblin Guide", "type_line": "Creature — Goblin"},
            "3": {"name": "Shock", "type_line": "Instant"},
        }
    )

    odds = engine.compute(_snapshot())

    assert odds.status == "En partida"
    assert [item.label for item in odds.categories] == [
        "Tierras",
        "Criaturas",
        "Hechizos",
        "Otras",
    ]
    assert [item.remaining for item in odds.categories] == [4, 4, 2, 0]
    assert abs(odds.categories[0].next_probability - 0.4) < 1e-9
    assert abs(odds.categories[0].in_three_probability - (1 - 20 / 120)) < 1e-9
    assert abs(odds.categories[2].next_probability - 0.2) < 1e-9


def test_engine_top_cards_prefers_nonlands_and_uses_remaining_counts():
    engine = DrawOddsEngine(
        card_meta={
            "1": {"name": "Bosque", "type_line": "Basic Land — Forest"},
            "2": {"name": "Goblin Guide", "type_line": "Creature — Goblin"},
            "3": {"name": "Shock", "type_line": "Instant"},
        }
    )

    odds = engine.compute(_snapshot())

    assert [item.name for item in odds.top_cards] == ["Goblin Guide", "Shock"]
    assert [item.remaining for item in odds.top_cards] == [4, 2]
    assert abs(odds.top_cards[1].in_three_probability - (1 - 56 / 120)) < 1e-9


def test_engine_builds_deck_tracker_lands_and_opponent_cards():
    engine = DrawOddsEngine(
        card_meta={
            "1": {"name": "Bosque", "type_line": "Basic Land — Forest"},
            "2": {"name": "Goblin Guide", "type_line": "Creature — Goblin"},
            "3": {"name": "Shock", "type_line": "Instant"},
            "9": {"name": "Duress", "type_line": "Sorcery"},
            "10": {"name": "Cut Down", "type_line": "Instant"},
        }
    )
    snapshot = _snapshot(
        lands_in_play=3,
        lands_untapped=2,
        lands_in_hand=1,
        opponent_revealed={"9": 2, "10": 1},
        opponent_order=["9", "10"],
    )

    odds = engine.compute(snapshot)

    assert (odds.lands_in_play, odds.lands_untapped, odds.lands_in_hand) == (
        3,
        2,
        1,
    )
    assert odds.lands_in_library == 4
    assert [card.name for card in odds.deck_cards] == [
        "Bosque",
        "Goblin Guide",
        "Shock",
    ]
    assert [card.remaining for card in odds.deck_cards] == [4, 4, 2]
    assert abs(odds.deck_cards[0].next_probability - 0.4) < 1e-9
    assert [card.name for card in odds.opponent_cards] == [
        "Cut Down",
        "Duress",
    ]
    assert [card.quantity for card in odds.opponent_cards] == [1, 2]


def test_engine_uses_placeholder_when_metadata_has_no_type_or_name():
    engine = DrawOddsEngine(card_meta={"1": {}, "2": {}, "3": {}})

    odds = engine.compute(_snapshot())

    assert odds.status == "En partida"
    assert odds.categories[0].remaining == 0
    assert odds.categories[3].remaining == 10
    assert odds.top_cards[0].name.startswith("Carta #")


def test_engine_waits_while_card_metadata_is_being_resolved():
    engine = DrawOddsEngine(card_meta={})

    odds = engine.compute(_snapshot())

    assert odds.status == "Resolviendo cartas"
    assert odds.categories == ()


def test_engine_waits_for_game_or_deck():
    engine = DrawOddsEngine(card_meta={})

    waiting = engine.compute(GameSnapshot())
    no_deck = engine.compute(_snapshot(deck_total=0))

    assert waiting.status == "Esperando partida"
    assert no_deck.status == "Esperando mazo"


def test_engine_handles_empty_library():
    engine = DrawOddsEngine(card_meta={})

    odds = engine.compute(_snapshot(library_count=0))

    assert odds.status == "Sin cartas en biblioteca"
    assert odds.categories == ()
