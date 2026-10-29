"""Pruebas mínimas de widgets que formatean datos de la base."""
from __future__ import annotations

from PyQt6.QtTest import QTest

from mtga_companion.database import format_local_timestamp, init_db, save_match
from mtga_companion.gui import history_widget as history_module
from mtga_companion.gui.history_widget import HistoryWidget


def test_history_widget_renders_match_with_local_timestamp(qapp, tmp_path):
    db_path = tmp_path / "gui.db"
    init_db(db_path)
    save_match(
        "Mono Red",
        [],
        "win",
        "atoras",
        "Standard",
        db_path=db_path,
        timestamp="2026-10-20T13:15:31",
        match_id="match-gui",
    )

    widget = HistoryWidget(db_path=db_path)
    try:
        assert widget.table.rowCount() == 1
        assert widget.table.item(0, 0).text() == format_local_timestamp(
            "2026-10-20T13:15:31"
        )
        assert widget.table.item(0, 1).text() == "Mono Red"
    finally:
        widget.deleteLater()


def _save(db_path, deck, match_id):
    save_match(
        deck,
        [],
        "win",
        "atoras",
        "Standard",
        db_path=db_path,
        timestamp="2026-10-20T13:15:31",
        match_id=match_id,
    )


def test_history_widget_skips_reload_when_database_is_unchanged(
    qapp, tmp_path, monkeypatch
):
    db_path = tmp_path / "cache.db"
    init_db(db_path)
    _save(db_path, "Mono Red", "match-1")

    widget = HistoryWidget(db_path=db_path)
    calls = []
    real_get_matches = history_module.get_matches

    def counting_get_matches(path):
        calls.append(path)
        return real_get_matches(path)

    monkeypatch.setattr(history_module, "get_matches", counting_get_matches)
    try:
        widget.load()
        assert calls == []

        _save(db_path, "Mono Blue", "match-2")
        widget.load()
        assert len(calls) == 1
        assert widget.table.rowCount() == 2
    finally:
        widget.deleteLater()


def test_history_widget_search_is_debounced(qapp, tmp_path):
    db_path = tmp_path / "debounce.db"
    init_db(db_path)
    _save(db_path, "Mono Red", "match-red")
    _save(db_path, "Azorius Control", "match-azorius")

    widget = HistoryWidget(db_path=db_path)
    try:
        widget.search.setText("mono")
        assert widget.table.rowCount() == 2

        QTest.qWait(250)
        assert widget.table.rowCount() == 1
        assert widget.table.item(0, 1).text() == "Mono Red"
    finally:
        widget.deleteLater()
