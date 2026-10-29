"""Pestaña Historial: listado completo de partidas registradas."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mtga_companion.database import DB_PATH, format_local_timestamp, get_matches
from mtga_companion.i18n import tr

from .theme import COLORS
from .widgets.ui import set_chip

# Columnas con ancho automático. Se congelan mientras se puebla la tabla:
# con la tabla visible, ``ResizeToContents`` recalcula el ancho en cada
# ``setItem`` y el poblado pasa de ~24 ms a varios segundos.
_AUTO_WIDTH_COLUMNS = (0, 2, 3, 5)


class HistoryWidget(QWidget):
    def __init__(self, db_path=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._all_matches = []
        self._db_signature = None
        self._render_key = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._apply_filter)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ------------------------------------------------------------------
        # Barra de filtros
        # ------------------------------------------------------------------
        filter_frame = QFrame()
        filter_frame.setObjectName("surface")
        filter_bar = QHBoxLayout(filter_frame)
        filter_bar.setContentsMargins(12, 10, 12, 10)
        filter_bar.setSpacing(8)

        search_label = QLabel(tr("Buscar"))
        search_label.setObjectName("muted")
        filter_bar.addWidget(search_label)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Mazo, oponente o formato…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search_changed)
        filter_bar.addWidget(self.search, stretch=1)

        btn_clear = QPushButton(tr("Limpiar"))
        btn_clear.setObjectName("ghostButton")
        btn_clear.clicked.connect(self.search.clear)
        filter_bar.addWidget(btn_clear)

        btn_refresh = QPushButton(tr("Actualizar"))
        btn_refresh.clicked.connect(lambda: self.load(force=True))
        filter_bar.addWidget(btn_refresh)

        self.count_label = QLabel(tr("0 partidas"))
        set_chip(self.count_label, tr("0 partidas"), "muted")
        filter_bar.addWidget(self.count_label)
        root.addWidget(filter_frame)

        # ------------------------------------------------------------------
        # Tabla
        # ------------------------------------------------------------------
        table_frame = QFrame()
        table_frame.setObjectName("surface")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(8, 6, 8, 8)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                tr("FECHA"),
                tr("MAZO"),
                tr("FORMATO"),
                tr("RESULTADO"),
                tr("OPONENTE"),
                tr("CARTAS"),
                tr("ID"),
            ]
        )
        self.table.setColumnHidden(6, True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        table_layout.addWidget(self.table)
        root.addWidget(table_frame, stretch=1)

        self.load()

    def _on_search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _current_signature(self):
        """Firma del archivo SQLite (incluye el WAL) para detectar cambios."""
        base = Path(self.db_path or DB_PATH)
        signature = []
        for candidate in (base, Path(f"{base}-wal")):
            try:
                stat = candidate.stat()
            except OSError:
                signature.append(None)
            else:
                signature.append((stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    @contextmanager
    def _frozen_auto_columns(self):
        """Congela las columnas de ancho automático mientras se puebla."""
        header = self.table.horizontalHeader()
        modes = {}
        for column in _AUTO_WIDTH_COLUMNS:
            modes[column] = header.sectionResizeMode(column)
            if modes[column] == QHeaderView.ResizeMode.ResizeToContents:
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        try:
            yield
        finally:
            for column, mode in modes.items():
                if header.sectionResizeMode(column) != mode:
                    header.setSectionResizeMode(column, mode)

    def load(self, force: bool = False):
        signature = self._current_signature()
        if not force and signature == self._db_signature:
            # Nada cambió en disco: reutilizamos las filas ya cargadas.
            self._apply_filter()
            return

        try:
            matches = get_matches(self.db_path)
        except Exception:
            matches = []
        self._all_matches = matches
        self._db_signature = signature
        self._apply_filter()

    def _apply_filter(self):
        self._search_timer.stop()
        text = self.search.text().lower().strip()
        render_key = (self._db_signature, text)
        if render_key == self._render_key:
            return
        matches = getattr(self, "_all_matches", [])
        if text:
            matches = [
                m for m in matches
                if text in (m.get("deck_name") or "").lower()
                or text in (m.get("opponent") or "").lower()
                or text in (m.get("format") or "").lower()
            ]

        with self._frozen_auto_columns():
            self.table.setRowCount(len(matches))
            for row, match in enumerate(matches):
                fecha = format_local_timestamp(match.get("timestamp"))
                deck = match.get("deck_name") or "-"
                fmt = match.get("format") or "-"
                result = match.get("result") or "?"
                opponent = match.get("opponent") or "-"
                mid = str(match.get("id", ""))
                card_count = self._card_count(match.get("deck_cards"))

                date_item = QTableWidgetItem(fecha)
                date_item.setForeground(QColor(COLORS["muted"]))
                deck_item = QTableWidgetItem(deck)
                deck_item.setForeground(QColor(COLORS["text_soft"]))
                fmt_item = QTableWidgetItem(fmt)
                fmt_item.setForeground(QColor(COLORS["muted"]))

                result_item = QTableWidgetItem(self._result_label(result))
                result_item.setFont(QFont("Noto Sans", 10, QFont.Weight.DemiBold))
                if result == "win":
                    result_item.setForeground(QColor(COLORS["green"]))
                elif result == "loss":
                    result_item.setForeground(QColor(COLORS["red"]))
                else:
                    result_item.setForeground(QColor(COLORS["muted"]))

                opponent_item = QTableWidgetItem(opponent)
                opponent_item.setForeground(QColor(COLORS["text_soft"]))
                cards_item = QTableWidgetItem(card_count)
                cards_item.setForeground(QColor(COLORS["muted"]))
                cards_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )

                for column, item in enumerate(
                    (
                        date_item,
                        deck_item,
                        fmt_item,
                        result_item,
                        opponent_item,
                        cards_item,
                        QTableWidgetItem(mid),
                    )
                ):
                    self.table.setItem(row, column, item)

        total = len(getattr(self, "_all_matches", []))
        if text:
            label = tr(
                "{count} de {total} partidas",
                count=len(matches),
                total=total,
            )
        else:
            label = tr("{count} partidas", count=total)
        set_chip(self.count_label, label, "muted")
        self._render_key = render_key

    @staticmethod
    def _result_label(result: str) -> str:
        return {
            "win": tr("Victoria"),
            "loss": tr("Derrota"),
            "unknown": tr("Desconocido"),
        }.get(result, result or "—")

    @staticmethod
    def _card_count(raw: str | None) -> str:
        if not raw:
            return "—"
        try:
            cards = json.loads(raw)
        except (TypeError, ValueError):
            return "—"
        if not isinstance(cards, list):
            return "—"
        try:
            return str(sum(int(card.get("quantity", 0)) for card in cards))
        except (TypeError, ValueError, AttributeError):
            return "—"

    def on_match_detected(self, match_result):
        """Llamar cuando el watcher detecta una nueva partida."""
        self.load(force=True)
