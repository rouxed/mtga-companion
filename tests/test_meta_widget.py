"""Tests de la señal que entrega los mazos meta al hilo de la GUI."""
from __future__ import annotations

import time

from mtga_companion.gui.meta_widget import MetaWidget, _FetchSignals


def test_decks_loaded_signal_accepts_decks_and_request_id(qapp):
    signals = _FetchSignals()
    received = []

    signals.decks_loaded.connect(
        lambda decks, request_id: received.append((decks, request_id))
    )
    signals.decks_loaded.emit([{"name": "Mono Red"}], 7)

    assert received == [([{"name": "Mono Red"}], 7)]


def test_refresh_populates_the_list_from_a_worker_thread(qapp, monkeypatch):
    class FakeFetcher:
        def load_cached_meta(self, format_name=None):
            return {"decks": [], "format": None, "updated_at": None}

        def fetch_meta(self, fmt, force=False):
            return [
                {
                    "name": "Mono Red",
                    "format": fmt,
                    "meta_share": "10%",
                    "price": "$50",
                    "cards": [],
                }
            ]

    monkeypatch.setattr(
        "mtga_companion.gui.meta_widget.MetaFetcher",
        FakeFetcher,
    )

    widget = MetaWidget()
    try:
        widget._refresh()

        deadline = time.time() + 3
        while widget.list.count() == 0 and time.time() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert widget.list.count() == 1
        assert "Mono Red" in widget.list.item(0).text()
    finally:
        widget.cleanup()
        widget.deleteLater()


def test_export_text_uses_arena_format_with_sideboard(qapp):
    widget = MetaWidget()
    try:
        widget._current_cards = [
            {"name": "Lightning Bolt", "quantity": 4, "zone": "main"},
            {"name": "Counterspell", "quantity": 2, "zone": "main"},
            {"name": "Spell Pierce", "quantity": 2, "zone": "sideboard"},
            {"name": "Carta #123", "quantity": 1, "zone": "sideboard"},
        ]
        widget._update_export_text()

        assert widget.export_text.toPlainText() == (
            "Deck\n"
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "\n"
            "Sideboard\n"
            "2 Spell Pierce"
        )
    finally:
        widget.cleanup()
        widget.deleteLater()
