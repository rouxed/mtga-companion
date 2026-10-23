"""Ventana principal del MTGA Companion para Linux."""
from __future__ import annotations

import logging

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mtga_companion.config import DB_PATH, load_settings, save_settings
from mtga_companion.database import init_db
from mtga_companion.i18n import (
    get_language,
    normalize_language,
    runtime_message,
    set_language,
    tr,
)
from mtga_companion.overlay_positions import DEFAULT_POSITION
from mtga_companion.thread_registry import stop_all_threads
from .dashboard_widget import DashboardWidget
from .decks_widget import DecksWidget
from .history_widget import HistoryWidget
from .meta_widget import MetaWidget
from .overlay_controller import OverlayController
from .settings_widget import SettingsWidget
from .theme import GLOBAL_QSS, icon_path
from .widgets.ui import set_chip

logger = logging.getLogger(__name__)

_PAGES = [
    (
        "Dashboard",
        "Resumen de rendimiento y partidas recientes",
        "dashboard",
    ),
    (
        "Historial",
        "Todas tus partidas registradas",
        "history",
    ),
    (
        "Mazos",
        "Tus mazos y las cartas que los componen",
        "decks",
    ),
    (
        "Meta",
        "Mazos populares del metajuego actual",
        "meta",
    ),
    (
        "Configuración",
        "Player.log, jugador, overlay y seguimiento en vivo",
        "settings",
    ),
]


class MainWindow(QMainWindow):
    def __init__(self, initial_tab: int = 0):
        super().__init__()
        self.setWindowTitle(tr("MTGA Companion — Arena Tracker"))
        self.setWindowIcon(QIcon(icon_path("logo")))
        self.resize(1280, 820)
        self.setMinimumSize(1080, 680)
        self.setStyleSheet(GLOBAL_QSS)

        init_db()

        # El overlay vive en un proceso XCB aparte para no forzar toda la app
        # (que puede correr en Wayland) a usar XWayland.
        self.overlay = OverlayController(self)

        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content(), stretch=1)

        # Barra de estado discreta: el estado principal vive en el sidebar.
        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        self.setStatusBar(self.status)
        self.status.showMessage(tr("Iniciando seguimiento del Player.log…"))

        # Refrescar pestañas cuando se vuelven visibles.
        self.tabs.currentChanged.connect(self._on_tab_changed)
        initial_tab = max(0, min(int(initial_tab), self.tabs.count() - 1))
        self.tabs.setCurrentIndex(initial_tab)
        self._on_tab_changed(initial_tab)

        # Conectar antes de arrancar: el backfill puede emitir eventos de
        # inmediato y no queremos perderlos.
        self.tab_settings.watcher_created.connect(self._on_watcher_created)
        self.tab_settings.watcher_stopped.connect(self._on_watcher_stopped)
        self.tab_settings.name_edit.textChanged.connect(self._on_player_name_changed)
        self._on_player_name_changed(self.tab_settings.name_edit.text())

        self.tab_settings.overlay_settings_changed.connect(
            self._on_overlay_settings_changed
        )
        self.tab_settings.language_changed.connect(self._on_language_changed)
        self.overlay.status_changed.connect(self.tab_settings.set_overlay_status)
        self.overlay.position_changed.connect(self._on_overlay_position_changed)
        self._apply_overlay_settings(self.tab_settings.overlay_settings())

        # Auto-iniciar el watcher aunque el Player.log todavía no exista.
        self.tab_settings.start_watcher_if_configured()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(226)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 16)
        layout.setSpacing(8)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QIcon(icon_path("logo")).pixmap(QSize(34, 34)))
        logo.setFixedSize(34, 34)
        brand.addWidget(logo)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        logo_text = QLabel("MTGA")
        logo_text.setObjectName("logoText")
        logo_sub = QLabel("COMPANION")
        logo_sub.setObjectName("logoSub")
        brand_text.addWidget(logo_text)
        brand_text.addWidget(logo_sub)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(24)

        caption = QLabel(tr("NAVEGACIÓN"))
        caption.setObjectName("sideCaption")
        layout.addWidget(caption)
        layout.addSpacing(4)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, (label, _subtitle, icon_name) in enumerate(_PAGES):
            button = QPushButton(f"  {tr(label)}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(QIcon(icon_path(icon_name)))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(
                lambda _checked=False, i=index: self.tabs.setCurrentIndex(i)
            )
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)

        footer = QFrame()
        footer.setObjectName("sideFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 11, 12, 11)
        footer_layout.setSpacing(4)

        session_caption = QLabel(tr("SESIÓN"))
        session_caption.setObjectName("sideCaption")
        footer_layout.addWidget(session_caption)

        self.sidebar_player = QLabel(tr("Jugador"))
        self.sidebar_player.setStyleSheet(
            "color: #E8EDF3; font-size: 12px; font-weight: 600;"
        )
        footer_layout.addWidget(self.sidebar_player)

        self.sidebar_status = QLabel(tr("● INICIANDO"))
        set_chip(self.sidebar_status, tr("● INICIANDO"), "waiting")
        self.sidebar_status.setToolTip(tr("Estado del seguimiento de Arena"))
        footer_layout.addWidget(self.sidebar_status, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(footer)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("contentRoot")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 18, 24, 12)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 14)
        header_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.page_title = QLabel(tr("Dashboard"))
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel(
            tr("Resumen de rendimiento y partidas recientes")
        )
        self.page_subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)

        self.header_player = QLabel(tr("Jugador"))
        self.header_player.setObjectName("muted")
        header_layout.addWidget(self.header_player)

        self.overlay_button = QPushButton(tr("Overlay"))
        self.overlay_button.setObjectName("overlayButton")
        self.overlay_button.setCheckable(True)
        self.overlay_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overlay_button.setToolTip(
            tr("Mostrar u ocultar el deck tracker durante la partida")
        )
        self.overlay_button.toggled.connect(self._on_overlay_button_toggled)
        header_layout.addWidget(self.overlay_button)

        self.live_chip = QLabel(tr("● INICIANDO"))
        set_chip(self.live_chip, tr("● INICIANDO"), "waiting")
        self.live_chip.setToolTip(tr("Estado del seguimiento de Arena"))
        header_layout.addWidget(self.live_chip)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().hide()
        layout.addWidget(self.tabs, stretch=1)

        self.tab_dashboard = DashboardWidget(db_path=DB_PATH)
        self.tab_history = HistoryWidget(db_path=DB_PATH)
        self.tab_decks = DecksWidget(db_path=DB_PATH)
        self.tab_meta = MetaWidget(db_path=DB_PATH)
        self.tab_settings = SettingsWidget()
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.viewport().setStyleSheet("background: #0B0F14;")
        settings_scroll.setWidget(self.tab_settings)

        self.tabs.addTab(self.tab_dashboard, tr("Dashboard"))
        self.tabs.addTab(self.tab_history, tr("Historial"))
        self.tabs.addTab(self.tab_decks, tr("Mazos"))
        self.tabs.addTab(self.tab_meta, tr("Meta"))
        self.tabs.addTab(settings_scroll, tr("Configuración"))
        return content

    # ------------------------------------------------------------------
    # Watcher y navegación
    # ------------------------------------------------------------------
    def _connect_watcher_signals(self, watcher) -> None:
        """Conectar las señales del watcher a los widgets de visualización."""
        watcher.signals.match_detected.connect(self.tab_dashboard.on_match_detected)
        watcher.signals.match_detected.connect(self.tab_history.on_match_detected)
        watcher.signals.deck_detected.connect(self.tab_dashboard.on_deck_detected)
        watcher.signals.deck_detected.connect(self.overlay.on_deck_detected)
        watcher.signals.game_state_changed.connect(self.overlay.on_game_state)
        if hasattr(self.tab_decks, "on_deck_detected"):
            watcher.signals.deck_detected.connect(self.tab_decks.on_deck_detected)

    def _on_watcher_created(self, watcher) -> None:
        """Se llama cuando settings_widget crea un nuevo watcher."""
        self._connect_watcher_signals(watcher)
        watcher.signals.status_changed.connect(self._on_watcher_status)
        watcher.signals.error_occurred.connect(self._on_watcher_error)
        set_chip(self.live_chip, tr("● EN VIVO"), "live")
        set_chip(self.sidebar_status, tr("● EN VIVO"), "live")

    def _on_watcher_status(self, message: str) -> None:
        if message.startswith("Observando:"):
            path = message.split(":", 1)[1].strip()
            self.status.showMessage(tr("Seguimiento activo · Player.log"))
            self.live_chip.setToolTip(path)
            set_chip(self.live_chip, tr("● EN VIVO"), "live")
            set_chip(self.sidebar_status, tr("● EN VIVO"), "live")
            return

        localized = runtime_message(message)
        self.status.showMessage(localized)
        if "Esperando" in message:
            set_chip(self.live_chip, tr("● ESPERANDO"), "waiting")
            set_chip(self.sidebar_status, tr("● ESPERANDO"), "waiting")
            self.live_chip.setToolTip(localized)
        elif message:
            set_chip(self.live_chip, tr("● EN VIVO"), "live")
            set_chip(self.sidebar_status, tr("● EN VIVO"), "live")
            self.live_chip.setToolTip(localized)

    def _on_watcher_error(self, message: str) -> None:
        logger.warning("Error del watcher: %s", message)
        localized = runtime_message(message)
        self.status.showMessage(localized)
        set_chip(self.live_chip, tr("● ERROR"), "error")
        set_chip(self.sidebar_status, tr("● ERROR"), "error")
        self.live_chip.setToolTip(localized)

    def _on_watcher_stopped(self) -> None:
        self.overlay.clear()
        self.status.showMessage(tr("Seguimiento detenido"))
        set_chip(self.live_chip, tr("● DETENIDO"), "muted")
        set_chip(self.sidebar_status, tr("● DETENIDO"), "muted")
        self.live_chip.setToolTip(tr("El seguimiento está detenido"))

    def _on_player_name_changed(self, text: str) -> None:
        name = (text or "").strip() or tr("Jugador")
        self.header_player.setText(name)
        self.sidebar_player.setText(name)

    def _on_overlay_button_toggled(self, checked: bool) -> None:
        self.tab_settings.set_overlay_enabled(checked)
        self._apply_overlay_settings(
            self.tab_settings.overlay_settings(),
            persist=True,
        )

    def _on_overlay_settings_changed(self, settings: dict) -> None:
        self._apply_overlay_settings(settings, persist=True)

    def _apply_overlay_settings(self, settings: dict, persist: bool = False) -> None:
        enabled = bool(settings.get("enabled", False))
        self.overlay.configure(
            enabled=enabled,
            position=str(settings.get("position") or DEFAULT_POSITION),
            click_through=bool(settings.get("click_through", True)),
            opacity=float(settings.get("opacity", 0.94)),
        )

        self.overlay_button.blockSignals(True)
        self.overlay_button.setChecked(enabled)
        self.overlay_button.setText(tr("Overlay ON") if enabled else tr("Overlay"))
        self.overlay_button.blockSignals(False)

        if not persist:
            return
        stored = load_settings()
        stored.update(
            {
                "overlay_enabled": enabled,
                "overlay_position": str(settings.get("position") or DEFAULT_POSITION),
                "overlay_click_through": bool(
                    settings.get("click_through", True)
                ),
                "overlay_opacity": float(settings.get("opacity", 0.94)),
            }
        )
        save_settings(stored)

    def _on_overlay_position_changed(self, position: str) -> None:
        self.tab_settings.set_overlay_position(position)
        self._apply_overlay_settings(
            self.tab_settings.overlay_settings(),
            persist=True,
        )

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < len(_PAGES):
            title, subtitle, _icon = _PAGES[index]
            self.page_title.setText(tr(title))
            self.page_subtitle.setText(tr(subtitle))
        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

        widget = self.tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()
        elif hasattr(widget, "load"):
            widget.load()
        elif hasattr(widget, "load_decks"):
            widget.load_decks()

    def _on_language_changed(self, language: str) -> None:
        """Guarda el idioma y reconstruye la ventana con las traducciones nuevas."""
        normalized = normalize_language(language)
        if normalized == get_language():
            return

        settings = load_settings()
        settings["language"] = normalized
        save_settings(settings)
        self.status.showMessage(tr("Aplicando idioma…"))
        QTimer.singleShot(0, lambda: self._rebuild_for_language(normalized))

    def _rebuild_for_language(self, language: str) -> None:
        """Recrea la ventana en el mismo proceso para aplicar el idioma.

        Cerrar la ventana anterior detiene su watcher, su overlay y sus hilos.
        Se desactiva temporalmente ``quitOnLastWindowClosed`` para que Qt no
        termine la aplicación durante el breve intervalo entre ambas ventanas.
        """
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return

        initial_tab = self.tabs.currentIndex()
        geometry = self.geometry()
        maximized = self.isMaximized()

        set_language(language)
        app.setQuitOnLastWindowClosed(False)
        self.close()

        try:
            window = MainWindow(initial_tab=initial_tab)
            window.setGeometry(geometry)
            if maximized:
                window.showMaximized()
            else:
                window.show()
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo reconstruir la ventana al cambiar el idioma")
            app.setQuitOnLastWindowClosed(True)
            app.quit()
            return

        app._mtga_main_window = window
        app.setQuitOnLastWindowClosed(True)
        self.deleteLater()

    def closeEvent(self, event):  # noqa: N802
        """Detiene hilos, temporizadores y cierra de forma ordenada."""
        logger.info("Cerrando la aplicación")
        self.overlay.cleanup()
        for widget in (
            self.tab_settings,
            self.tab_meta,
            self.tab_decks,
            self.tab_dashboard,
        ):
            cleanup = getattr(widget, "cleanup", None)
            if cleanup is not None:
                try:
                    cleanup()
                except Exception:  # noqa: BLE001
                    logger.exception("Error limpiando %s", widget)
        stop_all_threads()
        event.accept()
