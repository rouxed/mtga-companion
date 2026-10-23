"""Proceso auxiliar del overlay.

La app principal corre bajo Wayland para no perder la integración nativa. Este
proceso se lanza únicamente cuando el overlay está activo y usa XCB/XWayland,
que sí permite ventanas siempre arriba y click-through. La comunicación es por
stdin: una línea JSON por snapshot.
"""
from __future__ import annotations

import json
import logging
import os
import sys

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from .config import load_settings
from .i18n import LANGUAGE_ENV_VAR, set_language, tr

logger = logging.getLogger(__name__)


class StdinReader(QThread):
    payload = pyqtSignal(object)
    closed = pyqtSignal()

    def run(self) -> None:
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Snapshot de overlay inválido: %r", line[:200])
                    continue
                if isinstance(data, dict):
                    self.payload.emit(data)
        except (OSError, ValueError):
            logger.debug("cerrando lector de overlay", exc_info=True)
        finally:
            self.closed.emit()

    def stop(self) -> None:
        # El hilo se desbloquea cuando la app principal cierra stdin.
        self.requestInterruption()


def main() -> int:
    # El proceso auxiliar no comparte memoria con la app principal: recibe el
    # idioma por entorno y, como respaldo, lo lee de la configuración.
    set_language(
        os.environ.get(LANGUAGE_ENV_VAR) or load_settings().get("language")
    )

    if not os.environ.get("DISPLAY"):
        print(
            tr("El overlay X11 no está disponible: no hay DISPLAY/XWayland."),
            file=sys.stderr,
        )
        return 1

    if not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    from .overlay_window import OverlayWindow

    app = QApplication(sys.argv)
    app.setApplicationName("MTGA Companion Overlay")
    app.setQuitOnLastWindowClosed(False)

    # No mostramos la ventana hasta que llegue el primer snapshot: así no
    # aparece un panel vacío al activar el overlay desde el menú principal.
    window = OverlayWindow()

    reader = StdinReader()
    reader.payload.connect(window.apply_payload)
    reader.closed.connect(app.quit)
    reader.start()

    exit_code = app.exec()
    reader.stop()
    reader.wait(1000)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
