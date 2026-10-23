"""Punto de entrada del MTGA Companion para Linux."""
from __future__ import annotations

import logging
import signal
import sys

from PyQt6.QtCore import QTimer, QtMsgType, qInstallMessageHandler
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QApplication

from . import __version__
from .config import ensure_app_data, load_settings
from .i18n import set_language
from .logging_config import setup_logging, shutdown_logging
from .thread_registry import stop_all_threads

logger = logging.getLogger(__name__)


def _qt_message_handler(mode: QtMsgType, context, message: str) -> None:
    """Redirige los mensajes de Qt al log de la aplicación."""
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    level = levels.get(mode, logging.INFO)
    logging.getLogger("qt").log(
        level,
        "%s (%s:%s)",
        message,
        getattr(context, "file", None) or "?",
        getattr(context, "line", 0) or 0,
    )


def main() -> int:
    if "--version" in sys.argv:
        print(f"MTGA Companion {__version__}")
        return 0

    # En un build con PyInstaller no existe ``python -m``: el proceso auxiliar
    # del overlay se relanza con el mismo ejecutable y este argumento.
    if "--overlay-process" in sys.argv:
        sys.argv = [arg for arg in sys.argv if arg != "--overlay-process"]
        from .overlay_process import main as overlay_main

        return overlay_main()

    setup_logging()
    ensure_app_data()
    set_language(load_settings().get("language"))
    qInstallMessageHandler(_qt_message_handler)

    app = QApplication(sys.argv)
    app.setApplicationName("MTGA Companion")
    app.setApplicationDisplayName("MTGA Companion")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("mtga-companion")
    app.setStyle("Fusion")
    base_font = QFont("Noto Sans")
    base_font.setPointSize(10)
    app.setFont(base_font)

    # Importar después de preparar datos/logging.
    from .gui.main_window import MainWindow
    from .gui.theme import icon_path

    app.setWindowIcon(QIcon(icon_path("logo")))

    window = MainWindow()
    app._mtga_main_window = window
    window.show()

    def _request_quit(signum, frame) -> None:
        logger.info("Señal %s recibida; cerrando la aplicación", signum)
        app.quit()

    try:
        signal.signal(signal.SIGINT, _request_quit)
        signal.signal(signal.SIGTERM, _request_quit)
    except ValueError:
        # No estamos en el hilo principal (por ejemplo, en un test).
        pass

    # Permite que Qt procese las señales de Unix mientras corre el event loop.
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(250)

    exit_code = 0
    try:
        exit_code = app.exec()
    finally:
        current_window = getattr(app, "_mtga_main_window", window)
        try:
            current_window.close()
        except Exception:  # noqa: BLE001
            logger.exception("Error cerrando la ventana principal")
        stop_all_threads()
        logger.info("Aplicación cerrada")
        shutdown_logging()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
