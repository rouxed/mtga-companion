"""Tests de la ventana de overlay y de su configuración."""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

from mtga_companion.gui import settings_widget as settings_module
from mtga_companion.gui.overlay_controller import OverlayController
from mtga_companion.gui.settings_widget import SettingsWidget
from mtga_companion.overlay_window import OverlayWindow


def _live_payload() -> dict:
    return {
        "visible": False,
        "position": "top-right",
        "click_through": True,
        "opacity": 0.9,
        "odds": {
            "status": "En partida",
            "deck_name": "Mono Red",
            "turn": 5,
            "on_play": True,
            "library_count": 40,
            "hand_count": 3,
            "lands_in_play": 3,
            "lands_untapped": 1,
            "lands_in_hand": 1,
            "lands_in_library": 16,
            "categories": [
                {
                    "key": "lands",
                    "label": "Tierras",
                    "remaining": 16,
                    "next": 0.4,
                    "in_three": 0.83,
                },
                {
                    "key": "creatures",
                    "label": "Criaturas",
                    "remaining": 12,
                    "next": 0.3,
                    "in_three": 0.71,
                },
                {
                    "key": "spells",
                    "label": "Hechizos",
                    "remaining": 10,
                    "next": 0.25,
                    "in_three": 0.62,
                },
                {
                    "key": "other",
                    "label": "Otras",
                    "remaining": 2,
                    "next": 0.05,
                    "in_three": 0.14,
                },
            ],
            "deck_cards": [
                {
                    "card_id": "1",
                    "name": "Mountain",
                    "type_line": "Basic Land — Mountain",
                    "category": "lands",
                    "remaining": 16,
                    "next": 0.4,
                },
                {
                    "card_id": "2",
                    "name": "Goblin Guide",
                    "type_line": "Creature — Goblin",
                    "category": "creatures",
                    "remaining": 4,
                    "next": 0.1,
                },
                {
                    "card_id": "3",
                    "name": "Lightning Bolt",
                    "type_line": "Instant",
                    "category": "spells",
                    "remaining": 3,
                    "next": 0.075,
                },
            ],
            "opponent_cards": [
                {
                    "card_id": "9",
                    "name": "Duress",
                    "type_line": "Sorcery",
                    "quantity": 2,
                }
            ],
        },
    }


def test_overlay_window_renders_live_draw_odds(qapp):
    window = OverlayWindow()
    try:
        window.apply_payload(_live_payload())

        assert window.status_chip.text() == "EN VIVO"
        assert window.deck_label.text() == "Mono Red"
        assert "Turno 5" in window.context_label.text()
        assert window.category_rows[0]["name"].text() == "Tierras"
        assert window.category_rows[0]["now"].text() == "40%"
        assert window.category_rows[0]["three"].text() == "83%"
        assert "3 en juego" in window.land_label.text()
        assert "1 sin girar" in window.land_label.text()
        assert window.deck_section.text() == "MAZO RESTANTE · 23"
        assert "Mountain" in window.deck_rows[0].text()
        assert "10% · 4× Goblin Guide" == window.deck_rows[1].text()
        assert "2× Duress" in window.opponent_rows[0].text()
        assert "Robos naturales" in window.footer_label.text()
    finally:
        window.deleteLater()


def test_overlay_window_shows_waiting_state(qapp):
    window = OverlayWindow()
    try:
        window.apply_payload(
            {
                "visible": False,
                "odds": {"status": "Esperando partida", "deck_name": "Mono Red"},
            }
        )

        assert window.status_chip.text() == "ESPERANDO"
        assert window.empty_label.text() == "Esperando partida"
        assert window.deck_label.text() == "Mono Red"
        assert window.context_label.text() == "Abrí Arena y jugá una partida"
        assert window.category_rows[0]["now"].text() == "—"
        assert window.land_label.text() == "—"
        assert window.deck_rows[0].text() == ""
        assert window.opponent_rows[0].text() == ""
    finally:
        window.deleteLater()


def test_overlay_click_through_flag_can_be_toggled(qapp):
    window = OverlayWindow()
    try:
        assert bool(
            window.windowFlags() & Qt.WindowType.WindowTransparentForInput
        )

        window.apply_payload({"visible": False, "click_through": False})
        assert not bool(
            window.windowFlags() & Qt.WindowType.WindowTransparentForInput
        )

        window.apply_payload({"visible": False, "click_through": True})
        assert bool(
            window.windowFlags() & Qt.WindowType.WindowTransparentForInput
        )
    finally:
        window.deleteLater()


def test_overlay_window_places_middle_left_vertically_centered(qapp):
    window = OverlayWindow()
    try:
        screen = QGuiApplication.primaryScreen()
        assert screen is not None
        available = screen.availableGeometry()

        window._position_key = "middle-left"
        window._place()

        assert window.x() == available.left() + 24
        assert window.y() == available.top() + (
            available.height() - window.height()
        ) // 2
    finally:
        window.deleteLater()


def test_settings_offers_middle_left_position(qapp, monkeypatch):
    monkeypatch.setattr(settings_module, "discover_log_candidates", lambda: [])
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})

    widget = SettingsWidget()
    try:
        assert widget.overlay_position.findData("middle-left") >= 0
        assert widget.overlay_settings()["position"] == "middle-left"
    finally:
        widget.cleanup()
        widget.deleteLater()


def test_frozen_controller_relaunches_the_bundled_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/MTGA-Companion.AppImage")

    program, arguments = OverlayController._overlay_command()

    assert program == "/opt/MTGA-Companion.AppImage"
    assert arguments == ["--overlay-process"]


def test_main_reports_version(monkeypatch, capsys):
    import mtga_companion.main as main_module
    from mtga_companion import __version__

    monkeypatch.setattr(sys, "argv", ["mtga-companion", "--version"])

    assert main_module.main() == 0
    assert capsys.readouterr().out.strip() == f"MTGA Companion {__version__}"


def test_main_routes_overlay_process(monkeypatch):
    import mtga_companion.main as main_module

    called: list[bool] = []
    monkeypatch.setattr(sys, "argv", ["mtga-companion", "--overlay-process"])
    monkeypatch.setattr(
        "mtga_companion.overlay_process.main",
        lambda: called.append(True) or 7,
    )

    assert main_module.main() == 7
    assert called == [True]
    assert sys.argv == ["mtga-companion"]


def test_controller_disables_overlay_without_starting_a_process(qapp):
    controller = OverlayController()
    statuses: list[str] = []
    controller.status_changed.connect(statuses.append)

    controller.configure(enabled=False)

    assert statuses == ["Overlay desactivado"]
    assert controller._process is None


def test_controller_reports_missing_x11_instead_of_crashing(qapp, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)

    controller = OverlayController()
    statuses: list[str] = []
    controller.status_changed.connect(statuses.append)

    controller.configure(enabled=True)

    assert controller._process is None
    assert statuses
    assert "no disponible" in statuses[-1].lower()
    assert "DISPLAY" in statuses[-1]


def test_settings_exposes_and_emits_overlay_configuration(qapp, monkeypatch):
    monkeypatch.setattr(settings_module, "discover_log_candidates", lambda: [])
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: {
            "overlay_enabled": True,
            "overlay_position": "bottom-left",
            "overlay_click_through": False,
            "overlay_opacity": 0.78,
        },
    )

    widget = SettingsWidget()
    try:
        assert widget.overlay_settings() == {
            "enabled": True,
            "position": "bottom-left",
            "click_through": False,
            "opacity": 0.78,
        }
        assert widget.overlay_opacity_value.text() == "78%"

        emitted: list[dict] = []
        widget.overlay_settings_changed.connect(emitted.append)
        widget.overlay_enabled.setChecked(False)

        assert emitted
        assert emitted[-1]["enabled"] is False
    finally:
        widget.cleanup()
        widget.deleteLater()
