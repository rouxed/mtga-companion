"""Tarjetas y grupos de cartas en formato grilla (estilo colección)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mtga_companion.i18n import tr

from .image_loader import get_global_loader

CARD_WIDTH = 154
CARD_HEIGHT = 266
IMAGE_WIDTH = 140
IMAGE_HEIGHT = 196
GRID_GAP = 8


class CardTile(QFrame):
    """Una carta del mazo: imagen, cantidad, nombre y tipo."""

    def __init__(self, card: dict, parent=None):
        super().__init__(parent)
        self.card = card
        self.setObjectName("cardTile")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setToolTip(self._tooltip_text(card))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(4)

        # Marco de la imagen con la cantidad superpuesta.
        image_frame = QFrame()
        image_frame.setObjectName("cardImage")
        image_frame.setFixedSize(IMAGE_WIDTH, IMAGE_HEIGHT)

        image_grid = QGridLayout(image_frame)
        image_grid.setContentsMargins(3, 3, 3, 3)
        image_grid.setSpacing(0)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet(
            "background: transparent; border: none; color: #667386; font-size: 22px;"
        )
        image_grid.addWidget(self.img_label, 0, 0)

        qty = int(card.get("quantity", 1) or 1)
        self.qty_label = QLabel(str(qty))
        self.qty_label.setObjectName("qtyBadge")
        self.qty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qty_label.setFixedHeight(20)
        self.qty_label.setMinimumWidth(22)
        if qty <= 1:
            self.qty_label.hide()
        image_grid.addWidget(
            self.qty_label,
            0,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )

        name = card.get("name", tr("Carta desconocida"))
        self.name_label = QLabel(name)
        self.name_label.setObjectName("cardName")
        self.name_label.setWordWrap(True)
        self.name_label.setFixedHeight(30)
        self.name_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        type_line = card.get("type_line", "") or ""
        self.type_label = QLabel(type_line)
        self.type_label.setObjectName("cardType")
        self.type_label.setFixedHeight(14)
        self.type_label.setToolTip(type_line)

        layout.addWidget(image_frame)
        layout.addWidget(self.name_label)
        layout.addWidget(self.type_label)

        self._load_image(card.get("image"))

    @staticmethod
    def _tooltip_text(card: dict) -> str:
        name = card.get("name", tr("Carta desconocida"))
        type_line = card.get("type_line", "")
        qty = int(card.get("quantity", 1) or 1)
        parts = [f"{qty} × {name}"]
        if type_line:
            parts.append(type_line)
        return "\n".join(parts)

    def _load_image(self, url: str | None) -> None:
        if not url:
            self.img_label.setText("—")
            return
        loader = get_global_loader()
        pixmap = loader.load(url, self._on_image_loaded)
        if pixmap is not None:
            self._on_image_loaded(pixmap)

    def _on_image_loaded(self, pixmap: QPixmap | None) -> None:
        if pixmap is None or pixmap.isNull():
            self.img_label.setText("—")
            return
        self.img_label.setText("")
        self.img_label.setPixmap(
            pixmap.scaled(
                IMAGE_WIDTH - 8,
                IMAGE_HEIGHT - 8,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class DeckGroup(QWidget):
    """Grupo de cartas plegable con grilla adaptable al ancho disponible."""

    def __init__(self, category: str, cards: list[dict], parent=None):
        super().__init__(parent)
        self.category = category
        self.cards = cards
        self._collapsed = False
        self._cols = 4

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("groupHeader")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self.toggle_btn)

        self.cards_container = QWidget()
        self.grid = QGridLayout(self.cards_container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(GRID_GAP)
        self.grid.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self.cards_container)

        self._update_header()
        self._populate()

    def _card_count(self) -> int:
        return sum(int(c.get("quantity", 1) or 1) for c in self.cards)

    def _update_header(self) -> None:
        arrow = "▸" if self._collapsed else "▾"
        count = self._card_count()
        label = tr("carta") if count == 1 else tr("cartas")
        self.toggle_btn.setText(f"{arrow}  {self.category}   ·   {count} {label}")

    def _columns_for_width(self) -> int:
        width = self.width()
        if width <= 0:
            width = self.cards_container.width()
        if width <= 0:
            return self._cols
        available = width - 2
        columns = int((available + GRID_GAP) // (CARD_WIDTH + GRID_GAP))
        return max(2, min(6, columns))

    def _populate(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, card in enumerate(self.cards):
            row, col = divmod(index, self._cols)
            self.grid.addWidget(CardTile(card), row, col)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        columns = self._columns_for_width()
        if columns != self._cols:
            self._cols = columns
            self._populate()

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self.cards_container.setVisible(not self._collapsed)
        self._update_header()
