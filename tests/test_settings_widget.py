"""Tests de la pestaña Configuración y del arranque sin Player.log."""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from mtga_companion.gui import settings_widget as settings_module
from mtga_companion.gui.settings_widget import SettingsWidget


class _FakeSignals(QObject):
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)


class _FakeWatcher:
    instances: list["_FakeWatcher"] = []

    def __init__(self, log_path=None, player_name=None, db_path=None):
        self.log_path = log_path
        self.player_name = player_name
        self.db_path = db_path
        self.signals = _FakeSignals()
        self.started = False
        self.stopped = False
        self.deleted = False
        self.instances.append(self)

    def start(self):
        self.started = True

    def isRunning(self):
        return self.started and not self.stopped

    def stop(self):
        self.stopped = True

    def wait(self, timeout_ms):
        return True

    def deleteLater(self):
        self.deleted = True


def test_settings_can_start_watcher_without_a_log_path(qapp, monkeypatch):
    _FakeWatcher.instances.clear()
    monkeypatch.setattr(settings_module, "detect_log_path", lambda: None)
    monkeypatch.setattr(settings_module, "LogWatcherThread", _FakeWatcher)

    widget = SettingsWidget()
    try:
        widget.path_edit.setText("")
        widget.start_watcher_if_configured()

        assert len(_FakeWatcher.instances) == 1
        watcher = _FakeWatcher.instances[0]
        assert watcher.log_path is None
        assert watcher.started is True
        assert widget.watcher_status.text() == "Activo"

        widget.cleanup()
        assert watcher.stopped is True
    finally:
        widget.deleteLater()


def test_settings_start_uses_configured_path_without_requiring_it_to_exist(
    qapp, monkeypatch, tmp_path
):
    _FakeWatcher.instances.clear()
    monkeypatch.setattr(settings_module, "detect_log_path", lambda: None)
    monkeypatch.setattr(settings_module, "LogWatcherThread", _FakeWatcher)

    missing_log = tmp_path / "todavia-no-existe" / "Player.log"
    widget = SettingsWidget()
    try:
        widget.path_edit.setText(str(missing_log))
        widget._start_watcher()

        watcher = _FakeWatcher.instances[0]
        assert watcher.log_path == str(missing_log)
        assert watcher.started is True
    finally:
        widget.cleanup()
        widget.deleteLater()


def test_settings_selector_shows_detected_log_and_sets_path(qapp, monkeypatch, tmp_path):
    from mtga_companion.config import LogCandidate

    log = tmp_path / "prefix" / "Player.log"
    log.parent.mkdir()
    log.write_text("", encoding="utf-8")
    candidate = LogCandidate(
        path=log,
        source="Lutris",
        prefix=tmp_path / "prefix",
        mtime=log.stat().st_mtime,
        size=0,
    )
    monkeypatch.setattr(settings_module, "discover_log_candidates", lambda: [candidate])
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})

    widget = SettingsWidget()
    try:
        assert widget.detected_combo.isEnabled() is True
        assert widget.detected_combo.count() == 1
        assert widget.detected_combo.currentData() == str(log)
        assert widget.path_edit.text() == str(log)
        assert "Lutris" in widget.detected_combo.currentText()
        assert "detectado automáticamente" in widget.status_label.text()
    finally:
        widget.cleanup()
        widget.deleteLater()


def test_settings_language_selector_emits_selected_language(qapp, monkeypatch):
    from mtga_companion.i18n import get_language, set_language

    monkeypatch.setattr(settings_module, "load_settings", lambda: {})
    set_language("es")
    widget = SettingsWidget()
    received: list[str] = []
    widget.language_changed.connect(received.append)
    try:
        index = widget.language_combo.findData("en")
        assert index >= 0
        widget.language_combo.setCurrentIndex(index)
        assert received == ["en"]
        assert get_language() == "es"
    finally:
        widget.cleanup()
        widget.deleteLater()


def test_settings_renders_language_labels_in_english(qapp, monkeypatch):
    from mtga_companion.i18n import set_language

    monkeypatch.setattr(settings_module, "load_settings", lambda: {"language": "en"})
    set_language("en")
    widget = SettingsWidget()
    try:
        assert widget.language_combo.currentData() == "en"
        assert widget.path_edit.placeholderText() == "Path to Player.log..."
        assert widget.btn_toggle.text() == "Start tracking"
    finally:
        widget.cleanup()
        widget.deleteLater()


def test_settings_selector_keeps_manual_pending_path(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module, "discover_log_candidates", lambda: [])
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: {"log_path": str(tmp_path / "todavia-no-existe" / "Player.log")},
    )

    widget = SettingsWidget()
    try:
        assert widget.detected_combo.count() == 1
        assert widget.detected_combo.currentData() == str(
            tmp_path / "todavia-no-existe" / "Player.log"
        )
        assert "pendiente" in widget.detected_combo.currentText()
    finally:
        widget.cleanup()
        widget.deleteLater()
