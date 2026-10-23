"""Tests del listado meta, decklists y caché por formato."""
from __future__ import annotations

import json
import time
import types

from bs4 import BeautifulSoup

from mtga_companion.meta_fetcher import (
    META_CACHE_TTL,
    MetaFetcher,
    _parse_meta_share,
    parse_decklist,
)


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _tile(
    name: str,
    share: str = "11.5%",
    count: str = "(148)",
    paper: str = "$ 241",
    mtgo: str = "42 tix",
    href: str = "/archetype/standard-izzet-spellementals-woe#online",
) -> str:
    return f"""
    <div class="archetype-tile">
      <div class="archetype-tile-title">
        <span class="deck-price-online"><a href="{href}">{name}</a></span>
      </div>
      <ul><li>Sunderflock</li><li>Eddymurk Crab</li></ul>
      <div class="archetype-tile-statistics">
        <div class="archetype-tile-statistics-left">
          <div class="metagame-percentage">
            <div class="archetype-tile-statistic-name">META%</div>
            <div class="archetype-tile-statistic-value">{share}
              <span class="archetype-tile-statistic-value-extra-data">{count}</span>
            </div>
          </div>
        </div>
        <div class="archetype-tile-statistics-right">
          <div class="deck-price-paper">
            <div class="archetype-tile-statistic-value">{paper}</div>
          </div>
          <div class="deck-price-online">
            <div class="archetype-tile-statistic-value">{mtgo}</div>
          </div>
        </div>
      </div>
    </div>
    """


def test_parse_meta_share_normalizes_goldfish_text():
    assert _parse_meta_share("META%11.5%(148)") == ("11.5%", 148)
    assert _parse_meta_share("9,7%") == ("9.7%", None)
    assert _parse_meta_share("Top") == (None, None)


def test_fetch_mtggoldfish_meta_normalizes_share_and_prices(monkeypatch, tmp_path):
    html = "<html><body>" + _tile("Izzet Spellementals") + "</body></html>"
    monkeypatch.setattr(
        "mtga_companion.meta_fetcher.requests.get",
        lambda *args, **kwargs: _FakeResponse(html),
    )

    fetcher = MetaFetcher(cache_path=tmp_path / "meta.json")
    decks = fetcher.fetch_mtggoldfish_meta("Standard")

    assert len(decks) == 1
    deck = decks[0]
    assert deck["name"] == "Izzet Spellementals"
    assert deck["meta_share"] == "11.5%"
    assert deck["meta_share_count"] == 148
    assert deck["price_paper"] == "$241"
    assert deck["price_mtgo"] == "42 tix"
    assert deck["url"] == (
        "https://www.mtggoldfish.com/archetype/"
        "standard-izzet-spellementals-woe"
    )
    assert deck["top_cards"] == ["Sunderflock", "Eddymurk Crab"]


def test_parse_decklist_supports_main_sideboard_and_x_syntax():
    cards = parse_decklist(
        """Deck
4 Lightning Bolt
2x Counterspell
4 Fire // Ice

Sideboard
1 Annul
2 Spell Pierce
"""
    )

    assert cards == [
        {"name": "Lightning Bolt", "quantity": 4, "zone": "main"},
        {"name": "Counterspell", "quantity": 2, "zone": "main"},
        {"name": "Fire // Ice", "quantity": 4, "zone": "main"},
        {"name": "Annul", "quantity": 1, "zone": "sideboard"},
        {"name": "Spell Pierce", "quantity": 2, "zone": "sideboard"},
    ]


def test_fetch_deck_cards_prefers_hidden_sample_decklist(monkeypatch, tmp_path):
    html = """
    <html><body>
      <input id="deck_input_deck" name="deck_input[deck]"
             value="4 Lightning Bolt
2 Counterspell
sideboard
3 Spell Pierce" />
      <div class="deck-archetype-breakdown">
        <div class="spoiler-card-container">
          <h3>Creatures</h3>
          <div class="spoiler-card">
            <img alt="Should Not Be Used" />
            <p>4.0 in 100% of decks</p>
          </div>
        </div>
      </div>
    </body></html>
    """
    monkeypatch.setattr(
        "mtga_companion.meta_fetcher.requests.get",
        lambda *args, **kwargs: _FakeResponse(html),
    )

    fetcher = MetaFetcher(cache_path=tmp_path / "meta.json")
    fetcher.scryfall = types.SimpleNamespace(
        resolve_deck_by_name=lambda candidates: [
            {**c, "found": True, "image": "", "type_line": ""}
            for c in candidates
        ]
    )

    cards = fetcher.fetch_deck_cards("https://example.test/archetype")

    assert [(c["name"], c["quantity"], c["zone"]) for c in cards] == [
        ("Lightning Bolt", 4, "main"),
        ("Counterspell", 2, "main"),
        ("Spell Pierce", 3, "sideboard"),
    ]


def test_cache_is_kept_per_format_and_expires(monkeypatch, tmp_path):
    fetcher = MetaFetcher(cache_path=tmp_path / "meta.json")
    monkeypatch.setattr(
        fetcher,
        "fetch_mtggoldfish_meta",
        lambda fmt: [
            {
                "name": f"{fmt} Deck",
                "format": fmt,
                "meta_share": "10%",
                "cards": [],
                "source": "MTGGoldfish",
            }
        ],
    )

    fetcher.fetch_meta("Standard", force=True)
    fetcher.fetch_meta("Historic", force=True)

    standard = fetcher.load_cached_meta("Standard")
    historic = fetcher.load_cached_meta("Historic")
    assert standard["decks"][0]["name"] == "Standard Deck"
    assert historic["decks"][0]["name"] == "Historic Deck"
    assert standard["stale"] is False

    raw = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    raw["formats"]["Standard"]["updated_at"] = time.time() - META_CACHE_TTL - 10
    (tmp_path / "meta.json").write_text(json.dumps(raw), encoding="utf-8")

    assert fetcher.load_cached_meta("Standard")["stale"] is True
    assert fetcher.load_cached_meta("Historic")["stale"] is False


def test_legacy_cache_shape_is_migrated_and_normalized(tmp_path):
    cache_path = tmp_path / "meta.json"
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": time.time(),
                "format": "Standard",
                "decks": [
                    {
                        "name": "Viejo",
                        "meta_share": "META%11.6%(153)",
                        "price": None,
                        "cards": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cache = MetaFetcher(cache_path=cache_path).load_cached_meta("Standard")

    assert cache["decks"][0]["meta_share"] == "11.6%"
    assert cache["decks"][0]["meta_share_count"] == 153
    assert cache["stale"] is False


def test_fresh_cache_avoids_network(monkeypatch, tmp_path):
    fetcher = MetaFetcher(cache_path=tmp_path / "meta.json")
    fetcher._save_cached_meta(
        "Standard",
        [{"name": "Cache Deck", "format": "Standard", "cards": [], "source": "MTGGoldfish"}],
    )
    monkeypatch.setattr(
        fetcher,
        "fetch_mtggoldfish_meta",
        lambda fmt: (_ for _ in ()).throw(AssertionError("no debe usar red")),
    )

    decks = fetcher.fetch_meta("Standard", force=False)

    assert decks[0]["name"] == "Cache Deck"


def test_network_failure_uses_stale_cache(monkeypatch, tmp_path):
    fetcher = MetaFetcher(cache_path=tmp_path / "meta.json")
    fetcher._save_cached_meta(
        "Standard",
        [{"name": "Cache Deck", "format": "Standard", "cards": [], "source": "MTGGoldfish"}],
    )
    raw = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    raw["formats"]["Standard"]["updated_at"] = time.time() - META_CACHE_TTL - 10
    (tmp_path / "meta.json").write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(
        fetcher,
        "fetch_mtggoldfish_meta",
        lambda fmt: (_ for _ in ()).throw(RuntimeError("sin red")),
    )

    decks = fetcher.fetch_meta("Standard", force=True)

    assert decks[0]["name"] == "Cache Deck"


def test_network_failure_without_cache_uses_local_fallback(monkeypatch, tmp_path):
    fetcher = MetaFetcher(cache_path=tmp_path / "meta.json")
    monkeypatch.setattr(
        fetcher,
        "fetch_mtggoldfish_meta",
        lambda fmt: (_ for _ in ()).throw(RuntimeError("sin red")),
    )

    decks = fetcher.fetch_meta("Standard", force=True)

    assert decks
    assert all(deck["source"] == "Fallback local" for deck in decks)


def test_requested_format_without_cache_does_not_return_another_format(tmp_path):
    fetcher = MetaFetcher(cache_path=tmp_path / "meta.json")
    fetcher._save_cached_meta(
        "Standard",
        [{"name": "Standard Deck", "format": "Standard", "cards": [], "source": "MTGGoldfish"}],
    )

    historic = fetcher.load_cached_meta("Historic")

    assert historic["format"] == "Historic"
    assert historic["decks"] == []
    assert historic["stale"] is True


def test_card_breakdown_fallback_ignores_ui_images():
    html = """
    <html><body>
      <img alt="Discord" />
      <div class="deck-archetype-breakdown">
        <div class="spoiler-card-container">
          <h3>Creatures</h3>
          <div class="spoiler-card">
            <img alt="Sunderflock [ECL]" />
            <p>4.0 in 100% of decks</p>
          </div>
        </div>
        <div class="spoiler-card-container">
          <h3>Sideboard</h3>
          <div class="spoiler-card">
            <img alt="Annul [THS]" />
            <p>1.4 in 40% of decks</p>
          </div>
        </div>
      </div>
    </body></html>
    """

    cards = MetaFetcher._parse_card_breakdown(BeautifulSoup(html, "html.parser"))

    assert cards == [
        {"name": "Sunderflock", "quantity": 4, "zone": "main"},
        {"name": "Annul", "quantity": 1, "zone": "sideboard"},
    ]
