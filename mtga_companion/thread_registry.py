"""Registro global de QThreads para detenerlos de forma cooperativa al salir."""
from __future__ import annotations

import logging

from PyQt6.QtCore import QThread

logger = logging.getLogger(__name__)

_active_threads: list[QThread] = []


def register_thread(thread: QThread) -> None:
    """Registra un QThread para poder detenerlo al cerrar la aplicación."""
    if thread not in _active_threads:
        _active_threads.append(thread)


def unregister_thread(thread: QThread) -> None:
    """Desregistra un QThread cuando termina normalmente."""
    try:
        _active_threads.remove(thread)
    except ValueError:
        pass


def stop_all_threads(timeout_ms: int = 5000) -> None:
    """Detiene todos los QThreads registrados sin usar ``terminate()``.

    Los hilos deben implementar ``stop()`` para cancelar su trabajo de forma
    cooperativa. Si alguno no termina a tiempo se registra una advertencia;
    no se destruye a la fuerza para evitar corrupción de estado.
    """
    for thread in list(_active_threads):
        try:
            if hasattr(thread, "stop"):
                thread.stop()
            if thread.isRunning():
                thread.quit()
                if not thread.wait(timeout_ms):
                    logger.warning(
                        "El hilo %s no terminó en %s ms", thread, timeout_ms
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Error deteniendo el hilo %s", thread)
    _active_threads.clear()
