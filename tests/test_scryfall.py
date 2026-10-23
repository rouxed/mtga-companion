"""Tests del cliente de Scryfall y de la ruta del placeholder."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from mtga_companion import scryfall
from mtga_companion.scryfall import (
    PLACEHOLDER_IMAGE_PATH,
    ScryfallCancelled,
    ScryfallClient,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_placeholder_image_path_exists():
    assert Path(PLACEHOLDER_IMAGE_PATH).is_file()


def test_extract_image_from_card_faces():
    card = {
        "card_faces": [
            {"image_uris": {"normal": "https://img/front.jpg"}},
            {"image_uris": {"normal": "https://img/back.jpg"}},
        ]
    }

    assert ScryfallClient._extract_image(card) == "https://img/front.jpg"


def test_resolve_by_name_marks_found_and_uses_image(monkeypatch, tmp_path):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(args)
        return _FakeResponse(
            200,
            {
                "name": "The One Ring",
                "image_uris": {"normal": "https://img/ring.jpg"},
                "type_line": "Legendary Artifact",
            },
        )

    monkeypatch.setattr(scryfall.requests, "get", fake_get)
    monkeypatch.setattr(scryfall, "_RATE_SLEEP", 0)

    client = ScryfallClient(cache_path=tmp_path / "cards.json")
    info = client.resolve_by_name("The One Ring")

    assert info["found"] is True
    assert info["name"] == "The One Ring"
    assert info["image"] == "https://img/ring.jpg"
    assert info["type_line"] == "Legendary Artifact"
    assert len(calls) == 1

    # La segunda consulta sale de la caché, sin llamar a la red.
    again = client.resolve_by_name("The One Ring")
    assert again["found"] is True
    assert len(calls) == 1


def test_resolve_by_name_uses_placeholder_when_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(
        scryfall.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(404),
    )
    monkeypatch.setattr(scryfall, "_RATE_SLEEP", 0)

    client = ScryfallClient(cache_path=tmp_path / "cards.json")
    info = client.resolve_by_name("Definitely Not A Card")

    assert info["found"] is False
    assert info["image"] == PLACEHOLDER_IMAGE_PATH
    assert info["name"] == "Definitely Not A Card"


def test_cache_is_written_as_valid_json(monkeypatch, tmp_path):
    monkeypatch.setattr(
        scryfall.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            200,
            {
                "name": "Island",
                "image_uris": {"normal": "https://img/island.jpg"},
                "type_line": "Basic Land — Island",
            },
        ),
    )
    monkeypatch.setattr(scryfall, "_RATE_SLEEP", 0)

    cache_path = tmp_path / "cards.json"
    client = ScryfallClient(cache_path=cache_path)
    client.resolve_by_name("Island")

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["Island"]["found"] is True
    assert data["Island"]["image"] == "https://img/island.jpg"


def test_cancelled_client_stops_before_network(tmp_path):
    cancel_event = threading.Event()
    cancel_event.set()
    client = ScryfallClient(
        cache_path=tmp_path / "cards.json", cancel_event=cancel_event
    )

    with pytest.raises(ScryfallCancelled):
        client.resolve("123")


def test_negative_cache_is_retried_after_a_transient_failure(monkeypatch, tmp_path):
    responses = [
        _FakeResponse(503),
        _FakeResponse(
            200,
            {
                "name": "The One Ring",
                "image_uris": {"normal": "https://img/ring.jpg"},
                "type_line": "Legendary Artifact",
            },
        ),
    ]
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(args)
        return responses.pop(0)

    monkeypatch.setattr(scryfall.requests, "get", fake_get)
    monkeypatch.setattr(scryfall, "_RATE_SLEEP", 0)

    client = ScryfallClient(cache_path=tmp_path / "cards.json")

    first = client.resolve_by_name("The One Ring")
    second = client.resolve_by_name("The One Ring")

    assert first["found"] is False
    assert second["found"] is True
    assert len(calls) == 2
