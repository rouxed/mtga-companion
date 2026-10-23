"""Pestaña Mazos: listado de mazos usados con sus cartas agrupadas por tipo."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from mtga_companion.database import format_local_timestamp, get_connection, get_deck
from mtga_companion.config import DB_PATH as CONFIG_DB_PATH
from mtga_companion.i18n import tr
from .widgets.card_tile import DeckGroup
from .widgets.deck_loader import DeckLoaderThread
from .widgets.ui import DeckItemDelegate


class DecksWidget(QWidget):
    def __init__(self, db_path=CONFIG_DB_PATH, parent=None):
        super().__init__(parent)
        self.db_path = Path(db_path)
        self._loader_thread: DeckLoaderThread | None = None
        self._load_generation = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # --- Panel izquierdo: lista de mazos ---
        left = QFrame()
        left.setObjectName("surface")
        left.setFixedWidth(330)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 12)
        left_layout.setSpacing(8)

        list_title = QLabel(tr("MAZOS REGISTRADOS"))
        list_title.setObjectName("sectionTitle")
        left_layout.addWidget(list_title)

        list_hint = QLabel(tr("Ordenados por última vez jugados"))
        list_hint.setObjectName("sectionHint")
        left_layout.addWidget(list_hint)

        self.list = QListWidget()
        self.list.setObjectName("deckList")
        self.list.setSpacing(2)
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(DeckItemDelegate(self.list))
        self.list.currentItemChanged.connect(self._on_deck_selected)
        left_layout.addWidget(self.list, stretch=1)

        btn_refresh = QPushButton(tr("Actualizar lista"))
        btn_refresh.clicked.connect(self.load_decks)
        left_layout.addWidget(btn_refresh)

        root.addWidget(left)

        # --- Panel derecho: detalle del mazo ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.detail_title = QLabel(tr("Seleccioná un mazo"))
        self.detail_title.setObjectName("detailTitle")
        right_layout.addWidget(self.detail_title)

        self.detail_stats = QLabel("")
        self.detail_stats.setObjectName("muted")
        self.detail_stats.setWordWrap(True)
        right_layout.addWidget(self.detail_stats)

        # Indicador de carga
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

        root.addWidget(right, stretch=1)

        self.load_decks()

    def load_decks(self):
        self.list.clear()
        con = get_connection(self.db_path)
        try:
            rows = con.execute(
                "SELECT name, wins, losses, unknown, format, last_seen FROM decks ORDER BY last_seen DESC"
            ).fetchall()
        finally:
            con.close()

        if not rows:
            self.detail_title.setText(tr("Todavía no hay mazos"))
            self.detail_stats.setText(
                tr(
                    "Jugá una partida con Arena abierto para registrar tu primer mazo."
                )
            )

        for row in rows:
            name = row["name"]
            wins = row["wins"]
            losses = row["losses"]
            total = wins + losses
            wr = round(100 * wins / total, 1) if total else 0
            detail = tr(
                "{format}  ·  {wins}V-{losses}D  ·  {wr}%",
                format=row["format"] or tr("Formato desconocido"),
                wins=wins,
                losses=losses,
                wr=wr,
            )
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setData(Qt.ItemDataRole.UserRole + 1, detail)
            item.setSizeHint(QSize(0, 54))
            item.setToolTip(f"{name}\n{detail}")
            self.list.addItem(item)

    def _on_deck_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if not current:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        self._show_deck(name)

    def _show_deck(self, name: str):
        deck = get_deck(name, self.db_path)
        if not deck:
            return

        self.detail_title.setText(name)
        fmt = deck.get("format") or "-"
        wins = deck.get("wins") or 0
        losses = deck.get("losses") or 0
        total = wins + losses
        wr = round(100 * wins / total, 1) if total else 0
        self.detail_stats.setText(
            tr(
                "{format}  ·  {wins}V-{losses}D  ·  {wr}% de winrate  ·  "
                "última vez {date}",
                format=fmt,
                wins=wins,
                losses=losses,
                wr=wr,
                date=format_local_timestamp(
                    deck.get("last_seen"), "%Y-%m-%d"
                ),
            )
        )

        # Limpiar contenido previo y mostrar cargando
        self._clear_detail()
        self.loading_lbl.setVisible(True)

        card_ids = deck.get("card_ids") or "{}"
        try:
            id_counts = json.loads(card_ids)
        except json.JSONDecodeError:
            id_counts = {}

        entries = [{"cardId": cid, "quantity": qty} for cid, qty in id_counts.items()]

        # Lanzar resolución asíncrona de cartas
        if self._loader_thread is not None:
            self._disconnect_loader(self._loader_thread)
            self._loader_thread.stop()
            self._loader_thread.join(timeout=1.0)
        self._load_generation += 1
        generation = self._load_generation
        self._loader_thread = DeckLoaderThread(entries)
        self._loader_thread.signals.finished.connect(
            lambda cards, gen=generation: self._on_cards_resolved(cards, gen)
        )
        self._loader_thread.signals.error.connect(
            lambda msg, gen=generation: self._on_cards_error(msg, gen)
        )
        self._loader_thread.start()

    def _clear_detail(self):
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.detail_layout.addStretch()

    def _on_cards_resolved(self, cards: list[dict], generation: int):
        if generation != self._load_generation:
            return
        self.loading_lbl.setVisible(False)

        # Quitar el stretch previo para agregar contenido y luego volver a ponerlo
        # (el stretch está al final, lo movemos temporalmente)
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

        buckets = {}
        for c in cards:
            buckets.setdefault(cat_of(c), []).append(c)

        # El stretch está al último índice
        last_idx = self.detail_layout.count() - 1
        for cat in CATEGORY_ORDER:
            group_cards = buckets.get(cat)
            if group_cards:
                self.detail_layout.insertWidget(
                    last_idx, DeckGroup(tr(cat), group_cards)
                )
                last_idx += 1

    def _on_cards_error(self, msg: str, generation: int):
        if generation != self._load_generation:
            return
        self.loading_lbl.setVisible(False)
        self.detail_title.setText(tr("Error cargando cartas"))
        self.detail_stats.setText(msg)

    def on_deck_detected(self, detected_deck):
        """Llamar cuando el watcher detecta un mazo activo."""
        if detected_deck and detected_deck.name:
            # Seleccionar el mazo en la lista si existe
            for i in range(self.list.count()):
                item = self.list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == detected_deck.name:
                    self.list.setCurrentItem(item)
                    break

    @staticmethod
    def _disconnect_loader(loader: DeckLoaderThread) -> None:
        """Evita que un hilo antiguo actualice la UI después de ser reemplazado."""
        try:
            loader.signals.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            loader.signals.error.disconnect()
        except (TypeError, RuntimeError):
            pass

    def cleanup(self):
        """Cancela la carga de cartas en curso antes de cerrar."""
        self._load_generation += 1
        if self._loader_thread is not None:
            self._disconnect_loader(self._loader_thread)
            self._loader_thread.stop()
            self._loader_thread.join(timeout=1.0)
            self._loader_thread = None

    def closeEvent(self, event):  # noqa: N802
        self.cleanup()
        super().closeEvent(event)
