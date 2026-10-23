"""Tests de persistencia y cálculo de winrate por período."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from mtga_companion.database import (
    compute_daily_summary,
    compute_summary,
    format_local_timestamp,
    get_deck,
    get_matches,
    init_db,
    local_midnight_utc_naive,
    save_match,
)


def _insert_match(db_path, timestamp: str, result: str, deck: str = "Mazo") -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            """
            INSERT INTO matches
                (timestamp, deck_name, deck_cards, result, opponent, format)
            VALUES (?, ?, '[]', ?, 'Oponente', 'Standard')
            """,
            (timestamp, deck, result),
        )
        con.commit()
    finally:
        con.close()


def test_local_midnight_uses_local_calendar_day():
    # 2026-10-20 13:00 UTC = 10:00 en UTC-3.
    now = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)
    tz = timezone(timedelta(hours=-3))

    midnight = local_midnight_utc_naive(now, tz)

    assert midnight == datetime(2026, 10, 20, 3, 0, 0)


def test_today_is_local_calendar_day_not_last_24_hours(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # "Ahora" es 2026-10-20 13:00 UTC (10:00 local en UTC-3).
    # La medianoche local de hoy fue 2026-10-20 03:00 UTC.
    _insert_match(db_path, "2026-10-20T02:59:59", "win")   # ayer local
    _insert_match(db_path, "2026-10-20T03:00:00", "loss")  # hoy local
    _insert_match(db_path, "2026-10-20T12:00:00", "win")   # hoy local
    _insert_match(db_path, "2026-10-14T00:00:00", "win")   # últimos 7 días
    _insert_match(db_path, "2026-10-13T12:59:59", "loss")  # fuera de 7 días
    _insert_match(db_path, "2020-01-01T00:00:00", "win")   # histórico

    summary = compute_daily_summary(
        db_path,
        now=datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc),
        tz=timezone(timedelta(hours=-3)),
    )

    assert summary["today"] == {
        "total": 2,
        "wins": 1,
        "losses": 1,
        "unknown": 0,
        "winrate": 50.0,
    }
    # Últimos 7 días: incluye el partido de ayer local (02:59) y el del 14.
    assert summary["last7"]["total"] == 4
    assert summary["last7"]["wins"] == 3
    assert summary["last7"]["losses"] == 1
    assert summary["last7"]["winrate"] == 75.0
    assert summary["all_time"]["total"] == 6
    assert summary["all_time"]["wins"] == 4
    assert summary["all_time"]["losses"] == 2


def test_compute_summary_totals_and_breakdown(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _insert_match(db_path, "2026-10-20T10:00:00", "win", deck="Mono Red")
    _insert_match(db_path, "2026-10-20T11:00:00", "loss", deck="Mono Red")
    _insert_match(db_path, "2026-10-20T12:00:00", "unknown", deck="Azorius")

    summary = compute_summary(db_path)

    assert summary["total"] == 3
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["unknown"] == 1
    assert summary["overall_winrate"] == 50.0
    by_deck = {item["name"]: item for item in summary["by_deck"]}
    assert by_deck["Mono Red"]["total"] == 2
    assert by_deck["Mono Red"]["winrate"] == 50.0


def test_save_match_updates_deck_stats_and_timestamp(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    match_id = save_match(
        deck_name="Mono Red",
        deck_cards=[{"cardId": 123, "quantity": 4}],
        result="win",
        opponent="atoras",
        fmt="Standard",
        db_path=db_path,
    )

    matches = get_matches(db_path)
    assert match_id == 1
    assert len(matches) == 1
    assert matches[0]["deck_name"] == "Mono Red"
    assert matches[0]["opponent"] == "atoras"
    # La base sigue guardando UTC sin sufijo; no debe romper el orden lexicográfico.
    assert "+" not in matches[0]["timestamp"]
    assert not matches[0]["timestamp"].endswith("Z")

    deck = get_deck("Mono Red", db_path)
    assert deck is not None
    assert deck["wins"] == 1
    assert deck["losses"] == 0


def test_format_local_timestamp_converts_from_utc():
    value = "2026-10-20T13:15:31.234000"
    expected = (
        datetime.fromisoformat(value)
        .replace(tzinfo=timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
    )

    assert format_local_timestamp(value) == expected
    assert format_local_timestamp(None) == "-"
