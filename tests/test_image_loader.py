"""Tests del loader de imágenes (sin acceso real a red)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager

from mtga_companion.gui.widgets.image_loader import (
    MAX_CONCURRENT_DOWNLOADS,
    ImageLoader,
)
from mtga_companion.scryfall import PLACEHOLDER_IMAGE_PATH


def _patch_network(monkeypatch):
    calls: list[str] = []

    def fake_get(self, request):
        calls.append(request.url().toString())

    monkeypatch.setattr(QNetworkAccessManager, "get", fake_get)
    return calls


def _pixmap() -> QPixmap:
    pixmap = QPixmap(4, 4)
    pixmap.fill(Qt.GlobalColor.red)
    return pixmap


def test_new_url_starts_a_download(qapp, monkeypatch):
    calls = _patch_network(monkeypatch)
    loader = ImageLoader()
    received = []

    url = "https://example.test/card.jpg"
    assert loader.load(url, received.append) is None

    assert calls == [url]
    assert url in loader._pending


def test_repeated_load_does_not_duplicate_the_request(qapp, monkeypatch):
    calls = _patch_network(monkeypatch)
    loader = ImageLoader()
    received = []

    url = "https://example.test/card.jpg"
    loader.load(url, received.append)
    loader.load(url, received.append)

    assert calls == [url]
    assert len(loader._pending[url]) == 2

    pixmap = _pixmap()
    loader._deliver(url, pixmap)

    assert len(received) == 2
    assert all(not item.isNull() for item in received)
    assert url not in loader._pending


def test_error_delivers_none_to_callbacks(qapp, monkeypatch):
    _patch_network(monkeypatch)
    loader = ImageLoader()
    received = []

    url = "https://example.test/error.jpg"
    loader.load(url, received.append)
    loader._deliver(url, None)

    assert received == [None]


def test_local_file_is_loaded_without_network(qapp, monkeypatch, tmp_path):
    calls = _patch_network(monkeypatch)
    loader = ImageLoader()
    path = tmp_path / "local.png"
    assert _pixmap().save(str(path))

    received = []
    pixmap = loader.load(str(path), received.append)

    assert pixmap is not None
    assert not pixmap.isNull()
    assert calls == []
    assert len(received) == 1


def test_placeholder_file_is_loaded_directly(qapp, monkeypatch):
    calls = _patch_network(monkeypatch)
    loader = ImageLoader()

    received = []
    pixmap = loader.load(PLACEHOLDER_IMAGE_PATH, received.append)

    assert pixmap is not None
    assert not pixmap.isNull()
    assert calls == []


def test_concurrency_is_limited(qapp, monkeypatch):
    calls = _patch_network(monkeypatch)
    loader = ImageLoader()

    total = MAX_CONCURRENT_DOWNLOADS + 3
    for index in range(total):
        loader.load(f"https://example.test/{index}.jpg", lambda _pixmap: None)

    assert len(calls) == MAX_CONCURRENT_DOWNLOADS
    assert len(loader._queue) == 3

    loader._deliver(calls[0], None)

    assert len(calls) == MAX_CONCURRENT_DOWNLOADS + 1
    assert len(loader._queue) == 2
