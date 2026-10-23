"""Widgets visuales reutilizables del tema Arena."""
from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from mtga_companion.i18n import tr

from ..theme import COLORS


def set_chip(label: QLabel, text: str, kind: str = "muted") -> None:
    """Actualiza el texto y el color semántico de un chip."""
    label.setText(text)
    label.setProperty("chip", kind)
    style = label.style()
    if style is not None:
        style.unpolish(label)
        style.polish(label)
    label.update()


class WinrateRing(QWidget):
    """Anillo de winrate dibujado con QPainter (sin dependencias extra)."""

    def __init__(self, diameter: int = 164, parent=None):
        super().__init__(parent)
        self._diameter = diameter
        self._winrate: float | None = None
        self._wins = 0
        self._losses = 0
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def sizeHint(self) -> QSize:  # noqa: N802 - API de Qt
        return QSize(self._diameter, self._diameter)

    def set_data(self, wins: int, losses: int, unknown: int = 0) -> None:
        self._wins = max(0, int(wins))
        self._losses = max(0, int(losses))
        decided = self._wins + self._losses
        self._winrate = (self._wins / decided * 100.0) if decided else None
        wins_key = "{count} victoria" if self._wins == 1 else "{count} victorias"
        losses_key = (
            "{count} derrota" if self._losses == 1 else "{count} derrotas"
        )
        tooltip = (
            tr(wins_key, count=self._wins)
            + " · "
            + tr(losses_key, count=self._losses)
        )
        if unknown:
            tooltip += tr(" · {count} sin resultado", count=unknown)
        self.setToolTip(tooltip)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        side = min(self.width(), self.height())
        margin = 11.0
        ring = QRectF(
            (self.width() - side) / 2 + margin,
            (self.height() - side) / 2 + margin,
            side - margin * 2,
            side - margin * 2,
        )

        track_pen = QPen(QColor(COLORS["border_strong"]), 11)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(ring, 0, 360 * 16)

        if self._winrate is not None:
            value = max(0.0, min(100.0, self._winrate))
            color = QColor(COLORS["green"] if value >= 50 else COLORS["red"])
            value_pen = QPen(color, 11)
            value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(value_pen)
            # Empieza arriba y avanza en sentido horario.
            painter.drawArc(ring, 90 * 16, -int(360 * 16 * value / 100.0))

        painter.setPen(QColor(COLORS["text"]))
        value_font = QFont("Noto Sans")
        value_font.setPixelSize(29)
        value_font.setWeight(QFont.Weight.Bold)
        painter.setFont(value_font)
        painter.drawText(
            ring.adjusted(0, -13, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            "—" if self._winrate is None else f"{self._winrate:.1f}%",
        )

        caption_font = QFont("Noto Sans")
        caption_font.setPixelSize(8)
        caption_font.setWeight(QFont.Weight.Bold)
        caption_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.3)
        painter.setFont(caption_font)
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(
            ring.adjusted(0, 38, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            tr("WINRATE GLOBAL"),
        )


class SectionHeader(QWidget):
    """Título de sección con una pequeña marca dorada y acción opcional."""

    def __init__(self, title: str, hint: str = "", parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        accent = QFrame()
        accent.setFixedSize(3, 16)
        accent.setStyleSheet(
            f"background: {COLORS['gold']}; border: none; border-radius: 1px;"
        )
        self._layout.addWidget(accent)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("sectionTitle")
        self._layout.addWidget(title_lbl)

        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setObjectName("sectionHint")
            self._layout.addWidget(hint_lbl)

        self._layout.addStretch(1)

    def add_action(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class MetricCard(QFrame):
    """Tarjeta compacta para un número grande y su etiqueta."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        subtitle: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(74)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("statLabel")
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("statValue")
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("statSub")
        self.sub_lbl.setWordWrap(True)

        layout.addWidget(title_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.sub_lbl)
        layout.addStretch(1)

    def set_value(self, value: str) -> None:
        self.value_lbl.setText(str(value))

    def set_subtitle(self, text: str) -> None:
        self.sub_lbl.setText(text)


class PeriodCard(QFrame):
    """Resumen de winrate para un período (hoy, 7 días, 30 días)."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(94)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(0)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("statLabel")
        self.value_lbl = QLabel("—")
        self.value_lbl.setObjectName("statValue")
        self.detail_lbl = QLabel(tr("Sin partidas"))
        self.detail_lbl.setObjectName("statSub")
        self.detail_lbl.setWordWrap(True)

        layout.addWidget(title_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.detail_lbl)
        layout.addStretch(1)

    def set_stats(self, total: int, wins: int, losses: int, winrate: str) -> None:
        total = int(total or 0)
        wins = int(wins or 0)
        losses = int(losses or 0)
        if total == 0:
            self.value_lbl.setText("—")
            self.detail_lbl.setText(tr("Sin partidas"))
            self.value_lbl.setStyleSheet(
                f"color: {COLORS['muted']}; font-size: 30px; font-weight: 700;"
            )
            return

        self.value_lbl.setText(winrate)
        self.detail_lbl.setText(
            tr(
                "{total} partidas · {wins}V · {losses}D",
                total=total,
                wins=wins,
                losses=losses,
            )
        )
        try:
            numeric = float(str(winrate).replace("%", "").replace(",", "."))
        except ValueError:
            numeric = 50.0
        color = COLORS["green"] if numeric >= 50 else COLORS["red"]
        self.value_lbl.setStyleSheet(
            f"color: {color}; font-size: 30px; font-weight: 700;"
        )


class DetailChip(QLabel):
    """Chip de metadatos para cabeceras de detalle."""

    def __init__(self, text: str = "", kind: str = "muted", parent=None):
        super().__init__(text, parent)
        self.setProperty("chip", kind)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

class DeckListRow(QWidget):
    """Fila de dos líneas para listas de mazos (sin texto truncado)."""

    def __init__(self, name: str, detail: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)

        self.name_lbl = QLabel(name)
        self.name_lbl.setObjectName("deckName")
        self.name_lbl.setToolTip(name)
        self.detail_lbl = QLabel(detail)
        self.detail_lbl.setObjectName("deckMeta")
        self.detail_lbl.setToolTip(detail)
        layout.addWidget(self.name_lbl)
        layout.addWidget(self.detail_lbl)

class DeckItemDelegate(QStyledItemDelegate):
    """Dibuja filas de mazos con nombre y detalle en dos líneas."""

    def sizeHint(self, option, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(0, 54)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1B2736"))
            painter.drawRoundedRect(rect, 9, 9)

        name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        detail = str(index.data(Qt.ItemDataRole.UserRole + 1) or "")

        name_font = QFont("Noto Sans")
        name_font.setPixelSize(12)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor("#E8C97F" if selected else "#E8EDF3"))
        name_rect = QRect(rect.left() + 10, rect.top() + 5, rect.width() - 20, 23)
        metrics = painter.fontMetrics()
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(name, Qt.TextElideMode.ElideRight, name_rect.width()),
        )

        detail_font = QFont("Noto Sans")
        detail_font.setPixelSize(10)
        painter.setFont(detail_font)
        painter.setPen(QColor("#7F8BA0" if not selected else "#A9B4C4"))
        detail_rect = QRect(rect.left() + 10, rect.top() + 29, rect.width() - 20, 17)
        metrics = painter.fontMetrics()
        painter.drawText(
            detail_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(detail, Qt.TextElideMode.ElideRight, detail_rect.width()),
        )
        painter.restore()
