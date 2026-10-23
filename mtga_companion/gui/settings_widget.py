"""Pestaña Configuración: rutas, nombre de jugador y control del watcher."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from mtga_companion.config import (
    LogCandidate,
    detect_log_path,
    discover_log_candidates,
    load_settings,
    save_settings,
)
from mtga_companion.i18n import (
    LANGUAGE_OPTIONS,
    get_language,
    normalize_language,
    runtime_message,
    tr,
)
from mtga_companion.log_watcher import LogWatcherThread
from mtga_companion.overlay_positions import DEFAULT_POSITION, POSITION_ITEMS
from .widgets.ui import set_chip

logger = logging.getLogger(__name__)


class SettingsWidget(QWidget):
    """Pestaña Configuración: rutas, nombre de jugador y control del watcher."""
    # Señal emitida cuando se crea un nuevo watcher (para conectar señales desde main_window)
    watcher_created = pyqtSignal(object)
    watcher_stopped = pyqtSignal()
    overlay_settings_changed = pyqtSignal(dict)
    language_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.watcher: LogWatcherThread | None = None
        self._destroyed = False
        self._candidates: list[LogCandidate] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # --- Idioma ---
        language_layout = QHBoxLayout()
        language_layout.setSpacing(10)
        language_label = QLabel(tr("Idioma"))
        language_label.setObjectName("muted")
        language_layout.addWidget(language_label)
        language_info = QLabel(tr("Idioma de la interfaz. Se aplica al instante."))
        language_info.setObjectName("sectionHint")
        language_info.setWordWrap(True)
        language_layout.addWidget(language_info, stretch=1)
        self.language_combo = QComboBox()
        for code, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(label, code)
        self.language_combo.setMinimumWidth(150)
        language_layout.addWidget(self.language_combo)
        root.addLayout(language_layout)

        # --- Ruta del log ---
        log_group = QGroupBox(tr("Player.log de MTG Arena"))
        log_layout = QVBoxLayout(log_group)

        info = QLabel(
            tr(
                "El companion lee el archivo Player.log de MTG Arena en tiempo real.\n"
                "La ruta se detecta automáticamente; si hay varias instalaciones, "
                "podés elegir una abajo."
            )
        )
        info.setWordWrap(True)
        info.setObjectName("sectionHint")
        log_layout.addWidget(info)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("Ruta al Player.log..."))
        path_row.addWidget(self.path_edit, stretch=1)

        btn_browse = QPushButton(tr("Examinar…"))
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        log_layout.addLayout(path_row)

        detected_row = QHBoxLayout()
        detected_label = QLabel(tr("Detectadas"))
        detected_label.setObjectName("muted")
        detected_row.addWidget(detected_label)

        self.detected_combo = QComboBox()
        self.detected_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.detected_combo.setMinimumContentsLength(42)
        self.detected_combo.setPlaceholderText(tr("Sin rutas detectadas"))
        self.detected_combo.currentIndexChanged.connect(self._on_candidate_selected)
        detected_row.addWidget(self.detected_combo, stretch=1)

        btn_detect = QPushButton(tr("Buscar rutas"))
        btn_detect.clicked.connect(self._auto_detect)
        detected_row.addWidget(btn_detect)
        log_layout.addLayout(detected_row)

        detect_hint = QLabel(
            tr(
                "Se buscan instalaciones de Steam, Lutris, Heroic/Epic, Bottles, "
                "Wine manual y particiones Windows."
            )
        )
        detect_hint.setObjectName("sectionHint")
        detect_hint.setWordWrap(True)
        log_layout.addWidget(detect_hint)

        self.status_label = QLabel("")
        self.status_label.setObjectName("sectionHint")
        self.status_label.setWordWrap(True)
        log_layout.addWidget(self.status_label)

        root.addWidget(log_group)

        # --- Nombre de jugador ---
        name_group = QGroupBox(tr("Tu nombre de jugador en Arena"))
        name_layout = QVBoxLayout(name_group)
        name_info = QLabel(
            tr(
                "Se usa para saber si sos vos quien ganó o perdió cada partida "
                "(formato \"Nombre#12345\"). Si lo dejás vacío, el resultado se marcará como desconocido."
            )
        )
        name_info.setWordWrap(True)
        name_info.setObjectName("sectionHint")
        name_layout.addWidget(name_info)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("Nombre#12345"))
        name_layout.addWidget(self.name_edit)
        root.addWidget(name_group)

        # --- Control del watcher ---
        ctrl_group = QGroupBox(tr("Seguimiento de partidas en vivo"))
        ctrl_layout = QVBoxLayout(ctrl_group)

        self.btn_toggle = QPushButton(tr("Iniciar seguimiento"))
        self.btn_toggle.setStyleSheet(
            "QPushButton { background: #D6B36A; color: #151A21; border: 1px solid #D6B36A;"
            " font-weight: 700; padding: 9px; border-radius: 9px; }"
            "QPushButton:hover { background: #E8C97F; border-color: #E8C97F; }"
            "QPushButton:pressed { background: #C5A257; }"
        )
        self.btn_toggle.clicked.connect(self._toggle_watcher)
        ctrl_layout.addWidget(self.btn_toggle)

        self.watcher_status = QLabel(tr("Detenido"))
        set_chip(self.watcher_status, tr("Detenido"), "muted")
        self.watcher_status.setToolTip(tr("Estado del seguimiento de Arena"))
        ctrl_layout.addWidget(self.watcher_status)

        root.addWidget(ctrl_group)

        # --- Overlay de partida ---
        overlay_group = QGroupBox(tr("Overlay de partida"))
        overlay_layout = QVBoxLayout(overlay_group)

        overlay_info = QLabel(
            tr(
                "Deck tracker con probabilidades de robo, contador de tierras y "
                "cartas vistas del oponente. Usa únicamente tu mazo, tu mano y las "
                "zonas públicas o reveladas del log; nunca la mano ni la biblioteca "
                "oculta del oponente."
            )
        )
        overlay_info.setWordWrap(True)
        overlay_info.setObjectName("sectionHint")
        overlay_layout.addWidget(overlay_info)

        self.overlay_enabled = QCheckBox(tr("Mostrar overlay durante la partida"))
        overlay_layout.addWidget(self.overlay_enabled)

        self.overlay_click_through = QCheckBox(
            tr("Click-through: no bloquear los clics del juego")
        )
        self.overlay_click_through.setToolTip(
            tr(
                "Con click-through activo, el overlay no recibe clics. "
                "Podés desactivarlo para moverlo con el mouse."
            )
        )
        overlay_layout.addWidget(self.overlay_click_through)

        position_row = QHBoxLayout()
        position_label = QLabel(tr("Posición"))
        position_label.setObjectName("muted")
        position_row.addWidget(position_label)
        self.overlay_position = QComboBox()
        for label, key in POSITION_ITEMS:
            self.overlay_position.addItem(tr(label), key)
        position_row.addWidget(self.overlay_position, stretch=1)
        overlay_layout.addLayout(position_row)

        opacity_row = QHBoxLayout()
        opacity_label = QLabel(tr("Opacidad"))
        opacity_label.setObjectName("muted")
        opacity_row.addWidget(opacity_label)
        self.overlay_opacity = QSlider(Qt.Orientation.Horizontal)
        self.overlay_opacity.setRange(45, 100)
        self.overlay_opacity.setValue(94)
        self.overlay_opacity.setToolTip(tr("Opacidad del panel del overlay"))
        opacity_row.addWidget(self.overlay_opacity, stretch=1)
        self.overlay_opacity_value = QLabel("94%")
        self.overlay_opacity_value.setObjectName("muted")
        self.overlay_opacity_value.setFixedWidth(40)
        self.overlay_opacity_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        opacity_row.addWidget(self.overlay_opacity_value)
        overlay_layout.addLayout(opacity_row)

        self.overlay_status = QLabel(tr("Overlay desactivado"))
        set_chip(self.overlay_status, tr("Overlay desactivado"), "muted")
        self.overlay_status.setToolTip(tr("Estado del proceso de overlay"))
        overlay_layout.addWidget(
            self.overlay_status, alignment=Qt.AlignmentFlag.AlignLeft
        )

        root.addWidget(overlay_group)
        root.addStretch()

        # Cargar configuración guardada
        self._load_config()

        self.overlay_enabled.toggled.connect(self._emit_overlay_settings)
        self.overlay_click_through.toggled.connect(self._emit_overlay_settings)
        self.overlay_position.currentIndexChanged.connect(
            self._emit_overlay_settings
        )
        self.overlay_opacity.valueChanged.connect(self._on_opacity_changed)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

    def _load_config(self):
        settings = load_settings()
        language = normalize_language(settings.get("language", get_language()))
        language_index = self.language_combo.findData(language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)

        path = settings.get("log_path", "") or ""
        name = settings.get("player_name", "") or ""
        self.path_edit.setText(path)
        self.path_edit.setCursorPosition(0)
        self.name_edit.setText(name)

        self.overlay_enabled.setChecked(bool(settings.get("overlay_enabled", False)))
        self.overlay_click_through.setChecked(
            bool(settings.get("overlay_click_through", True))
        )
        position = str(settings.get("overlay_position") or DEFAULT_POSITION)
        position_index = self.overlay_position.findData(position)
        if position_index < 0:
            position_index = self.overlay_position.findData(DEFAULT_POSITION)
        self.overlay_position.setCurrentIndex(max(0, position_index))
        try:
            opacity = int(round(float(settings.get("overlay_opacity", 0.94)) * 100))
        except (TypeError, ValueError):
            opacity = 94
        self.overlay_opacity.setValue(max(45, min(100, opacity)))
        self.overlay_opacity_value.setText(f"{self.overlay_opacity.value()}%")

        candidates = self._refresh_candidates(update_path=not bool(path))
        if not path:
            if candidates:
                self.path_edit.setText(str(candidates[0].path))
                self.path_edit.setCursorPosition(0)
                self.status_label.setText(tr("Player.log detectado automáticamente"))
                self.status_label.setToolTip(str(candidates[0].path))
            else:
                self.status_label.setText(tr("No se detectó el Player.log todavía."))
        else:
            self.status_label.setText(tr("Ruta configurada · Player.log"))
            self.status_label.setToolTip(path)

    def _on_language_changed(self, _index: int) -> None:
        language = self.language_combo.currentData()
        if language and language != get_language():
            self.language_changed.emit(str(language))

    @staticmethod
    def _compact_path(path: Path) -> str:
        """Ruta corta para el selector; el path completo queda en el tooltip."""
        try:
            path = path.expanduser()
            home = Path.home()
            if path.is_relative_to(home):
                path = Path("~") / path.relative_to(home)
        except (ValueError, OSError):
            pass
        parts = path.parts
        if len(parts) > 5:
            return "…/" + "/".join(parts[-4:])
        return str(path)

    def _candidate_label(self, candidate: LogCandidate) -> str:
        if candidate.prefix:
            context = self._compact_path(candidate.prefix)
        else:
            context = self._compact_path(candidate.path)
        return f"{tr(candidate.source)} · {context}"

    @staticmethod
    def _same_path(left: str | Path, right: str | Path) -> bool:
        try:
            return (
                Path(left).expanduser().resolve(strict=False)
                == Path(right).expanduser().resolve(strict=False)
            )
        except (OSError, RuntimeError):
            return str(left) == str(right)

    def _combo_index_for_path(self, path: str) -> int:
        for index in range(self.detected_combo.count()):
            data = self.detected_combo.itemData(index)
            if data and self._same_path(data, path):
                return index
        return -1

    def _refresh_candidates(self, update_path: bool = False) -> list[LogCandidate]:
        """Escanea prefijos y llena el selector de rutas detectadas."""
        try:
            candidates = discover_log_candidates()
        except Exception:  # noqa: BLE001
            logger.exception("Error buscando rutas de Player.log")
            candidates = []

        self._candidates = candidates
        current = self.path_edit.text().strip()

        self.detected_combo.blockSignals(True)
        self.detected_combo.clear()
        for candidate in candidates:
            label = self._candidate_label(candidate)
            self.detected_combo.addItem(label, str(candidate.path))
            index = self.detected_combo.count() - 1
            self.detected_combo.setItemData(
                index,
                f"{tr(candidate.source)}\n{candidate.path}\n"
                f"{tr('Modificado: {date}', date=tr(candidate.modified_label))}",
                Qt.ItemDataRole.ToolTipRole,
            )

        # Si la ruta configurada es manual y no apareció en el escaneo,
        # mostrarla igualmente para que el selector refleje el estado real.
        normalized_current = None
        if current:
            try:
                normalized_current = str(Path(current).expanduser().resolve(strict=False))
            except (OSError, RuntimeError):
                normalized_current = current
        candidate_paths = set()
        for candidate in candidates:
            try:
                candidate_paths.add(str(candidate.path.resolve(strict=False)))
            except (OSError, RuntimeError):
                candidate_paths.add(str(candidate.path))
        if current and normalized_current not in candidate_paths:
            state = "" if Path(current).expanduser().is_file() else tr("(pendiente)")
            self.detected_combo.addItem(
                tr(
                    "Ruta configurada{state} · {path}",
                    state=f" {state}" if state else "",
                    path=self._compact_path(Path(current)),
                ),
                current,
            )
            index = self.detected_combo.count() - 1
            self.detected_combo.setItemData(index, current, Qt.ItemDataRole.ToolTipRole)

        if self.detected_combo.count() == 0:
            self.detected_combo.addItem(tr("Sin rutas detectadas"), None)
            self.detected_combo.setEnabled(False)
        else:
            self.detected_combo.setEnabled(True)
            index = self._combo_index_for_path(current) if current else -1
            if index < 0 and (update_path or not current):
                index = 0
                selected_path = self.detected_combo.itemData(0)
                if selected_path:
                    self.path_edit.setText(str(selected_path))
                    self.path_edit.setCursorPosition(0)
            if index < 0 and current:
                index = self.detected_combo.count() - 1
            self.detected_combo.setCurrentIndex(index if index >= 0 else 0)

        self.detected_combo.blockSignals(False)
        return candidates

    def _on_candidate_selected(self, index: int) -> None:
        if index < 0:
            return
        path = self.detected_combo.itemData(index)
        if not path:
            return
        self.path_edit.setText(str(path))
        self.path_edit.setCursorPosition(0)
        self.status_label.setText(tr("Ruta de Player.log seleccionada"))
        self.status_label.setToolTip(str(path))

    def _sync_combo_to_path(self, path: str) -> None:
        """Refleja en el selector una ruta elegida manualmente."""
        if not path:
            return
        self.detected_combo.blockSignals(True)
        try:
            if (
                self.detected_combo.count() == 1
                and self.detected_combo.itemData(0) is None
            ):
                self.detected_combo.clear()
            index = self._combo_index_for_path(path)
            if index < 0:
                state = "" if Path(path).expanduser().is_file() else tr("(pendiente)")
                self.detected_combo.addItem(
                    tr(
                        "Ruta configurada{state} · {path}",
                        state=f" {state}" if state else "",
                        path=self._compact_path(Path(path)),
                    ),
                    path,
                )
                index = self.detected_combo.count() - 1
                self.detected_combo.setItemData(
                    index, path, Qt.ItemDataRole.ToolTipRole
                )
            if index >= 0:
                self.detected_combo.setEnabled(True)
                self.detected_combo.setCurrentIndex(index)
        finally:
            self.detected_combo.blockSignals(False)

    def start_watcher_if_configured(self):
        """Inicia el watcher automáticamente al abrir la aplicación.

        Se inicia incluso si todavía no hay una ruta o el archivo no existe:
        el watcher espera y detecta el Player.log cuando MTG Arena lo cree.
        """
        if self.watcher is not None and self.watcher.isRunning():
            return  # Ya está corriendo

        log_path = self.path_edit.text().strip() or None

        if not log_path:
            detected = detect_log_path()
            if detected:
                log_path = str(detected)
                self.path_edit.setText(log_path)
                self.path_edit.setCursorPosition(0)
                self.status_label.setText(tr("Player.log detectado automáticamente"))
                self.status_label.setToolTip(log_path)
                self._sync_combo_to_path(log_path)

        self._start_watcher()

    def _on_watcher_status(self, message: str) -> None:
        localized = runtime_message(message)
        if message.startswith("Observando:"):
            path = message.split(":", 1)[1].strip()
            set_chip(self.watcher_status, tr("Activo · Player.log"), "live")
            self.watcher_status.setToolTip(path)
        elif "Esperando" in message:
            set_chip(self.watcher_status, tr("Esperando Player.log"), "waiting")
            self.watcher_status.setToolTip(localized)
        elif message:
            set_chip(self.watcher_status, localized, "live")
            self.watcher_status.setToolTip(localized)

    def overlay_settings(self) -> dict:
        return {
            "enabled": self.overlay_enabled.isChecked(),
            "position": self.overlay_position.currentData() or DEFAULT_POSITION,
            "click_through": self.overlay_click_through.isChecked(),
            "opacity": self.overlay_opacity.value() / 100.0,
        }

    def _on_opacity_changed(self, value: int) -> None:
        self.overlay_opacity_value.setText(f"{value}%")
        self._emit_overlay_settings()

    def _emit_overlay_settings(self, *_args) -> None:
        self.overlay_settings_changed.emit(self.overlay_settings())

    def set_overlay_enabled(self, enabled: bool) -> None:
        self.overlay_enabled.blockSignals(True)
        self.overlay_enabled.setChecked(bool(enabled))
        self.overlay_enabled.blockSignals(False)

    def set_overlay_position(self, position: str) -> None:
        index = self.overlay_position.findData(position)
        if index < 0:
            return
        self.overlay_position.blockSignals(True)
        self.overlay_position.setCurrentIndex(index)
        self.overlay_position.blockSignals(False)

    def set_overlay_status(self, message: str) -> None:
        enabled = self.overlay_enabled.isChecked()
        lower = message.lower()
        if "no disponible" in lower or "unavailable" in lower or "error" in lower:
            kind = "error"
        elif enabled:
            kind = "live"
        else:
            kind = "muted"
        set_chip(self.overlay_status, message or tr("Overlay"), kind)
        self.overlay_status.setToolTip(message)

    def _browse(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            tr("Seleccionar Player.log"),
            str(Path.home()),
            tr("Logs (*.log);;Todos (*)"),
        )
        if file:
            self.path_edit.setText(file)
            self.path_edit.setCursorPosition(0)
            self.status_label.setText(tr("Ruta de Player.log seleccionada"))
            self.status_label.setToolTip(file)
            self._sync_combo_to_path(file)

    def _auto_detect(self):
        candidates = self._refresh_candidates(update_path=True)
        if candidates:
            best = candidates[0]
            self.path_edit.setText(str(best.path))
            self.path_edit.setCursorPosition(0)
            self.status_label.setText(
                tr(
                    "{count} ruta(s) detectada(s) · usando {source}",
                    count=len(candidates),
                    source=tr(best.source),
                )
            )
            self.status_label.setToolTip(str(best.path))
            if len(candidates) == 1:
                detail = str(best.path)
            else:
                detail = "\n".join(
                    f"• {tr(c.source)}: {c.path}" for c in candidates[:6]
                )
                if len(candidates) > 6:
                    detail += "\n" + tr(
                        "… y {count} más", count=len(candidates) - 6
                    )
            QMessageBox.information(
                self,
                tr("Rutas detectadas"),
                tr(
                    "Se encontraron {count} Player.log.\n\n"
                    "Se usará la ruta más reciente; podés cambiarla en el selector.\n\n"
                    "{detail}",
                    count=len(candidates),
                    detail=detail,
                ),
            )
        else:
            self.status_label.setText(tr("No se detectó el Player.log todavía."))
            QMessageBox.warning(
                self,
                tr("No encontrado"),
                tr(
                    "No se pudo detectar automáticamente el Player.log.\n"
                    "Se buscaron Steam, Lutris, Heroic/Epic, Bottles, Wine "
                    "y particiones Windows.\n\n"
                    "Si tu instalación usa una ruta personalizada, seleccionala "
                    "manualmente con 'Examinar…'."
                ),
            )

    def _toggle_watcher(self):
        if self.watcher is not None and self.watcher.isRunning():
            self._stop_watcher()
        else:
            self._start_watcher()

    def _start_watcher(self):
        log_path = self.path_edit.text().strip() or None
        player_name = self.name_edit.text().strip() or None
        if log_path:
            self._sync_combo_to_path(log_path)

        if self.watcher is not None:
            self._stop_watcher()

        self.watcher = LogWatcherThread(log_path=log_path, player_name=player_name)
        self.watcher.signals.status_changed.connect(self._on_watcher_status)
        self.watcher.signals.error_occurred.connect(
            lambda msg: QMessageBox.warning(
                self, tr("Error del watcher"), runtime_message(msg)
            )
        )

        # Conectar consumidores antes de arrancar el hilo: el backfill puede
        # emitir eventos inmediatamente.
        self.watcher_created.emit(self.watcher)
        self.watcher.start()
        logger.info(
            "Seguimiento iniciado (log=%s, jugador=%s)",
            log_path or "auto-detectar",
            player_name or "sin configurar",
        )

        self.btn_toggle.setText(tr("Detener seguimiento"))
        self.btn_toggle.setStyleSheet(
            "QPushButton { background: rgba(255, 107, 107, 0.14); color: #FF6B6B;"
            " border: 1px solid rgba(255, 107, 107, 0.45); font-weight: 700;"
            " padding: 9px; border-radius: 9px; }"
            "QPushButton:hover { background: rgba(255, 107, 107, 0.22); }"
            "QPushButton:pressed { background: rgba(255, 107, 107, 0.10); }"
        )
        set_chip(self.watcher_status, tr("Activo"), "live")

        # Guardar configuración
        settings = load_settings()
        settings["log_path"] = log_path or ""
        settings["player_name"] = player_name or ""
        save_settings(settings)


    def _stop_watcher(self):
        watcher = self.watcher
        self.watcher = None
        if watcher is not None:
            watcher.stop()
            if not watcher.wait(5000):
                logger.warning("El watcher no terminó en 5 segundos")
            else:
                watcher.deleteLater()
            logger.info("Seguimiento detenido")

        self.btn_toggle.setText(tr("Iniciar seguimiento"))
        self.btn_toggle.setStyleSheet(
            "QPushButton { background: #D6B36A; color: #151A21; border: 1px solid #D6B36A;"
            " font-weight: 700; padding: 9px; border-radius: 9px; }"
            "QPushButton:hover { background: #E8C97F; border-color: #E8C97F; }"
            "QPushButton:pressed { background: #C5A257; }"
        )
        set_chip(self.watcher_status, tr("Detenido"), "muted")
        self.watcher_status.style().unpolish(self.watcher_status)
        self.watcher_status.style().polish(self.watcher_status)
        self.watcher_stopped.emit()

    def stop_watcher(self):
        """Alias público para el cierre desde MainWindow."""
        self._stop_watcher()

    def cleanup(self):
        """Detener todos los hilos antes de cerrar la aplicación."""
        self._stop_watcher()