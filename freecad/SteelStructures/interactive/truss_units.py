"""Local presentation of lengths; never changes the document or unit preferences."""
import FreeCAD as App
from PySide import QtCore


def preferred_length(value):
    quantity = App.Units.Quantity(float(value), App.Units.Length)
    _text, factor, unit = quantity.getUserPreferred()
    return float(factor), unit


def length_text(value, locale=None):
    factor, unit = preferred_length(value)
    locale = locale if locale is not None else QtCore.QLocale()
    return locale.toString(float(value) / factor, "f", 2) + " " + unit
