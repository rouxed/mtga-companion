"""Configuración común de pytest para el proyecto."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Qt debe usar el plugin "offscreen" en tests sin servidor gráfico.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Aislar los datos/configuración reales del usuario durante los tests.
_TEST_RUNTIME = Path(tempfile.mkdtemp(prefix="mtga-companion-tests-"))
os.environ["XDG_DATA_HOME"] = str(_TEST_RUNTIME / "data")
os.environ["XDG_CONFIG_HOME"] = str(_TEST_RUNTIME / "config")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_RUNTIME, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_language():
    """Aísla los tests del idioma global y conserva español por defecto."""
    from mtga_companion.i18n import DEFAULT_LANGUAGE, set_language

    set_language(DEFAULT_LANGUAGE)
    yield
    set_language(DEFAULT_LANGUAGE)


@pytest.fixture(scope="session")
def qapp():
    """Una única QApplication para todos los tests que usan Qt."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
