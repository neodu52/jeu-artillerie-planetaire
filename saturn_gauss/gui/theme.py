"""Thème sombre « espace » et palette."""

BG = "#0b0f1a"
PANEL = "#121826"
PANEL2 = "#182036"
BORDER = "#26314d"
TEXT = "#d8e0f0"
DIM = "#8794b3"
ACCENT = "#4cc9f0"
GOOD = "#2ecc71"
WARN = "#ffb703"
BAD = "#ff4d6d"

QSS = f"""
* {{ font-family: "DejaVu Sans", "Segoe UI", sans-serif; font-size: 10pt; }}
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; }}
QLabel, QCheckBox {{ background: transparent; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; background: {BG}; top: -1px; }}
QTabBar::tab {{ background: {PANEL}; color: {DIM}; padding: 9px 18px; border: 1px solid {BORDER};
    border-bottom: none; margin-right: 2px; border-top-left-radius: 7px; border-top-right-radius: 7px; }}
QTabBar::tab:selected {{ background: {PANEL2}; color: {ACCENT}; font-weight: bold; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px; padding: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {ACCENT}; font-weight: bold; }}
QPushButton {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #4b5675; border-color: #1c253d; }}
QPushButton#fire {{ background: #6b1d2e; border-color: {BAD}; color: white; font-weight: bold; padding: 9px 22px; }}
QPushButton#fire:hover {{ background: {BAD}; }}
QPushButton#good {{ background: #14532d; border-color: {GOOD}; }}
QPushButton#accent {{ border-color: {ACCENT}; color: {ACCENT}; }}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit, QTextBrowser {{
    background: #0e1424; border: 1px solid {BORDER}; border-radius: 5px; padding: 4px; selection-background-color: #1d4e6e; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; selection-background-color: #1d4e6e; }}
QTableWidget {{ background: #0e1424; gridline-color: {BORDER}; border: 1px solid {BORDER}; border-radius: 5px;
    alternate-background-color: #111a2e; selection-background-color: #1d4e6e; selection-color: white; }}
QHeaderView::section {{ background: {PANEL2}; color: {ACCENT}; border: none; border-right: 1px solid {BORDER};
    padding: 5px; font-weight: bold; }}
QProgressBar {{ background: #0e1424; border: 1px solid {BORDER}; border-radius: 4px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {GOOD}; border-radius: 3px; }}
QSlider::groove:horizontal {{ height: 6px; background: {BORDER}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -5px 0; border-radius: 7px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
QLabel#title {{ color: {ACCENT}; font-size: 13pt; font-weight: bold; }}
QLabel#value {{ color: white; font-size: 12pt; font-weight: bold; }}
QLabel#banner {{ background: #5a1020; border: 1px solid {BAD}; border-radius: 6px; padding: 8px; font-weight: bold; }}
QStatusBar {{ background: {PANEL}; color: {DIM}; }}
QScrollBar:vertical {{ background: {PANEL}; width: 12px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QSplitter::handle {{ background: {BORDER}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {ACCENT}; }}
"""
