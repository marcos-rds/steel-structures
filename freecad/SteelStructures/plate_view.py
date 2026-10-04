# SPDX-License-Identifier: LGPL-2.1-or-later
"""Persistent standard shape view for StructuralPlate."""

from .paths import PLATE_ICON


class StructuralPlateViewProvider:
    def __init__(self, view_object):
        view_object.Proxy = self

    def attach(self, view_object):
        self.ViewObject = view_object
        self.Object = view_object.Object

    def getIcon(self):
        return PLATE_ICON

    def getDisplayModes(self, _view_object):
        return []

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def setDisplayMode(self, mode):
        return mode

    def claimChildren(self):
        return []

    def dumps(self):
        return None

    def loads(self, _state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, _state):
        return None
