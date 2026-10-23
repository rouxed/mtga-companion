"""Configuración de logging de la aplicación.

Los logs van a un archivo rotativo dentro del directorio de datos XDG. Se
incluye además un manejador de consola para ejecuciones desde terminal y un
``sys.excepthook`` que registra excepciones no capturadas.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LOG_DIR

_configured = False
_log_path: Path | None = None
_original_excepthook = sys.excepthook


def _is_our_handler(handler: logging.Handler) -> bool:
    return bool(getattr(handler, "_mtga_companion", False))


def setup_logging(log_dir: Path | None = None, force: bool = False) -> Path:
    """Configura el logging y devuelve la ruta del archivo de log.

    Es idempotente: llamarla dos veces no duplica handlers. ``force`` sirve
    para tests y para reinicializar la configuración.
    """
    global _configured, _log_path

    log_dir = log_dir or LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "mtga-companion.log"

    if _configured and not force and _log_path is not None:
        return _log_path

    root = logging.getLogger()
    if force:
        for handler in list(root.handlers):
            if _is_our_handler(handler):
                root.removeHandler(handler)
                handler.close()

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler._mtga_companion = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler._mtga_companion = True  # type: ignore[attr-defined]
    root.addHandler(console_handler)

    def _excepthook(exc_type, exc_value, exc_tb):
        logging.getLogger("mtga_companion").critical(
            "Excepción no capturada",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    _configured = True
    _log_path = log_path
    logging.getLogger(__name__).info("Log iniciado en %s", log_path)
    return log_path


def shutdown_logging() -> None:
    """Cierra y quita solo los handlers instalados por esta aplicación."""
    global _configured, _log_path
    root = logging.getLogger()
    for handler in list(root.handlers):
        if _is_our_handler(handler):
            root.removeHandler(handler)
            handler.close()
    sys.excepthook = _original_excepthook
    _configured = False
    _log_path = None
