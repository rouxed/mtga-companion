"""Tokens visuales y hoja de estilos global del companion.

La idea es concentrar acá la identidad visual para que las pantallas no
repitan colores ni estilos. El tema es oscuro, con superficies en capas,
oro viejo para acciones/selección y verde/rojo reservados para resultados.
"""
from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICONS_DIR = ASSETS_DIR / "icons"


def icon_path(name: str) -> str:
    """Devuelve la ruta de un ícono SVG del tema."""
    return str(ICONS_DIR / f"{name}.svg")


COLORS = {
    "bg": "#0B0F14",
    "sidebar": "#0D131B",
    "surface": "#111821",
    "surface_hover": "#151F2B",
    "surface_raised": "#182231",
    "border": "#222D3B",
    "border_strong": "#2E3B4E",
    "text": "#F2F5F8",
    "text_soft": "#C7D0DC",
    "muted": "#8E9AAF",
    "muted_dark": "#667386",
    "gold": "#D6B36A",
    "gold_light": "#E8C97F",
    "green": "#42D392",
    "red": "#FF6B6B",
    "blue": "#5AA9FF",
    "violet": "#A78BFA",
}


GLOBAL_QSS = """
* {
    outline: none;
}

QWidget {
    color: #F2F5F8;
    font-family: "Noto Sans";
    font-size: 13px;
}

QMainWindow, QWidget#appRoot, QWidget#contentRoot {
    background: #0B0F14;
}

QFrame#sidebar {
    background: #0D131B;
    border-right: 1px solid #1B2532;
}

QLabel#logoText {
    color: #F2F5F8;
    font-size: 15px;
    font-weight: 700;
}

QLabel#logoSub {
    color: #6F7C90;
    font-size: 10px;
    letter-spacing: 1px;
}

QLabel#sideCaption {
    color: #667386;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
}

QLabel#sideStatus {
    color: #8E9AAF;
    font-size: 11px;
}

QFrame#sideFooter {
    background: #101720;
    border: 1px solid #1F2A39;
    border-radius: 12px;
}

QPushButton#navButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    color: #98A5B8;
    font-size: 13px;
    font-weight: 500;
    padding: 10px 12px;
    text-align: left;
}

QPushButton#navButton:hover {
    background: #141D28;
    color: #F2F5F8;
}

QPushButton#navButton:checked {
    background: #192331;
    border: 1px solid #2A374A;
    color: #E8C97F;
}

QFrame#header {
    background: transparent;
    border-bottom: 1px solid #1B2532;
}

QLabel#pageTitle {
    color: #F5F7FA;
    font-size: 24px;
    font-weight: 700;
}

QLabel#pageSubtitle {
    color: #8E9AAF;
    font-size: 12px;
}

QLabel#sectionTitle {
    color: #D6B36A;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.3px;
}

QLabel#sectionHint {
    color: #6F7C90;
    font-size: 11px;
}

QLabel[chip="live"] {
    background: rgba(66, 211, 146, 0.10);
    border: 1px solid rgba(66, 211, 146, 0.35);
    border-radius: 10px;
    color: #42D392;
    font-size: 10px;
    font-weight: 700;
    padding: 4px 9px;
}

QLabel[chip="waiting"] {
    background: rgba(214, 179, 106, 0.10);
    border: 1px solid rgba(214, 179, 106, 0.35);
    border-radius: 10px;
    color: #D6B36A;
    font-size: 10px;
    font-weight: 700;
    padding: 4px 9px;
}

QLabel[chip="error"] {
    background: rgba(255, 107, 107, 0.10);
    border: 1px solid rgba(255, 107, 107, 0.35);
    border-radius: 10px;
    color: #FF6B6B;
    font-size: 10px;
    font-weight: 700;
    padding: 4px 9px;
}

QLabel[chip="gold"] {
    background: rgba(214, 179, 106, 0.10);
    border: 1px solid rgba(214, 179, 106, 0.30);
    border-radius: 9px;
    color: #E8C97F;
    font-size: 10px;
    font-weight: 600;
    padding: 3px 8px;
}

QLabel[chip="muted"] {
    background: #101720;
    border: 1px solid #222D3B;
    border-radius: 9px;
    color: #8E9AAF;
    font-size: 10px;
    padding: 3px 8px;
}

QFrame#surface, QFrame#statCard, QFrame#heroCard {
    background: #111821;
    border: 1px solid #222D3B;
    border-radius: 14px;
}

QFrame#statCard {
    border-radius: 12px;
}

QFrame#statCard:hover {
    background: #141D28;
    border-color: #2E3B4E;
}

QLabel#statLabel {
    color: #8E9AAF;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.2px;
}

QLabel#statValue {
    color: #F5F7FA;
    font-size: 24px;
    font-weight: 700;
}

QLabel#statSub {
    color: #6F7C90;
    font-size: 10px;
}

QLabel#detailTitle {
    color: #F5F7FA;
    font-size: 22px;
    font-weight: 700;
}

QLabel#muted {
    color: #8E9AAF;
    font-size: 12px;
}

QLabel#cacheStatus {
    background: #101720;
    border: 1px solid #222D3B;
    border-radius: 10px;
    color: #8E9AAF;
    font-size: 10px;
    padding: 4px 9px;
}

QPushButton {
    background: #17202B;
    border: 1px solid #2A3547;
    border-radius: 9px;
    color: #E8EDF3;
    font-size: 12px;
    font-weight: 500;
    padding: 8px 14px;
}

QPushButton:hover {
    background: #1D2937;
    border-color: #3B4A60;
}

QPushButton:pressed {
    background: #121A24;
}

QPushButton:disabled {
    color: #667386;
    border-color: #1F2A39;
}

QPushButton#primaryButton {
    background: #D6B36A;
    border: 1px solid #D6B36A;
    color: #151A21;
    font-weight: 700;
}

QPushButton#primaryButton:hover {
    background: #E8C97F;
    border-color: #E8C97F;
}

QPushButton#overlayButton {
    background: rgba(214, 179, 106, 0.08);
    border: 1px solid rgba(214, 179, 106, 0.38);
    color: #E8C97F;
    font-size: 11px;
    font-weight: 700;
    padding: 6px 11px;
    border-radius: 9px;
}

QPushButton#overlayButton:hover {
    background: rgba(214, 179, 106, 0.16);
    border-color: rgba(214, 179, 106, 0.65);
}

QPushButton#overlayButton:checked {
    background: rgba(66, 211, 146, 0.10);
    border-color: rgba(66, 211, 146, 0.45);
    color: #42D392;
}

QPushButton#ghostButton {
    background: transparent;
    border-color: transparent;
    color: #8E9AAF;
}

QPushButton#ghostButton:hover {
    background: #141D28;
    color: #F2F5F8;
}

QTabWidget#mainTabs::pane {
    border: none;
    background: transparent;
}

QTabBar::tab {
    background: transparent;
}

QListWidget {
    background: transparent;
    border: none;
    color: #DCE3EC;
}

QListWidget::item {
    border-radius: 9px;
    margin: 2px 0;
    padding: 10px 12px;
}

QListWidget::item:hover {
    background: #151F2B;
}

QListWidget::item:selected {
    background: #1B2736;
    color: #E8C97F;
}

QListWidget#metaList::item, QListWidget#deckList::item {
    margin: 2px 0;
    padding: 4px 6px;
}

QLabel#deckName {
    color: #E8EDF3;
    font-size: 12px;
    font-weight: 600;
}

QLabel#deckMeta {
    color: #7F8BA0;
    font-size: 10px;
}

QTableWidget {
    background: transparent;
    alternate-background-color: #0F151E;
    border: none;
    color: #DCE3EC;
    gridline-color: transparent;
    selection-background-color: #1B2736;
    selection-color: #F5F7FA;
}

QTableWidget::item {
    border-bottom: 1px solid #18212D;
    padding: 4px 8px;
}

QHeaderView::section {
    background: #0E141C;
    border: none;
    color: #7F8BA0;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding: 9px 8px;
}

QLineEdit, QComboBox, QSpinBox {
    background: #0F151E;
    border: 1px solid #26303F;
    border-radius: 9px;
    color: #E8EDF3;
    padding: 8px 10px;
    selection-background-color: #D6B36A;
    selection-color: #151A21;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #D6B36A;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background: #111821;
    border: 1px solid #26303F;
    color: #E8EDF3;
    selection-background-color: #1B2736;
    selection-color: #E8C97F;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #2A3547;
    border-radius: 5px;
    min-height: 28px;
}

QScrollBar::handle:vertical:hover {
    background: #3A4A61;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    background: #2A3547;
    border-radius: 5px;
    min-width: 28px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QTextEdit#exportText {
    background: #0C121A;
    border: 1px solid #222D3B;
    border-radius: 10px;
    color: #C8D2DF;
    font-family: "Noto Sans Mono";
    font-size: 11px;
    padding: 8px;
}

QFrame#cardTile {
    background: #101720;
    border: 1px solid #222D3B;
    border-radius: 10px;
}

QFrame#cardTile:hover {
    background: #141D28;
    border-color: #D6B36A;
}

QFrame#cardImage {
    background: #080C12;
    border: 1px solid #1F2A39;
    border-radius: 7px;
}

QLabel#cardName {
    color: #E8EDF3;
    font-size: 11px;
    font-weight: 600;
}

QLabel#cardType {
    color: #7F8BA0;
    font-size: 9px;
}

QLabel#qtyBadge {
    background: #D6B36A;
    border-radius: 8px;
    color: #151A21;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 5px;
}

QPushButton#groupHeader {
    background: transparent;
    border: none;
    color: #D6B36A;
    font-size: 12px;
    font-weight: 700;
    padding: 4px 2px;
    text-align: left;
}

QPushButton#groupHeader:hover {
    color: #E8C97F;
    background: transparent;
}

QGroupBox {
    background: #111821;
    border: 1px solid #222D3B;
    border-radius: 12px;
    margin-top: 14px;
    padding: 14px;
}

QGroupBox::title {
    color: #D6B36A;
    font-size: 11px;
    font-weight: 700;
    left: 14px;
    padding: 0 6px;
    subcontrol-origin: margin;
}

QStatusBar {
    background: #0D131B;
    border-top: 1px solid #1B2532;
    color: #7F8BA0;
    font-size: 10px;
}

QStatusBar::item {
    border: none;
}

QToolTip {
    background: #171F2A;
    border: 1px solid #2A3547;
    border-radius: 6px;
    color: #E8EDF3;
    padding: 6px;
}

QMessageBox {
    background: #111821;
}
"""
