"""Pestaña Dashboard: resumen general de winrate y partidas recientes."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mtga_companion.database import (
    compute_daily_summary,
    format_local_timestamp,
    get_matches,
)
from mtga_companion.i18n import tr
from .theme import COLORS
from .widgets.ui import MetricCard, PeriodCard, SectionHeader, WinrateRing


class DashboardWidget(QWidget):
    def __init__(self, db_path=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ------------------------------------------------------------------
        # Héroe: anillo de winrate + contadores globales
        # ------------------------------------------------------------------
        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(26)

        ring_box = QVBoxLayout()
        ring_box.setSpacing(6)
        ring_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ring = WinrateRing(148)
        self.record_lbl = QLabel(tr("Sin partidas"))
        self.record_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_lbl.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 13px; font-weight: 600;"
        )
        self.record_sub = QLabel(tr("Registro global"))
        self.record_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_sub.setObjectName("statSub")
        ring_box.addWidget(self.ring, alignment=Qt.AlignmentFlag.AlignCenter)
        ring_box.addWidget(self.record_lbl)
        ring_box.addWidget(self.record_sub)
        hero_layout.addLayout(ring_box)

        stats_box = QVBoxLayout()
        stats_box.setSpacing(8)
        stats_title = QLabel(tr("RENDIMIENTO GLOBAL"))
        stats_title.setObjectName("sectionTitle")
        stats_sub = QLabel(tr("Todo tu historial registrado en Arena"))
        stats_sub.setObjectName("sectionHint")
        stats_box.addWidget(stats_title)
        stats_box.addWidget(stats_sub)

        stats_grid = QGridLayout()
        stats_grid.setContentsMargins(0, 6, 0, 0)
        stats_grid.setHorizontalSpacing(10)
        stats_grid.setVerticalSpacing(10)
        self.card_total = MetricCard(
            tr("Partidas"), "0", tr("Partidas registradas")
        )
        self.card_wins = MetricCard(
            tr("Victorias"), "0", tr("Resultados ganados")
        )
        self.card_losses = MetricCard(
            tr("Derrotas"), "0", tr("Resultados perdidos")
        )
        self.card_unknown = MetricCard(
            tr("Sin resultado"), "0", tr("No se pudo determinar")
        )
        stats_grid.addWidget(self.card_total, 0, 0)
        stats_grid.addWidget(self.card_wins, 0, 1)
        stats_grid.addWidget(self.card_losses, 1, 0)
        stats_grid.addWidget(self.card_unknown, 1, 1)
        stats_box.addLayout(stats_grid)
        stats_box.addStretch(1)
        hero_layout.addLayout(stats_box, stretch=1)

        root.addWidget(hero)

        # ------------------------------------------------------------------
        # Winrate por período
        # ------------------------------------------------------------------
        period_header = SectionHeader(
            tr("Winrate por período"), tr("Hoy, 7 y 30 días")
        )
        root.addWidget(period_header)

        periods = QHBoxLayout()
        periods.setSpacing(10)
        self.card_today = PeriodCard(tr("Hoy"))
        self.card_week = PeriodCard(tr("Últimos 7 días"))
        self.card_month = PeriodCard(tr("Últimos 30 días"))
        for card in (self.card_today, self.card_week, self.card_month):
            periods.addWidget(card, stretch=1)
        root.addLayout(periods)

        # ------------------------------------------------------------------
        # Partidas recientes
        # ------------------------------------------------------------------
        recent_header = SectionHeader(
            tr("Partidas recientes"), tr("Últimas 15 partidas")
        )
        btn_refresh = QPushButton(tr("Actualizar"))
        btn_refresh.setObjectName("ghostButton")
        btn_refresh.clicked.connect(self.refresh)
        recent_header.add_action(btn_refresh)
        root.addWidget(recent_header)

        table_frame = QFrame()
        table_frame.setObjectName("surface")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(8, 6, 8, 8)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [
                tr("FECHA"),
                tr("MAZO"),
                tr("FORMATO"),
                tr("RESULTADO"),
                tr("OPONENTE"),
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
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

        table_layout.addWidget(self.table)
        root.addWidget(table_frame, stretch=1)

        self.refresh()

        # Refrescar cada 10 segundos si hay datos nuevos.
        self._timer.start(10000)

    def _format_wr(self, wr) -> str:
        """Formatea un winrate para mostrar."""
        if wr is None:
            return "—"
        return f"{wr}%"

    def refresh(self):
        try:
            daily = compute_daily_summary(self.db_path)
        except Exception:
            daily = {
                "today": {"total": 0, "wins": 0, "losses": 0, "unknown": 0, "winrate": None},
                "last7": {"total": 0, "wins": 0, "losses": 0, "unknown": 0, "winrate": None},
                "last30": {"total": 0, "wins": 0, "losses": 0, "unknown": 0, "winrate": None},
                "all_time": {"total": 0, "wins": 0, "losses": 0, "unknown": 0, "winrate": None},
            }

        at = daily["all_time"]
        total = at["total"]
        wins = at["wins"]
        losses = at["losses"]
        unknown = at["unknown"]
        wr = at["winrate"]

        self.ring.set_data(wins, losses, unknown)
        if wins + losses:
            self.record_lbl.setText(
                tr("{wins}V · {losses}D", wins=wins, losses=losses)
            )
            self.record_sub.setText(
                tr(
                    "{count} partidas · {winrate} de winrate",
                    count=total,
                    winrate=self._format_wr(wr),
                )
            )
        else:
            self.record_lbl.setText(tr("Sin partidas"))
            self.record_sub.setText(tr("Registro global"))

        self.card_total.set_value(str(total))
        self.card_total.set_subtitle(tr("Partidas registradas"))
        self.card_wins.set_value(str(wins))
        self.card_wins.set_subtitle(
            tr("{winrate} de winrate", winrate=self._format_wr(wr))
        )
        self.card_losses.set_value(str(losses))
        self.card_losses.set_subtitle(tr("Resultados perdidos"))
        self.card_unknown.set_value(str(unknown))
        self.card_unknown.set_subtitle(tr("No se pudo determinar"))

        for key, card in (
            ("today", self.card_today),
            ("last7", self.card_week),
            ("last30", self.card_month),
        ):
            data = daily[key]
            card.set_stats(
                data["total"],
                data["wins"],
                data["losses"],
                self._format_wr(data["winrate"]),
            )

        # Tabla de partidas recientes.
        try:
            all_matches = get_matches(self.db_path)
        except Exception:
            all_matches = []

        recent = all_matches[:15]
        self.table.setRowCount(len(recent))
        for row, match in enumerate(recent):
            fecha = format_local_timestamp(match.get("timestamp"))
            deck = match.get("deck_name") or "-"
            fmt = match.get("format") or "-"
            result = match.get("result") or "?"
            opponent = match.get("opponent") or "-"

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

            for column, item in enumerate(
                (date_item, deck_item, fmt_item, result_item, opponent_item)
            ):
                self.table.setItem(row, column, item)

    @staticmethod
    def _result_label(result: str) -> str:
        return {
            "win": tr("Victoria"),
            "loss": tr("Derrota"),
            "unknown": tr("Desconocido"),
        }.get(result, result or "—")

    def on_match_detected(self, match_result):
        """Llamar cuando el watcher detecta una nueva partida."""
        self.refresh()

    def on_deck_detected(self, detected_deck):
        """Llamar cuando el watcher detecta un mazo activo."""
        pass

    def cleanup(self):
        """Detiene el refresco periódico antes de cerrar."""
        self._timer.stop()
