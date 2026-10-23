"""Tests del filtro de cartas de Meta y de la validación contra Scryfall."""
from __future__ import annotations

import types

import pytest

from mtga_companion.meta_fetcher import MetaFetcher, _is_non_card


@pytest.mark.parametrize(
    "name",
    [
        "The One Ring",
        "The Wandering Emperor",
        "Sword of Fire and Ice",
        "Sign in Blood",
        "Wishclaw Talisman",
        "Cartouche of Ambition",
        "Iconoclast",
        "Search for Tomorrow",
        "Aether Vial",
    ],
)
def test_real_cards_are_not_filtered(name):
    assert _is_non_card(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "",
        "MTGGoldfish",
        "MTG Goldfish",
        "MTGGoldfish Logo",
        "Sign in",
        "Log In",
        "Discord",
        "Facebook",
        "Instagram",
        "Twitter",
        "RSS",
        "Generic Card Back",
        "Shopping Cart Icon",
        "Carta #12345",
        "https://www.mtggoldfish.com",
        "???",
    ],
)
def test_ui_and_social_elements_are_filtered(name):
    assert _is_non_card(name) is True


def test_resolve_candidates_drops_unresolved_names():
    fetcher = MetaFetcher()
    fetcher.scryfall = types.SimpleNamespace(
        resolve_deck_by_name=lambda candidates: [
            {"name": "The One Ring", "found": True},
            {"name": "Fake UI Text", "found": False},
        ]
    )

    resolved = fetcher._resolve_candidates([{"name": "x", "quantity": 1}])

    assert [card["name"] for card in resolved] == ["The One Ring"]


def test_resolve_candidates_keeps_candidates_if_scryfall_is_unavailable():
    fetcher = MetaFetcher()
    fetcher.scryfall = types.SimpleNamespace(
        resolve_deck_by_name=lambda candidates: [
            {"name": "The One Ring", "found": False},
            {"name": "Mono Red Card", "found": False},
        ]
    )

    resolved = fetcher._resolve_candidates([{"name": "x", "quantity": 1}])

    assert len(resolved) == 2
