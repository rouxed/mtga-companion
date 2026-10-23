"""Tests de la configuración de logging."""
from __future__ import annotations

import logging

from mtga_companion.logging_config import setup_logging, shutdown_logging


def test_setup_logging_writes_to_a_rotating_file(tmp_path):
    try:
        log_path = setup_logging(tmp_path, force=True)
        logging.getLogger("test.mtga").info("mensaje de prueba")

        for handler in logging.getLogger().handlers:
            handler.flush()

        assert log_path.exists()
        assert "mensaje de prueba" in log_path.read_text(encoding="utf-8")
        assert "Log iniciado" in log_path.read_text(encoding="utf-8")
    finally:
        shutdown_logging()
