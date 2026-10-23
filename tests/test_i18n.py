"""Pruebas del cambio de idioma y de las traducciones visibles."""
from __future__ import annotations

from mtga_companion.i18n import (
    DEFAULT_LANGUAGE,
    get_language,
    normalize_language,
    runtime_message,
    set_language,
    tr,
)


def test_normalize_language_accepts_locale_variants_and_falls_back_to_spanish():
    assert normalize_language("en") == "en"
    assert normalize_language("en_US") == "en"
    assert normalize_language("EN-us") == "en"
    assert normalize_language("es_AR") == "es"
    assert normalize_language("français") == DEFAULT_LANGUAGE
    assert normalize_language(None) == DEFAULT_LANGUAGE


def test_language_switch_translates_static_and_dynamic_strings():
    set_language("es")
    assert get_language() == "es"
    assert tr("Partidas recientes") == "Partidas recientes"

    set_language("en")
    assert get_language() == "en"
    assert tr("Partidas recientes") == "Recent matches"
    assert tr("{total} partidas · {wins}V · {losses}D", total=12, wins=8, losses=4) == (
        "12 matches · 8W · 4L"
    )
    assert tr("0 partidas") == "0 matches"
    assert tr("Texto sin traducción") == "Texto sin traducción"


def test_runtime_messages_are_localized_for_display():
    set_language("en")
    assert runtime_message("Observando: /tmp/Player.log") == (
        "Watching: /tmp/Player.log"
    )
    assert runtime_message(
        "Archivo reemplazado, releyendo: /tmp/Player.log"
    ) == "File replaced, re-reading: /tmp/Player.log"
    assert runtime_message("Seguimiento detenido") == "Tracking stopped"


def test_period_card_does_not_leak_spanish_abbreviations_in_english(qapp):
    from mtga_companion.gui.widgets.ui import PeriodCard

    set_language("en")
    card = PeriodCard(tr("Últimos 7 días"))
    try:
        card.set_stats(total=7, wins=5, losses=2, winrate="71.4%")
        assert card.detail_lbl.text() == "7 matches · 5W · 2L"
    finally:
        card.deleteLater()
