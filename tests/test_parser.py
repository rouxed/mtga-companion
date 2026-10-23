"""Tests del parser de resultados de MTG Arena."""
from __future__ import annotations

from mtga_companion.parser import _same_player, parse_match_result


def _event(players, winning_team, scopes=("Match",)):
    return {
        "matchGameRoomStateChangedEvent": {
            "gameRoomInfo": {
                "gameRoomConfig": {
                    "reservedPlayers": [
                        {"playerName": name, "teamId": team}
                        for name, team in players
                    ]
                },
                "finalMatchResult": {
                    "resultList": [
                        {
                            "scope": f"MatchScope_{scope}",
                            "winningTeamId": winning_team,
                        }
                        for scope in scopes
                    ]
                },
            }
        }
    }


def test_opponent_is_the_other_player_when_local_player_is_first():
    data = _event([("Rouxed", 1), ("atoras", 2)], winning_team=1)

    result = parse_match_result(data, "Rouxed")

    assert result.result == "win"
    assert result.opponent == "atoras"


def test_opponent_is_the_other_player_when_local_player_is_second():
    data = _event([("atoras", 1), ("Rouxed", 2)], winning_team=2)

    result = parse_match_result(data, "Rouxed")

    assert result.result == "win"
    assert result.opponent == "atoras"


def test_loss_is_detected_correctly():
    data = _event([("atoras", 1), ("Rouxed", 2)], winning_team=1)

    result = parse_match_result(data, "Rouxed")

    assert result.result == "loss"
    assert result.opponent == "atoras"


def test_player_name_with_tag_matches_log_name_without_tag():
    data = _event([("atoras", 1), ("Rouxed", 2)], winning_team=2)

    result = parse_match_result(data, "Rouxed#12345")

    assert result.result == "win"
    assert result.opponent == "atoras"


def test_without_player_name_result_is_unknown_and_opponent_not_guessed():
    data = _event([("Rouxed", 1), ("atoras", 2)], winning_team=1)

    result = parse_match_result(data, None)

    assert result.result == "unknown"
    assert result.opponent == "desconocido"


def test_unknown_player_name_does_not_claim_an_opponent():
    data = _event([("Rouxed", 1), ("atoras", 2)], winning_team=1)

    result = parse_match_result(data, "OtroJugador")

    assert result.result == "unknown"
    assert result.opponent == "desconocido"


def test_bo1_falls_back_to_game_scope():
    data = _event([("Rouxed", 1), ("atoras", 2)], winning_team=2, scopes=("Game",))

    result = parse_match_result(data, "Rouxed")

    assert result.result == "loss"
    assert result.opponent == "atoras"


def test_same_player_ignores_case_and_tag():
    assert _same_player("Rouxed#12345", "rouxed")
    assert _same_player("Rouxed", "Rouxed#12345")
    assert not _same_player("Rouxed", "atoras")
    assert not _same_player("", "Rouxed")


def test_timestamp_and_match_id_are_extracted_from_the_log_event():
    data = _event([("Rouxed", 1), ("atoras", 2)], winning_team=1)
    # Arena escribe el timestamp como string numérico en el log real.
    data["timestamp"] = "1700000000000"
    data["matchGameRoomStateChangedEvent"]["gameRoomInfo"]["gameRoomConfig"][
        "matchId"
    ] = "match-abc"

    result = parse_match_result(data, "Rouxed")

    assert result.timestamp == "2023-11-14T22:13:20"
    assert result.match_id == "match-abc"


def test_timestamp_also_accepts_a_numeric_value():
    data = _event([("Rouxed", 1), ("atoras", 2)], winning_team=1)
    data["timestamp"] = 1700000000000

    result = parse_match_result(data, "Rouxed")

    assert result.timestamp == "2023-11-14T22:13:20"


def test_missing_timestamp_and_match_id_are_empty():
    data = _event([("Rouxed", 1), ("atoras", 2)], winning_team=1)

    result = parse_match_result(data, "Rouxed")

    assert result.timestamp == ""
    assert result.match_id is None
