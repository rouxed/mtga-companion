"""Tests de integración del watcher con la base de datos."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from mtga_companion.database import get_deck, get_matches, init_db, save_match
from mtga_companion.log_watcher import LogWatcherThread
from mtga_companion.models import CardEntry, DetectedDeck
from mtga_companion.thread_registry import unregister_thread


def _match_line(
    match_id: str | None = "match-1",
    timestamp_ms: int | None = None,
    winning_team: int = 1,
) -> str:
    if timestamp_ms is None:
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    game_room_config = {
        "reservedPlayers": [
            {"playerName": "Rouxed", "teamId": 1},
            {"playerName": "atoras", "teamId": 2},
        ]
    }
    if match_id is not None:
        game_room_config["matchId"] = match_id

    data = {
        "timestamp": timestamp_ms,
        "matchGameRoomStateChangedEvent": {
            "gameRoomInfo": {
                "gameRoomConfig": game_room_config,
                "finalMatchResult": {
                    "resultList": [
                        {
                            "scope": "MatchScope_Match",
                            "winningTeamId": winning_team,
                        }
                    ]
                },
                "stateType": "MatchGameRoomStateType_MatchCompleted",
            }
        },
    }
    return json.dumps(data)


def _make_watcher(tmp_path):
    db_path = tmp_path / "watcher.db"
    init_db(db_path)
    watcher = LogWatcherThread(
        log_path=None,
        player_name="Rouxed",
        db_path=db_path,
    )
    watcher._current_deck = DetectedDeck(
        name="Mono Red",
        fmt="Standard",
        cards=[CardEntry(card_id="123", quantity=4)],
    )
    return watcher, db_path


def _cleanup(watcher):
    watcher.stop()
    unregister_thread(watcher)
    watcher.deleteLater()


def test_live_match_is_saved_with_log_timestamp_and_deduplicated(qapp, tmp_path):
    watcher, db_path = _make_watcher(tmp_path)
    try:
        line = _match_line(timestamp_ms=1700000000000)
        watcher._process_line(line)
        watcher._process_line(line)

        matches = get_matches(db_path)
        assert len(matches) == 1
        assert matches[0]["match_id"] == "match-1"
        assert matches[0]["timestamp"] == "2023-11-14T22:13:20"
        assert matches[0]["deck_name"] == "Mono Red"
        assert matches[0]["result"] == "win"
        assert matches[0]["opponent"] == "atoras"

        deck = get_deck("Mono Red", db_path)
        assert deck["wins"] == 1
        assert deck["first_seen"] == "2023-11-14T22:13:20"
        assert deck["last_seen"] == "2023-11-14T22:13:20"
    finally:
        _cleanup(watcher)


def test_deck_detection_emits_a_fresh_snapshot_with_the_deck(qapp, tmp_path):
    watcher, _db_path = _make_watcher(tmp_path)
    watcher._current_deck = None
    decks = []
    snapshots = []
    watcher.signals.deck_detected.connect(decks.append)
    watcher.signals.game_state_changed.connect(snapshots.append)
    try:
        line = json.dumps(
            {
                "CurrentModule": "CreateMatch",
                "CourseDeckSummary": {"Name": "Mono Red", "Format": "Standard"},
                "CourseDeck": {
                    "MainDeck": [
                        {"cardId": 123, "quantity": 4},
                        {"cardId": 456, "quantity": 2},
                    ]
                },
            }
        )

        watcher._process_line(line)

        assert len(decks) == 1
        assert decks[0].name == "Mono Red"
        assert snapshots
        assert snapshots[-1].deck_name == "Mono Red"
        assert snapshots[-1].deck_total == 6
    finally:
        _cleanup(watcher)


def test_backfill_ignores_old_matches(qapp, tmp_path):
    watcher, db_path = _make_watcher(tmp_path)
    try:
        # 2020-01-01, muy anterior a la ventana de backfill.
        old_line = _match_line(match_id="old", timestamp_ms=1577836800000)
        watcher._process_line(old_line, backfill=True)

        assert get_matches(db_path) == []
    finally:
        _cleanup(watcher)


def test_backfill_accepts_recent_match(qapp, tmp_path):
    watcher, db_path = _make_watcher(tmp_path)
    try:
        watcher._process_line(_match_line(match_id="recent"), backfill=True)

        matches = get_matches(db_path)
        assert len(matches) == 1
        assert matches[0]["match_id"] == "recent"
    finally:
        _cleanup(watcher)


def test_backfill_requires_match_id(qapp, tmp_path):
    watcher, db_path = _make_watcher(tmp_path)
    try:
        watcher._process_line(_match_line(match_id=None), backfill=True)

        assert get_matches(db_path) == []
    finally:
        _cleanup(watcher)


def test_live_match_without_deck_is_still_saved(qapp, tmp_path):
    watcher, db_path = _make_watcher(tmp_path)
    watcher._current_deck = None
    try:
        watcher._process_line(_match_line(match_id="sin-mazo"))

        matches = get_matches(db_path)
        assert len(matches) == 1
        assert matches[0]["deck_name"] is None
    finally:
        _cleanup(watcher)


def test_backfill_does_not_duplicate_a_legacy_match_without_match_id(qapp, tmp_path):
    watcher, db_path = _make_watcher(tmp_path)
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        timestamp_ms = int(now.timestamp() * 1000)
        legacy_timestamp = now.replace(tzinfo=None).isoformat()
        save_match(
            "Mono Red",
            [],
            "win",
            "atoras",
            "Standard",
            db_path=db_path,
            timestamp=legacy_timestamp,
            match_id=None,
        )

        watcher._process_line(
            _match_line(match_id="new-id", timestamp_ms=timestamp_ms),
            backfill=True,
        )

        matches = get_matches(db_path)
        assert len(matches) == 1
        assert matches[0]["match_id"] is None
    finally:
        _cleanup(watcher)


def test_watcher_resolves_detected_log_when_configured_path_is_missing(
    qapp, tmp_path, monkeypatch
):
    log = tmp_path / "detectado" / "Player.log"
    log.parent.mkdir()
    log.write_text("", encoding="utf-8")
    watcher, _db_path = _make_watcher(tmp_path)
    watcher.log_path = tmp_path / "todavia-no-existe" / "Player.log"
    monkeypatch.setattr(
        "mtga_companion.log_watcher.detect_log_path", lambda: log
    )
    try:
        assert watcher._resolve_path() == log
        assert watcher.log_path == log
    finally:
        _cleanup(watcher)
