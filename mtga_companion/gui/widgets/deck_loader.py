"""Worker asíncrono para resolver cartas de un mazo vía Scryfall sin bloquear la GUI."""
from __future__ import annotations

import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from mtga_companion.scryfall import ScryfallCancelled, ScryfallClient

logger = logging.getLogger(__name__)


class DeckLoaderSignals(QObject):
    finished = pyqtSignal(object)   # lista de cartas resueltas
    error = pyqtSignal(str)         # mensaje de error


class DeckLoaderThread(threading.Thread):
    """Resuelve las cartas de un mazo en un hilo daemon.

    Se usa ``threading.Thread`` (no ``QThread``) para que el cierre de la
    aplicación no dependa de destruir un QThread en ejecución. Las señales
    Qt se emiten desde el hilo y Qt las entrega en el hilo de la GUI.
    """

    def __init__(self, card_entries: list[dict], parent=None):
        super().__init__(daemon=True, name="DeckLoader")
        self.signals = DeckLoaderSignals(parent)
        self.card_entries = card_entries
        self._cancel_event = threading.Event()

    def run(self) -> None:
        try:
            scryfall = ScryfallClient(cancel_event=self._cancel_event)
            cards = scryfall.resolve_deck(self.card_entries)
            if self._cancel_event.is_set():
                return
            self.signals.finished.emit(cards)
        except ScryfallCancelled:
            logger.debug("Resolución de mazo cancelada")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error resolviendo cartas del mazo")
            if not self._cancel_event.is_set():
                self.signals.error.emit(str(exc))

    def stop(self) -> None:
        self._cancel_event.set()
