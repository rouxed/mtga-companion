"""Tests de migraciones SQLite y de la deduplicación por matchId."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from mtga_companion.database import (
    SCHEMA_VERSION,
    get_deck,
    get_matches,
    init_db,
    match_exists,
    save_match,
)


def _create_legacy_db(path):
    con = sqlite3.connect(str(path))
    try:
        con.executescript(
            """
            CREATE TABLE matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                deck_name TEXT,
                deck_cards TEXT,
                result TEXT,
                opponent TEXT,
                format TEXT
            );
            CREATE TABLE decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                format TEXT,
                card_ids TEXT,
                first_seen TEXT,
                last_seen TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                unknown INTEGER DEFAULT 0
            );
            INSERT INTO matches
                (timestamp, deck_name, deck_cards, result, opponent, format)
            VALUES
                ('2024-01-01T00:00:00', 'Mazo viejo', '[]', 'win', 'Viejo', 'Standard');
            """
        )
        con.commit()
    finally:
        con.close()


def _columns(path) -> set[str]:
    con = sqlite3.connect(str(path))
    try:
        return {row[1] for row in con.execute("PRAGMA table_info(matches)")}
    finally:
        con.close()


def test_init_db_migrates_legacy_schema_without_losing_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)

    assert "match_id" in _columns(db_path)
    con = sqlite3.connect(str(db_path))
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        rows = con.execute("SELECT timestamp, deck_name FROM matches").fetchall()
    finally:
        con.close()
    assert version == SCHEMA_VERSION
    assert rows == [("2024-01-01T00:00:00", "Mazo viejo")]


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "new.db"
    init_db(db_path)
    init_db(db_path)

    con = sqlite3.connect(str(db_path))
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()
    assert version == SCHEMA_VERSION


def test_save_match_uses_log_timestamp_and_deduplicates_by_match_id(tmp_path):
    db_path = tmp_path / "matches.db"
    init_db(db_path)

    first_id = save_match(
        deck_name="Mono Red",
        deck_cards=[{"cardId": 1, "quantity": 4}],
        result="win",
        opponent="atoras",
        fmt="Standard",
        db_path=db_path,
        timestamp="2025-01-02T03:04:05",
        match_id="match-1",
    )
    second_id = save_match(
        deck_name="Mono Red",
        deck_cards=[{"cardId": 1, "quantity": 4}],
        result="win",
        opponent="atoras",
        fmt="Standard",
        db_path=db_path,
        timestamp="2025-01-02T03:04:05",
        match_id="match-1",
    )

    matches = get_matches(db_path)
    assert len(matches) == 1
    assert matches[0]["timestamp"] == "2025-01-02T03:04:05"
    assert matches[0]["match_id"] == "match-1"
    assert first_id == second_id
    assert match_exists("match-1", db_path)
    assert not match_exists("match-2", db_path)

    deck = get_deck("Mono Red", db_path)
    assert deck["wins"] == 1
    assert deck["first_seen"] == "2025-01-02T03:04:05"
    assert deck["last_seen"] == "2025-01-02T03:04:05"


def test_deck_first_seen_and_last_seen_are_kept_in_order(tmp_path):
    db_path = tmp_path / "matches.db"
    init_db(db_path)

    save_match(
        "Mono Red", [], "win", "A", "Standard", db_path,
        timestamp="2025-01-02T00:00:00", match_id="late",
    )
    save_match(
        "Mono Red", [], "loss", "B", "Standard", db_path,
        timestamp="2025-01-01T00:00:00", match_id="early",
    )

    deck = get_deck("Mono Red", db_path)
    assert deck["first_seen"] == "2025-01-01T00:00:00"
    assert deck["last_seen"] == "2025-01-02T00:00:00"
    assert deck["wins"] == 1
    assert deck["losses"] == 1


def test_save_match_accepts_datetime_timestamp(tmp_path):
    db_path = tmp_path / "matches.db"
    init_db(db_path)

    save_match(
        "Mono Red", [], "win", "A", "Standard", db_path,
        timestamp=datetime(2025, 3, 4, 5, 6, 7),
        match_id="dt",
    )

    assert get_matches(db_path)[0]["timestamp"] == "2025-03-04T05:06:07"
