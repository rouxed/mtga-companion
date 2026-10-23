"""Ventana flotante que muestra las probabilidades de robo.

Se ejecuta en un proceso aparte con el backend XCB para poder usar una ventana
transparente, click-through y siempre arriba incluso cuando la app principal
corre bajo Wayland. El proceso recibe snapshots JSON por stdin.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .gui.theme import COLORS
from .i18n import tr
from .overlay_positions import DEFAULT_POSITION, normalize_position

_OVERLAY_QSS = """
QWidget {
    color: #F2F5F8;
    font-family: "Noto Sans";
    font-size: 12px;
}
QFrame#overlayRoot {
    background: rgba(9, 14, 20, 252);
    border: 1px solid rgba(214, 179, 106, 0.52);
    border-radius: 16px;
}
QLabel#overlayKicker {
    color: #D6B36A;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
}
QLabel#overlayTitle {
    color: #F5F7FA;
    font-size: 22px;
    font-weight: 700;
}
QLabel#overlayDeck {
    color: #C7D0DC;
    font-size: 11px;
    font-weight: 600;
}
QLabel#overlayContext {
    color: #7F8BA0;
    font-size: 10px;
}
QLabel#overlaySection {
    color: #D6B36A;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.2px;
}
QLabel#overlayMuted {
    color: #7F8BA0;
    font-size: 10px;
}
QLabel#overlayValue {
    color: #E8EDF3;
    font-size: 13px;
    font-weight: 700;
}
QLabel#overlayProbability {
    color: #E8C97F;
    font-size: 13px;
    font-weight: 700;
}
QLabel#overlaySmallProbability {
    color: #8E9AAF;
    font-size: 11px;
    font-weight: 600;
}
QLabel#overlayCard {
    color: #DCE3EC;
    font-size: 10px;
    font-weight: 600;
}
QLabel#overlayLand {
    color: #E8EDF3;
    font-size: 11px;
    font-weight: 600;
}
QLabel#overlayEmpty {
    color: #8E9AAF;
    font-size: 12px;
}
QFrame#overlayDivider {
    background: rgba(214, 179, 106, 0.18);
    border: none;
    max-height: 1px;
}
"""


class OverlayWindow(QWidget):
    """Panel compacto, sin bordes y click-through por defecto."""

    def __init__(self):
        super().__init__(None)
        self._click_through = True
        self._position_key = DEFAULT_POSITION
        self._placed = False
        self._payload: dict = {}
        self._drag_offset = None

        self.setWindowTitle("MTGA Companion Overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(0.94)
        self._apply_flags()
        self.setFixedSize(380, 680)
        self._build_ui()
        for label in self.findChildren(QLabel):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(_OVERLAY_QSS)
        self._render_waiting(
            tr("Esperando partida"),
            tr("Abrí Arena y jugá una partida"),
        )

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        root = QFrame()
        root.setObjectName("overlayRoot")
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        kicker_row = QHBoxLayout()
        kicker = QLabel(tr("MTGA COMPANION"))
        kicker.setObjectName("overlayKicker")
        kicker_row.addWidget(kicker)
        kicker_row.addStretch(1)
        self.status_chip = QLabel(tr("ESPERANDO"))
        self.status_chip.setObjectName("overlayKicker")
        kicker_row.addWidget(self.status_chip)
        layout.addLayout(kicker_row)

        title = QLabel(tr("DECK TRACKER"))
        title.setObjectName("overlayTitle")
        layout.addWidget(title)

        self.deck_label = QLabel(tr("Sin mazo activo"))
        self.deck_label.setObjectName("overlayDeck")
        layout.addWidget(self.deck_label)

        self.context_label = QLabel(tr("Abrí Arena y jugá una partida"))
        self.context_label.setObjectName("overlayContext")
        layout.addWidget(self.context_label)

        divider = QFrame()
        divider.setObjectName("overlayDivider")
        layout.addWidget(divider)

        section_lands = QLabel(tr("TIERRAS"))
        section_lands.setObjectName("overlaySection")
        layout.addWidget(section_lands)

        self.land_label = QLabel("—")
        self.land_label.setObjectName("overlayLand")
        layout.addWidget(self.land_label)

        section_next = QLabel(tr("PROBABILIDADES"))
        section_next.setObjectName("overlaySection")
        layout.addWidget(section_next)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        for col, text in enumerate(
            (tr("CATEGORÍA"), tr("AHORA"), tr("3 ROBOS"))
        ):
            lbl = QLabel(text)
            lbl.setObjectName("overlayMuted")
            if col:
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, 0, col)
        self.category_rows: list[dict[str, QLabel]] = []
        for row in range(1, 5):
            name = QLabel("—")
            name.setObjectName("overlayValue")
            now = QLabel("—")
            now.setObjectName("overlayProbability")
            now.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            three = QLabel("—")
            three.setObjectName("overlaySmallProbability")
            three.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(name, row, 0)
            grid.addWidget(now, row, 1)
            grid.addWidget(three, row, 2)
            self.category_rows.append({"name": name, "now": now, "three": three})
        layout.addLayout(grid)

        self.deck_section = QLabel(tr("MAZO RESTANTE"))
        self.deck_section.setObjectName("overlaySection")
        layout.addWidget(self.deck_section)

        deck_grid = QGridLayout()
        deck_grid.setContentsMargins(0, 0, 0, 0)
        deck_grid.setHorizontalSpacing(10)
        deck_grid.setVerticalSpacing(2)
        deck_grid.setColumnStretch(0, 1)
        deck_grid.setColumnStretch(1, 1)
        self.deck_rows: list[QLabel] = []
        for row in range(14):
            for col in range(2):
                label = QLabel("")
                label.setObjectName("overlayCard")
                label.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                deck_grid.addWidget(label, row, col)
                self.deck_rows.append(label)
        layout.addLayout(deck_grid)

        self.deck_more_label = QLabel("")
        self.deck_more_label.setObjectName("overlayMuted")
        layout.addWidget(self.deck_more_label)

        section_opponent = QLabel(tr("CARTAS VISTAS DEL OPONENTE"))
        section_opponent.setObjectName("overlaySection")
        layout.addWidget(section_opponent)

        opponent_grid = QGridLayout()
        opponent_grid.setContentsMargins(0, 0, 0, 0)
        opponent_grid.setHorizontalSpacing(10)
        opponent_grid.setVerticalSpacing(2)
        opponent_grid.setColumnStretch(0, 1)
        opponent_grid.setColumnStretch(1, 1)
        self.opponent_rows: list[QLabel] = []
        for row in range(3):
            for col in range(2):
                label = QLabel("")
                label.setObjectName("overlayCard")
                label.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                opponent_grid.addWidget(label, row, col)
                self.opponent_rows.append(label)
        layout.addLayout(opponent_grid)

        self.opponent_more_label = QLabel("")
        self.opponent_more_label.setObjectName("overlayMuted")
        layout.addWidget(self.opponent_more_label)

        layout.addStretch(1)
        self.empty_label = QLabel("")
        self.empty_label.setObjectName("overlayEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self.footer_label = QLabel("")
        self.footer_label.setObjectName("overlayMuted")
        layout.addWidget(self.footer_label)

    # ------------------------------------------------------------------
    # Ventana
    # ------------------------------------------------------------------
    def _apply_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            # KWin deja las ventanas fullscreen por encima de una ventana
            # normal con _NET_WM_STATE_ABOVE. Un override-redirect de X11
            # (bypass) sí queda por encima del fullscreen de Arena.
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        if self._click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)

    def _set_click_through(self, enabled: bool) -> None:
        if self._click_through == enabled:
            return
        self._click_through = enabled
        was_visible = self.isVisible()
        self._apply_flags()
        if was_visible:
            self.show()
            self.raise_()

    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = 24
        if self._position_key.endswith("left"):
            x = available.left() + margin
        else:
            x = available.right() - self.width() - margin + 1
        if self._position_key.startswith("middle"):
            y = available.top() + (available.height() - self.height()) // 2
        elif self._position_key.startswith("bottom"):
            y = available.bottom() - self.height() - margin + 1
        else:
            y = available.top() + margin
        self.move(x, y)
        self._placed = True

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (
            not self._click_through
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            not self._click_through
            and self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def apply_payload(self, payload: dict) -> None:
        """Actualiza la ventana con un snapshot enviado por la app principal."""
        if not isinstance(payload, dict):
            return
        self._payload = payload

        self._set_click_through(bool(payload.get("click_through", True)))
        try:
            opacity = float(payload.get("opacity", 0.94))
        except (TypeError, ValueError):
            opacity = 0.94
        self.setWindowOpacity(max(0.45, min(1.0, opacity)))

        position = normalize_position(payload.get("position"))
        if position != self._position_key or not self._placed:
            self._position_key = position
            self._place()

        self._render(payload.get("odds") or {})
        if bool(payload.get("visible", True)):
            self.show()
            self.raise_()
        else:
            self.hide()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    @staticmethod
    def _pct(value) -> str:
        try:
            return f"{max(0.0, min(1.0, float(value))) * 100:.0f}%"
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _elide(label: QLabel, text: str, width: int = 166) -> None:
        metrics = label.fontMetrics()
        label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, width))

    def _render_waiting(self, message: str, context: str = "") -> None:
        self.status_chip.setText(tr("ESPERANDO"))
        self.status_chip.setStyleSheet(f"color: {COLORS['muted']};")
        self.context_label.setText(context)
        self.empty_label.setText(message)
        self.footer_label.setText("")
        self.land_label.setText("—")
        self.deck_section.setText(tr("MAZO RESTANTE"))
        self.deck_more_label.setText("")
        self.opponent_more_label.setText("")
        for row in self.category_rows:
            row["name"].setText("—")
            row["now"].setText("—")
            row["three"].setText("—")
        for label in self.deck_rows:
            label.setText("")
        for label in self.opponent_rows:
            label.setText("")

    def _render(self, odds: dict) -> None:
        status = str(odds.get("status") or "")
        if status != "En partida":
            self.deck_label.setText(
                str(odds.get("deck_name") or tr("Esperando partida"))
            )
            if status == "Esperando partida" or not status:
                context = tr("Abrí Arena y jugá una partida")
            else:
                context = tr(
                    "{count} cartas · mano {hand}",
                    count=odds.get("library_count", 0),
                    hand=odds.get("hand_count", 0),
                )
            self._render_waiting(
                tr(status or "Esperando partida"), context
            )
            return

        self.empty_label.setText("")
        self.status_chip.setText(tr("EN VIVO"))
        self.status_chip.setStyleSheet(f"color: {COLORS['green']};")

        deck = str(odds.get("deck_name") or tr("Mazo sin nombre"))
        self._elide(self.deck_label, deck, 280)

        turn = odds.get("turn")
        play = odds.get("on_play")
        play_text = ""
        if play is True:
            play_text = tr(" · en play")
        elif play is False:
            play_text = tr(" · en draw")
        context = tr(
            "{count} cartas · mano {hand}",
            count=odds.get("library_count", 0),
            hand=odds.get("hand_count", 0),
        )
        if turn is not None:
            context = tr(
                "Turno {turn}{play} · {context}",
                turn=turn,
                play=play_text,
                context=context,
            )
        self.context_label.setText(context)

        lands_in_play = int(odds.get("lands_in_play") or 0)
        lands_untapped = int(odds.get("lands_untapped") or 0)
        lands_in_hand = int(odds.get("lands_in_hand") or 0)
        lands_in_library = int(odds.get("lands_in_library") or 0)
        land_text = tr("{count} en juego", count=lands_in_play)
        if lands_in_play:
            land_text += tr(" ({count} sin girar)", count=lands_untapped)
        land_text += tr(" · {count} en mano", count=lands_in_hand)
        land_text += tr(" · {count} en biblioteca", count=lands_in_library)
        self._elide(self.land_label, land_text, 330)

        categories = list(odds.get("categories") or [])
        for index, row in enumerate(self.category_rows):
            if index >= len(categories):
                row["name"].setText("—")
                row["now"].setText("—")
                row["three"].setText("—")
                continue
            item = categories[index]
            row["name"].setText(tr(str(item.get("label") or "—")))
            row["now"].setText(self._pct(item.get("next")))
            row["three"].setText(self._pct(item.get("in_three")))

        cards = list(odds.get("deck_cards") or [])
        for index, label in enumerate(self.deck_rows):
            if index >= len(cards):
                label.setText("")
                continue
            item = cards[index]
            name = str(item.get("name") or tr("Carta"))
            quantity = int(item.get("remaining") or 0)
            text = f"{self._pct(item.get('next'))} · {quantity}× {name}"
            self._elide(label, text, 165)
        remaining = sum(int(item.get("remaining") or 0) for item in cards)
        self.deck_section.setText(
            tr("MAZO RESTANTE · {count}", count=remaining)
        )
        hidden_cards = max(0, len(cards) - len(self.deck_rows))
        if hidden_cards:
            self.deck_more_label.setText(
                tr("+{count} cartas más", count=hidden_cards)
            )
        elif not cards:
            self.deck_more_label.setText(tr("Sin cartas restantes"))
        else:
            self.deck_more_label.setText("")

        opponents = list(odds.get("opponent_cards") or [])
        for index, label in enumerate(self.opponent_rows):
            if index >= len(opponents):
                label.setText("")
                continue
            item = opponents[index]
            name = str(item.get("name") or tr("Carta"))
            quantity = int(item.get("quantity") or 0)
            self._elide(label, f"{quantity}× {name}", 165)
        hidden_opponents = max(0, len(opponents) - len(self.opponent_rows))
        if hidden_opponents:
            self.opponent_more_label.setText(
                tr("+{count} cartas vistas más", count=hidden_opponents)
            )
        elif not opponents:
            self.opponent_rows[0].setText(tr("Sin cartas vistas"))
            self.opponent_more_label.setText("")
        else:
            self.opponent_more_label.setText("")

        unresolved = int(odds.get("unresolved_used") or 0)
        footer = tr("Robos naturales · sin scry, surveil ni tutores")
        if unresolved:
            footer += tr(" · {count} sin identificar", count=unresolved)
        self.footer_label.setText(footer)
