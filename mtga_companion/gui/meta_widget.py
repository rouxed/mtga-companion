"""Pestaña Meta: mazos meta de internet con sus cartas (estilo Untapped.gg)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mtga_companion.config import DB_PATH
from mtga_companion.i18n import tr
from mtga_companion.meta_fetcher import FALLBACK_DECKS, MetaFetcher
from mtga_companion.scryfall import ScryfallClient

from .widgets.card_tile import DeckGroup
from .widgets.image_loader import clear_all_pending
from .widgets.ui import DeckItemDelegate

logger = logging.getLogger(__name__)


def _format_cache_time(value) -> str:
    """Formatea la fecha de actualización de la caché en hora local."""
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(float(value)).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


class _FetchSignals(QObject):
    """Señales para entregar resultados del hilo secundario al hilo GUI."""
    decks_loaded = pyqtSignal(object, int)  # lista de mazos, request_id
    fetch_error = pyqtSignal(str)
    cards_loaded = pyqtSignal(object, int)  # lista de cartas, request_id
    cards_error = pyqtSignal(int, str)


class MetaWidget(QWidget):
    def __init__(self, db_path=DB_PATH, parent=None):
        super().__init__(parent)
        self.db_path = Path(db_path)
        self.fetcher = MetaFetcher()
        self._destroyed = False
        self._request_id = 0
        self._current_cards: list[dict] = []

        # Señales para entrega segura al hilo GUI
        self._signals = _FetchSignals()
        self._signals.decks_loaded.connect(self._on_decks_loaded)
        self._signals.fetch_error.connect(self._on_fetch_error)
        self._signals.cards_loaded.connect(self._on_cards_loaded)
        self._signals.cards_error.connect(self._on_cards_error)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # --- Barra de controles ---
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        format_label = QLabel(tr("Formato"))
        format_label.setObjectName("muted")
        ctrl.addWidget(format_label)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Standard", "Historic", "Explorer", "Alchemy"])
        self.format_combo.setFixedWidth(150)
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        ctrl.addWidget(self.format_combo)

        btn_refresh = QPushButton(tr("Buscar en internet"))
        btn_refresh.setObjectName("primaryButton")
        btn_refresh.clicked.connect(lambda: self._refresh(force=True))
        ctrl.addWidget(btn_refresh)

        ctrl.addStretch()

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("cacheStatus")
        self.status_lbl.setToolTip(tr("Estado de la caché de mazos meta"))
        ctrl.addWidget(self.status_lbl)
        root.addLayout(ctrl)

        # --- Contenido principal ---
        content = QHBoxLayout()
        content.setSpacing(14)

        # Panel izquierdo: lista de mazos meta
        left = QFrame()
        left.setObjectName("surface")
        left.setFixedWidth(340)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 12)
        left_layout.setSpacing(4)

        list_title = QLabel(tr("MAZOS META POPULARES"))
        list_title.setObjectName("sectionTitle")
        left_layout.addWidget(list_title)

        list_hint = QLabel(tr("Compartidos en MTGGoldfish"))
        list_hint.setObjectName("sectionHint")
        left_layout.addWidget(list_hint)

        self.list = QListWidget()
        self.list.setObjectName("metaList")
        self.list.setSpacing(2)
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(DeckItemDelegate(self.list))
        self.list.currentItemChanged.connect(self._on_deck_selected)
        left_layout.addWidget(self.list, stretch=1)
        content.addWidget(left)

        # Panel derecho: detalle del mazo
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.detail_title = QLabel(tr("Seleccioná un mazo meta"))
        self.detail_title.setObjectName("detailTitle")
        right_layout.addWidget(self.detail_title)

        self.detail_info = QLabel("")
        self.detail_info.setObjectName("muted")
        self.detail_info.setWordWrap(True)
        right_layout.addWidget(self.detail_info)

        self.loading_lbl = QLabel(tr("Cargando cartas…"))
        self.loading_lbl.setObjectName("sectionHint")
        self.loading_lbl.setVisible(False)
        right_layout.addWidget(self.loading_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setStyleSheet("background: #0B0F14;")
        self.detail_content = QWidget()
        self.detail_content.setStyleSheet("background: transparent;")
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(0, 4, 0, 0)
        self.detail_layout.setSpacing(12)
        self.detail_layout.addStretch()
        scroll.setWidget(self.detail_content)
        right_layout.addWidget(scroll, stretch=1)

        # Panel de exportación
        export_frame = QFrame()
        export_frame.setObjectName("surface")
        export_layout = QVBoxLayout(export_frame)
        export_layout.setContentsMargins(14, 11, 14, 12)
        export_layout.setSpacing(6)

        export_header = QHBoxLayout()
        export_title = QLabel(tr("LISTA PARA MTG ARENA"))
        export_title.setObjectName("sectionTitle")
        export_header.addWidget(export_title)
        export_header.addStretch()
        export_hint = QLabel(tr("Copiá y pegala en el juego"))
        export_hint.setObjectName("sectionHint")
        export_header.addWidget(export_hint)
        export_layout.addLayout(export_header)

        self.export_text = QTextEdit()
        self.export_text.setObjectName("exportText")
        self.export_text.setReadOnly(True)
        self.export_text.setFixedHeight(118)
        export_layout.addWidget(self.export_text)

        btn_copy = QPushButton(tr("Copiar lista"))
        btn_copy.setObjectName("primaryButton")
        btn_copy.clicked.connect(self._copy_export_list)
        export_layout.addWidget(btn_copy)

        right_layout.addWidget(export_frame)

        content.addWidget(right, stretch=1)
        root.addLayout(content, stretch=1)

        # Cargar caché si existe
        self._load_cached()

    # ------------------------------------------------------------------ #
    # Carga de mazos
    # ------------------------------------------------------------------ #
    def _cache_status(self, cache: dict) -> str:
        decks = cache.get("decks", [])
        updated = _format_cache_time(cache.get("updated_at"))
        state = "vencida" if cache.get("stale") else "actualizada"
        parts = [tr("Caché: {count} mazos", count=len(decks)), tr(state)]
        if updated:
            parts.append(updated)
        return " · ".join(parts)

    def _reset_detail(self):
        if self._destroyed:
            return
        self._request_id += 1
        clear_all_pending()
        self._current_cards = []
        self.detail_title.setText(tr("Seleccioná un mazo meta"))
        self.detail_info.setText("")
        self.loading_lbl.setText(tr("Cargando cartas…"))
        self.loading_lbl.setVisible(False)
        self.export_text.clear()
        self._clear_detail()

    def _load_cached(self):
        if self._destroyed:
            return
        cache = self.fetcher.load_cached_meta()
        decks = cache.get("decks", [])
        fmt = cache.get("format")
        if fmt:
            idx = self.format_combo.findText(fmt)
            if idx >= 0:
                self.format_combo.blockSignals(True)
                self.format_combo.setCurrentIndex(idx)
                self.format_combo.blockSignals(False)
        self._populate_list(decks)
        if decks:
            self.status_lbl.setText(self._cache_status(cache))
        else:
            self.status_lbl.setText(
                tr("Sin caché. Presioná «Buscar en internet».")
            )

    def refresh(self):
        """Refresca la pestaña si la caché está vencida o no existe."""
        if self._destroyed:
            return
        fmt = self.format_combo.currentText()
        cache = self.fetcher.load_cached_meta(fmt)
        if not cache.get("decks") or cache.get("stale"):
            self._refresh(force=True)

    def _on_format_changed(self, fmt: str):
        if self._destroyed:
            return
        self._reset_detail()
        cache = self.fetcher.load_cached_meta(fmt)
        decks = cache.get("decks", [])
        self._populate_list(decks)
        if decks:
            self.status_lbl.setText(self._cache_status(cache))
            if cache.get("stale"):
                self._refresh(force=True)
        else:
            self.status_lbl.setText(
                tr("Sin caché de {format}. Buscando...", format=fmt)
            )
            self._refresh(force=True)

    def _refresh(self, force: bool = True):
        if self._destroyed:
            return
        fmt = self.format_combo.currentText()
        self._reset_detail()
        self._request_id += 1
        current_request_id = self._request_id

        self.list.clear()
        self.loading_lbl.setVisible(True)
        self.status_lbl.setText(
            tr("Buscando mazos meta ({format})...", format=fmt)
        )

        def _task():
            try:
                decks = self.fetcher.fetch_meta(fmt, force=force)
            except Exception as exc:  # noqa: BLE001
                if not self._destroyed:
                    self._signals.fetch_error.emit(str(exc))
                return
            if not self._destroyed and current_request_id == self._request_id:
                self._signals.decks_loaded.emit(decks, current_request_id)

        t = threading.Thread(target=_task, daemon=True)
        t.start()

    def _on_decks_loaded(self, decks: list[dict], request_id: int):
        if self._destroyed or request_id != self._request_id:
            return
        self.loading_lbl.setVisible(False)
        self._populate_list(decks)

        if not decks:
            self.status_lbl.setText(
                tr(
                    "Sin mazos disponibles para {format}",
                    format=self.format_combo.currentText(),
                )
            )
            return

        if all(d.get("source") == "Fallback local" for d in decks):
            self.status_lbl.setText(
                tr(
                    "Sin conexión: {count} mazos de respaldo",
                    count=len(decks),
                )
            )
        else:
            fmt = self.format_combo.currentText()
            cache = self.fetcher.load_cached_meta(fmt)
            if cache.get("decks"):
                self.status_lbl.setText(self._cache_status(cache))
            else:
                self.status_lbl.setText(
                    tr("{count} mazos encontrados", count=len(decks))
                )

        if decks:
            self.list.setCurrentRow(0)

    def _on_fetch_error(self, msg: str):
        if self._destroyed:
            return
        self.loading_lbl.setVisible(False)
        self.status_lbl.setText(tr("Error al buscar mazos meta"))
        cache = self.fetcher.load_cached_meta(self.format_combo.currentText())
        if cache.get("decks"):
            self._populate_list(cache["decks"])
            self.status_lbl.setText(self._cache_status(cache))

    def _populate_list(self, decks: list[dict]):
        if self._destroyed:
            return
        self.list.clear()
        for d in decks:
            name = d.get("name", tr("Sin nombre"))
            share = d.get("meta_share") or "?"
            count = d.get("meta_share_count")
            share_text = f"{share} · {count}" if count else str(share)
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(0, 54))
            item.setData(Qt.ItemDataRole.UserRole, d)
            item.setData(Qt.ItemDataRole.UserRole + 1, share_text)
            item.setToolTip("\n".join([
                name,
                tr("Meta share: {share}", share=share_text),
                *(
                    [tr("Tabletop: {price}", price=d["price_paper"])]
                    if d.get("price_paper")
                    else []
                ),
                *(
                    [tr("MTGO: {price}", price=d["price_mtgo"])]
                    if d.get("price_mtgo")
                    else []
                ),
                *(
                    [tr("Fuente: {source}", source=tr(d["source"]))]
                    if d.get("source")
                    else []
                ),
            ]))
            self.list.addItem(item)

    # ------------------------------------------------------------------ #
    # Detalle de un mazo
    # ------------------------------------------------------------------ #
    def _on_deck_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if self._destroyed or not current:
            return
        # Incrementar request_id para invalidar operaciones anteriores
        self._request_id += 1
        current_request_id = self._request_id

        # Limpiar descargas de imágenes pendientes del mazo anterior
        clear_all_pending()

        deck = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(deck, dict):
            return
        self._show_deck(deck, current_request_id)

    def _show_deck(self, deck: dict, request_id: int):
        if self._destroyed or not isinstance(deck, dict):
            return
        if request_id != self._request_id:
            return

        name = deck.get("name", tr("Mazo meta"))
        self.detail_title.setText(name)

        share = deck.get("meta_share") or "?"
        count = deck.get("meta_share_count")
        share_text = (
            tr("{share} ({count} mazos)", share=share, count=count)
            if count
            else str(share)
        )
        info_parts = [tr("Meta share: {share}", share=share_text)]
        if deck.get("price_paper"):
            info_parts.append(
                tr("Tabletop: {price}", price=deck["price_paper"])
            )
        if deck.get("price_mtgo"):
            info_parts.append(tr("MTGO: {price}", price=deck["price_mtgo"]))
        if not deck.get("price_paper") and not deck.get("price_mtgo"):
            price = deck.get("price")
            if price:
                info_parts.append(tr("Precio aprox.: {price}", price=price))
        source = deck.get("source") or "?"
        info_parts.append(tr("Fuente: {source}", source=tr(source)))
        self.detail_info.setText("  ·  ".join(info_parts))

        self._clear_detail()
        self.loading_lbl.setText(tr("Cargando cartas…"))
        self.loading_lbl.setVisible(True)
        self.export_text.clear()

        cards = deck.get("cards", [])
        if not cards:
            self._load_deck_cards(deck, request_id)
            return

        needs_resolve = any(not c.get("image") for c in cards)
        if needs_resolve:
            self._resolve_cards(cards, request_id)
        else:
            self.loading_lbl.setVisible(False)
            self._render_cards(cards)

    def _load_deck_cards(self, deck: dict, request_id: int):
        if self._destroyed:
            return

        def _task():
            url = deck.get("url")
            cards = []
            if url:
                try:
                    cards = self.fetcher.fetch_deck_cards(url)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Error trayendo cartas de %s: %s", deck.get("name"), exc
                    )
                    cards = []
            if not cards:
                fallback = [
                    d for d in FALLBACK_DECKS.get(deck.get("format", "Standard"), [])
                    if d["name"] == deck.get("name")
                ]
                if fallback:
                    name_qty = fallback[0].get("cards", [])
                    cards = self.fetcher.scryfall.resolve_deck_by_name(name_qty)
            if self._destroyed or request_id != self._request_id:
                return
            if not cards:
                self._signals.cards_error.emit(
                    request_id, tr("No se pudieron cargar las cartas del mazo.")
                )
                return
            self._signals.cards_loaded.emit(cards, request_id)

        t = threading.Thread(target=_task, daemon=True)
        t.start()

    def _resolve_cards(self, name_qty_list: list[dict], request_id: int):
        if self._destroyed:
            return

        def _task():
            scryfall = ScryfallClient()
            cards = scryfall.resolve_deck_by_name(name_qty_list)
            if self._destroyed or request_id != self._request_id:
                return
            self._signals.cards_loaded.emit(cards, request_id)

        t = threading.Thread(target=_task, daemon=True)
        t.start()

    def _on_cards_loaded(self, cards: list[dict], request_id: int):
        if self._destroyed or request_id != self._request_id:
            return
        self.loading_lbl.setVisible(False)
        self._render_cards(cards)

    def _on_cards_error(self, request_id: int, msg: str):
        if self._destroyed:
            return
        if request_id != self._request_id:
            return
        self.loading_lbl.setText(msg or tr("No se pudieron cargar las cartas."))
        self.loading_lbl.setVisible(True)
        self.export_text.clear()

    # ------------------------------------------------------------------ #
    # Renderizado
    # ------------------------------------------------------------------ #
    def _clear_detail(self):
        if self._destroyed:
            return
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.detail_layout.addStretch()

    def _render_cards(self, cards: list[dict]):
        if self._destroyed:
            return
        self._current_cards = cards
        self._update_export_text()

        CATEGORY_ORDER = ["Criaturas", "Planeswalkers", "Instantáneos", "Conjuros",
                          "Artefactos", "Encantamientos", "Batallas", "Otras", "Tierras"]

        def cat_of(card):
            tl = card.get("type_line", "") or ""
            if "Land" in tl: return "Tierras"
            if "Creature" in tl: return "Criaturas"
            if "Planeswalker" in tl: return "Planeswalkers"
            if "Instant" in tl: return "Instantáneos"
            if "Sorcery" in tl: return "Conjuros"
            if "Artifact" in tl: return "Artefactos"
            if "Enchantment" in tl: return "Encantamientos"
            if "Battle" in tl: return "Batallas"
            return "Otras"

        main_cards = [c for c in cards if c.get("zone") != "sideboard"]
        side_cards = [c for c in cards if c.get("zone") == "sideboard"]

        def render_zone(zone_cards: list[dict], prefix: str):
            buckets = {}
            for c in zone_cards:
                buckets.setdefault(cat_of(c), []).append(c)
            last_idx = self.detail_layout.count() - 1
            for cat in CATEGORY_ORDER:
                group_cards = buckets.get(cat)
                if group_cards:
                    self.detail_layout.insertWidget(
                        last_idx, DeckGroup(f"{prefix}{tr(cat)}", group_cards)
                    )
                    last_idx += 1

        render_zone(main_cards, "")
        render_zone(side_cards, tr("Banquillo · "))

    def _update_export_text(self):
        """Genera una lista compatible con la importación de MTG Arena."""
        main_cards = [
            c for c in self._current_cards if c.get("zone") != "sideboard"
        ]
        side_cards = [
            c for c in self._current_cards if c.get("zone") == "sideboard"
        ]

        def card_line(card: dict) -> str | None:
            name = (card.get("export_name") or card.get("name") or "").strip()
            if not name or name.startswith(("Carta #", "Card #")):
                return None
            qty = max(1, int(card.get("quantity", 1) or 1))
            return f"{qty} {name}"

        lines = ["Deck"]
        for card in main_cards:
            line = card_line(card)
            if line:
                lines.append(line)

        side_lines = [line for line in (card_line(c) for c in side_cards) if line]
        if side_lines:
            lines.extend(["", "Sideboard", *side_lines])

        self.export_text.setPlainText("\n".join(lines))

    def _copy_export_list(self):
        text = self.export_text.toPlainText().strip()
        if not text or text == "Deck":
            QMessageBox.information(
                self, tr("Vacío"), tr("No hay ninguna lista para copiar.")
            )
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        QMessageBox.information(
            self,
            tr("Copiado"),
            tr(
                "Lista de exportación copiada al portapapeles.\n"
                "Pegala en MTG Arena para importar el mazo."
            ),
        )

    def cleanup(self):
        self._destroyed = True
        self._request_id += 1
        clear_all_pending()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
