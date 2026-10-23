"""Pruebas mínimas de widgets que formatean datos de la base."""
from __future__ import annotations

from mtga_companion.database import format_local_timestamp, init_db, save_match
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
