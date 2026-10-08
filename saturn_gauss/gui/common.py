"""Petits utilitaires d'interface."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QHeaderView, QLabel, QProgressBar, QTableWidget,
                               QTableWidgetItem)

from . import theme


def new_table(headers, stretch=None, select=True):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection if select else QAbstractItemView.NoSelection)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeToContents)
    if stretch is not None:
        h.setSectionResizeMode(stretch, QHeaderView.Stretch)
    return t


def cell(text, color=None, align=None, bold=False):
    it = QTableWidgetItem(str(text))
    if color:
        it.setForeground(QColor(color))
    if align == "r":
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    elif align == "c":
        it.setTextAlignment(Qt.AlignCenter)
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def bar(frac, text=None, color=None):
    b = QProgressBar()
    b.setRange(0, 1000)
    b.setValue(int(max(0.0, min(1.0, frac)) * 1000))
    b.setFormat(text if text is not None else f"{100 * frac:.0f} %")
    c = color or (theme.GOOD if frac > 0.6 else theme.WARN if frac > 0.25 else theme.BAD)
    b.setMinimumWidth(70)
    b.setStyleSheet(f"QProgressBar::chunk {{ background: {c}; }}")
    return b


def hp_cell(frac, color=None):
    """Cellule de tableau « barre » en caractères (évite les widgets incrustés)."""
    frac = max(0.0, min(1.0, frac))
    n = int(round(frac * 8))
    c = color or (theme.GOOD if frac > 0.6 else theme.WARN if frac > 0.25 else theme.BAD)
    return cell(f"{'█' * n}{'░' * (8 - n)} {100 * frac:3.0f} %", c)


def title(text):
    l = QLabel(text)
    l.setObjectName("title")
    return l


def value_label(text=""):
    l = QLabel(text)
    l.setObjectName("value")
    return l


def spin(minimum, maximum, value, decimals=3, step=None, suffix="", width=None):
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(minimum, maximum)
    s.setValue(value)
    s.setKeyboardTracking(False)
    if step:
        s.setSingleStep(step)
    if suffix:
        s.setSuffix(suffix)
    if width:
        s.setMinimumWidth(width)
    return s


def select_row_by_id(table, ident, col=0):
    for r in range(table.rowCount()):
        it = table.item(r, col)
        if it is not None and it.text() == str(ident):
            table.selectRow(r)
            return
