"""Tests de rutas XDG y detección de bibliotecas de Steam."""
from __future__ import annotations

import os
from pathlib import Path

from mtga_companion import config


def test_data_and_config_paths_use_xdg_directories():
    data_home = Path(os.environ["XDG_DATA_HOME"])
    config_home = Path(os.environ["XDG_CONFIG_HOME"])

    assert config.DATA_DIR == data_home / config.APP_DIR_NAME
    assert config.CONFIG_DIR == config_home / config.APP_DIR_NAME
    assert config.DB_PATH.parent == config.DATA_DIR
    assert config.CARD_CACHE_PATH.parent == config.DATA_DIR
    assert config.META_CACHE_PATH.parent == config.DATA_DIR
    assert config.CARD_IMAGES_DIR.parent == config.DATA_DIR
    assert config.LOG_DIR.parent == config.DATA_DIR
    assert config.SETTINGS_PATH.parent == config.CONFIG_DIR


def test_parse_library_folders_reads_steam_vdf(tmp_path):
    vdf = tmp_path / "libraryfolders.vdf"
    vdf.write_text(
        '"libraryfolders"\n'
        "{\n"
        '\t"0"\n'
        "\t{\n"
        '\t\t"path"\t\t"/home/alguien/.local/share/Steam"\n'
        "\t}\n"
        '\t"1"\n'
        "\t{\n"
        '\t\t"path"\t\t"/run/media/alguien/Disco Secundario/SteamLibrary"\n'
        "\t}\n"
        "}\n",
        encoding="utf-8",
    )

    libraries = config._parse_library_folders(vdf)

    assert libraries == [
        Path("/home/alguien/.local/share/Steam"),
        Path("/run/media/alguien/Disco Secundario/SteamLibrary"),
    ]


def test_detect_log_path_returns_an_existing_file(tmp_path, monkeypatch):
    log = tmp_path / "Player.log"
    log.write_text("", encoding="utf-8")
    missing = tmp_path / "missing.log"

    monkeypatch.setattr(config, "candidate_log_paths", lambda: [missing, log])

    assert config.detect_log_path() == log


def _make_player_log(prefix: Path, user: str = "player") -> Path:
    log = (
        prefix
        / "drive_c"
        / "users"
        / user
        / "AppData"
        / "LocalLow"
        / "Wizards Of The Coast"
        / "MTGA"
        / "Player.log"
    )
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")
    return log


def test_discovers_steam_prefix_with_any_wine_user(tmp_path):
    home = tmp_path / "home"
    prefix = (
        home
        / ".local"
        / "share"
        / "Steam"
        / "steamapps"
        / "compatdata"
        / config.STEAM_APP_ID
        / "pfx"
    )
    log = _make_player_log(prefix, user="steamuser")

    candidates = config.discover_log_candidates(
        home=home, mount_roots=(), env={}
    )

    assert [candidate.path for candidate in candidates] == [log]
    assert candidates[0].source == "Steam"
    assert candidates[0].prefix == prefix
    assert candidates[0].modified_label


def test_discovers_lutris_prefix_from_game_config(tmp_path):
    home = tmp_path / "home"
    prefix = home / "Juegos" / "MTGA-Lutris"
    log = _make_player_log(prefix, user="pepe")
    config_dir = home / ".config" / "lutris" / "games"
    config_dir.mkdir(parents=True)
    (config_dir / "mtga.yml").write_text(
        f"game:\n  prefix: {prefix}\n", encoding="utf-8"
    )

    candidates = config.discover_log_candidates(
        home=home, mount_roots=(), env={}
    )

    assert [candidate.path for candidate in candidates] == [log]
    assert candidates[0].source == "Lutris"


def test_discovers_heroic_prefix_from_json_config(tmp_path):
    home = tmp_path / "home"
    prefix = home / "Games" / "Heroic" / "Prefixes" / "MTGA"
    log = _make_player_log(prefix, user="heroic")
    config_dir = home / ".config" / "heroic" / "GamesConfig"
    config_dir.mkdir(parents=True)
    (config_dir / "mtga.json").write_text(
        '{"winePrefix": "' + str(prefix) + '"}', encoding="utf-8"
    )

    candidates = config.discover_log_candidates(
        home=home, mount_roots=(), env={}
    )

    assert [candidate.path for candidate in candidates] == [log]
    assert candidates[0].source == "Heroic / Epic"


def test_discovers_bottles_prefix(tmp_path):
    home = tmp_path / "home"
    prefix = home / ".local" / "share" / "bottles" / "bottles" / "MTGA"
    log = _make_player_log(prefix)

    candidates = config.discover_log_candidates(
        home=home, mount_roots=(), env={}
    )

    assert [candidate.path for candidate in candidates] == [log]
    assert candidates[0].source == "Bottles"


def test_discovers_manual_wine_prefix_and_env_path(tmp_path):
    home = tmp_path / "home"
    prefix = home / "Juegos" / "wine-manual"
    log = _make_player_log(prefix, user="root")

    candidates = config.discover_log_candidates(
        home=home, mount_roots=(), env={}
    )
    assert [candidate.path for candidate in candidates] == [log]
    assert candidates[0].source == "Prefijo Wine"

    explicit = tmp_path / "otro" / "Player.log"
    explicit.parent.mkdir(parents=True)
    explicit.write_text("", encoding="utf-8")
    candidates = config.discover_log_candidates(
        home=home,
        mount_roots=(),
        env={"MTGA_LOG_PATH": str(explicit)},
    )
    assert candidates[0].path == explicit
    assert candidates[0].source == "Variable MTGA_LOG_PATH"


def test_discovers_windows_partition_and_sorts_by_mtime(tmp_path):
    home = tmp_path / "home"
    prefix_a = home / "Juegos" / "viejo"
    prefix_b = home / "Juegos" / "nuevo"
    log_a = _make_player_log(prefix_a)
    log_b = _make_player_log(prefix_b)
    os.utime(log_a, (1_000, 1_000))
    os.utime(log_b, (2_000, 2_000))

    candidates = config.discover_log_candidates(
        home=home, mount_roots=(), env={}
    )
    assert [candidate.path for candidate in candidates] == [log_b, log_a]

    mount = tmp_path / "windows"
    log_windows = (
        mount
        / "Windows"
        / "Users"
        / "pepe"
        / "AppData"
        / "LocalLow"
        / "Wizards Of The Coast"
        / "MTGA"
        / "Player.log"
    )
    log_windows.parent.mkdir(parents=True, exist_ok=True)
    log_windows.write_text("", encoding="utf-8")
    candidates = config.discover_log_candidates(
        home=tmp_path / "sin-home",
        mount_roots=(mount,),
        env={},
    )
    assert [candidate.path for candidate in candidates] == [log_windows]
    assert candidates[0].source == "Partición Windows"


def test_discovers_lutris_prefix_from_custom_xdg_config(tmp_path):
    home = tmp_path / "home"
    xdg_config = tmp_path / "xdg-config"
    prefix = tmp_path / "fuera-de-rutas-comunes" / "MTGA"
    log = _make_player_log(prefix)
    config_dir = xdg_config / "lutris" / "games"
    config_dir.mkdir(parents=True)
    (config_dir / "mtga.yml").write_text(
        f"game:\n  prefix: {prefix}\n", encoding="utf-8"
    )

    candidates = config.discover_log_candidates(
        home=home,
        mount_roots=(),
        env={
            "XDG_CONFIG_HOME": str(xdg_config),
            "XDG_DATA_HOME": str(tmp_path / "xdg-data"),
        },
    )

    assert [candidate.path for candidate in candidates] == [log]
    assert candidates[0].source == "Lutris"
