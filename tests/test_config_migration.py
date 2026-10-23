"""Tests de migración de datos desde el directorio del paquete a XDG."""
from __future__ import annotations

from mtga_companion.config import ensure_app_data


def _make_legacy_tree(root):
    legacy = root / "legacy"
    legacy_data = legacy / "data"
    (legacy_data / "card_images").mkdir(parents=True)

    (legacy_data / "mtga_companion.db").write_bytes(b"legacy-db")
    (legacy / "card_cache.json").write_text('{"legacy": true}', encoding="utf-8")
    (legacy_data / "meta_cache.json").write_text('{"decks": []}', encoding="utf-8")
    (legacy / "settings.json").write_text(
        '{"player_name": "Rouxed"}', encoding="utf-8"
    )
    (legacy_data / "card_images" / "carta.jpg").write_bytes(b"imagen")
    return legacy


def test_ensure_app_data_copies_legacy_files(tmp_path):
    legacy = _make_legacy_tree(tmp_path)
    data_dir = tmp_path / "xdg-data" / "mtga-companion"
    config_dir = tmp_path / "xdg-config" / "mtga-companion"

    ensure_app_data(data_dir=data_dir, config_dir=config_dir, legacy_dir=legacy)

    assert (data_dir / "mtga_companion.db").read_bytes() == b"legacy-db"
    assert (data_dir / "card_cache.json").read_text(encoding="utf-8") == '{"legacy": true}'
    assert (data_dir / "meta_cache.json").read_text(encoding="utf-8") == '{"decks": []}'
    assert (config_dir / "settings.json").read_text(encoding="utf-8") == '{"player_name": "Rouxed"}'
    assert (data_dir / "card_images" / "carta.jpg").read_bytes() == b"imagen"

    # Los datos antiguos se copian, no se mueven ni se borran.
    assert (legacy / "data" / "mtga_companion.db").exists()


def test_ensure_app_data_does_not_overwrite_new_data(tmp_path):
    legacy = _make_legacy_tree(tmp_path)
    data_dir = tmp_path / "xdg-data" / "mtga-companion"
    config_dir = tmp_path / "xdg-config" / "mtga-companion"
    data_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (data_dir / "mtga_companion.db").write_bytes(b"new-db")
    (data_dir / "card_cache.json").write_text('{"new": true}', encoding="utf-8")
    (config_dir / "settings.json").write_text('{"player_name": "Nuevo"}', encoding="utf-8")
    (data_dir / "card_images").mkdir()
    (data_dir / "card_images" / "carta.jpg").write_bytes(b"nueva")

    ensure_app_data(data_dir=data_dir, config_dir=config_dir, legacy_dir=legacy)

    assert (data_dir / "mtga_companion.db").read_bytes() == b"new-db"
    assert (data_dir / "card_cache.json").read_text(encoding="utf-8") == '{"new": true}'
    assert (config_dir / "settings.json").read_text(encoding="utf-8") == '{"player_name": "Nuevo"}'
    assert (data_dir / "card_images" / "carta.jpg").read_bytes() == b"nueva"


def test_ensure_app_data_is_idempotent_and_merges_missing_images(tmp_path):
    legacy = _make_legacy_tree(tmp_path)
    data_dir = tmp_path / "xdg-data" / "mtga-companion"
    config_dir = tmp_path / "xdg-config" / "mtga-companion"

    ensure_app_data(data_dir=data_dir, config_dir=config_dir, legacy_dir=legacy)
    (data_dir / "card_images" / "otra.jpg").write_bytes(b"nueva")
    ensure_app_data(data_dir=data_dir, config_dir=config_dir, legacy_dir=legacy)

    assert (data_dir / "card_images" / "carta.jpg").exists()
    assert (data_dir / "card_images" / "otra.jpg").read_bytes() == b"nueva"
    assert (data_dir / "mtga_companion.db").read_bytes() == b"legacy-db"
